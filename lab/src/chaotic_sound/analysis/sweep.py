"""Parameter sweeps: classify the dynamics and measure the quantities the catalog needs.

At each value ``p`` of the modulated parameter we integrate the system, then record whether
the motion is bounded and stationary, its largest Lyapunov exponent, and per variable the mean,
standard deviation, extremes, spectral-peak period, prominence and return time.

Sweeps use **continuation**: the end state at one value seeds the next, moving outward from
a start value. This tracks the attractor branch that a slowly modulated box actually
follows (spec §4.2, ADR 0006). :func:`hysteresis` sweeps up and down to find stretches where
the branch depends on the direction of travel (multistability), and
:func:`select_playable_range` picks the knob range (ADR 0012).

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
    centroid_period: float
    prominence: float
    return_time: float
    drift: float
    peak: float = math.nan
    """Robust peak: 99.9th percentile of ``|x − mean|`` (for the level normalization)."""


@dataclass(frozen=True)
class PointResult:
    """Analysis of the system at one parameter value.

    ``stationary`` checks *every* audible variable; range selection uses the drift of the
    tuning variable only (see :func:`select_playable_range`).
    """

    value: float
    bounded: bool
    stationary: bool
    lyapunov: float
    """Largest Lyapunov exponent, 1/system time (NaN if unbounded)."""
    variables: dict[str, VariableStats] = field(default_factory=dict)
    x_end: NDArray[np.float64] = field(default_factory=lambda: np.empty(0), repr=False)

    def is_chaotic(self, period: float, threshold: float) -> bool:
        """Bounded with λ·P above ``threshold`` (nats per period ``period``)."""
        return self.bounded and math.isfinite(self.lyapunov) and self.lyapunov * period > threshold


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
        mean = float(s.mean())
        std = float(s.std())
        drift = float(abs(s[:half].mean() - s[half:].mean()) / std) if std > 0 else math.inf
        stationary &= drift <= settings.drift_threshold
        if std > 0:
            pk = spectral_peak(s, dt, nperseg=nperseg, f_min=f_min)
            peak_period, centroid_period, prominence = pk.period, pk.centroid_period, pk.prominence
            return_time = mean_return_time(s, dt).mean
        else:  # a fixed point: no oscillation at all
            peak_period = centroid_period = return_time = math.nan
            prominence = 0.0
        stats[name] = VariableStats(
            mean=mean,
            std=std,
            minimum=float(s.min()),
            maximum=float(s.max()),
            peak_period=peak_period,
            centroid_period=centroid_period,
            prominence=prominence,
            return_time=return_time,
            drift=drift,
            peak=float(np.percentile(np.abs(s - mean), 99.9)),
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
    """Measure P_ref and the statistics of ``system`` at its dysts (reference) parameters.

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
    mean = np.zeros(system.dim)
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


def continuation(
    system: SystemDef,
    values: Sequence[float] | NDArray[np.float64],
    reference: ReferenceScale,
    settings: AnalysisSettings,
    x0: NDArray[np.float64],
) -> list[PointResult]:
    """Analyze ``values`` in the given order, seeding each point with the previous end state.

    After an unbounded point the walk restarts from ``x0``.
    """
    results = []
    state = x0
    for value in values:
        res = analyze_point(system, float(value), reference, settings, state)
        results.append(res)
        state = res.x_end.copy() if res.bounded else x0
    return results


def sweep(
    system: SystemDef,
    values: Sequence[float] | NDArray[np.float64],
    reference: ReferenceScale,
    settings: AnalysisSettings,
    *,
    start_value: float | None = None,
    start_state: NDArray[np.float64] | None = None,
) -> list[PointResult]:
    """Analyze ``values`` (strictly increasing) by continuation outward from a start value.

    The walk starts at the value closest to ``start_value`` (default: the system's dysts
    value) from ``start_state`` (default: the system's initial condition), moves up, then
    down from the start again. Results are returned in the order of ``values``.
    """
    vals = np.asarray(values, dtype=np.float64)
    if np.any(np.diff(vals) <= 0):
        raise ValueError("values must be strictly increasing")
    center = system.default_value if start_value is None else start_value
    x0 = system.initial_state() if start_state is None else np.array(start_state)
    i0 = int(np.argmin(np.abs(vals - center)))
    up = continuation(system, vals[i0:], reference, settings, x0)
    seed = up[0].x_end.copy() if up[0].bounded else x0
    down = continuation(system, vals[:i0][::-1], reference, settings, seed)
    return down[::-1] + up


