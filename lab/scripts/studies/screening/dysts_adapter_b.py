"""Wrap a dysts flow as a chaotic_sound ``SystemDef`` (screening batch B, study helper).

dysts calls ``Model._rhs(x, y, z, t, *params)`` with the parameters in **sorted key order**
(``dysts.base``: ``param_list = [params[k] for k in sorted(params)]``). We generate, with
``exec``, an ``@njit`` function ``rhs(x, p, out)`` that calls the dysts numba kernel and copies
the returned tuple into ``out``. ``p`` follows the same sorted order, so
``SystemDef.param_names = tuple(sorted(model.params))``.

Forced (non-autonomous) dysts flows of this batch already carry the drive phase as a state
variable (``z' = w``); we mark it in ``phase_indices`` and wrap its initial value modulo 2π.

Nothing here touches ``src/``; ``register`` only adds the system to the in-memory registry of
the running process, so the engine's ``Dynamical`` block can render it.
"""

from __future__ import annotations

import math

import numba
import numpy as np

from chaotic_sound.systems.base import SystemDef


def _make_rhs(kernel: object, dim: int, n_params: int) -> object:
    args = ", ".join(
        [f"x[{i}]" for i in range(dim)] + ["0.0"] + [f"p[{j}]" for j in range(n_params)]
    )
    body = "\n".join(f"    out[{i}] = r[{i}]" for i in range(dim))
    src = f"def rhs(x, p, out):\n    r = _kernel({args})\n{body}\n"
    ns: dict[str, object] = {"_kernel": kernel}
    exec(src, ns)  # noqa: S102 - generated from integers only
    return numba.njit(cache=False)(ns["rhs"])


def make_system(
    dysts_name: str,
    modulated_param: str,
    candidate_range: tuple[float, float],
    *,
    name: str | None = None,
    phase_index: int | None = None,
    drive_param: str | None = None,
    overrides: dict[str, float] | None = None,
) -> SystemDef:
    """Build a ``SystemDef`` from the dysts class ``dysts_name``.

    Parameters
    ----------
    overrides
        Optional changes to the dysts default parameters (for exploring other branches).
    """
    import dysts.flows

    cls = getattr(dysts.flows, dysts_name)
    model = cls()
    keys = tuple(sorted(model.params))
    values = dict(model.params)
    if overrides:
        values.update(overrides)
    ic = np.asarray(model.ic, dtype=np.float64).copy()
    dim = ic.size
    phase = () if phase_index is None else (phase_index,)
    for i in phase:
        ic[i] = math.fmod(ic[i], 2.0 * math.pi)
    rhs = _make_rhs(cls._rhs, dim, len(keys))
    variables = ("x", "y", "z", "w")[:dim] if dim <= 4 else tuple(f"x{i}" for i in range(dim))
    return SystemDef(
        name=name or dysts_name.lower(),
        display_name=dysts_name,
        variables=variables,
        param_names=keys,
        default_params=tuple(float(values[k]) for k in keys),
        initial_condition=tuple(float(v) for v in ic),
        modulated_param=modulated_param,
        candidate_range=candidate_range,
        rhs=rhs,
        dysts_name=dysts_name,
        period_hint=float(model.period),
        phase_indices=phase,
        drive_frequency_param=drive_param,
    )


def verify_against_dysts(system: SystemDef, n: int = 50, seed: int = 1234) -> float:
    """Max relative deviation of our wrapper from ``model.rhs(X, 0)`` at random points."""
    import dysts.flows

    model = getattr(dysts.flows, system.dysts_name)()
    rng = np.random.default_rng(seed)
    p = np.array([float(model.params[k]) for k in system.param_names])
    out = np.empty(system.dim)
    scale = np.maximum(np.abs(system.initial_state()), 1.0)
    worst = 0.0
    for _ in range(n):
        x = system.initial_state() + scale * rng.normal(size=system.dim)
        system.rhs(x, p, out)
        ref = np.asarray(model.rhs(x, 0.0), dtype=float)
        worst = max(worst, float(np.max(np.abs(out - ref) / (np.abs(ref) + 1e-12))))
    return worst


def register(system: SystemDef) -> None:
    """Add ``system`` to the in-process registry so ``Dynamical`` can find it."""
    from chaotic_sound import systems

    systems.SYSTEMS[system.name] = system
