"""Modulator block: a slow control signal in [0, 1] (spec §4.1, ADR 0008)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType

SHAPES = ("sine", "triangle", "square", "ramp_up", "ramp_down")
MODES = ("loop", "once")
MIN_PERIOD_S = 0.001
"""Shortest allowed period (1 ms); shorter values make the phase arithmetic meaningless."""


def shape_value(shape: str, phase: Signal) -> Signal:
    """Evaluate a modulator shape on phases in [0, 1] (spec §4.1 table).

    The shapes are defined on the closed interval, so ``phase = 1`` gives the value a
    ``once`` envelope holds at its end.
    """
    if shape == "sine":
        return 0.5 * (1.0 - np.cos(2.0 * np.pi * phase))
    if shape == "triangle":
        return 1.0 - np.abs(2.0 * phase - 1.0)
    if shape == "square":
        return np.where(phase < 0.5, 1.0, 0.0)
    if shape == "ramp_up":
        return np.array(phase, dtype=np.float64, copy=True)
    if shape == "ramp_down":
        return 1.0 - phase
    raise ValueError(f"unknown shape {shape!r}; choose one of {SHAPES}")


@dataclass(frozen=True)
class ModulatorParams(BlockParams):
    """Settings of a modulator.

    Attributes
    ----------
    shape
        One of :data:`SHAPES`.
    period_s
        Seconds per cycle (``loop``) or length of the envelope (``once``).
    mode
        ``"loop"`` repeats the cycle; ``"once"`` plays it once and holds the final value.
    """

    shape: str = "sine"
    period_s: float = 4.0
    mode: str = "loop"

    def __post_init__(self) -> None:
        self.check_types()
        if self.shape not in SHAPES:
            raise ValueError(f"unknown shape {self.shape!r}; choose one of {SHAPES}")
        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode!r}; choose one of {MODES}")
        if not (math.isfinite(self.period_s) and self.period_s >= MIN_PERIOD_S):
            raise ValueError(f"period_s must be at least {MIN_PERIOD_S} s, got {self.period_s}")


class Modulator(Block):
    """Low-frequency oscillator or one-shot envelope with output in [0, 1].

    Its time origin is the start of the render (t = 0); the phase is computed from an
    integer sample counter, so long renders do not accumulate rounding drift. The exact
    float64 recipe is pinned by spec §4.1 so that every engine flips square and ramp edges
    on the same samples: ``t = i / fs``, ``c = t / T``, ``φ = c − floor(c)`` (loop) or
    ``φ = min(c, 1)`` (once).
    """

    type_name = "modulator"
    Params = ModulatorParams
    OUTPUTS = (Port("out", SignalType.CONTROL),)
    params: ModulatorParams

    def reset(self, sample_rate: float) -> None:
        """Restart at t = 0."""
        self.sample_rate = float(sample_rate)
        self._n = 0

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of the control signal."""
        t = (self._n + np.arange(n, dtype=np.float64)) / self.sample_rate
        self._n += n
        cycles = t / self.params.period_s
        loop = self.params.mode == "loop"
        phase = cycles - np.floor(cycles) if loop else np.minimum(cycles, 1.0)
        return {"out": shape_value(self.params.shape, phase)}
