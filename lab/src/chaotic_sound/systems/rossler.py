"""Rössler (1976): spiral-type chaos in a minimal oscillator model.

Values from dysts (commit 2a03f1ae7b06), class ``Rossler``.
"""

from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def rossler_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Rössler RHS. ``p = (a, b, c)``."""
    a, b, c = p[0], p[1], p[2]
    out[0] = -x[1] - x[2]
    out[1] = x[0] + a * x[1]
    out[2] = b + x[2] * (x[0] - c)


ROSSLER = SystemDef(
    name="rossler",
    display_name="Rössler",
    variables=("x", "y", "z"),
    param_names=("a", "b", "c"),
    default_params=(0.2, 0.2, 5.7),
    initial_condition=(6.5134412, 0.4772013, 0.34164294),
    modulated_param="c",
    candidate_range=(3.0, 12.0),
    rhs=rossler_rhs,
    dysts_name="Rossler",
    equations_latex=r"\dot x = -y - z,\quad \dot y = x + a y,\quad \dot z = b + z (x - c)",
)
