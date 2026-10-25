"""Chua's circuit (1983), dimensionless form with a piecewise-linear diode.

Values from dysts (commit 2a03f1ae7b06), class ``Chua``.
"""

from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def chua_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Chua RHS. ``p = (alpha, beta, m0, m1)``.

    ``h(x) = m1·x + ½(m0 − m1)(|x + 1| − |x − 1|)`` is the Chua diode characteristic:
    slope ``m0`` for ``|x| < 1`` and ``m1`` outside.
    """
    alpha, beta, m0, m1 = p[0], p[1], p[2], p[3]
    h = m1 * x[0] + 0.5 * (m0 - m1) * (abs(x[0] + 1.0) - abs(x[0] - 1.0))
    out[0] = alpha * (x[1] - x[0] - h)
    out[1] = x[0] - x[1] + x[2]
    out[2] = -beta * x[1]


CHUA = SystemDef(
    name="chua",
    display_name="Chua",
    variables=("x", "y", "z"),
    param_names=("alpha", "beta", "m0", "m1"),
    default_params=(15.6, 28.0, -1.142857, -0.71429),
    initial_condition=(1.1262351, -0.11386474, -0.78324421),
    modulated_param="alpha",
    candidate_range=(8.0, 20.0),
    rhs=chua_rhs,
    dysts_name="Chua",
    equations_latex=(
        r"\dot x = \alpha\,(y - x - h(x)),\quad \dot y = x - y + z,\quad \dot z = -\beta y,"
        r"\quad h(x) = m_1 x + \tfrac12 (m_0 - m_1)\left(|x+1| - |x-1|\right)"
    ),
)
