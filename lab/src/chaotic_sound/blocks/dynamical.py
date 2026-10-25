"""Dynamical block: a chaotic ODE tuned to a musical note (spec §4.2, ADR 0006).

Per sample: smooth the controls, map the knob u to the system parameter, set the time scale
k = P(u)·f₀ (pitch lock), advance the ODE by k/fs system-time units with RK4 sub-steps, and
turn the heard variable into audio normalized to an RMS of :data:`RMS_TARGET`.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType, _check_unit
from chaotic_sound.catalog import Catalog, CatalogEntry, load_default_catalog
from chaotic_sound.dsp import dc_block, dc_block_coefficient, one_pole, one_pole_coefficient
from chaotic_sound.integrate import render_tuned
from chaotic_sound.pitch import note_to_hz
from chaotic_sound.systems import SYSTEMS, get_system

RMS_TARGET = 0.25
"""RMS of a dynamical block at amp = 1 (≈ −12 dBFS), spec §3."""
DECLICK_TIME_S = 0.005
"""Time constant of the control smoothers (spec §3)."""
DC_BLOCK_HZ = 5.0
"""Cut-off of the output DC blocker (spec §4.2 step 6)."""
IC_PERTURBATION = 1e-6
"""Relative size of the seeded initial-condition perturbation (spec §4.2 step 9)."""


def stable_seed(block_id: str) -> int:
    """Deterministic seed derived from a block id (CRC-32, independent of Python's hash)."""
    return zlib.crc32(block_id.encode("utf-8")) & 0x7FFFFFFF


@dataclass(frozen=True)
class DynamicalParams(BlockParams):
    """Settings and knobs of a dynamical block (spec §4.2 table).

    ``observable`` and ``param`` default to ``None``, meaning "the catalog's default"; the
    resolved values are available on the block as ``observable`` and ``knob_param``.
    """

    system: str = "rossler"
    note: str = "A3"
    cents: float = 0.0
    observable: str | None = None
    observable_right: str | None = None
    pitch_lock: bool = True
    seed: int | None = None
    param: float | None = None
    amp: float = 1.0

    def __post_init__(self) -> None:
        if self.system not in SYSTEMS:
            raise ValueError(f"unknown system {self.system!r}; available: {sorted(SYSTEMS)}")
        note_to_hz(self.note)  # raises ValueError on a bad note name
        if not -100.0 <= self.cents <= 100.0:
            raise ValueError(f"cents must be in [-100, 100], got {self.cents}")
        audio = get_system(self.system).audio_variables
        for name, obs in (
            ("observable", self.observable),
            ("observable_right", self.observable_right),
        ):
            if obs is not None and obs not in audio:
                raise ValueError(
                    f"{name} {obs!r} is not an audible variable of {self.system}: {audio}"
                )
        if self.param is not None:
            _check_unit("param", self.param)
        _check_unit("amp", self.amp)


class Dynamical(Block):
    """A tuned chaotic oscillator (spec §4.2).

    Parameters
    ----------
    block_id
        Unique id in the patch (also seeds the initial-condition perturbation).
    catalog
        Catalog to read tuning tables from (default: :func:`load_default_catalog`).
    **params
        Fields of :class:`DynamicalParams`.

    Attributes
    ----------
    resets
        Number of safety resets during the current render (should stay 0).
    """

    type_name = "dynamical"
    Params = DynamicalParams
    INPUTS = (Port("param", SignalType.CONTROL), Port("amp", SignalType.CONTROL))
    OUTPUTS = (Port("out", SignalType.AUDIO),)
    params: DynamicalParams

    def __init__(self, block_id: str, catalog: Catalog | None = None, **params: Any) -> None:
        super().__init__(block_id, **params)
        p = self.params
        self.system = get_system(p.system)
        self.entry: CatalogEntry = (catalog or load_default_catalog())[p.system]
        self.observable = p.observable or self.entry.default_observable
        self.observable_right = p.observable_right
        self.knob_param = self.entry.u_default if p.param is None else float(p.param)
        self.frequency_hz = note_to_hz(p.note, p.cents)
        self.seed = stable_seed(block_id) if p.seed is None else int(p.seed)
        self.resets = 0

    def reset(self, sample_rate: float) -> None:
        """Restart at t = 0 from the seeded initial condition."""
        self.sample_rate = float(sample_rate)
        system, entry = self.system, self.entry
        rng = np.random.default_rng(self.seed)
        scale = np.ones(system.dim)
        for var in system.audio_variables:
            scale[system.variable_index(var)] = float(entry.std(var, entry.u_default))
        self._x = entry.initial_condition + IC_PERTURBATION * scale * rng.standard_normal(
            system.dim
        )
        self._x_reset = self._x.copy()
        self._p = system.params_array()
        self._wrap = system.wrap_mask()
        self._alpha = one_pole_coefficient(DECLICK_TIME_S, self.sample_rate)
        self._u_state: Signal | None = None  # initialized from the first control value
        self._a_state = np.zeros(1)  # amp starts at 0: every box fades in over a few ms
        self._dc_r = dc_block_coefficient(DC_BLOCK_HZ, self.sample_rate)
        self._dc_state = np.zeros((2, 2))
        self._period_unlocked = float(entry.period(entry.u_default))
        self.resets = 0

    def _audio(self, traj: Signal, observable: str, u: Signal, a: Signal) -> Signal:
        i = self.system.variable_index(observable)
        mean = self.entry.mean(observable, u)
        std = self.entry.std(observable, u)
        return a * RMS_TARGET * (traj[:, i] - mean) / std

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of stereo audio (spec §4.2 steps 1–9)."""
        u_in = inputs.get("param")
        a_in = inputs.get("amp")
        u_raw = np.full(n, self.knob_param) if u_in is None else np.asarray(u_in, dtype=np.float64)
        a_raw = np.full(n, self.params.amp) if a_in is None else np.asarray(a_in, dtype=np.float64)
        if self._u_state is None:
            self._u_state = np.array([u_raw[0]])
        u = np.empty(n)
        a = np.empty(n)
        one_pole(u_raw, self._u_state, self._alpha, u)
        one_pole(a_raw, self._a_state, self._alpha, a)

        entry = self.entry
        p_values = entry.param_value(u)
        period = entry.period(u) if self.params.pitch_lock else np.full(n, self._period_unlocked)
        dtau = period * (self.frequency_hz / self.sample_rate)
        traj = np.empty((n, self.system.dim))
        self.resets += int(
            render_tuned(
                self.system.rhs, self._x, self._p, self.system.modulated_index, p_values, dtau,
                entry.h_max, self._wrap, entry.bounds_lo, entry.bounds_hi, self._x_reset, traj,
            )
        )  # fmt: skip

        left = self._audio(traj, self.observable, u, a)
        right = left if self.observable_right is None else self._audio(
            traj, self.observable_right, u, a
        )  # fmt: skip
        out = np.empty((n, 2))
        dc_block(left, self._dc_state[0], self._dc_r, out[:, 0])
        dc_block(right, self._dc_state[1], self._dc_r, out[:, 1])
        return {"out": out}

    def substeps_per_sample(self, u: float | None = None) -> int:
        """RK4 sub-steps per sample at knob position ``u`` (cost indicator)."""
        u = self.knob_param if u is None else u
        period = float(self.entry.period(u)) if self.params.pitch_lock else self._period_unlocked
        fs = self.sample_rate or 48_000.0
        return max(1, math.ceil(period * self.frequency_hz / fs / self.entry.h_max))
