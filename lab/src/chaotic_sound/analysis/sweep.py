"""Parameter sweeps: classify the dynamics and measure the quantities the catalog needs.

At each value ``p`` of the modulated parameter we integrate the system, then record whether
the motion is bounded and stationary, its largest Lyapunov exponent, and per variable the mean,
standard deviation, extremes, spectral-peak period, prominence and return time.

Sweeps use **continuation**: the end state at one value seeds the next, moving outward from
the default value. This tracks the attractor branch that a slowly modulated box actually
follows (spec §4.2, ADR 0006).

Time units: everything is in system time; the reference period P_ref sets the step size and
the analysis windows so that all systems are treated alike.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.integrate import max_lyapunov, trajectory
from chaotic_sound.systems.base import SystemDef


@dataclass(frozen=True)
class AnalysisSettings:
    """Numerical settings of the analysis. All durations are in units of P_ref."""

    steps_per_period: int = 256
    samples_per_period: int = 32
    transient_periods: float = 50.0
    record_periods: float = 2000.0
    welch_segment_periods: float = 128.0
    lyapunov_periods: float = 300.0
    lyapunov_renorm_periods: float = 0.25
    f_min_ratio: float = 0.25
    """Ignore spectral content below ``f_min_ratio / P_ref`` (slow drifts, lobe switching)."""
    escape_factor: float = 50.0
    """Unbounded if a variable leaves ``mean_ref ± escape_factor · std_ref``."""
    drift_threshold: float = 0.2
    """Non-stationary if the two half-record means differ by more than this many σ."""


DEFAULT_SETTINGS = AnalysisSettings()
"""Accurate settings used for the catalog tables."""

SWEEP_SETTINGS = AnalysisSettings(
    record_periods=1000.0, welch_segment_periods=64.0, lyapunov_periods=200.0
)
"""Settings for the range-selection sweep (many points, moderate accuracy)."""

QUICK_SETTINGS = AnalysisSettings(
    record_periods=400.0, welch_segment_periods=64.0, lyapunov_periods=150.0
)
"""Cheaper settings for tests and the coarse first sweep."""


@dataclass(frozen=True)
class ReferenceScale:
    """Scale of a system at its default parameters, used to normalize the analysis.

    Attributes
    ----------
    period
        P_ref in system time: the drive period for forced systems, otherwise the shortest
        characteristic time (spectral-peak period or mean return time) among the audible
        variables at the default parameter.
    mean, std
        Per-variable mean and standard deviation at the default parameter (escape check).
    """

    period: float
    mean: NDArray[np.float64]
    std: NDArray[np.float64]


@dataclass(frozen=True)
class VariableStats:
    """Statistics of one variable at one parameter value (system time units)."""

    mean: float
    std: float
    minimum: float
    maximum: float
    peak_period: float
    prominence: float
    return_time: float
    drift: float


@dataclass(frozen=True)
class PointResult:
    """Analysis of the system at one parameter value."""

    value: float
    bounded: bool
    stationary: bool
    lyapunov: float
    """Largest Lyapunov exponent, 1/system time (NaN if unbounded)."""
    variables: dict[str, VariableStats] = field(default_factory=dict)
    x_end: NDArray[np.float64] = field(default_factory=lambda: np.empty(0), repr=False)

    def is_chaotic(self, period: float, threshold: float) -> bool:
        """Bounded, stationary and with λ·P above ``threshold`` (nats per period)."""
        return (
            self.bounded
            and self.stationary
            and math.isfinite(self.lyapunov)
            and self.lyapunov * period > threshold
        )


def _measure(
    system: SystemDef,
    value: float,
    x0: NDArray[np.float64],
    settings: AnalysisSettings,
    period: float,
    escape: tuple[NDArray[np.float64], NDArray[np.float64]] | None,
) -> PointResult:
    params = system.params_array(**{system.modulated_param: value})
    h = period / settings.steps_per_period
    dt = period / settings.samples_per_period
    n_transient = math.ceil(settings.transient_periods * settings.samples_per_period)
    n_record = math.ceil(settings.record_periods * settings.samples_per_period)
    transient, x = trajectory(system, params, x0, dt=dt, n_samples=n_transient, h_max=h)
    record, x_end = trajectory(system, params, x, dt=dt, n_samples=n_record, h_max=h)

    audio_idx = [system.variable_index(v) for v in system.audio_variables]
    bounded = bool(np.all(np.isfinite(transient)) and np.all(np.isfinite(record)))
    if bounded and escape is not None:
        lo, hi = escape
        sub = record[:, audio_idx]
        bounded = bool(np.all(sub >= lo[audio_idx]) and np.all(sub <= hi[audio_idx]))
    if not bounded:
        return PointResult(value=value, bounded=False, stationary=False, lyapunov=math.nan)

    nperseg = round(settings.welch_segment_periods * settings.samples_per_period)
    f_min = settings.f_min_ratio / period
    stats: dict[str, VariableStats] = {}
    stationary = True
    half = n_record // 2
    for name, i in zip(system.audio_variables, audio_idx, strict=True):
        s = record[:, i]
        std = float(s.std())
        drift = float(abs(s[:half].mean() - s[half:].mean()) / std) if std > 0 else math.inf
        stationary &= drift <= settings.drift_threshold
        if std > 0:
            peak = spectral_peak(s, dt, nperseg=nperseg, f_min=f_min)
            peak_period, prominence = peak.period, peak.prominence
            return_time = mean_return_time(s, dt).mean
        else:  # a fixed point: no oscillation at all
            peak_period, prominence, return_time = math.nan, 0.0, math.nan
        stats[name] = VariableStats(
            mean=float(s.mean()),
            std=std,
            minimum=float(s.min()),
            maximum=float(s.max()),
            peak_period=peak_period,
            prominence=prominence,
            return_time=return_time,
            drift=drift,
        )
    lyap = max_lyapunov(
        system,
        params,
        x_end,
        h=h,
        t_transient=0.0,
        t_measure=settings.lyapunov_periods * period,
        t_renorm=settings.lyapunov_renorm_periods * period,
    )
    return PointResult(
        value=value,
        bounded=True,
        stationary=bool(stationary),
        lyapunov=lyap,
        variables=stats,
        x_end=x_end,
    )


def reference_scale(system: SystemDef, settings: AnalysisSettings) -> ReferenceScale:
    """Measure P_ref and the default-parameter statistics of ``system``.

    A first pass uses dysts' ``period_hint`` for step sizes; P_ref is then the drive period
    (forced systems) or the shortest characteristic time among audible variables.
    """
    drive = system.drive_period()
    first = _measure(
        system,
        system.default_value,
        system.initial_state(),
        settings,
        period=drive if drive is not None else system.period_hint,
        escape=None,
    )
    if not first.bounded:
        raise RuntimeError(f"{system.name}: diverges at its default parameters")
    # Shortest time scale seen in any audible variable (spectral peak or return time), so
    # that step sizes and sampling resolve the fastest oscillation.
    shortest = min(
        min(t for t in (v.peak_period, v.return_time) if math.isfinite(t))
        for v in first.variables.values()
    )
    period = drive if drive is not None else shortest
    mean = system.initial_state() * 0.0
    std = np.ones(system.dim)
    for name, v in first.variables.items():
        i = system.variable_index(name)
        mean[i], std[i] = v.mean, v.std
    return ReferenceScale(period=float(period), mean=mean, std=std)


def analyze_point(
    system: SystemDef,
    value: float,
    reference: ReferenceScale,
    settings: AnalysisSettings,
    x0: NDArray[np.float64] | None = None,
) -> PointResult:
    """Analyze ``system`` with its modulated parameter set to ``value``.

    Parameters
    ----------
    x0
        Initial state (default: the system's initial condition). Pass the previous point's
        ``x_end`` for continuation.
    """
    escape = (
        reference.mean - settings.escape_factor * reference.std,
        reference.mean + settings.escape_factor * reference.std,
    )
    start = system.initial_state() if x0 is None else x0
    return _measure(system, value, start, settings, reference.period, escape)


def sweep(
    system: SystemDef,
    values: Sequence[float] | NDArray[np.float64],
    reference: ReferenceScale,
    settings: AnalysisSettings,
    progress: Callable[[int, int], None] | None = None,
) -> list[PointResult]:
    """Analyze every value in ``values`` (sorted ascending) with continuation from the default.

    The walk starts at the value closest to the system default (from the system's initial
    condition) and moves up, then down, seeding each point with its neighbor's end state.
    After an unbounded point the walk restarts from the initial condition.
    """
    vals = np.asarray(values, dtype=np.float64)
    if np.any(np.diff(vals) <= 0):
        raise ValueError("values must be strictly increasing")
    start = int(np.argmin(np.abs(vals - system.default_value)))
    results: list[PointResult | None] = [None] * len(vals)
    done = 0
    for order in (range(start, len(vals)), range(start - 1, -1, -1)):
        x0 = system.initial_state() if order.start == start else _seed(results[start], system)
        for i in order:
            res = analyze_point(system, float(vals[i]), reference, settings, x0)
            results[i] = res
            x0 = _seed(res, system)
            done += 1
            if progress is not None:
                progress(done, len(vals))
    return [r for r in results if r is not None]


def _seed(result: PointResult | None, system: SystemDef) -> NDArray[np.float64]:
    if result is None or not result.bounded:
        return system.initial_state()
    return result.x_end.copy()


@dataclass(frozen=True)
class RangeSelection:
    """Chaotic interval of the modulated parameter chosen from a sweep.

    ``lo_reason`` / ``hi_reason`` explain why each end stopped; ``windows`` lists the narrow
    periodic windows ``(start, end)`` that were accepted inside the interval.
    """

    lo: float
    hi: float
    lo_reason: str
    hi_reason: str
    windows: tuple[tuple[float, float], ...] = ()


def select_chaotic_range(
    results: Sequence[PointResult],
    default_value: float,
    period_ref: float,
    period_of: Callable[[PointResult], float],
    drift_of: Callable[[PointResult], float],
    *,
    drift_threshold: float = 0.2,
    lyapunov_threshold: float = 0.05,
    max_period_jump: float = 0.15,
    max_window_width: float = 0.0,
    escape_margin: float = 0.0,
) -> RangeSelection:
    """Largest interval around the default value that is safe and (essentially) chaotic.

    Walking outward from the default, the interval keeps growing while points are bounded,
    stationary (``drift_of(point) ≤ drift_threshold``) and chaotic
    (λ·P_ref > ``lyapunov_threshold``). It stops:

    - at a point that is unbounded or non-stationary; the end is then pulled back so it lies
      at least ``escape_margin`` (parameter units) away from that point, because a slowly
      modulated trajectory near a crisis can still escape;
    - where ``period_of`` jumps by more than ``max_period_jump`` (relative) between
      neighbors, because pitch lock would glitch there;
    - at a periodic window (bounded, stationary, not chaotic) wider than
      ``max_window_width``. Narrower windows are accepted and reported: chaotic bands of
      many systems (e.g. Rössler) are riddled with them, and inside a window the sound is
      simply periodic.

    Both ends are always chaotic points.

    Parameters
    ----------
    results
        Sweep results sorted by parameter value.
    default_value
        The system's default parameter value (must be chaotic).
    period_ref
        P_ref, used to express the Lyapunov exponent per period.
    period_of
        Characteristic period of the system at a point (method-dependent).
    drift_of
        Drift statistic of the tuning observable at a point. Only that observable is checked:
        variables such as Lorenz's x switch lobes slowly and look "drifty" over finite
        records without being non-stationary in any way that matters for the sound.
    """
    vals = np.array([r.value for r in results])

    def stationary(r: PointResult) -> bool:
        return r.bounded and drift_of(r) <= drift_threshold

    ok = [
        stationary(r) and math.isfinite(r.lyapunov) and r.lyapunov * period_ref > lyapunov_threshold
        for r in results
    ]
    start = int(np.argmin(np.abs(vals - default_value)))
    if not ok[start]:
        raise RuntimeError(f"default value {default_value} is not chaotic by the criteria")

    def walk(step: int) -> tuple[int, str, list[tuple[float, float]]]:
        last_ok = start
        windows: list[tuple[float, float]] = []
        window_start: int | None = None
        i = start
        while True:
            j = i + step
            if j < 0 or j >= len(results):
                return last_ok, "end of candidate range", windows
            r = results[j]
            if not stationary(r):
                kind = "unbounded" if not r.bounded else "non-stationary (drift)"
                # Pull back from the unsafe point by at least escape_margin.
                k = last_ok
                while k != start and abs(vals[k] - r.value) < escape_margin:
                    k -= step
                    while k != start and not ok[k]:
                        k -= step
                windows = [w for w in windows if min(w) * step <= vals[k] * step]
                return k, f"{kind} at {r.value:.6g}", windows
            jump = abs(period_of(r) / period_of(results[i]) - 1.0)
            if not np.isfinite(jump) or jump > max_period_jump:
                return last_ok, f"period jump of {100 * jump:.0f}% at {r.value:.6g}", windows
            if ok[j]:
                if window_start is not None:
                    windows.append((float(vals[window_start]), float(vals[j - step])))
                    window_start = None
                last_ok = j
            else:
                if window_start is None:
                    window_start = j
                if abs(r.value - vals[last_ok]) > max_window_width:
                    lam = r.lyapunov * period_ref
                    return last_ok, f"periodic window (λ·P={lam:.3f}) at {r.value:.6g}", windows
            i = j

    i_hi, hi_reason, w_hi = walk(+1)
    i_lo, lo_reason, w_lo = walk(-1)
    windows = tuple(sorted((min(w), max(w)) for w in w_lo + w_hi))
    return RangeSelection(
        lo=float(vals[i_lo]),
        hi=float(vals[i_hi]),
        lo_reason=lo_reason,
        hi_reason=hi_reason,
        windows=windows,
    )
