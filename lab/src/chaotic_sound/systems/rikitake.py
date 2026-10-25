"""Rikitake two-disc dynamo (1958): a toy model of the reversals of Earth's magnetic field.

Two coupled Faraday disc dynamos; x and y are the currents in the two coils, z the angular
velocity of the discs (all non-dimensional). The sign of x and y flips irregularly, like the
polarity of the geomagnetic field. Values from dysts (commit 2a03f1ae7b06), class
``RikitakeDynamo``.
"""

from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def rikitake_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Rikitake RHS. ``p = (a, mu)``; ``mu`` is the resistive dissipation of the coils."""
    a, mu = p[0], p[1]
    out[0] = -mu * x[0] + x[1] * x[2]
    out[1] = -mu * x[1] - a * x[0] + x[0] * x[2]
    out[2] = 1.0 - x[0] * x[1]


RIKITAKE = SystemDef(
    name="rikitake",
    display_name="Rikitake dynamo",
    variables=("x", "y", "z"),
    param_names=("a", "mu"),
    default_params=(1.0, 1.0),
    initial_condition=(-0.7791562791136255, -0.6302244598741468, 2.671200187214492),
    modulated_param="mu",
    # The screening (docs/studies/fifth-system-screening.md) found chaos for μ ≳ 0.51 and quiet
    # spells on the attractor from μ ≈ 2.1, so the top is set by hand at 1.8.
    candidate_range=(0.2, 1.8),
    rhs=rikitake_rhs,
    dysts_name="RikitakeDynamo",
    period_hint=5.8975,
    equations_latex=(
        r"\dot x = -\mu x + y z,\quad \dot y = -\mu y - a x + x z,\quad \dot z = 1 - x y"
    ),
)
