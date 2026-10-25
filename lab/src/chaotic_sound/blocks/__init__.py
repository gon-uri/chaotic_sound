"""Processing blocks (architecture layer 4): Modulator, Dynamical, Sum, Output."""

from chaotic_sound.blocks.base import Block, BlockParams, Port, Signal, SignalType
from chaotic_sound.blocks.dynamical import Dynamical, DynamicalParams
from chaotic_sound.blocks.modulator import SHAPES, Modulator, ModulatorParams
from chaotic_sound.blocks.output import Output, OutputParams
from chaotic_sound.blocks.sum import Sum, SumParams

BLOCK_TYPES: dict[str, type[Block]] = {
    cls.type_name: cls for cls in (Modulator, Dynamical, Sum, Output)
}
"""Registry used by the patch JSON loader: ``type`` field → block class."""

__all__ = [
    "BLOCK_TYPES",
    "SHAPES",
    "Block",
    "BlockParams",
    "Dynamical",
    "DynamicalParams",
    "Modulator",
    "ModulatorParams",
    "Output",
    "OutputParams",
    "Port",
    "Signal",
    "SignalType",
    "Sum",
    "SumParams",
]
