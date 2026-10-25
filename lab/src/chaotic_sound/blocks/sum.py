"""Sum block: adds audio signals (spec §4.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType, _check_unit


@dataclass(frozen=True)
class SumParams(BlockParams):
    """``gain`` ∈ [0, 1] scales the sum."""

    gain: float = 1.0

    def __post_init__(self) -> None:
        self.check_types()
        _check_unit("gain", self.gain)


class Sum(Block):
    """Audio mixer: ``out = gain · Σ inputs`` (spec §4.3).

    ``in`` is the only port that accepts several audio cables; the patch graph adds them, so
    this block only applies the gain. With nothing connected it outputs silence.
    """

    type_name = "sum"
    Params = SumParams
    INPUTS = (Port("in", SignalType.AUDIO, multi=True),)
    OUTPUTS = (Port("out", SignalType.AUDIO),)
    params: SumParams

    def reset(self, sample_rate: float) -> None:
        """Stateless; only records the sample rate."""
        self.sample_rate = float(sample_rate)

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of the mix."""
        x = inputs.get("in")
        if x is None:
            return {"out": np.zeros((n, 2))}
        return {"out": self.params.gain * x}
