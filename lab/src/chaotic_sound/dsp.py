"""Small DSP building blocks (architecture layer 3): smoothing, DC blocking, soft clipping.

Every recurrence here is pinned exactly in the spec (§3, §4.2, §4.4) so that another engine
can reproduce it sample for sample:

- one-pole smoother: ``y[n] = y[n−1] + α_n (x[n] − y[n−1])``, output *after* the update;
- DC blocker: ``y[n] = x[n] − x[n−1] + R·y[n−1]`` with ``x[−1] = y[−1] = 0``;
- both flush their state to 0 when ``|state| < FLUSH_TO_ZERO`` (avoids subnormal numbers,
  which are slow on many CPUs and never decay to an exact 0).

Stateful filters take an explicit ``state`` array that the caller keeps between calls, so
chunked processing is seamless (spec §6, block-size independence).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit
from numpy.typing import NDArray

SOFT_CLIP_KNEE = 0.9
"""Below this absolute value the soft clipper is the identity (spec §4.4)."""
FLUSH_TO_ZERO = 1e-30
"""Filter states smaller than this in magnitude are set to exactly 0."""


def one_pole_coefficient(time_constant_s: float, sample_rate: float) -> float:
    """Smoothing coefficient ``α = 1 − exp(−1 / (τ·fs))`` of a one-pole low-pass.

    A step input reaches 63 % after τ seconds. ``τ ≤ 0`` gives ``α = 1`` (no smoothing).
    """
    if time_constant_s <= 0:
        return 1.0
    return 1.0 - math.exp(-1.0 / (time_constant_s * sample_rate))


@njit(cache=True)
def one_pole(x_in, state, alpha, out):  # type: ignore[no-untyped-def]
    """One-pole low-pass with a constant coefficient. ``state[0]`` is ``y[n−1]``."""
    y = state[0]
    for i in range(x_in.shape[0]):
        y += alpha * (x_in[i] - y)
        if abs(y) < FLUSH_TO_ZERO:
            y = 0.0
        out[i] = y
    state[0] = y


@njit(cache=True)
def one_pole_varying(x_in, state, alpha, out):  # type: ignore[no-untyped-def]
    """One-pole low-pass with a per-sample coefficient array ``alpha`` (same length as x)."""
    y = state[0]
    for i in range(x_in.shape[0]):
        y += alpha[i] * (x_in[i] - y)
        if abs(y) < FLUSH_TO_ZERO:
            y = 0.0
        out[i] = y
    state[0] = y


def dc_block_coefficient(cutoff_hz: float, sample_rate: float) -> float:
    """Pole radius ``R = exp(−2π f_c / fs)`` of the first-order DC blocker."""
    return math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)


@njit(cache=True)
def dc_block(x_in, state, r, out):  # type: ignore[no-untyped-def]
    """First-order DC blocker ``y[n] = x[n] − x[n−1] + R·y[n−1]``.

    ``state = [x_prev, y_prev]`` is updated in place (both start at 0).
    """
    xp = state[0]
    yp = state[1]
    for i in range(x_in.shape[0]):
        y = x_in[i] - xp + r * yp
        if abs(y) < FLUSH_TO_ZERO:
            y = 0.0
        xp = x_in[i]
        yp = y
        out[i] = y
    state[0] = xp
    state[1] = yp


def soft_clip(x: NDArray[np.float64], knee: float = SOFT_CLIP_KNEE) -> NDArray[np.float64]:
    """Identity for ``|x| ≤ knee``; above it, squash smoothly into ``(knee, 1)``.

    ``y = sign(x)·(knee + (1 − knee)·tanh((|x| − knee)/(1 − knee)))``. The curve and its slope
    are continuous at the knee, and ``|y| ≤ 1`` (strictly below 1 up to float rounding).
    """
    ax = np.abs(x)
    over = ax > knee
    y = np.array(x, dtype=np.float64, copy=True)
    width = 1.0 - knee
    y[over] = np.sign(x[over]) * (knee + width * np.tanh((ax[over] - knee) / width))
    return y
