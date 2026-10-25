import json

import numpy as np
import pytest

from chaotic_sound.blocks import Dynamical, Modulator, Output, Sum
from chaotic_sound.catalog import Catalog
from chaotic_sound.patch import Patch, PatchError

FS = 48_000


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


def test_render_shape_and_order(catalog: Catalog) -> None:
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
    b = p.render(seconds=0.6, block_size=4096)
    c = p.render(seconds=0.6, block_size=1001)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(a, c)


def test_json_round_trip_renders_identically(catalog: Catalog) -> None:
    p = example_patch(catalog)
    q = Patch.from_json(p.to_json(), catalog=catalog)
    assert q.to_dict() == p.to_dict()
    np.testing.assert_array_equal(p.render(seconds=0.3), q.render(seconds=0.3))
    assert json.loads(p.to_json())["format"] == "chaotic-sound-patch"


def test_sum_adds_signals(catalog: Catalog) -> None:
    def single(bid: str) -> np.ndarray:
        p = Patch(catalog=catalog)
        p.add_block("dynamical", bid, system="chua", note="C3")
        p.add_block("output", "out", volume=0.5)
        p.connect(f"{bid}.out", "out.in")
        return p.render(seconds=0.2)

    p = Patch(catalog=catalog)
    p.add_block("dynamical", "a", system="chua", note="C3")
    p.add_block("dynamical", "b", system="chua", note="C3")
    p.add_block("sum", "mix")
    p.add_block("output", "out", volume=0.5)
    for src in ("a", "b"):
        p.connect(f"{src}.out", "mix.in")
    p.connect("mix.out", "out.in")
    both = p.render(seconds=0.2)
    # Volume 0.5 keeps everything below the soft-clip knee, so the sum is exact.
    assert np.max(np.abs(both)) < 0.9
    np.testing.assert_allclose(both, single("a") + single("b"), atol=1e-12)


def test_control_fan_in_is_clipped(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("modulator", "m1", shape="square", period_s=10.0)  # 1 for the first 5 s
    p.add_block("modulator", "m2", shape="square", period_s=10.0)
    p.add_block("dynamical", "osc", system="rossler")
    p.add_block("output", "out")
    p.connect("m1.out", "osc.param")
    p.connect("m2.out", "osc.param")
    p.connect("osc.out", "out.in")
    reference = Patch(catalog=catalog)
    reference.add_block("dynamical", "osc", system="rossler", param=1.0)
    reference.add_block("output", "out")
    reference.connect("osc.out", "out.in")
    # 1 + 1 clipped to 1 must equal a knob at 1 (after the first smoother sample).
    a, b = p.render(seconds=0.2), reference.render(seconds=0.2)
    np.testing.assert_allclose(a, b, atol=1e-12)


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


def test_output_rules(catalog: Catalog) -> None:
    p = Patch(catalog=catalog)
    p.add_block("dynamical", "a")
    p.add_block("dynamical", "b")
    with pytest.raises(PatchError, match="exactly one output"):
        p.render(seconds=0.01)
    p.add_block("output", "out")
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
    with pytest.raises(PatchError):
        Patch.from_dict({"format": "other", "version": 0})


def test_remove_and_disconnect(catalog: Catalog) -> None:
    p = example_patch(catalog)
    p.disconnect("lor.out", "mix.in")
    assert len(p.cables) == 4
    p.remove("ross")
    assert all("ross" not in (c.src_block, c.dst_block) for c in p.cables)
    assert isinstance(p.blocks["lfo_param"], Modulator)
    assert isinstance(p.blocks["mix"], Sum) and isinstance(p.blocks["out"], Output)
    assert isinstance(p.blocks["lor"], Dynamical)
