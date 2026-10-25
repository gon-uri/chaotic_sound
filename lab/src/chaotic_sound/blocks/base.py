"""Block interface (architecture layer 4).

A block is a processing unit with typed input and output ports (spec §2–3). The patch graph
(layer 5) gathers each input from the connected cables, already summed and, for control
inputs, clipped to [0, 1], and calls :meth:`Block.process` one chunk of samples at a time.

Conventions:

- Audio arrays have shape ``(n, 2)`` (stereo); control arrays have shape ``(n,)``.
- An unconnected input is passed as ``None``; the block then uses its knob.
- Blocks keep all their state between calls, so the output never depends on how a render
  is split into chunks (spec §6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray

Signal = NDArray[np.float64]


class SignalType(StrEnum):
    """The two kinds of signal a port can carry (spec §3)."""

    AUDIO = "audio"
    CONTROL = "control"


@dataclass(frozen=True)
class Port:
    """A named, typed input or output of a block.

    ``multi`` (inputs only) says whether several cables may connect to it.
    """

    name: str
    type: SignalType
    multi: bool = True


@dataclass(frozen=True)
class BlockParams:
    """Base class of every block's parameter dataclass.

    Subclasses validate their values in ``__post_init__`` and raise ``ValueError``.
    """

    def to_dict(self) -> dict[str, Any]:
        """Parameters as a plain dict (JSON-ready)."""
        return asdict(self)


def _check_unit(name: str, value: float) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


class Block(ABC):
    """Abstract processing block.

    Subclasses set ``type_name`` (the patch-JSON ``type``), ``Params`` (a
    :class:`BlockParams` dataclass), ``INPUTS`` and ``OUTPUTS``, and implement :meth:`reset`
    and :meth:`process`.
    """

    type_name: ClassVar[str]
    Params: ClassVar[type[BlockParams]]
    INPUTS: ClassVar[tuple[Port, ...]] = ()
    OUTPUTS: ClassVar[tuple[Port, ...]] = ()

    def __init__(self, block_id: str, **params: Any) -> None:
        if not block_id or "." in block_id:
            raise ValueError(f"invalid block id {block_id!r} (non-empty, no '.')")
        allowed = {f.name for f in fields(self.Params)}
        unknown = set(params) - allowed
        if unknown:
            raise ValueError(
                f"{self.type_name} '{block_id}': unknown parameter(s) {sorted(unknown)}; "
                f"allowed: {sorted(allowed)}"
            )
        self.id = block_id
        self.params = self.Params(**params)
        self.sample_rate: float = 0.0

    # -- ports -------------------------------------------------------------------------

    @classmethod
    def input_port(cls, name: str) -> Port:
        """Input port by name."""
        for port in cls.INPUTS:
            if port.name == name:
                return port
        raise KeyError(f"{cls.type_name} has no input {name!r}")

    @classmethod
    def output_port(cls, name: str) -> Port:
        """Output port by name."""
        for port in cls.OUTPUTS:
            if port.name == name:
                return port
        raise KeyError(f"{cls.type_name} has no output {name!r}")

    # -- processing ----------------------------------------------------------------------

    @abstractmethod
    def reset(self, sample_rate: float) -> None:
        """Prepare to render from t = 0 at ``sample_rate`` (Hz); clears all state."""

    @abstractmethod
    def process(self, n: int, inputs: Mapping[str, Signal | None]) -> dict[str, Signal]:
        """Produce the next ``n`` samples of every output.

        Parameters
        ----------
        n
            Number of samples in this chunk.
        inputs
            One entry per input port: the summed signal of its cables, or ``None`` if
            nothing is connected.

        Returns
        -------
        dict
            One array per output port (and, for the Output block, the key ``"main"``).
        """

    # -- serialization -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Patch-JSON representation of this block (spec §5)."""
        return {"id": self.id, "type": self.type_name, "params": self.params.to_dict()}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.id!r}, {self.params})"
