"""Dynamical block: a chaotic ODE tuned to a musical note (spec §4.2, ADR 0006/0013).

Per sample:

1. smooth the controls (pitch, parameter, amplitude);
2. turn the pitch into a frequency f (note + cents, or the pitch input);
3. map the knob u to the system parameter and set the time scale k = P(u)·f (pitch lock);
4. advance the ODE by k/fs system-time units with RK4 sub-steps;
5. turn the heard variable into a level-normalized signal, make it more harmonic by the
   ``tonality`` amount (harmonic resynthesis, ADR 0015), and apply the perceptual amp curve.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from chaotic_sound.blocks.base import (
    Block,
    BlockContext,
    BlockParams,
    Port,
    Signal,
    SignalType,
    _check_unit,
    check_signal,
)
from chaotic_sound.catalog import CatalogEntry
from chaotic_sound.dsp import (
    AMP_EXPONENT,
    TONAL_COHERENCE_FLOOR,
    TONAL_MIX_EXPONENT,
    TONAL_Q,
    dc_block,
    dc_block_coefficient,
    one_pole,
    one_pole_coefficient,
    one_pole_varying,
    tonal,
    tonal_state,
)
from chaotic_sound.integrate import render_tuned
from chaotic_sound.pitch import NOTE_MAX, NOTE_MIN, midi_to_hz, note_to_hz, note_to_midi
from chaotic_sound.rng import Mulberry32, stable_seed
from chaotic_sound.systems import SYSTEMS, get_system

RMS_TARGET = 0.25
"""RMS of a dynamical block at amp = 1 (≈ −12 dBFS), spec §3."""
PEAK_TARGET = 0.8
"""Robust peak (99.9th percentile) a block may reach at amp = 1 (spec §4.2 step 6)."""
DECLICK_TIME_S = 0.005
"""Time constant of the control smoothers (spec §3)."""
PARAM_SLEW_PERIODS = 2.0
"""The parameter smoother is at least this many oscillation periods slow (ADR 0013)."""
DC_BLOCK_HZ = 5.0
"""Cut-off of the output DC blocker (spec §4.2 step 6)."""
IC_PERTURBATION = 1e-6
"""Relative size of the seeded initial-condition perturbation (spec §4.2 step 9)."""
TONALITY_DEFAULT = 0.3
"""Default tonality: mostly the raw attractor, noticeably more pitched (owner's choice)."""
AMP_CURVES = ("perceptual", "linear")
SEED_LIMIT = 2**31


@dataclass(frozen=True)
class DynamicalParams(BlockParams):
    """Settings and knobs of a dynamical block (spec §4.2 table).

    ``observable`` and ``param`` default to ``None``, meaning "the catalog's default"; the
    resolved values are available on the block as ``observable`` and ``knob_param``.
    """

    system: str = "rossler"
    note: str = "A3"
    cents: float = 0.0
    pitch_min: str = "A1"
    pitch_max: str = "A5"
    observable: str | None = None
    observable_right: str | None = None
    pitch_lock: bool = True
    amp_curve: str = "perceptual"
    seed: int | None = None
    param: float | None = None
    amp: float = 1.0
    tonality: float = TONALITY_DEFAULT

    def __post_init__(self) -> None:
        self.check_types()
        if self.system not in SYSTEMS:
            raise ValueError(f"unknown system {self.system!r}; available: {sorted(SYSTEMS)}")
        for name in ("note", "pitch_min", "pitch_max"):
            midi = note_to_midi(getattr(self, name))  # raises on a bad note name
            if not NOTE_MIN <= midi <= NOTE_MAX:
                raise ValueError(f"{name} must be between C0 and C8, got {getattr(self, name)!r}")
        if note_to_midi(self.pitch_min) >= note_to_midi(self.pitch_max):
            raise ValueError("pitch_min must be lower than pitch_max")
        if not -100.0 <= self.cents <= 100.0:
            raise ValueError(f"cents must be in [-100, 100], got {self.cents}")
        audio = get_system(self.system).audio_variables
        for name in ("observable", "observable_right"):
            obs = getattr(self, name)
            if obs is not None and obs not in audio:
                raise ValueError(
                    f"{name} {obs!r} is not an audible variable of {self.system}: {audio}"
                )
        if self.amp_curve not in AMP_CURVES:
            raise ValueError(f"amp_curve must be one of {AMP_CURVES}, got {self.amp_curve!r}")
        if self.seed is not None and not 0 <= self.seed < SEED_LIMIT:
            raise ValueError(f"seed must be in [0, 2**31), got {self.seed}")
        if self.param is not None:
            _check_unit("param", self.param)
        _check_unit("amp", self.amp)
        _check_unit("tonality", self.tonality)


class Dynamical(Block):
    """A tuned chaotic oscillator (spec §4.2).

    Parameters
    ----------
    block_id
        Unique id in the patch (also seeds the initial-condition perturbation).
    context
        Supplies the catalog (default: the repository catalog).
    **params
        Fields of :class:`DynamicalParams`.
    """

    type_name = "dynamical"
    Params = DynamicalParams
    INPUTS = (
        Port("param", SignalType.CONTROL),
        Port("amp", SignalType.CONTROL),
        Port("pitch", SignalType.CONTROL),
        Port("tonality", SignalType.CONTROL),
    )
    OUTPUTS = (Port("out", SignalType.AUDIO),)
    params: DynamicalParams

    def __init__(
        self, block_id: str, *, context: BlockContext | None = None, **params: Any
    ) -> None:
        super().__init__(block_id, context=context, **params)
        p = self.params
        self.system = get_system(p.system)
        self.entry: CatalogEntry = self.context.require_catalog()[p.system]
        self.entry.check_against(self.system)
        self.observable = p.observable or self.entry.default_observable
        self.observable_right = p.observable_right
        self.knob_param = self.entry.u_default if p.param is None else float(p.param)
        self.frequency_hz = note_to_hz(p.note, p.cents)
        self.midi_min = float(note_to_midi(p.pitch_min))
        self.midi_max = float(note_to_midi(p.pitch_max))
        self.seed = stable_seed(block_id) if p.seed is None else p.seed
        self.resets = 0

    # -- setup -------------------------------------------------------------------------

    def initial_state(self) -> np.ndarray:
        """Catalog initial condition plus the seeded perturbation (spec §4.2 step 9)."""
        system, entry = self.system, self.entry
        rng = Mulberry32(self.seed)
        x = entry.initial_condition.copy()
        for j, var in enumerate(system.variables):
            scale = 1.0 if j in system.phase_indices else float(entry.std(var, entry.u_default))
            x[j] += IC_PERTURBATION * scale * rng.normal()
        return x

    def reset(self, sample_rate: float) -> None:
        """Restart at t = 0 from the seeded initial condition."""
        highest = max(self.frequency_hz, midi_to_hz(self.midi_max))
        if not highest < sample_rate / 2:
            nyquist = sample_rate / 2
            raise ValueError(f"dynamical '{self.id}': {highest:.1f} Hz is not below {nyquist} Hz")
        self.sample_rate = float(sample_rate)
        self._x = self.initial_state()
        self._x_reset = self._x.copy()
        self._p = self.system.params_array()
        self._wrap = self.system.wrap_mask()
        self._alpha = one_pole_coefficient(DECLICK_TIME_S, self.sample_rate)
        self._u_state: np.ndarray | None = None  # starts at the first control value
        self._q_state: np.ndarray | None = None  # pitch input smoother, same rule
        self._a_state = np.zeros(1)  # amp starts at 0: every box fades in over a few ms
        self._dc_r = dc_block_coefficient(DC_BLOCK_HZ, self.sample_rate)
        self._dc_state = np.zeros((2, 2))
        self._t_state: np.ndarray | None = None  # tonality smoother: first control value
        self._tonal_states = [tonal_state(), tonal_state()]  # one per channel (spec §4.2 step 7)
        self._tonal_was_on = False
        self._period_unlocked = float(self.entry.period(self.entry.u_default))
        self.resets = 0

    # -- processing --------------------------------------------------------------------

    def _frequency(self, n: int, q_in: Signal | None) -> Signal:
        """Per-sample frequency (Hz): the note, or the smoothed pitch input (spec §4.2 step 3)."""
        if q_in is None:
            self._q_state = None  # a pitch cable connected later starts from its first value
            return np.full(n, self.frequency_hz)
        if self._q_state is None:
            self._q_state = np.array([q_in[0]])
        q = np.empty(n)
        one_pole(q_in, self._q_state, self._alpha, q)
        midi = self.midi_min + q * (self.midi_max - self.midi_min)
        return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)

    def _normalized(self, traj: Signal, observable: str, u: Signal) -> Signal:
        """R = s(u)·(x_obs − μ(u)), s(u) = min(0.25/σ(u), 0.8/π(u)) (spec §4.2 step 7)."""
        e = self.entry
        i = self.system.variable_index(observable)
        scale = np.minimum(RMS_TARGET / e.std(observable, u), PEAK_TARGET / e.peak(observable, u))
        return scale * (traj[:, i] - e.mean(observable, u))

    def _tonal(self, r: Signal, f_a: Signal, tau: Signal, channel: int) -> Signal:
        """Mix one channel: m = (1 − τ)^0.75·r + τ^0.75·t (spec §4.2 step 7)."""
        out = np.empty_like(r)
        scalars, coef, filt, bands = self._tonal_states[channel]
        tonal(r, f_a, tau, self.sample_rate, scalars, coef, filt, bands, *TONAL_Q,
              TONAL_MIX_EXPONENT, TONAL_COHERENCE_FLOOR, out)  # fmt: skip
        return out

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of stereo audio (spec §4.2 steps 1–9)."""
        if n == 0:
            return {"out": np.zeros((0, 2))}
        u_in = check_signal("param", inputs.get("param"), n)
        a_in = check_signal("amp", inputs.get("amp"), n)
        q_in = check_signal("pitch", inputs.get("pitch"), n)
        t_in = check_signal("tonality", inputs.get("tonality"), n)

        freq = self._frequency(n, q_in)
        u_raw = np.full(n, self.knob_param) if u_in is None else u_in
        a_raw = np.full(n, self.params.amp) if a_in is None else a_in
        if self._u_state is None:
            self._u_state = np.array([u_raw[0]])
        # Parameter slew: at least 5 ms and at least PARAM_SLEW_PERIODS periods of the note,
        # so abrupt jumps (square/ramp modulators) are gentle in system time (ADR 0013).
        tau = np.maximum(DECLICK_TIME_S, PARAM_SLEW_PERIODS / freq)
        alpha_u = 1.0 - np.exp(-1.0 / (tau * self.sample_rate))
        u = np.empty(n)
        a = np.empty(n)
        one_pole_varying(u_raw, self._u_state, alpha_u, u)
        one_pole(a_raw, self._a_state, self._alpha, a)
        gain = a**AMP_EXPONENT if self.params.amp_curve == "perceptual" else a

        entry = self.entry
        p_values = entry.param_value(u)
        period = entry.period(u) if self.params.pitch_lock else np.full(n, self._period_unlocked)
        dtau = period * freq / self.sample_rate
        traj = np.empty((n, self.system.dim))
        self.resets += int(
            render_tuned(
                self.system.rhs, self._x, self._p, self.system.modulated_index, p_values, dtau,
                entry.h_max, self._wrap, entry.bounds_lo, entry.bounds_hi, self._x_reset, traj,
            )
        )  # fmt: skip

        # Tonality: smoothed like amp, but it starts at its first value (no initial glide).
        t_raw = np.full(n, self.params.tonality) if t_in is None else t_in
        if self._t_state is None:
            self._t_state = np.array([t_raw[0]])
        # Skip the step only while the knob is 0, no cable is connected and τ_s is 0 (decided
        # at the chunk start, so a glide to 0 finishes before the step switches off).
        tonal_on = t_in is not None or self.params.tonality > 0.0 or self._t_state[0] != 0.0
        if tonal_on and not self._tonal_was_on:
            self._tonal_states = [tonal_state(), tonal_state()]  # restart from the reset value
        self._tonal_was_on = tonal_on
        tau = np.empty(n)
        one_pole(t_raw, self._t_state, self._alpha, tau)
        f_a = freq if self.params.pitch_lock else freq * self._period_unlocked / entry.period(u)

        r_left = self._normalized(traj, self.observable, u)
        m_left = self._tonal(r_left, f_a, tau, 0) if tonal_on else r_left
        left = gain * m_left
        if self.observable_right is None:
            right = left
        else:
            r_right = self._normalized(traj, self.observable_right, u)
            m_right = self._tonal(r_right, f_a, tau, 1) if tonal_on else r_right
            right = gain * m_right
        out = np.empty((n, 2))
        dc_block(left, self._dc_state[0], self._dc_r, out[:, 0])
        dc_block(right, self._dc_state[1], self._dc_r, out[:, 1])
        if not np.all(np.isfinite(self._dc_state)):
            # Defense in depth: a non-finite sample would stay in the blocker's memory forever.
            self._dc_state[:] = 0.0
            self.resets += 1
        for ch in range(2):  # same for a channel's tonal band statistics (spec §4.2 step 8)
            if not np.all(np.isfinite(self._tonal_states[ch][3])):
                self._tonal_states[ch] = tonal_state()
                self.resets += 1
        return {"out": out}

    def diagnostics(self) -> dict[str, int]:
        """Safety resets during the current render (should stay 0).

        Counts ODE resets (spec §4.2 step 8) and recoveries of a non-finite DC-blocker state.
        """
        return {"safety_resets": self.resets}

    def substeps_per_sample(self, u: float | None = None, frequency_hz: float | None = None) -> int:
        """RK4 sub-steps per sample at knob position ``u`` and frequency (cost indicator)."""
        u = self.knob_param if u is None else u
        f = self.frequency_hz if frequency_hz is None else frequency_hz
        period = float(self.entry.period(u)) if self.params.pitch_lock else self._period_unlocked
        fs = self.sample_rate or 48_000.0
        return max(1, math.ceil(period * f / fs / self.entry.h_max))
