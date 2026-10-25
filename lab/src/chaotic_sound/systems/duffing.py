"""Forced Duffing oscillator (1918), written autonomously with a drive phase ``z``.

dysts naming (note: swapped with respect to many textbooks): ``beta`` multiplies the linear
term and ``alpha`` the cubic one; ``beta = −1`` gives a double-well potential.
Values from dysts (commit 2a03f1ae7b06), class ``Duffing``.
"""

import numpy as np
from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def duffing_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Duffing RHS. ``p = (alpha, beta, delta, gamma, omega)``; ``x[2]`` is the drive phase."""
    alpha, beta, delta, gamma, omega = p[0], p[1], p[2], p[3], p[4]
    out[0] = x[1]
    out[1] = -delta * x[1] - beta * x[0] - alpha * x[0] ** 3 + gamma * np.cos(x[2])
    out[2] = omega


DUFFING = SystemDef(
    name="duffing",
    display_name="Duffing (forced)",
    variables=("x", "y", "z"),
    param_names=("alpha", "beta", "delta", "gamma", "omega"),
    default_params=(1.0, -1.0, 0.1, 0.35, 1.4),
    initial_condition=(-1.1635382, -0.5092374, 0.0),
    modulated_param="gamma",
    candidate_range=(0.1, 0.8),
    rhs=duffing_rhs,
    dysts_name="Duffing",
    phase_indices=(2,),
    drive_frequency_param="omega",
    equations_latex=(
        r"\dot x = y,\quad \dot y = -\delta y - \beta x - \alpha x^3 + \gamma \cos z,"
        r"\quad \dot z = \omega"
    ),
)
