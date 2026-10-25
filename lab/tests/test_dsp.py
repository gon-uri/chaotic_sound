import math

import numpy as np
import pytest

from chaotic_sound.dsp import (
    dc_block,
    dc_block_coefficient,
    one_pole,
    one_pole_coefficient,
    soft_clip,
)


def test_one_pole_time_constant() -> None:
    fs = 48_000.0
    tau = 0.005
    alpha = one_pole_coefficient(tau, fs)
    step = np.ones(int(fs * 0.05))
    out = np.empty_like(step)
    one_pole(step, np.zeros(1), alpha, out)
    # After τ seconds a one-pole filter reaches 1 − 1/e of a unit step.
    assert out[round(tau * fs) - 1] == pytest.approx(1 - math.exp(-1), abs=1e-3)


def test_one_pole_chunking() -> None:
    rng = np.random.default_rng(0)
    x = rng.random(1000)
    alpha = 0.1
    whole = np.empty_like(x)
    one_pole(x, np.zeros(1), alpha, whole)
    state = np.zeros(1)
    parts = []
    for chunk in np.array_split(x, 7):
        out = np.empty_like(chunk)
        one_pole(chunk, state, alpha, out)
        parts.append(out)
    np.testing.assert_array_equal(whole, np.concatenate(parts))


def test_dc_block_removes_offset_and_keeps_audio() -> None:
    fs = 48_000.0
    t = np.arange(int(fs)) / fs
    x = 0.5 + np.sin(2 * np.pi * 220 * t)
    out = np.empty_like(x)
    dc_block(x, np.zeros(2), dc_block_coefficient(5.0, fs), out)
    tail = out[len(out) // 2 :]
    assert abs(tail.mean()) < 1e-3
    assert np.std(tail) == pytest.approx(np.std(np.sin(2 * np.pi * 220 * t)), rel=1e-3)


def test_soft_clip() -> None:
    x = np.linspace(-5, 5, 10_001)
    y = soft_clip(x)
    inside = np.abs(x) <= 0.9
    np.testing.assert_array_equal(y[inside], x[inside])
    assert np.all(np.abs(y) <= 1.0)  # tanh rounds to exactly 1.0 for huge inputs
    assert np.all(np.diff(y) >= 0)  # monotonic
    assert np.max(np.abs(np.diff(y))) <= np.max(np.diff(x)) + 1e-12  # slope ≤ 1, continuous


def test_soft_clip_curve_above_the_knee() -> None:
    x = np.array([0.95, 1.0, 1.5, -1.2])
    expected = np.sign(x) * (0.9 + 0.1 * np.tanh((np.abs(x) - 0.9) / 0.1))
    np.testing.assert_allclose(soft_clip(x), expected, rtol=0, atol=1e-15)


def test_filters_flush_tiny_states_to_zero() -> None:
    out = np.empty(5000)
    one_pole(np.zeros(5000), np.array([1.0]), 0.1, out)
    assert out[-1] == 0.0  # would otherwise be a subnormal number forever
    dc = np.empty(5000)
    dc_block(np.r_[1.0, np.zeros(4999)], np.zeros(2), 0.9, dc)
    assert dc[-1] == 0.0


def test_one_pole_varying_matches_constant() -> None:
    from chaotic_sound.dsp import one_pole_varying

    rng = np.random.default_rng(1)
    x = rng.random(500)
    a, b = np.empty(500), np.empty(500)
    one_pole(x, np.array([0.3]), 0.05, a)
    one_pole_varying(x, np.array([0.3]), np.full(500, 0.05), b)
    np.testing.assert_array_equal(a, b)
