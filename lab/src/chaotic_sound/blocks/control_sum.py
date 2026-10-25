"""Control Sum block: combines several control signals explicitly (spec §4.5, ADR 0013).

Control inputs of other blocks accept a single cable, so that adding controllers is always
visible in the patch. This block adds its inputs, scales by ``gain`` and clips to [0, 1].
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType, _check_unit


@dataclass(frozen=True)
class ControlSumParams(BlockParams):
    """``gain`` ∈ [0, 1] scales the sum before clipping (0.5 averages two inputs)."""

    gain: float = 1.0

    def __post_init__(self) -> None:
        self.check_types()
        _check_unit("gain", self.gain)


class ControlSum(Block):
    """``out = clip(gain · Σ inputs, 0, 1)``; with nothing connected, ``out = 0``."""

    type_name = "control_sum"
    Params = ControlSumParams
    INPUTS = (Port("in", SignalType.CONTROL, multi=True),)
    OUTPUTS = (Port("out", SignalType.CONTROL),)
    params: ControlSumParams

    def reset(self, sample_rate: float) -> None:
        """Stateless; only records the sample rate."""
        self.sample_rate = float(sample_rate)

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of the combined control signal."""
        x = inputs.get("in")
        if x is None:
            return {"out": np.zeros(n)}
        return {"out": np.clip(self.params.gain * x, 0.0, 1.0)}
