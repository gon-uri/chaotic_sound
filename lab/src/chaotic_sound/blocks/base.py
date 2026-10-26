"""Block interface (architecture layer 4).

A block is a processing unit with typed input and output ports (spec §2–3). The patch graph
(layer 5) passes each input (the signal of its one cable, or the sum of an audio Sum's
cables) and calls :meth:`Block.process` one chunk of samples at a time.

Conventions:

- Audio arrays have shape ``(n, 2)`` (stereo); control arrays have shape ``(n,)``.
- An unconnected input is passed as ``None``; the block then uses its knob.
- Blocks keep all their state between calls, so the output never depends on how a render
  is split into chunks (spec §6).
- Blocks never touch files or platform APIs. Data they need from outside (the catalog)
  arrives through a :class:`BlockContext` (hexagonal architecture, ADR 0011).
"""

from __future__ import annotations

import math
import types
import typing
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import MISSING, dataclass, fields
from enum import StrEnum
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray

from chaotic_sound.catalog import Catalog

Signal = NDArray[np.float64]


class SignalType(StrEnum):
    """The two kinds of signal a port can carry (spec §3)."""

    AUDIO = "audio"
    CONTROL = "control"


@dataclass(frozen=True)
class Port:
    """A named, typed input or output of a block.

    ``multi`` (inputs only) says whether several cables may connect to it. In v1 only the
    Sum blocks' ``in`` ports are ``multi`` (spec §3).
    """

    name: str
    type: SignalType
    multi: bool = False


@dataclass(frozen=True)
class BlockContext:
    """What a block may receive from the outside world (the driven ports of the core).

    Attributes
    ----------
    catalog
        System catalog used by dynamical blocks. ``None`` means "load the default one"
        (resolved lazily by :meth:`require_catalog`).
    """

    catalog: Catalog | None = None

    def require_catalog(self) -> Catalog:
        """Return the catalog, loading the default catalog file if none was given."""
        if self.catalog is not None:
            return self.catalog
        from chaotic_sound.catalog import load_default_catalog  # adapter, lazily

        return load_default_catalog()


def _check_unit(name: str, value: float) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


def check_block_id(block_id: Any) -> None:
    """Raise ``ValueError`` unless ``block_id`` is a valid block id (spec §3).

    A block id is a non-empty string without ``.`` that has a UTF-8 encoding: the default
    seed is the CRC-32 of its UTF-8 bytes (spec §4.2 step 9), and patch files are UTF-8. A
    Python ``str`` lacks one only when it holds an unpaired surrogate (U+D800 to U+DFFF
    alone, which JSON can spell as an escape), so such ids are rejected for every block type.
    """
    ok = isinstance(block_id, str) and block_id != "" and "." not in block_id
    if ok:
        try:
            block_id.encode("utf-8")
        except UnicodeEncodeError:
            ok = False
    if not ok:
        raise ValueError(
            f"invalid block id {block_id!r} (a non-empty string without '.' or unpaired surrogates)"
        )


def _type_ok(value: Any, annotation: Any) -> bool:
    """Check a JSON-like value against a resolved annotation (float, int, bool, str, X | None)."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(_type_ok(value, a) for a in typing.get_args(annotation))
    if annotation is type(None):
        return value is None
    if annotation is bool:
        return isinstance(value, bool)
    if annotation is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if annotation is float:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except OverflowError:  # an int beyond float64 (JavaScript's JSON.parse gives ±inf)
            return False
    if annotation is str:
        return isinstance(value, str)
    return True


@dataclass(frozen=True)
class BlockParams:
    """Base class of every block's parameter dataclass.

    Subclasses validate their values in ``__post_init__`` (after :meth:`check_types`) and
    raise ``ValueError``. Fields defaulting to ``None`` mean "use the documented default";
    they are left out of the patch JSON (spec §5).
    """

    def check_types(self) -> None:
        """Raise ``ValueError`` if a field has the wrong JSON type (e.g. a string for a bool)."""
        hints = typing.get_type_hints(type(self))
        for f in fields(self):
            value = getattr(self, f.name)
            if not _type_ok(value, hints[f.name]):
                raise ValueError(
                    f"parameter {f.name!r} has the wrong type: {value!r} (expected {f.type})"
                )

    def to_dict(self) -> dict[str, Any]:
        """Parameters that differ from their defaults, as a plain dict (JSON-ready).

        Writers omit defaulted values and never write ``null`` (spec §5), so a field equal
        to its default is left out, and so is ``None`` ("the documented default"). Building
        the params again from this dict gives equal params.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None or (f.default is not MISSING and value == f.default):
                continue
            out[f.name] = value
        return out


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
    IS_SINK: ClassVar[bool] = False
    """A sink (the Output block) has no output ports; its result is returned as ``"main"``."""

    def __init__(
        self, block_id: str, *, context: BlockContext | None = None, **params: Any
    ) -> None:
        check_block_id(block_id)
        self.check_param_names(block_id, params)
        self.id = block_id
        self.context = context or BlockContext()
        try:
            self.params = self.Params(**params)
        except ValueError as exc:
            raise ValueError(f"{self.type_name} '{block_id}': {exc}") from None
        self.sample_rate: float = 0.0

    @classmethod
    def check_param_names(cls, block_id: str, names: Iterable[str]) -> None:
        """Raise ``ValueError`` if a name is not a field of :attr:`Params` (spec §5)."""
        allowed = {f.name for f in fields(cls.Params)}
        unknown = set(names) - allowed
        if unknown:
            raise ValueError(
                f"{cls.type_name} '{block_id}': unknown parameter(s) {sorted(unknown)}; "
                f"allowed: {sorted(allowed)}"
            )

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
            Number of samples in this chunk (may be 0).
        inputs
            One entry per input port: its signal (length ``n``), or ``None`` if nothing is
            connected.

        Returns
        -------
        dict
            One array per output port (for a sink, the key ``"main"``).
        """

    def diagnostics(self) -> dict[str, int]:
        """Counters reported after a render (e.g. safety resets). Empty by default."""
        return {}

    # -- serialization -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Patch-JSON representation of this block (spec §5)."""
        return {"id": self.id, "type": self.type_name, "params": self.params.to_dict()}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.id!r}, {self.params})"


def check_signal(name: str, signal: Signal | None, n: int) -> Signal | None:
    """Validate an input's length (a cheap guard before numba kernels)."""
    if signal is not None and signal.shape[0] != n:
        raise ValueError(f"input {name!r} has {signal.shape[0]} samples, expected {n}")
    return signal