def hysteresis(
    system: SystemDef,
    values: NDArray[np.float64],
    reference: ReferenceScale,
    settings: AnalysisSettings,
    x_lo: NDArray[np.float64],
    x_hi: NDArray[np.float64],
    observable: str,
    period_of: Callable[[PointResult], float],
    *,
    std_tolerance: float = 0.10,
    period_tolerance: float = 0.03,
) -> list[bool]:
    """Sweep ``values`` up from ``x_lo`` and down from ``x_hi``; flag direction-dependent points.

    A slowly modulated box travels the knob range in both directions. Where the up and down
    sweeps land on different attractors (σ of the tuning variable differs by more than
    ``std_tolerance`` or its period by more than ``period_tolerance``, relative), pitch and
    level tables would depend on the history, so those points are flagged.

    Returns one flag per value: ``True`` = consistent in both directions.
    """
    vals = np.asarray(values, dtype=np.float64)
    up = continuation(system, vals, reference, settings, x_lo)
    down = continuation(system, vals[::-1], reference, settings, x_hi)[::-1]
    flags = []
    for a, b in zip(up, down, strict=True):
        if not (a.bounded and b.bounded):
            flags.append(False)
            continue
        sa, sb = a.variables[observable].std, b.variables[observable].std
        pa, pb = period_of(a), period_of(b)
        ok = (
            sa > 0
            and abs(sb / sa - 1.0) <= std_tolerance
            and math.isfinite(pa)
            and math.isfinite(pb)
            and abs(pb / pa - 1.0) <= period_tolerance
        )
        flags.append(ok)
    return flags


@dataclass(frozen=True)
class RangeCriteria:
    """What makes a knob range playable (ADR 0012). Widths are in parameter units."""

    lyapunov_threshold: float = 0.05
    """λ·P_ref (nats per period) above which a point counts as chaotic."""
    drift_threshold: float = 0.2
    max_period_jump: float = 0.15
    min_prominence: float = 0.15
    """Musicality: the tuning variable's spectral prominence at every point (0 disables)."""
    min_chaotic_fraction: float = 0.6
    escape_margin: float = 0.0
    min_points: int = 5


@dataclass(frozen=True)
class RangeSelection:
    """Knob range chosen from a sweep.

    ``lo_reason`` / ``hi_reason`` explain why each end stopped; ``windows`` lists the
    periodic (non-chaotic) stretches ``(start, end)`` inside the range.
    """

    lo: float
    hi: float
    lo_reason: str
    hi_reason: str
    windows: tuple[tuple[float, float], ...] = ()
    chaotic_fraction: float = 1.0


