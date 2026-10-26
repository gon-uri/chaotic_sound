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
AMP_EXPONENT = 1.0 / (2.0 * math.log10(2.0))
"""Perceptual gain curve g = a^1.661: every halving of the knob is −10 dB (half as loud)."""

TONAL_HARMONICS = 8
"""Harmonics resynthesized by the tonality step (spec §4.2 step 7, ADR 0015)."""
TONAL_Q = (1.0 / (2.0 * math.cos(math.pi / 8.0)), 1.0 / (2.0 * math.cos(3.0 * math.pi / 8.0)))
"""Q of the two state-variable sections of the 4th-order Butterworth band low-pass."""
TONAL_COHERENCE_FLOOR = 0.1
"""Phase normalization floor d_k = max(|v_k|, 0.1·(1 − τ)·√p_k): an incoherent band fades
out instead of flipping its partial's phase (spec §4.2 step 7, item 6). It scales with
(1 − τ) because fast phase flips need the short smoothing of low tonality; at τ = 1 (2 s
smoothing) directions change slowly and a floor would only lower the level."""
TONAL_MIX_EXPONENT = 0.75
"""Mix law m = (1 − τ)^0.75·r + τ^0.75·t: between equal amplitude (right for coherent sums)
and equal power (right for incoherent ones); keeps every v1 system within about ±1.2 dB."""


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


def tonal_state(n_harmonics: int = TONAL_HARMONICS) -> tuple[np.ndarray, ...]:
    """Fresh state of one tonality channel: (scalars, coefficients, filter memories, bands).

    ``scalars`` = [φ, n, f_last, τ_last, β_env, raw gain, tonal gain]; NaN in f_last and
    τ_last forces the first coefficient computation. ``coef`` = [a1, a2, a3] of the two
    state-variable sections. ``filt`` holds their states (s1, s2) per harmonic, part (re,
    im) and section. ``bands`` holds, per harmonic k, the smoothed power p_k and the
    smoothed complex amplitude v_k: [p, Re v, Im v] × K.
    """
    scalars = np.array([0.0, 0.0, np.nan, np.nan, 0.0, 0.0, 0.0])
    return scalars, np.zeros(6), np.zeros(8 * n_harmonics), np.zeros(3 * n_harmonics)


@njit(cache=True)
def tonal(r, f_a, tau, fs, scalars, coef, filt, bands, q1, q2, mix_exp, floor, out):  # type: ignore[no-untyped-def]
    """Harmonic resynthesis (spec §4.2 step 7, "Tonality"), one channel, ``n = len(r)`` samples.

    ``r`` is the level-normalized signal, ``f_a`` the fundamental actually heard (Hz) and
    ``tau`` the smoothed tonality, all per sample. Each band k = [k − ½, k + ½]·f_a is moved
    onto one partial with the band's smoothed power and smoothed phase. Writes
    m = (1 − τ)^0.75·r + τ^0.75·t to ``out``. The operation order follows the spec
    literally (it is mirrored by the TypeScript engine).
    """
    n_harm = bands.shape[0] // 3
    two_pi = 2.0 * math.pi
    for i in range(r.shape[0]):
        f = f_a[i]
        if f != scalars[2]:  # Butterworth low-pass at f_a/2: two TPT state-variable sections
            g = math.tan(math.pi * (f * 0.5) / fs)
            for j in range(2):
                kappa = 1.0 / (q1 if j == 0 else q2)
                a1 = 1.0 / (1.0 + g * (g + kappa))
                a2 = g * a1
                coef[3 * j] = a1
                coef[3 * j + 1] = a2
                coef[3 * j + 2] = g * a2
            scalars[2] = f
        t = tau[i]
        if t != scalars[3]:
            t_env = 0.002 * 10.0 ** (3.0 * t)
            scalars[4] = 1.0 - math.exp(-1.0 / (t_env * fs))
            scalars[5] = (1.0 - t) ** mix_exp
            scalars[6] = t**mix_exp
            scalars[3] = t
        ph = scalars[0] + f / fs
        ph = ph - math.floor(ph)
        scalars[0] = ph
        zr = math.cos(two_pi * ph)
        zi = math.sin(two_pi * ph)
        count = scalars[1]
        beta = max(scalars[4], 1.0 / (count + 1.0))
        scalars[1] = count + 1.0
        x = r[i]
        fl = floor * (1.0 - t)
        wr = 1.0
        wi = 0.0
        acc = 0.0
        for k in range(n_harm):
            nr = wr * zr - wi * zi
            ni = wr * zi + wi * zr
            wr = nr
            wi = ni
            c_re = 0.0
            c_im = 0.0
            for part in range(2):
                y = x * wr if part == 0 else -(x * wi)
                for j in range(2):
                    m = 8 * k + 4 * part + 2 * j
                    s1 = filt[m]
                    s2 = filt[m + 1]
                    v3 = y - s2
                    v1 = coef[3 * j] * s1 + coef[3 * j + 1] * v3
                    v2 = s2 + coef[3 * j + 1] * s1 + coef[3 * j + 2] * v3
                    filt[m] = 2.0 * v1 - s1
                    filt[m + 1] = 2.0 * v2 - s2
                    y = v2
                if part == 0:
                    c_re = y
                else:
                    c_im = y
            pw = c_re * c_re + c_im * c_im
            pk = bands[3 * k] + beta * (pw - bands[3 * k])
            vr = bands[3 * k + 1] + beta * (c_re - bands[3 * k + 1])
            vi = bands[3 * k + 2] + beta * (c_im - bands[3 * k + 2])
            bands[3 * k] = pk
            bands[3 * k + 1] = vr
            bands[3 * k + 2] = vi
            sp = math.sqrt(pk)
            den = max(math.sqrt(vr * vr + vi * vi), fl * sp)
            if den > 0.0:
                w = (0.45 * fs - (k + 1.0) * f) / (0.05 * fs)
                w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
                acc += w * 2.0 * sp * (vr * wr - vi * wi) / den
        out[i] = scalars[5] * x + scalars[6] * acc
