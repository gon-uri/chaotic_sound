"""Wrap dysts flows as chaotic_sound ``SystemDef`` objects (screening set "Halvorsen").

Study helper for the 5th-system screening (Halvorsen, Aizawa, Dadras, SprottB, SprottD,
ShimizuMorioka, Lorenz84, BurkeShaw). Nothing here touches ``src/``.

dysts calls ``Model._rhs(x, y, z, t, *params)`` with the parameters in **sorted key order**
(``dysts.base.BaseDyn``: ``param_list = [params[k] for k in sorted(params)]``). For flows with
parameters we generate, with ``exec``, an ``@njit`` ``rhs(x, p, out)`` that calls the dysts
numba kernel and copies the returned tuple into ``out``; ``p`` follows the sorted order.

SprottB and SprottD have **no parameters in dysts** (the coefficients are literals), so they
get hand-written kernels with one coefficient promoted to a parameter. At its default value
the kernel equals the dysts one; that is checked by :func:`verify_rhs`.

:func:`register` adds a system to the in-memory registry of the running process only, so that
the engine's ``Dynamical`` block can render it.
"""

from __future__ import annotations

import numba
import numpy as np
from numba import njit

from chaotic_sound.systems import SYSTEMS
from chaotic_sound.systems.base import SystemDef


def _make_rhs(kernel: object, dim: int, n_params: int) -> object:
    args = ", ".join(
        [f"x[{i}]" for i in range(dim)] + ["0.0"] + [f"p[{j}]" for j in range(n_params)]
    )
    body = "\n".join(f"    out[{i}] = r[{i}]" for i in range(dim))
    src = f"def rhs(x, p, out):\n    r = _kernel({args})\n{body}\n"
    ns: dict[str, object] = {"_kernel": kernel}
    exec(src, ns)
    return numba.njit(cache=False)(ns["rhs"])


# --- Parameter-free Sprott flows with one coefficient promoted to a parameter -------------


@njit(cache=False)
def sprottb_b_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Sprott B with damping ``b`` in y' (dysts: b = 1). p = (b,)."""
    out[0] = x[1] * x[2]
    out[1] = x[0] - p[0] * x[1]
    out[2] = 1.0 - x[0] * x[1]


@njit(cache=False)
def sprottb_c_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Sprott B with constant ``c`` in z' (dysts: c = 1). p = (c,)."""
    out[0] = x[1] * x[2]
    out[1] = x[0] - x[1]
    out[2] = p[0] - x[0] * x[1]


@njit(cache=False)
def sprottd_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Sprott D with coefficient ``a`` of y² in z' (dysts: a = 3). p = (a,)."""
    out[0] = -x[1]
    out[1] = x[0] + x[2]
    out[2] = x[0] * x[2] + p[0] * x[1] ** 2


_CUSTOM = {
    # name: (dysts class, param name, default, kernel)
    "sprottb_b": ("SprottB", "b", 1.0, sprottb_b_rhs),
    "sprottb_c": ("SprottB", "c", 1.0, sprottb_c_rhs),
    "sprottd": ("SprottD", "a", 3.0, sprottd_rhs),
}


def make_system(
    dysts_name: str,
    modulated_param: str,
    candidate_range: tuple[float, float],
    *,
    name: str | None = None,
    custom: str | None = None,
) -> SystemDef:
    """Build a ``SystemDef`` for the dysts class ``dysts_name``.

    Parameters
    ----------
    custom
        Key of :data:`_CUSTOM` for the hand-parameterized Sprott flows (ignores
        ``modulated_param``'s lookup in dysts, which has no parameters for them).
    """
    import dysts.flows

    cls = getattr(dysts.flows, dysts_name)
    model = cls()
    ic = np.asarray(model.ic, dtype=np.float64).copy()
    dim = ic.size
    if custom is not None:
        cls_name, pname, default, rhs = _CUSTOM[custom]
        assert cls_name == dysts_name and pname == modulated_param
        keys: tuple[str, ...] = (pname,)
        defaults: tuple[float, ...] = (default,)
    else:
        keys = tuple(sorted(model.params))
        defaults = tuple(float(model.params[k]) for k in keys)
        rhs = _make_rhs(cls._rhs, dim, len(keys))
    return SystemDef(
        name=name or (custom or dysts_name.lower()),
        display_name=dysts_name,
        variables=("x", "y", "z")[:dim],
        param_names=keys,
        default_params=defaults,
        initial_condition=tuple(float(v) for v in ic),
        modulated_param=modulated_param,
        candidate_range=candidate_range,
        rhs=rhs,
        dysts_name=dysts_name,
        period_hint=float(model.period),
    )


def verify_rhs(system: SystemDef, n: int = 50, seed: int = 1234) -> float:
    """Max abs difference between our RHS and dysts' ``model.rhs`` at random points.

    Same test as ``tests/test_systems.py::test_rhs_matches_dysts`` (points scattered around
    the initial condition with scale max(|ic|, 1)).
    """
    import dysts.flows

    model = getattr(dysts.flows, system.dysts_name)()
    rng = np.random.default_rng(seed)
    p = system.params_array()
    out = np.empty(system.dim)
    scale = np.maximum(np.abs(system.initial_state()), 1.0)
    worst = 0.0
    for _ in range(n):
        x = system.initial_state() + scale * rng.normal(size=system.dim)
        system.rhs(x, p, out)
        expected = np.asarray(model.rhs(x, 0.0), dtype=float)
        err = float(np.max(np.abs(out - expected) / np.maximum(1.0, np.abs(expected))))
        worst = max(worst, err)
    return worst


def register(system: SystemDef) -> None:
    """Add ``system`` to the in-process registry (not persisted) so ``Dynamical`` can use it."""
    SYSTEMS[system.name] = system


def use_uncached_kernels() -> None:
    """Swap the engine's ``cache=True`` integration kernels for uncached copies, in-process.

    Why: when this study started, the kernels taking the RHS dispatcher were ``cache=True``;
    numba keyed the on-disk specialization on the dispatcher's per-process identity, so (a) the
    cache never hit across processes and (b) saving the index failed with ``ReferenceError:
    underlying object has vanished`` for an ``exec``-generated RHS. ``integrate.py`` has since
    dropped disk caching for those kernels (2026-10-25), which makes this swap redundant but
    harmless. Must be called before any kernel is compiled in this process.
    """
    import chaotic_sound.blocks.dynamical as dyn
    import chaotic_sound.integrate as integ

    # Inner kernels first: the outer ones resolve them from the module globals at compile time.
    for name in ("rk4_step", "wrap_phases", "integrate_sampled", "max_lyapunov_kernel",
                 "render_tuned"):  # fmt: skip
        setattr(integ, name, numba.njit(cache=False)(getattr(integ, name).py_func))
    dyn.render_tuned = integ.render_tuned
