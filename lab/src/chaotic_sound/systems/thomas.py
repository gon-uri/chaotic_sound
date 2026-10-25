"""Thomas' cyclically symmetric attractor (1999), in the dysts parameterization.

The classical form ``x' = sin(y) − β·x`` (and cyclic) is recovered with ``β = a/b`` after
rescaling time by ``b``. Values from dysts (commit 2a03f1ae7b06), class ``Thomas``.
"""

import numpy as np
from numba import njit

from chaotic_sound.systems.base import SystemDef


@njit(cache=True)
def thomas_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """Thomas RHS. ``p = (a, b)``; ``a`` is the damping, ``b`` the feedback strength."""
    a, b = p[0], p[1]
    out[0] = -a * x[0] + b * np.sin(x[1])
    out[1] = -a * x[1] + b * np.sin(x[2])
    out[2] = -a * x[2] + b * np.sin(x[0])


THOMAS = SystemDef(
    name="thomas",
    display_name="Thomas",
    variables=("x", "y", "z"),
    param_names=("a", "b"),
    default_params=(1.85, 10.0),
    initial_condition=(2.199442, 2.3634225, 3.220197),
    modulated_param="a",
    candidate_range=(0.5, 2.5),
    rhs=thomas_rhs,
    dysts_name="Thomas",
    period_hint=4.969,
    equations_latex=(
        r"\dot x = -a x + b \sin y,\quad \dot y = -a y + b \sin z,\quad \dot z = -a z + b \sin x"
    ),
)
