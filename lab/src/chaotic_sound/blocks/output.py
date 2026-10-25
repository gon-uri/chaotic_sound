"""Output block: final volume and protection (spec §4.4)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType, _check_unit
from chaotic_sound.dsp import soft_clip


@dataclass(frozen=True)
class OutputParams(BlockParams):
    """``volume`` ∈ [0, 1] is the master gain."""

    volume: float = 0.8

    def __post_init__(self) -> None:
        self.check_types()
        _check_unit("volume", self.volume)


class Output(Block):
    """The patch's sink: ``main = softclip(volume · in)``.

    It has no output port (nothing can be cabled from it); the patch reads its ``"main"``
    signal as the rendered audio. With nothing connected it outputs silence (a valid patch).
    """

    type_name = "output"
    Params = OutputParams
    INPUTS = (Port("in", SignalType.AUDIO),)
    IS_SINK = True
    params: OutputParams

    def reset(self, sample_rate: float) -> None:
        """Stateless; only records the sample rate."""
        self.sample_rate = float(sample_rate)

    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Next ``n`` samples of the final stereo signal."""
        x = inputs.get("in")
        if x is None:
            return {"main": np.zeros((n, 2))}
        return {"main": soft_clip(self.params.volume * x)}
