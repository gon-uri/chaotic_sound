"""Processing blocks (architecture layer 4): Modulator, Dynamical, Sum, ControlSum, Output."""

from chaotic_sound.blocks.base import Block, BlockContext, BlockParams, Port, Signal, SignalType
from chaotic_sound.blocks.control_sum import ControlSum, ControlSumParams
from chaotic_sound.blocks.dynamical import Dynamical, DynamicalParams
from chaotic_sound.blocks.modulator import SHAPES, Modulator, ModulatorParams
from chaotic_sound.blocks.output import Output, OutputParams
from chaotic_sound.blocks.sum import Sum, SumParams

BLOCK_TYPES: dict[str, type[Block]] = {
    cls.type_name: cls for cls in (Modulator, Dynamical, Sum, ControlSum, Output)
}
"""Registry used by the patch JSON loader: ``type`` field → block class."""

__all__ = [
    "BLOCK_TYPES",
    "SHAPES",
    "Block",
    "BlockContext",
    "BlockParams",
    "ControlSum",
    "ControlSumParams",
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
