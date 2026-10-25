"""Characteristic-frequency estimators for (chaotic) signals.

Two estimators of the characteristic period of a scalar observable s(τ):

- :func:`spectral_peak`: the period of the most prominent peak of the power spectral density
  (Welch estimate, parabolic interpolation of the log-PSD around the maximum). This is the
  project's definition of P (ADR 0006).
- :func:`mean_return_time`: the mean time between successive local maxima above the mean
  (a Poincaré return time). Used as a cross-check: for phase-coherent attractors both agree.

All times are in the units of ``sample_spacing`` (system time in the lab).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import welch

PROMINENCE_BANDWIDTH = 0.03
"""Half-width, relative to the peak frequency, of the band counted as "the peak"."""


@dataclass(frozen=True)
class PeakEstimate:
    """Result of :func:`spectral_peak`.

    Attributes
    ----------
    frequency
        Peak frequency, in cycles per unit of ``sample_spacing``.
    period
        ``1 / frequency``.
    prominence
        Fraction of the signal power (above ``f_min``) within ±3 % of the peak frequency.
        It measures how pitched the signal is: about 1 for a sine, small for broadband noise.
    """

    frequency: float
    period: float
    prominence: float


def spectral_peak(
    signal: NDArray[np.float64],
    sample_spacing: float,
    *,
    nperseg: int,
    f_min: float = 0.0,
) -> PeakEstimate:
    """Locate the dominant spectral peak of ``signal``.

    Parameters
    ----------
    signal : float64[n]
        Uniformly sampled observable.
    sample_spacing
        Time between samples.
    nperseg
        Welch segment length in samples; the frequency resolution is
        ``1 / (nperseg · sample_spacing)`` before interpolation.
    f_min
        Ignore frequencies below this (removes DC and very slow drifts, e.g. Lorenz lobe
        switching when looking for the loop frequency).
    """
    fs = 1.0 / sample_spacing
    freqs, psd = welch(
        signal, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, window="hann", detrend="constant"
    )
    valid = freqs > max(f_min, 0.0)
    if not np.any(valid):
        raise ValueError("no frequencies above f_min")
    idx = np.flatnonzero(valid)
    k = int(idx[np.argmax(psd[idx])])
    df = freqs[1] - freqs[0]
    f_peak = float(freqs[k])
    if 0 < k < len(psd) - 1 and np.all(psd[k - 1 : k + 2] > 0):
        a, b, c = np.log(psd[k - 1 : k + 2])
        denom = a - 2.0 * b + c
        if denom < 0:  # proper maximum of the parabola
            f_peak += 0.5 * (a - c) / denom * df
    band = valid & (np.abs(freqs - f_peak) <= PROMINENCE_BANDWIDTH * f_peak)
    total = float(np.sum(psd[valid]))
    prominence = float(np.sum(psd[band]) / total) if total > 0 else 0.0
    return PeakEstimate(frequency=f_peak, period=1.0 / f_peak, prominence=prominence)


@dataclass(frozen=True)
class ReturnTimes:
    """Result of :func:`mean_return_time` (times in units of ``sample_spacing``)."""

    mean: float
    std: float
    count: int


def mean_return_time(signal: NDArray[np.float64], sample_spacing: float) -> ReturnTimes:
    """Mean and spread of the time between successive local maxima above the signal mean.

    Each maximum's time is refined by parabolic interpolation over three samples, so the
    estimate is accurate well below the sample spacing.
    """
    s = np.asarray(signal, dtype=np.float64)
    mid = s[1:-1]
    is_max = (mid > s[:-2]) & (mid >= s[2:]) & (mid > s.mean())
    k = np.flatnonzero(is_max) + 1
    if k.size < 3:
        return ReturnTimes(mean=float("nan"), std=float("nan"), count=int(k.size))
    a, b, c = s[k - 1], s[k], s[k + 1]
    denom = a - 2.0 * b + c
    with np.errstate(divide="ignore", invalid="ignore"):
        delta = np.where(denom < 0, 0.5 * (a - c) / denom, 0.0)
    t = (k + delta) * sample_spacing
    gaps = np.diff(t)
    return ReturnTimes(mean=float(gaps.mean()), std=float(gaps.std()), count=int(k.size))
