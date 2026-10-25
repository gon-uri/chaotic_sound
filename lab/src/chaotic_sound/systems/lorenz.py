"""Lorenz (1963): a minimal model of atmospheric convection.

Values from dysts (commit 2a03f1ae7b06), class ``Lorenz``.
"""

from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def lorenz_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Lorenz RHS. ``p = (sigma, rho, beta)``."""
    sigma, rho, beta = p[0], p[1], p[2]
    out[0] = sigma * (x[1] - x[0])
    out[1] = x[0] * (rho - x[2]) - x[1]
    out[2] = x[0] * x[1] - beta * x[2]


LORENZ = SystemDef(
    name="lorenz",
    display_name="Lorenz",
    variables=("x", "y", "z"),
    param_names=("sigma", "rho", "beta"),
    default_params=(10.0, 28.0, 2.667),
    initial_condition=(-9.7869288, -15.03852, 20.533978),
    modulated_param="rho",
    candidate_range=(24.8, 80.0),
    rhs=lorenz_rhs,
    dysts_name="Lorenz",
    period_hint=1.5008,
    equations_latex=(
        r"\dot x = \sigma (y - x),\quad \dot y = x(\rho - z) - y,\quad \dot z = x y - \beta z"
    ),
)
