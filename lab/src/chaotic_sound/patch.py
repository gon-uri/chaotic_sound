"""Patch graph: blocks + cables, validation, ordering, rendering, JSON (architecture layer 5).

Example
-------
>>> from chaotic_sound.patch import Patch
>>> patch = Patch()
>>> _ = patch.add_block("modulator", "lfo", shape="sine", period_s=8.0)
>>> _ = patch.add_block("dynamical", "ross", system="rossler", note="A3")
>>> _ = patch.add_block("output", "out")
>>> _ = patch.connect("lfo.out", "ross.param")
>>> _ = patch.connect("ross.out", "out.in")
>>> audio = patch.render(seconds=0.1)
>>> audio.shape
(4800, 2)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from chaotic_sound.blocks import BLOCK_TYPES, Block, Dynamical, Output, SignalType
from chaotic_sound.catalog import Catalog

PATCH_FORMAT = "chaotic-sound-patch"
PATCH_VERSION = 0
DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_BLOCK_SIZE = 512


class PatchError(ValueError):
    """An invalid patch (bad cable, cycle, missing or duplicate output, and so on)."""


@dataclass(frozen=True)
class Cable:
    """A connection from ``src_block.src_port`` (an output) to ``dst_block.dst_port``."""

    src_block: str
    src_port: str
    dst_block: str
    dst_port: str

    @staticmethod
    def _split(ref: str) -> tuple[str, str]:
        block, sep, port = ref.partition(".")
        if not sep or not block or not port:
            raise PatchError(f"port reference must look like 'block.port', got {ref!r}")
        return block, port

    @classmethod
    def parse(cls, src: str, dst: str) -> Cable:
        """Build a cable from ``"block.port"`` strings."""
        sb, sp = cls._split(src)
        db, dp = cls._split(dst)
        return cls(sb, sp, db, dp)

    def to_dict(self) -> dict[str, str]:
        """Patch-JSON representation."""
        return {
            "from": f"{self.src_block}.{self.src_port}",
            "to": f"{self.dst_block}.{self.dst_port}",
        }


@dataclass(frozen=True)
class RenderStats:
    """Diagnostics of the last render."""

    sample_rate: float
    n_samples: int
    safety_resets: dict[str, int]


class Patch:
    """A graph of blocks connected by cables (spec §3, §5, §6).

    Parameters
    ----------
    catalog
        Catalog given to every dynamical block created through :meth:`add_block` or
        :meth:`from_dict` (default: the repository catalog).
    """

    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog
        self.blocks: dict[str, Block] = {}
        self.cables: list[Cable] = []
        self.last_render: RenderStats | None = None

    # -- building ----------------------------------------------------------------------

    def add(self, block: Block) -> Block:
        """Add an existing block; ids must be unique."""
        if block.id in self.blocks:
            raise PatchError(f"duplicate block id {block.id!r}")
        if isinstance(block, Output) and any(isinstance(b, Output) for b in self.blocks.values()):
            raise PatchError("a patch has exactly one output block")
        self.blocks[block.id] = block
        return block

    def add_block(self, type_name: str, block_id: str, **params: Any) -> Block:
        """Create a block of the given patch-JSON ``type`` and add it."""
        try:
            cls = BLOCK_TYPES[type_name]
        except KeyError:
            raise PatchError(
                f"unknown block type {type_name!r}; known: {sorted(BLOCK_TYPES)}"
            ) from None
        if cls is Dynamical:
            return self.add(Dynamical(block_id, catalog=self.catalog, **params))
        return self.add(cls(block_id, **params))

    def connect(self, src: str, dst: str) -> Cable:
        """Connect output ``"block.port"`` to input ``"block.port"`` (spec §3 rules)."""
        cable = Cable.parse(src, dst)
        for bid in (cable.src_block, cable.dst_block):
            if bid not in self.blocks:
                raise PatchError(f"no block with id {bid!r}")
        src_block, dst_block = self.blocks[cable.src_block], self.blocks[cable.dst_block]
        try:
            out_port = src_block.output_port(cable.src_port)
        except KeyError as exc:
            raise PatchError(str(exc)) from None
        try:
            in_port = dst_block.input_port(cable.dst_port)
        except KeyError as exc:
            raise PatchError(str(exc)) from None
        if out_port.type is not in_port.type:
            raise PatchError(
                f"cannot connect {src} ({out_port.type.value}) to {dst} ({in_port.type.value})"
            )
        if cable in self.cables:
            raise PatchError(f"cable {src} → {dst} already exists")
        if not in_port.multi and any(
            c.dst_block == cable.dst_block and c.dst_port == cable.dst_port for c in self.cables
        ):
            raise PatchError(f"input {dst} accepts only one cable")
        self.cables.append(cable)
        try:
            self.order()
        except PatchError:
            self.cables.pop()
            raise
        return cable

    def disconnect(self, src: str, dst: str) -> None:
        """Remove a cable."""
        cable = Cable.parse(src, dst)
        try:
            self.cables.remove(cable)
        except ValueError:
            raise PatchError(f"no cable {src} → {dst}") from None

    def remove(self, block_id: str) -> None:
        """Remove a block and every cable attached to it."""
        if block_id not in self.blocks:
            raise PatchError(f"no block with id {block_id!r}")
        del self.blocks[block_id]
        self.cables = [c for c in self.cables if block_id not in (c.src_block, c.dst_block)]

    # -- validation and order ----------------------------------------------------------

    @property
    def output(self) -> Output:
        """The patch's single output block."""
        outputs = [b for b in self.blocks.values() if isinstance(b, Output)]
        if len(outputs) != 1:
            raise PatchError(f"a patch needs exactly one output block (found {len(outputs)})")
        return outputs[0]

    def order(self) -> list[str]:
        """Block ids in processing order (Kahn's algorithm, ties broken by insertion order).

        Raises :class:`PatchError` if the cables form a cycle (feedback is not in v1).
        """
        indegree = {bid: 0 for bid in self.blocks}
        children: dict[str, list[str]] = {bid: [] for bid in self.blocks}
        for c in self.cables:
            indegree[c.dst_block] += 1
            children[c.src_block].append(c.dst_block)
        ready = [bid for bid in self.blocks if indegree[bid] == 0]
        ordered: list[str] = []
        while ready:
            bid = ready.pop(0)
            ordered.append(bid)
            for child in children[bid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(ordered) != len(self.blocks):
            stuck = sorted(set(self.blocks) - set(ordered))
            raise PatchError(f"cables form a cycle through {stuck} (feedback is not supported)")
        return ordered

    def validate(self) -> None:
        """Check the whole patch (one output, acyclic, cables consistent)."""
        _ = self.output
        self.order()

    # -- rendering ---------------------------------------------------------------------

    def render(
        self,
        seconds: float | None = None,
        *,
        n_samples: int | None = None,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> NDArray[np.float64]:
        """Render the patch offline from t = 0.

        Give either ``seconds`` or ``n_samples``. The result does not depend on
        ``block_size`` (spec §6). Returns stereo audio of shape ``(n, 2)``.
        """
        if (seconds is None) == (n_samples is None):
            raise ValueError("give exactly one of seconds or n_samples")
        n_total = round(seconds * sample_rate) if seconds is not None else int(n_samples or 0)
        if block_size < 1:
            raise ValueError("block_size must be ≥ 1")
        self.validate()
        order = self.order()
        output_id = self.output.id
        incoming: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for c in self.cables:
            incoming.setdefault((c.dst_block, c.dst_port), []).append((c.src_block, c.src_port))
        for block in self.blocks.values():
            block.reset(sample_rate)

        out = np.empty((n_total, 2))
        pos = 0
        while pos < n_total:
            n = min(block_size, n_total - pos)
            signals: dict[tuple[str, str], NDArray[np.float64]] = {}
            for bid in order:
                block = self.blocks[bid]
                inputs: dict[str, NDArray[np.float64] | None] = {}
                for port in block.INPUTS:
                    sources = incoming.get((bid, port.name), [])
                    if not sources:
                        inputs[port.name] = None
                        continue
                    total = signals[sources[0]].copy()
                    for src in sources[1:]:
                        total += signals[src]
                    if port.type is SignalType.CONTROL:
                        np.clip(total, 0.0, 1.0, out=total)
                    inputs[port.name] = total
                for name, signal in block.process(n, inputs).items():
                    signals[(bid, name)] = signal
            out[pos : pos + n] = signals[(output_id, "main")]
            pos += n

        resets = {b.id: b.resets for b in self.blocks.values() if isinstance(b, Dynamical)}
        self.last_render = RenderStats(sample_rate, n_total, resets)
        return out

    # -- serialization -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Patch JSON (spec §5)."""
        return {
            "format": PATCH_FORMAT,
            "version": PATCH_VERSION,
            "blocks": [b.to_dict() for b in self.blocks.values()],
            "cables": [c.to_dict() for c in self.cables],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], catalog: Catalog | None = None) -> Patch:
        """Build a patch from its JSON form; unknown block types or params are errors."""
        if data.get("format") != PATCH_FORMAT:
            raise PatchError("not a chaotic_sound patch (missing 'format')")
        if data.get("version") != PATCH_VERSION:
            raise PatchError(f"unsupported patch version {data.get('version')!r}")
        patch = cls(catalog=catalog)
        for spec in data.get("blocks", []):
            params = dict(spec.get("params", {}))
            patch.add_block(spec["type"], spec["id"], **params)
        for cable in data.get("cables", []):
            patch.connect(cable["from"], cable["to"])
        return patch

    def to_json(self, indent: int = 2) -> str:
        """Patch JSON as a string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str, catalog: Catalog | None = None) -> Patch:
        """Inverse of :meth:`to_json`."""
        return cls.from_dict(json.loads(text), catalog=catalog)

    def save(self, path: str | Path) -> None:
        """Write the patch JSON to ``path``."""
        Path(path).write_text(self.to_json() + "\n")

    @classmethod
    def load(cls, path: str | Path, catalog: Catalog | None = None) -> Patch:
        """Read a patch JSON file."""
        return cls.from_json(Path(path).read_text(), catalog=catalog)
