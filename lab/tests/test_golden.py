"""The committed golden vectors must match the current reference engine.

If this fails after an intended behavior change, regenerate them with
``uv run python scripts/export_golden.py`` (and the TypeScript engine must follow). These
tests check the exact parts (initial states, modulator windows, prefix); the statistics are
too slow to recompute here.
"""

import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from chaotic_sound.blocks import Dynamical, Modulator
from chaotic_sound.patch import Patch

LAB = Path(__file__).resolve().parents[1]
EXAMPLES = LAB.parent / "examples"
GOLDEN = EXAMPLES / "golden"
FILES = sorted(GOLDEN.glob("*.json"))


def f64(b64: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(b64), dtype="<f8")


def exporter() -> ModuleType:
    """``scripts/export_golden.py`` as a module (scripts are not part of the package)."""
    spec = importlib.util.spec_from_file_location(
        "export_golden", LAB / "scripts" / "export_golden.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_golden_vectors_are_current(path: Path) -> None:
    g = json.loads(path.read_text(encoding="utf-8"))
    fs, block_size = g["sample_rate"], g["block_size"]
    patch = Patch.load(EXAMPLES / g["patch"])
    for bid, x0 in g["initial_states"].items():
        block = patch.blocks[bid]
        assert isinstance(block, Dynamical)
        np.testing.assert_array_equal(block.initial_state(), x0)
    for bid, windows in g["modulators"].items():
        block = patch.blocks[bid]
        assert isinstance(block, Modulator)
        m = Modulator(bid, **block.params.to_dict())
        m.reset(fs)
        expected = [f64(w["values_f64_b64"]) for w in windows]
        y = m.process(max(w["start"] + len(e) for w, e in zip(windows, expected, strict=True)), {})
        for w, e in zip(windows, expected, strict=True):
            np.testing.assert_array_equal(y["out"][w["start"] : w["start"] + len(e)], e)
    prefix = patch.render(n_samples=g["prefix"]["n"], sample_rate=fs, block_size=block_size)
    np.testing.assert_array_equal(prefix[:, 0], f64(g["prefix"]["left_f64_b64"]))
    np.testing.assert_array_equal(prefix[:, 1], f64(g["prefix"]["right_f64_b64"]))


def test_every_demo_and_fixture_has_golden_vectors() -> None:
    demos = {p.stem for p in (EXAMPLES / "patches").glob("*.json")}
    fixtures = {f.name for f in exporter().FIXTURES}
    assert demos.isdisjoint(fixtures)
    assert demos | fixtures == {p.stem for p in FILES}


def test_fixture_patches_are_current() -> None:
    module = exporter()
    on_disk = {p.stem for p in module.FIXTURE_PATCHES.glob("*.json")}
    assert on_disk == {f.name for f in module.FIXTURES}
    for f in module.FIXTURES:
        path = module.FIXTURE_PATCHES / f"{f.name}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == f.doc, f.name
        Patch.load(path)  # a valid patch
