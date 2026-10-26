import importlib.util
import json
import sys
from dataclasses import fields
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from chaotic_sound.blocks import BLOCK_TYPES, ControlSum, Dynamical, Modulator, Output, Sum
from chaotic_sound.catalog import Catalog
from chaotic_sound.patch import Patch, PatchError

FS = 48_000
EXAMPLES = sorted((Path(__file__).resolve().parents[2] / "examples" / "patches").glob("*.json"))
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
BASE = {"format": "chaotic-sound-patch", "version": 0}


def example_patch(catalog: Catalog) -> Patch:
    """The owner's example: LFO → Rössler param, LFO → Lorenz amp, sum, output."""
    p = Patch(catalog=catalog)
    p.add_block("modulator", "lfo_param", shape="sine", period_s=2.0)
    p.add_block("modulator", "lfo_amp", shape="triangle", period_s=1.0)
    p.add_block("dynamical", "ross", system="rossler", note="A3")
    p.add_block("dynamical", "lor", system="lorenz", note="E3")
    p.add_block("sum", "mix", gain=0.8)
    p.add_block("output", "out", volume=0.9)
    p.connect("lfo_param.out", "ross.param")
    p.connect("lfo_amp.out", "lor.amp")
    p.connect("ross.out", "mix.in")
    p.connect("lor.out", "mix.in")
    p.connect("mix.out", "out.in")
    return p


def single(catalog: Catalog, **params) -> Patch:
    p = Patch(catalog=catalog)
    p.add_block("dynamical", "osc", **params)
    p.add_block("output", "out", volume=0.5)
    p.connect("osc.out", "out.in")
    return p


