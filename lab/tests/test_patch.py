import json
from pathlib import Path

import numpy as np
import pytest

from chaotic_sound.blocks import ControlSum, Dynamical, Modulator, Output, Sum
from chaotic_sound.catalog import Catalog
from chaotic_sound.patch import Patch, PatchError

FS = 48_000
EXAMPLES = sorted((Path(__file__).resolve().parents[2] / "examples" / "patches").glob("*.json"))


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


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_example_fixtures_load_round_trip_and_render(catalog: Catalog, path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    p = Patch.from_dict(data, catalog=catalog)
    assert p.to_dict() == data
    a = p.render(seconds=0.2, block_size=128)
    np.testing.assert_array_equal(a, p.render(seconds=0.2, block_size=4096))


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