def select_playable_range(
    results: Sequence[PointResult],
    reference_value: float,
    period_ref: float,
    period_of: Callable[[PointResult], float],
    drift_of: Callable[[PointResult], float],
    prominence_of: Callable[[PointResult], float],
    criteria: RangeCriteria,
    extra_unsafe: Callable[[PointResult], str | None] | None = None,
) -> RangeSelection:
    """Pick the knob range: stable and musical first, chaos present (ADR 0012).

    1. A point is **unsafe** if it is unbounded, drifts, has no defined period, is not
       pitched enough (prominence below ``min_prominence``), or ``extra_unsafe`` says so
       (e.g. hysteresis). Points within ``escape_margin`` of an unbounded or drifting value
       are unsafe too.
    2. Between neighbors where the period jumps by more than ``max_period_jump`` the range
       is cut (pitch lock would glitch).
    3. Each remaining run of safe points is trimmed so that both ends are chaotic; it
       qualifies if at least ``min_chaotic_fraction`` of its points are chaotic and it has
       ``min_points`` points. Periodic windows of any width may lie inside.
    4. The run containing ``reference_value`` wins; otherwise the widest one.
    """
    vals = np.array([r.value for r in results])
    n = len(results)
    chaotic = [r.is_chaotic(period_ref, criteria.lyapunov_threshold) for r in results]

    reason: list[str | None] = []
    for r in results:
        if not r.bounded:
            reason.append("unbounded")
        elif drift_of(r) > criteria.drift_threshold:
            reason.append("drifting (non-stationary)")
        elif not math.isfinite(period_of(r)):
            reason.append("no defined period")
        elif prominence_of(r) < criteria.min_prominence:
            reason.append(f"not pitched (prominence {prominence_of(r):.2f})")
        elif extra_unsafe is not None and (extra := extra_unsafe(r)) is not None:
            reason.append(extra)
        else:
            reason.append(None)
    hard = [i for i, x in enumerate(reason) if x in ("unbounded", "drifting (non-stationary)")]
    for i in range(n):
        if reason[i] is None:
            near = [k for k in hard if abs(vals[k] - vals[i]) < criteria.escape_margin]
            if near:
                reason[i] = (
                    f"within the safety margin of the {reason[near[0]]} value {vals[near[0]]:.6g}"
                )

    def boundary(i: int, j: int) -> str | None:
        """Why the step from i to its neighbor j may not be crossed (None = it may)."""
        if reason[j] is not None:
            return f"{reason[j]} at {vals[j]:.6g}"
        jump = abs(period_of(results[j]) / period_of(results[i]) - 1.0)
        if jump > criteria.max_period_jump:
            return f"period jump of {100 * jump:.0f}% at {vals[j]:.6g}"
        return None

    runs: list[tuple[int, int, str, str]] = []
    i = 0
    while i < n:
        if reason[i] is not None:
            i += 1
            continue
        start = i
        lo_why = "end of candidate range" if start == 0 else (boundary(start, start - 1) or "")
        while i + 1 < n and boundary(i, i + 1) is None:
            i += 1
        hi_why = "end of candidate range" if i == n - 1 else (boundary(i, i + 1) or "")
        runs.append((start, i, lo_why, hi_why))
        i += 1

    candidates = []
    for a, b, lo_why, hi_why in runs:
        idx = [k for k in range(a, b + 1) if chaotic[k]]
        if not idx:
            continue
        lo_i, hi_i = idx[0], idx[-1]
        count = hi_i - lo_i + 1
        frac = sum(chaotic[lo_i : hi_i + 1]) / count
        if count < criteria.min_points or frac < criteria.min_chaotic_fraction:
            continue
        lo_r = lo_why if lo_i == a else f"periodic below (trimmed to chaotic end; {lo_why})"
        hi_r = hi_why if hi_i == b else f"periodic above (trimmed to chaotic end; {hi_why})"
        candidates.append((lo_i, hi_i, lo_r, hi_r, frac))
    if not candidates:
        raise RuntimeError("no playable range: no run of safe points is chaotic enough")

    def contains_ref(c: tuple[int, int, str, str, float]) -> bool:
        return bool(vals[c[0]] <= reference_value <= vals[c[1]])

    with_ref = [c for c in candidates if contains_ref(c)]
    best = with_ref[0] if with_ref else max(candidates, key=lambda c: vals[c[1]] - vals[c[0]])
    lo_i, hi_i, lo_r, hi_r, frac = best

    windows: list[tuple[float, float]] = []
    k = lo_i
    while k <= hi_i:
        if not chaotic[k]:
            w0 = k
            while k + 1 <= hi_i and not chaotic[k + 1]:
                k += 1
            windows.append((float(vals[w0]), float(vals[k])))
        k += 1
    return RangeSelection(
        lo=float(vals[lo_i]),
        hi=float(vals[hi_i]),
        lo_reason=lo_r,
        hi_reason=hi_r,
        windows=tuple(windows),
        chaotic_fraction=float(frac),
    )


def choose_default(
    results: Sequence[PointResult],
    selection: RangeSelection,
    period_ref: float,
    lyapunov_threshold: float,
    neighborhood: int = 2,
) -> int:
    """Index of the default parameter: the chaotic point nearest the middle of the range.

    The point and its ``neighborhood`` neighbors on each side must be chaotic, so the
    default never sits at the edge of a periodic window. Falls back to any chaotic point.
    """
    vals = np.array([r.value for r in results])
    inside = [i for i, v in enumerate(vals) if selection.lo <= v <= selection.hi]
    chaotic = {i for i in inside if results[i].is_chaotic(period_ref, lyapunov_threshold)}
    good = [
        i for i in chaotic
        if all(k in chaotic for k in range(i - neighborhood, i + neighborhood + 1))
    ]  # fmt: skip
    pool = good or sorted(chaotic)
    if not pool:
        raise RuntimeError("the selected range has no chaotic point")
    middle = 0.5 * (selection.lo + selection.hi)
    return min(pool, key=lambda i: abs(vals[i] - middle))
