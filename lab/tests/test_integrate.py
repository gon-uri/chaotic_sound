"""RK4 kernels: convergence order, sampling, tuned rendering, safety reset, Lyapunov."""

import math

import numpy as np
import pytest
from numba import njit

from chaotic_sound.integrate import (
    integrate_sampled,
    max_lyapunov,
    render_tuned,
    trajectory,
)
from chaotic_sound.systems import get_system
from chaotic_sound.systems.base import SystemDef


@njit
def harmonic_rhs(x, p, out):  # x'' = -ω² x as a first-order system
    out[0] = x[1]
    out[1] = -p[0] * p[0] * x[0]


HARMONIC = SystemDef(
    name="harmonic",
    display_name="Harmonic oscillator",
    variables=("x", "v"),
    param_names=("omega",),
    default_params=(1.0,),
    initial_condition=(1.0, 0.0),
    modulated_param="omega",
    candidate_range=(0.5, 2.0),
    rhs=harmonic_rhs,
    dysts_name="",
    period_hint=6.283,
)


def _harmonic_error(h: float, t_end: float = 2 * math.pi) -> float:
    steps = round(t_end / h)
    x = HARMONIC.initial_state()
    out = np.empty((1, 2))
    integrate_sampled(
        HARMONIC.rhs, x, HARMONIC.params_array(), t_end / steps, steps, out, HARMONIC.wrap_mask()
    )
    exact = np.array([math.cos(t_end), -math.sin(t_end)])
    return float(np.max(np.abs(out[0] - exact)))


def test_rk4_is_fourth_order() -> None:
    e1 = _harmonic_error(0.1)
    e2 = _harmonic_error(0.05)
    order = math.log2(e1 / e2)
    # Classical RK4 has global order 4; allow a little slack for the asymptotic regime.
    assert 3.8 < order < 4.2


def test_trajectory_sampling_is_consistent() -> None:
    lorenz = get_system("lorenz")
    a, _ = trajectory(lorenz, dt=0.01, n_samples=100, h_max=0.005)  # 2 steps per sample
    b, _ = trajectory(lorenz, dt=0.005, n_samples=200, h_max=0.005)  # 1 step per sample
    # Identical step size → identical arithmetic → identical states.
    np.testing.assert_array_equal(a, b[1::2])


def test_trajectory_continuation() -> None:
    lorenz = get_system("lorenz")
    whole, _ = trajectory(lorenz, dt=0.01, n_samples=200, h_max=0.005)
    first, x_mid = trajectory(lorenz, dt=0.01, n_samples=100, h_max=0.005)
    second, _ = trajectory(lorenz, x0=x_mid, dt=0.01, n_samples=100, h_max=0.005)
    np.testing.assert_array_equal(whole, np.vstack([first, second]))


def _render(
    system: SystemDef,
    dtau: np.ndarray,
    p_values: np.ndarray,
    h_max: float,
    x: np.ndarray | None = None,
    lo: float = -1e6,
    hi: float = 1e6,
):
    x = system.initial_state() if x is None else x
    p = system.params_array()
    out = np.empty((dtau.size, system.dim))
    resets = render_tuned(
        system.rhs,
        x,
        p,
        system.modulated_index,
        p_values,
        dtau,
        h_max,
        system.wrap_mask(),
        np.full(system.dim, lo),
        np.full(system.dim, hi),
        system.initial_state(),
        out,
    )
    return out, resets, x


def test_render_tuned_matches_trajectory_for_constant_inputs() -> None:
    rossler = get_system("rossler")
    n = 500
    dtau = np.full(n, 0.03)
    p_values = np.full(n, rossler.default_value)
    out, resets, _ = _render(rossler, dtau, p_values, h_max=0.01)  # exactly 3 sub-steps
    ref, _ = trajectory(rossler, dt=0.03, n_samples=n, h_max=0.01)
    assert resets == 0
    np.testing.assert_allclose(out, ref, rtol=0, atol=1e-12)


def test_render_tuned_chunking_is_seamless() -> None:
    rossler = get_system("rossler")
    rng = np.random.default_rng(0)
    n = 1000
    dtau = 0.02 + 0.03 * rng.random(n)  # varying number of sub-steps
    p_values = 5.0 + rng.random(n)
    whole, _, _ = _render(rossler, dtau, p_values, h_max=0.01)
    x = rossler.initial_state()
    a, _, x = _render(rossler, dtau[:333], p_values[:333], 0.01, x=x)
    b, _, _ = _render(rossler, dtau[333:], p_values[333:], 0.01, x=x)
    np.testing.assert_array_equal(whole, np.vstack([a, b]))


def test_render_tuned_resets_when_leaving_bounds() -> None:
    lorenz = get_system("lorenz")
    n = 200
    out, resets, _ = _render(lorenz, np.full(n, 0.01), np.full(n, 28.0), 0.005, lo=-5, hi=5)
    assert resets > 0
    assert np.all(np.abs(out) <= max(5.0, np.max(np.abs(lorenz.initial_state()))))


def test_phase_variable_is_wrapped() -> None:
    duffing = get_system("duffing")
    out, _ = trajectory(duffing, dt=0.1, n_samples=1000, h_max=0.01)
    assert out[:, 2].min() >= 0.0 and out[:, 2].max() < 2 * math.pi


@pytest.mark.slow
def test_lorenz_lyapunov_matches_literature() -> None:
    # Literature value for the standard Lorenz attractor: λ_max ≈ 0.906 (Sprott 2003).
    lam = max_lyapunov(get_system("lorenz"), h=0.002, t_transient=20, t_measure=1000, t_renorm=0.2)
    assert lam == pytest.approx(0.906, abs=0.05)


def test_harmonic_lyapunov_is_zero() -> None:
    lam = max_lyapunov(HARMONIC, h=0.01, t_transient=1, t_measure=500, t_renorm=1.0)
    assert abs(lam) < 0.01
