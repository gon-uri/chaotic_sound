import numpy as np
import pytest

from chaotic_sound.blocks import SHAPES, Modulator
from chaotic_sound.blocks.modulator import shape_value

FS = 1000.0


def render(mod: Modulator, n: int, chunk: int | None = None) -> np.ndarray:
    mod.reset(FS)
    chunk = chunk or n
    parts = []
    done = 0
    while done < n:
        m = min(chunk, n - done)
        parts.append(mod.process(m, {})["out"])
        done += m
    return np.concatenate(parts)


@pytest.mark.parametrize(
    ("shape", "values"),
    [
        ("sine", {0.0: 0.0, 0.25: 0.5, 0.5: 1.0, 0.75: 0.5, 1.0: 0.0}),
        ("triangle", {0.0: 0.0, 0.25: 0.5, 0.5: 1.0, 0.75: 0.5, 1.0: 0.0}),
        ("square", {0.0: 1.0, 0.49: 1.0, 0.5: 0.0, 0.99: 0.0, 1.0: 0.0}),
        ("ramp_up", {0.0: 0.0, 0.5: 0.5, 1.0: 1.0}),
        ("ramp_down", {0.0: 1.0, 0.5: 0.5, 1.0: 0.0}),
    ],
)
def test_shape_values(shape: str, values: dict[float, float]) -> None:
    phases = np.array(list(values))
    np.testing.assert_allclose(shape_value(shape, phases), list(values.values()), atol=1e-12)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("mode", ["loop", "once"])
def test_output_in_unit_interval_and_chunk_independent(shape: str, mode: str) -> None:
    mod = Modulator("m", shape=shape, period_s=0.37, mode=mode)
    whole = render(mod, 3000)
    assert whole.min() >= 0.0 and whole.max() <= 1.0
    np.testing.assert_array_equal(whole, render(mod, 3000, chunk=97))


def test_loop_is_periodic_and_once_holds() -> None:
    loop = render(Modulator("m", shape="ramp_up", period_s=0.5, mode="loop"), 2000)
    np.testing.assert_allclose(loop[:500], loop[500:1000], atol=1e-12)
    once = render(Modulator("m", shape="ramp_up", period_s=0.5, mode="once"), 2000)
    assert once[499] < 1.0 and np.all(once[500:] == 1.0)
    once_sine = render(Modulator("m", shape="sine", period_s=0.5, mode="once"), 2000)
    assert np.all(once_sine[500:] == 0.0)


def test_starts_at_t0() -> None:
    sig = render(Modulator("m", shape="sine", period_s=1.0), 10)
    assert sig[0] == 0.0  # sample 0 is t = 0


@pytest.mark.parametrize(
    "params",
    [
        {"shape": "saw"},
        {"mode": "pingpong"},
        {"period_s": 0.0},
        {"period_s": float("nan")},
        {"rate": 1.0},
    ],
)
def test_invalid_params(params: dict) -> None:
    with pytest.raises(ValueError):
        Modulator("m", **params)