def test_render_shape_order_and_diagnostics(catalog: Catalog) -> None:
    p = example_patch(catalog)
    order = p.order()
    assert order.index("lfo_param") < order.index("ross") < order.index("mix") < order.index("out")
    audio = p.render(seconds=0.5)
    assert audio.shape == (FS // 2, 2)
    assert np.all(np.isfinite(audio)) and np.max(np.abs(audio)) <= 1.0
    assert p.last_render is not None and p.last_render.safety_resets == {"ross": 0, "lor": 0}


def test_block_size_independence(catalog: Catalog) -> None:
    p = example_patch(catalog)
    a = p.render(seconds=0.6, block_size=128)
    np.testing.assert_array_equal(a, p.render(seconds=0.6, block_size=4096))
    np.testing.assert_array_equal(a, p.render(seconds=0.6, block_size=1001))
    np.testing.assert_array_equal(a[:300], p.render(n_samples=300, block_size=1))


def test_block_order_in_json_does_not_matter(catalog: Catalog) -> None:
    p = example_patch(catalog)
    d = p.to_dict()
    d["blocks"] = d["blocks"][::-1]
    q = Patch.from_dict(d, catalog=catalog)
    np.testing.assert_array_equal(p.render(seconds=0.3), q.render(seconds=0.3))


def test_json_round_trip_without_nulls_and_with_ui(catalog: Catalog) -> None:
    p = example_patch(catalog)
    p.ui["ross"] = {"x": 120, "y": 40}
    text = p.to_json()
    assert "null" not in text  # defaults are omitted, never written as null (spec §5)
    q = Patch.from_json(text, catalog=catalog)
    assert q.to_dict() == p.to_dict() and q.ui == {"ross": {"x": 120, "y": 40}}
    np.testing.assert_array_equal(p.render(seconds=0.3), q.render(seconds=0.3))
    assert json.loads(text)["format"] == "chaotic-sound-patch"
    # null is accepted as "default" on input
    d = q.to_dict()
    d["blocks"][2]["params"]["param"] = None
    np.testing.assert_array_equal(
        Patch.from_dict(d, catalog=catalog).render(seconds=0.1), q.render(seconds=0.1)
    )


def defaults(type_name: str) -> dict[str, Any]:
    """Documented defaults of a block type's params (fields defaulting to None excluded)."""
    return {
        f.name: f.default for f in fields(BLOCK_TYPES[type_name].Params) if f.default is not None
    }


def without(d: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != key}


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_example_fixtures_load_round_trip_and_render(catalog: Catalog, path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    p = Patch.from_dict(data, catalog=catalog)
    written = p.to_dict()
    assert without(written, "blocks") == without(data, "blocks")
    # The writer keeps every non-default value and drops only defaulted ones (spec §5).
    for given, out in zip(data["blocks"], written["blocks"], strict=True):
        assert without(out, "params") == without(given, "params")
        params = given.get("params", {})
        dropped = {k: v for k, v in params.items() if k not in out["params"]}
        assert out["params"].items() <= params.items()
        assert dropped.items() <= defaults(given["type"]).items()
    again = Patch.from_dict(written, catalog=catalog)
    assert again.to_dict() == written
    a = p.render(seconds=0.2, block_size=128)
    np.testing.assert_array_equal(a, p.render(seconds=0.2, block_size=4096))
    np.testing.assert_array_equal(a, again.render(seconds=0.2, block_size=128))


def test_writers_omit_defaulted_values(catalog: Catalog) -> None:
    """Spec §5: writers omit defaulted values and never write null."""
    p = Patch(catalog=catalog)
    p.add_block("dynamical", "v", system="lorenz", note="A3", cents=0, amp=1, pitch_lock=True)
    p.add_block("dynamical", "w", note="A4", cents=-0.5, pitch_lock=False, seed=7, param=0.0)
    p.add_block("modulator", "m", shape="sine", period_s=4, mode="once")
    p.add_block("output", "out", volume=0.8)
    blocks = {b["id"]: b for b in p.to_dict()["blocks"]}
    assert blocks["v"]["params"] == {"system": "lorenz"}  # 0 == 0.0 and 1 == 1.0: defaults
    assert blocks["w"]["params"] == {
        "note": "A4", "cents": -0.5, "pitch_lock": False, "seed": 7, "param": 0.0
    }  # fmt: skip
    assert blocks["m"]["params"] == {"mode": "once"}
    assert blocks["out"]["params"] == {}
    assert "null" not in p.to_json()
    # Building the params again from what was written gives the same params, which is what
    # export_golden.py relies on (Modulator(b.id, **b.params.to_dict())).
    for b in p.blocks.values():
        assert type(b.params)(**b.params.to_dict()) == b.params
    again = Patch.from_json(p.to_json(), catalog=catalog)
    assert {bid: b.params for bid, b in again.blocks.items()} == {
        bid: b.params for bid, b in p.blocks.items()
    }


def load_script(name: str) -> ModuleType:
    """Import ``lab/scripts/<name>.py`` (the scripts are not a package)."""
    spec = importlib.util.spec_from_file_location(f"_script_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while it executes
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def test_render_demos_writes_valid_patches_that_match_the_examples(catalog: Catalog) -> None:
    """Every demo patch written by render_demos.py loads again and is the committed example.

    The committed files may still spell out defaulted values (they were written before the
    writer omitted them); they must describe the same patch.
    """
    demos = load_script("render_demos").DEMOS
    assert sorted(f"{d.name}.json" for d in demos) == [p.name for p in EXAMPLES]
    for demo in demos:
        written = demo.build().to_dict()
        for b in written["blocks"]:
            assert not b["params"].items() & defaults(b["type"]).items(), (demo.name, b)
        assert Patch.from_json(json.dumps(written), catalog=catalog).to_dict() == written
        committed = Patch.load(SCRIPTS.parents[1] / "examples" / "patches" / f"{demo.name}.json")
        assert committed.to_dict() == written, demo.name


def test_sum_adds_and_scales(catalog: Catalog) -> None:
    def mix(gain: float) -> np.ndarray:
        p = Patch(catalog=catalog)
        p.add_block("dynamical", "a", system="chua", note="C3")
        p.add_block("dynamical", "b", system="chua", note="C3")
        p.add_block("sum", "mix", gain=gain)
        p.add_block("output", "out", volume=0.5)
        for src in ("a", "b"):
            p.connect(f"{src}.out", "mix.in")
        p.connect("mix.out", "out.in")
        return p.render(seconds=0.2)

    both = mix(1.0)
    # Volume 0.5 keeps everything below the soft-clip knee, so the sum is exact.
    assert np.max(np.abs(both)) < 0.9
    a = single(catalog, system="chua", note="C3").render(seconds=0.2)
    p_b = Patch(catalog=catalog)
    p_b.add_block("dynamical", "b", system="chua", note="C3")
    p_b.add_block("output", "out", volume=0.5)
    p_b.connect("b.out", "out.in")
    # (block id "osc" vs "a" changes the seed; rebuild "a" with the same id)
    p_a = Patch(catalog=catalog)
    p_a.add_block("dynamical", "a", system="chua", note="C3")
    p_a.add_block("output", "out", volume=0.5)
    p_a.connect("a.out", "out.in")
    np.testing.assert_allclose(both, p_a.render(seconds=0.2) + p_b.render(seconds=0.2), atol=1e-12)
    np.testing.assert_allclose(mix(0.5), 0.5 * both, atol=1e-12)
    assert a.shape == both.shape


def test_control_inputs_take_one_cable_and_control_sum_combines(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("modulator", "m1", shape="square", period_s=10.0)  # 1 for the first 5 s
    p.add_block("modulator", "m2", shape="square", period_s=10.0)
    p.add_block("dynamical", "osc", system="rossler")
    p.add_block("output", "out", volume=0.5)
    p.connect("m1.out", "osc.amp")
    with pytest.raises(PatchError, match=r"only one cable.*control_sum"):
        p.connect("m2.out", "osc.amp")
    p.disconnect("m1.out", "osc.amp")
    p.add_block("control_sum", "cs", gain=0.7)
    p.connect("m1.out", "cs.in")
    p.connect("m2.out", "cs.in")
    p.connect("cs.out", "osc.amp")
    p.connect("osc.out", "out.in")
    # clip(0.7 · (1 + 1), 0, 1) = 1 must equal a knob amp of 1 (no hidden fan-in).
    ref = single(catalog, system="rossler", amp=1.0)
    np.testing.assert_allclose(p.render(seconds=0.2), ref.render(seconds=0.2), atol=1e-12)


def test_control_sum_block() -> None:
    cs = ControlSum("cs", gain=0.5)
    cs.reset(FS)
    np.testing.assert_allclose(cs.process(3, {"in": np.array([0.2, 1.0, 3.0])})["out"],
                               [0.1, 0.5, 1.0])  # fmt: skip
    np.testing.assert_array_equal(cs.process(2, {"in": None})["out"], [0.0, 0.0])


def test_non_finite_control_values_are_sanitized(catalog: Catalog) -> None:
    from chaotic_sound.patch import sanitize_control

    np.testing.assert_array_equal(
        sanitize_control(np.array([np.nan, np.inf, -np.inf, 2.0, -1.0, 0.3])),
        [0.0, 1.0, 0.0, 1.0, 0.0, 0.3],
    )


@pytest.mark.parametrize(
    ("src", "dst", "message"),
    [
        ("lfo.out", "osc.out", "has no input"),
        ("osc.out", "osc.param", "cannot connect"),  # audio → control
        ("lfo.out", "mix.in", "cannot connect"),  # control → audio
        ("nope.out", "mix.in", "no block"),
        ("lfo", "osc.param", "block.port"),
    ],
)
def test_bad_cables(catalog: Catalog, src: str, dst: str, message: str) -> None:
    p = Patch(catalog=catalog)
    p.add_block("modulator", "lfo")
    p.add_block("dynamical", "osc")
    p.add_block("sum", "mix")
    with pytest.raises(PatchError, match=message):
        p.connect(src, dst)


def test_duplicate_cables_are_rejected(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("dynamical", "a")
    p.add_block("sum", "mix")
    p.connect("a.out", "mix.in")
    with pytest.raises(PatchError, match="already exists"):
        p.connect("a.out", "mix.in")


def test_output_rules(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("dynamical", "a")
    p.add_block("dynamical", "b")
    with pytest.raises(PatchError, match="exactly one output"):
        p.render(seconds=0.01)
    p.add_block("output", "out")
    np.testing.assert_array_equal(p.render(n_samples=64), np.zeros((64, 2)))  # unconnected: silent
    with pytest.raises(PatchError, match="exactly one output"):
        p.add_block("output", "out2")
    p.connect("a.out", "out.in")
    with pytest.raises(PatchError, match="only one cable"):
        p.connect("b.out", "out.in")


def test_cycles_are_rejected(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("sum", "s1")
    p.add_block("sum", "s2")
    p.connect("s1.out", "s2.in")
    with pytest.raises(PatchError, match="cycle"):
        p.connect("s2.out", "s1.in")
    assert len(p.cables) == 1  # the rejected cable is not kept


def test_unknown_things_are_errors(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    with pytest.raises(PatchError, match="unknown block type"):
        p.add_block("reverb", "r")
    with pytest.raises(ValueError, match="unknown parameter"):
        p.add_block("sum", "s", volume=1.0)
    p.add_block("sum", "s")
    with pytest.raises(PatchError, match="duplicate"):
        p.add_block("sum", "s")
    base = {"format": "chaotic-sound-patch", "version": 0, "blocks": [], "cables": []}
    with pytest.raises(PatchError):
        Patch.from_dict({"format": "other", "version": 0})
    with pytest.raises(PatchError, match="top-level"):
        Patch.from_dict({**base, "extra": 1}, catalog=catalog)
    with pytest.raises(PatchError, match="bad block"):
        Patch.from_dict({**base, "blocks": [{"id": "s", "type": "sum", "parms": {}}]})
    with pytest.raises(PatchError, match="bad cable"):
        Patch.from_dict(
            {
                **base,
                "blocks": [{"id": "s", "type": "sum"}],
                "cables": [{"from": "s.out", "to": "s.in", "x": 1}],
            }
        )
    with pytest.raises(PatchError, match="wrong type"):
        Patch.from_dict({**base, "blocks": [{"id": "o", "type": "dynamical",
                                             "params": {"pitch_lock": "false"}}]},
                        catalog=catalog)  # fmt: skip


def voice_doc(**params: Any) -> dict[str, Any]:
    return {
        **BASE,
        "blocks": [
            {"id": "v", "type": "dynamical", "params": params},
            {"id": "out", "type": "output"},
        ],
        "cables": [{"from": "v.out", "to": "out.in"}],
    }


def test_version_must_be_the_number_zero(catalog: Catalog) -> None:
    for bad in (False, True, "0", 1, 0.5, None, [0]):
        with pytest.raises(PatchError, match="unsupported patch version"):
            Patch.from_dict({**voice_doc(), "version": bad}, catalog=catalog)
    # JSON has a single number type: 0.0 is the integer 0 (spec §5; JSON.parse gives 0).
    Patch.from_json(json.dumps({**voice_doc(), "version": 0.0}), catalog=catalog).validate()


def test_null_or_missing_blocks_and_cables_mean_empty(catalog: Catalog) -> None:
    out_only = {**BASE, "blocks": [{"id": "out", "type": "output"}]}
    for doc in (out_only, {**out_only, "cables": None}, {**out_only, "cables": []}):
        p = Patch.from_dict(doc, catalog=catalog)
        np.testing.assert_array_equal(p.render(n_samples=8), np.zeros((8, 2)))
    p = Patch.from_dict({**BASE, "blocks": None, "cables": None}, catalog=catalog)
    assert p.blocks == {} and p.cables == []
    with pytest.raises(PatchError, match="exactly one output"):
        p.validate()
    for bad in ({}, "", 5, {"from": "v.out", "to": "out.in"}):
        with pytest.raises(PatchError, match="must be arrays"):
            Patch.from_dict({**out_only, "cables": bad}, catalog=catalog)
        with pytest.raises(PatchError, match="must be arrays"):
            Patch.from_dict({**out_only, "blocks": bad}, catalog=catalog)


def test_numbers_beyond_float64_are_patch_errors(catalog: Catalog) -> None:
    huge = 10**400  # json.loads keeps every digit; float(huge) raises OverflowError
    for params in ({"amp": huge}, {"cents": -huge}, {"param": huge}, {"seed": huge}):
        with pytest.raises(PatchError, match=r"wrong type|seed must be"):
            Patch.from_dict(voice_doc(**params), catalog=catalog)
    with pytest.raises(PatchError, match="wrong type"):
        Patch.from_json(
            '{"format": "chaotic-sound-patch", "version": 0, "blocks": '
            '[{"id": "m", "type": "modulator", "params": {"period_s": 1' + "0" * 400 + "}}]}"
        )
    with pytest.raises(PatchError, match="wrong type"):  # 1e400 parses as inf
        Patch.from_json(json.dumps(voice_doc(amp=0.5)).replace("0.5", "1e400"), catalog=catalog)


def test_patch_text_must_be_standard_json(catalog: Catalog) -> None:
    """Python's json module reads NaN and Infinity; JSON and JSON.parse do not."""
    text = json.dumps({**voice_doc(), "ui": {"zoom": 1.0}})
    Patch.from_json(text, catalog=catalog).validate()
    for constant in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(PatchError, match="not valid JSON"):
            Patch.from_json(text.replace("1.0", constant), catalog=catalog)


def test_save_escapes_unpaired_surrogates_in_ui(catalog: Catalog, tmp_path: Path) -> None:
    """A ui string may hold an unpaired surrogate (JSON can spell one); saving must work."""
    doc = {**BASE, "blocks": [{"id": "out", "type": "output", "ui": {"label": "\ud800é"}}]}
    p = Patch.from_dict(doc, catalog=catalog)
    assert '"\\ud800é"' in p.to_json()  # escaped as JSON.stringify does; é stays as is
    p.save(tmp_path / "p.json")
    assert Patch.load(tmp_path / "p.json", catalog=catalog).ui == {"out": {"label": "\ud800é"}}


@pytest.mark.parametrize(
    "block_id", ["", "a.b", 5, None, ["out"], {}, "\ud800", "out\udc00", "\udfff\ud800"]
)
def test_invalid_block_ids_are_patch_errors(catalog: Catalog, block_id: Any) -> None:
    """Ids are non-empty strings without '.' that have a UTF-8 encoding (spec §3, §4.2)."""
    for type_name in ("output", "dynamical"):
        doc = {**BASE, "blocks": [{"id": block_id, "type": type_name}]}
        with pytest.raises(PatchError, match="invalid block id"):
            Patch.from_dict(doc, catalog=catalog)
        with pytest.raises(ValueError, match="invalid block id"):
            Patch(catalog=catalog).add_block(type_name, block_id)


def test_unicode_block_ids_seed_from_their_utf8_bytes(catalog: Catalog) -> None:
    from chaotic_sound.rng import stable_seed

    p = Patch(catalog=catalog)
    for bid in ("voix_é", "声", "🎵 osc"):  # 2-, 3- and 4-byte UTF-8 (a surrogate pair in JS)
        block = p.add_block("dynamical", bid)
        assert isinstance(block, Dynamical) and block.seed == stable_seed(bid)


@pytest.mark.parametrize("name", ["context", "block_id", "self", "type_name", "foo"])
def test_any_unknown_param_name_is_a_patch_error(catalog: Catalog, name: str) -> None:
    """Names that collide with Python arguments must not escape as TypeError."""
    for value in (1, None):
        doc = {**BASE, "blocks": [{"id": "out", "type": "output", "params": {name: value}}]}
        with pytest.raises(PatchError, match="unknown parameter"):
            Patch.from_dict(doc, catalog=catalog)
    with pytest.raises(ValueError, match="unknown parameter"):
        Patch(catalog=catalog).add_block("output", "out", **{name: 1})


def test_note_names_inside_a_patch_use_the_whole_string(catalog: Catalog) -> None:
    for name in ("note", "pitch_min", "pitch_max"):
        with pytest.raises(PatchError, match="not a note name"):
            Patch.from_dict(voice_doc(**{name: "A4\n"}), catalog=catalog)


def test_render_argument_validation(catalog: Catalog) -> None:
    p = single(catalog)
    for fs in (0, -48_000, float("nan")):
        with pytest.raises(ValueError, match="sample_rate"):
            p.render(seconds=0.1, sample_rate=fs)
    assert p.render(n_samples=0).shape == (0, 2)
    assert p.render(n_samples=1).shape == (1, 2)


def test_remove_and_disconnect(catalog: Catalog) -> None:
    p = example_patch(catalog)
    p.disconnect("lor.out", "mix.in")
    assert len(p.cables) == 4
    p.remove("ross")
    assert all("ross" not in (c.src_block, c.dst_block) for c in p.cables)
    assert isinstance(p.blocks["lfo_param"], Modulator)
    assert isinstance(p.blocks["mix"], Sum) and isinstance(p.blocks["out"], Output)
    assert isinstance(p.blocks["lor"], Dynamical)
