"""Shared document rules: the edge-case patches of ``examples/golden/documents.json``.

The TypeScript engine reads the same file (``packages/engine/test/documents.test.ts``), so
both engines accept and reject exactly the same patch documents (spec §3, §4, §5).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import Catalog
from chaotic_sound.patch import Patch, PatchError

DOCUMENTS = Path(__file__).resolve().parents[2] / "examples" / "golden" / "documents.json"
FIXTURE = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
FS = FIXTURE["sample_rate"]
FRAMES = FIXTURE["render_frames"]
CASES: list[dict[str, Any]] = FIXTURE["cases"]
ACCEPT = [c for c in CASES if c["outcome"] == "accept"]
REJECT = [c for c in CASES if c["outcome"] == "reject"]


def test_fixture_shape() -> None:
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names)), "case names must be unique"
    assert {c["outcome"] for c in CASES} == {"accept", "reject"}
    assert all(set(c) <= {"name", "outcome", "rule", "seeds", "doc"} for c in CASES)


@pytest.mark.parametrize("case", ACCEPT, ids=[c["name"] for c in ACCEPT])
def test_accepted_documents_load_render_and_round_trip(
    catalog: Catalog, case: dict[str, Any]
) -> None:
    patch = Patch.from_dict(case["doc"], catalog=catalog)
    patch.validate()
    audio = patch.render(n_samples=FRAMES, sample_rate=FS)
    assert audio.shape == (FRAMES, 2) and np.all(np.isfinite(audio))
    for block_id, seed in case.get("seeds", {}).items():
        block = patch.blocks[block_id]
        assert isinstance(block, Dynamical) and block.seed == seed
    # The writer produces a document that loads again and plays the same (spec §5).
    written = patch.to_dict()
    again = Patch.from_json(patch.to_json(), catalog=catalog)
    assert again.to_dict() == written
    np.testing.assert_array_equal(again.render(n_samples=FRAMES, sample_rate=FS), audio)


@pytest.mark.parametrize("case", REJECT, ids=[c["name"] for c in REJECT])
def test_rejected_documents_raise_patch_error(catalog: Catalog, case: dict[str, Any]) -> None:
    with pytest.raises(PatchError):
        Patch.from_dict(case["doc"], catalog=catalog).validate()
    # Through the text form too. json.dumps writes 1e400 as Infinity, which is not JSON:
    # from_json rejects that with a PatchError as well.
    with pytest.raises(PatchError):
        Patch.from_json(json.dumps(case["doc"]), catalog=catalog).validate()
