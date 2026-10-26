"""Fixed-step RK4 integration kernels (architecture layer 2).

All kernels are numba ``@njit`` functions that take the system's RHS as their first argument
(numba compiles one specialization per RHS). They work in place on preallocated arrays.

Time units: ``h``, ``dtau`` and ``h_max`` are in **system time** τ (the ODE's own units).
Seconds only appear in the thin Python wrappers, through the sample rate.

Caching: kernels that take the RHS as an argument are compiled per process and NOT cached on
disk. numba would have to pickle the RHS dispatcher's type into a cache index shared by all
processes, which breaks as soon as another process compiled a different (e.g. dynamically
generated) RHS. Compilation takes about a second per system; the RHS functions themselves and
the DSP kernels are cached.

Why fixed-step RK4 (and not an adaptive solver)? Audio needs a predictable cost per sample,
and the time scale ``k`` can change every sample. Classical RK4 at ≥ 256 steps per
characteristic period is far more accurate than audio needs (see ``docs/math/tuning.md``).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numba import njit
from numpy.typing import NDArray

from chaotic_sound.systems.base import SystemDef

TWO_PI = 2.0 * math.pi
MAX_SUBSTEPS = 4096
"""Upper bound on RK4 sub-steps per sample (spec §4.2 step 5); a cost guard, never reached
for valid notes (at most 42, at C8)."""


@njit
def rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp):  # type: ignore[no-untyped-def]
    """Advance ``x`` in place by one classical RK4 step of size ``h`` (system time).

    ``k1 … k4`` and ``tmp`` are scratch arrays of the same length as ``x``.
    """
    n = x.shape[0]
    rhs(x, p, k1)
    for i in range(n):
        tmp[i] = x[i] + 0.5 * h * k1[i]
    rhs(tmp, p, k2)
    for i in range(n):
        tmp[i] = x[i] + 0.5 * h * k2[i]
    rhs(tmp, p, k3)
    for i in range(n):
        tmp[i] = x[i] + h * k3[i]
    rhs(tmp, p, k4)
    for i in range(n):
        x[i] += (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])


@njit(cache=True)
def wrap_phases(x, wrap):  # type: ignore[no-untyped-def]
    """Wrap the variables flagged in the boolean mask ``wrap`` into [0, 2π)."""
    for i in range(x.shape[0]):
        if wrap[i]:
            x[i] = x[i] % TWO_PI


@njit
def integrate_sampled(rhs, x, p, h, steps_per_sample, out, wrap):  # type: ignore[no-untyped-def]
    """Integrate with fixed step ``h`` and record the state every ``steps_per_sample`` steps.

    Parameters
    ----------
    x : float64[dim]
        Initial state; updated in place to the final state.
    p : float64[n_params]
        Parameter vector (constant).
    h : float
        Step size in system time.
    steps_per_sample : int
        RK4 steps between recorded samples (≥ 1).
    out : float64[n_samples, dim]
        Output; row ``i`` is the state after ``(i + 1) * steps_per_sample`` steps.
    wrap : bool[dim]
        Phase-variable mask (wrapped modulo 2π after every sample).
    """
    dim = x.shape[0]
    k1 = np.empty(dim)
    k2 = np.empty(dim)
    k3 = np.empty(dim)
    k4 = np.empty(dim)
    tmp = np.empty(dim)
    for i in range(out.shape[0]):
        for _ in range(steps_per_sample):
            rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp)
        wrap_phases(x, wrap)
        for j in range(dim):
            out[i, j] = x[j]


@njit
def render_tuned(  # type: ignore[no-untyped-def]
    rhs, x, p, mod_index, p_values, dtau, h_max, wrap, lo, hi, x_reset, out
):
    """Audio-rate integration with a per-sample parameter and time step (spec §4.2 steps 5–8).

    For each output sample ``i``: set ``p[mod_index] = p_values[i]``, advance the state by
    ``dtau[i]`` system-time units using ``n = clamp(ceil(dtau[i] / h_max), 1, MAX_SUBSTEPS)``
    equal RK4 sub-steps, wrap phase variables, run the safety check, and record the state.
    A non-finite or negative ``dtau[i]`` triggers a safety reset.

    Parameters
    ----------
    x : float64[dim]
        ODE state, updated in place (it persists between calls, so chunked rendering is
        seamless).
    p : float64[n_params]
        Parameter vector; entry ``mod_index`` is overwritten every sample.
    mod_index : int
        Index of the modulated parameter.
    p_values : float64[n]
        Modulated parameter value for every sample.
    dtau : float64[n]
        System time to advance per sample, ``k(t)/fs``.
    h_max : float
        Largest allowed RK4 step (system time).
    wrap : bool[dim]
        Phase-variable mask.
    lo, hi : float64[dim]
        Safety bounding box; leaving it (or a non-finite state) triggers a reset.
    x_reset : float64[dim]
        State to restart from after a safety reset.
    out : float64[n, dim]
        State after each sample.

    Returns
    -------
    int
        Number of safety resets that happened in this call.
    """
    dim = x.shape[0]
    k1 = np.empty(dim)
    k2 = np.empty(dim)
    k3 = np.empty(dim)
    k4 = np.empty(dim)
    tmp = np.empty(dim)
    resets = 0
    for i in range(p_values.shape[0]):
        p[mod_index] = p_values[i]
        d = dtau[i]
        ok = math.isfinite(d) and d >= 0.0
        if ok:
            # n_sub = clamp(ceil(dtau / h_max), 1, MAX_SUBSTEPS); with dtau = 0 the state holds.
            n_sub = 1
            q = d / h_max
            if q > 1.0:
                n_sub = MAX_SUBSTEPS if q >= MAX_SUBSTEPS else math.ceil(q)
            h = d / n_sub
            for _ in range(n_sub):
                rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp)
            wrap_phases(x, wrap)
        for j in range(dim):
            v = x[j]
            if not math.isfinite(v) or v < lo[j] or v > hi[j]:
                ok = False
        if not ok:
            for j in range(dim):
                x[j] = x_reset[j]
            resets += 1
        for j in range(dim):
            out[i, j] = x[j]
    return resets


@njit
def max_lyapunov_kernel(  # type: ignore[no-untyped-def]
    rhs, x, p, h, n_transient, n_renorm, steps_per_renorm, d0, wrap
):
    """Largest Lyapunov exponent by the two-trajectory (Benettin) method.

    A copy of the trajectory is displaced by ``d0`` and both are integrated; every
    ``steps_per_renorm`` steps the separation ``d`` is measured, ``log(d/d0)`` accumulated and
    the copy pulled back to distance ``d0`` along the current separation direction.

    Returns the exponent in units of 1/(system time). Phase-variable differences are taken
    modulo 2π.
    """
    dim = x.shape[0]
    k1 = np.empty(dim)
    k2 = np.empty(dim)
    k3 = np.empty(dim)
    k4 = np.empty(dim)
    tmp = np.empty(dim)
    for _ in range(n_transient):
        rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp)
        wrap_phases(x, wrap)
    # Displace along the diagonal of the non-phase variables.
    y = x.copy()
    n_free = 0
    for j in range(dim):
        if not wrap[j]:
            n_free += 1
    for j in range(dim):
        if not wrap[j]:
            y[j] += d0 / math.sqrt(n_free)
    diff = np.empty(dim)
    total = 0.0
    for _ in range(n_renorm):
        for _ in range(steps_per_renorm):
            rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp)
            rk4_step(rhs, y, p, h, k1, k2, k3, k4, tmp)
        wrap_phases(x, wrap)
        wrap_phases(y, wrap)
        d2 = 0.0
        for j in range(dim):
            dj = y[j] - x[j]
            if wrap[j]:
                dj = (dj + math.pi) % TWO_PI - math.pi
            diff[j] = dj
            d2 += dj * dj
        d = math.sqrt(d2)
        if d == 0.0 or not math.isfinite(d):
            return math.nan
        total += math.log(d / d0)
        for j in range(dim):
            y[j] = x[j] + diff[j] * (d0 / d)
    return total / (n_renorm * steps_per_renorm * h)


# --------------------------------------------------------------------------------------
# Thin Python wrappers
# --------------------------------------------------------------------------------------


def trajectory(
    system: SystemDef,
    params: NDArray[np.float64] | None = None,
    x0: NDArray[np.float64] | None = None,
    *,
    dt: float,
    n_samples: int,
    h_max: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Integrate ``system`` and return samples spaced ``dt`` apart (system time).

    Parameters
    ----------
    system
        The system to integrate.
    params
        Parameter vector (default: the system defaults).
    x0
        Initial state (default: the system's initial condition). Not modified.
    dt
        Sampling interval in system time.
    n_samples
        Number of samples to return.
    h_max
        Largest RK4 step; the actual step is ``dt / ceil(dt / h_max)``.

    Returns
    -------
    samples : float64[n_samples, dim]
        States at times ``dt, 2·dt, …``.
    x_end : float64[dim]
        Final state (to continue integrating).
    """
    p = system.params_array() if params is None else np.asarray(params, dtype=np.float64)
    x = system.initial_state() if x0 is None else np.array(x0, dtype=np.float64)
    steps = max(1, math.ceil(dt / h_max))
    out = np.empty((n_samples, system.dim))
    integrate_sampled(system.rhs, x, p, dt / steps, steps, out, system.wrap_mask())
    return out, x


def max_lyapunov(
    system: SystemDef,
    params: NDArray[np.float64] | None = None,
    x0: NDArray[np.float64] | None = None,
    *,
    h: float,
    t_transient: float,
    t_measure: float,
    t_renorm: float,
    d0: float = 1e-8,
) -> float:
    """Largest Lyapunov exponent (1/system time) via :func:`max_lyapunov_kernel`.

    All times are in system time. ``t_renorm`` should be a fraction of the characteristic
    period so the separation stays in the linear regime.
    """
    p = system.params_array() if params is None else np.asarray(params, dtype=np.float64)
    x = system.initial_state() if x0 is None else np.array(x0, dtype=np.float64)
    steps_per_renorm = max(1, round(t_renorm / h))
    n_renorm = max(1, round(t_measure / (steps_per_renorm * h)))
    n_transient = round(t_transient / h)
    result: Any = max_lyapunov_kernel(
        system.rhs, x, p, h, n_transient, n_renorm, steps_per_renorm, d0, system.wrap_mask()
    )
    return float(result)
