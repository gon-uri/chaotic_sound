"""The committed golden vectors must match the current reference engine.

If this fails after an intended behavior change, regenerate them with
``uv run python scripts/export_golden.py`` (and the TypeScript engine must follow).
"""

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from chaotic_sound.blocks import Dynamical
from chaotic_sound.patch import Patch

GOLDEN = Path(__file__).resolve().parents[2] / "examples" / "golden"
# documents.json holds the shared document rules (tests/test_documents.py), not vectors.
FILES = sorted(p for p in GOLDEN.glob("*.json") if p.name != "documents.json")


def f64(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype="<f8")


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_golden_vectors_are_current(path: Path) -> None:
    g = json.loads(path.read_text(encoding="utf-8"))
    patch = Patch.load(GOLDEN.parent / "patches" / g["patch"])
    for bid, x0 in g["initial_states"].items():
        block = patch.blocks[bid]
        assert isinstance(block, Dynamical)
        np.testing.assert_array_equal(block.initial_state(), x0)
    prefix = patch.render(n_samples=g["prefix"]["n"], sample_rate=g["sample_rate"],
                          block_size=g["block_size"])  # fmt: skip
    np.testing.assert_array_equal(prefix[:, 0], f64(g["prefix"]["left_f64_b64"]))
    np.testing.assert_array_equal(prefix[:, 1], f64(g["prefix"]["right_f64_b64"]))


def test_every_example_has_golden_vectors() -> None:
    patches = {p.name for p in (GOLDEN.parent / "patches").glob("*.json")}
    assert patches == {p.name for p in FILES}
