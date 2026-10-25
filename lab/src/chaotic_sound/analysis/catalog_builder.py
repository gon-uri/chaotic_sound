"""Build catalog entries from parameter sweeps (ADR 0003, ADR 0010, ADR 0012).

Pipeline for one system:

1. :func:`~chaotic_sound.analysis.sweep.reference_scale` measures P_ref at the dysts
   (reference) parameter value.
2. At the reference value, the most pitched audible variable (largest spectral prominence)
   becomes the *tuning observable*, and :func:`choose_period_method` decides how the
   system's characteristic period is measured on it.
3. A sweep over the system's ``candidate_range`` (continuation outward from the reference)
   feeds :func:`~chaotic_sound.analysis.sweep.select_playable_range`.
4. A hysteresis test sweeps the chosen range up and down; direction-dependent stretches are
   excluded and the selection is repeated.
5. The default parameter moves to the chaotic point nearest the middle of the range.
6. A finer, more accurate pass on a uniform u grid (plus an exact node at the default),
   by continuation outward from the default, produces the tables: the system's P(u), and
   μ(u), σ(u), π(u) of every audible variable. The selection is re-applied to this pass and
   the range shrunk if it reveals new problems.

One period per system: x, y and z of an attractor are views of the same oscillation, so the
note is set by the system's main oscillation whatever variable is heard; the choice of
variable changes the timbre, not the tuning.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from chaotic_sound import __version__
from chaotic_sound.analysis.sweep import (
    DEFAULT_SETTINGS,
    SWEEP_SETTINGS,
    AnalysisSettings,
    PointResult,
    RangeCriteria,
    RangeSelection,
    ReferenceScale,
    analyze_point,
    choose_default,
    hysteresis,
    reference_scale,
    select_playable_range,
    sweep,
)
from chaotic_sound.catalog import Catalog, CatalogEntry, ObservableTable
from chaotic_sound.systems.base import SystemDef

DYSTS_COMMIT = "2a03f1ae7b0680b0470458783dcb4664660e131a"


@dataclass(frozen=True)
class BuildSettings:
    """Settings of the catalog build. Fractions are relative to the candidate-range width."""

    sweep_points: int = 241
    sweep: AnalysisSettings = SWEEP_SETTINGS
    table_points: int = 129
    """Uniform grid size of the tables; the default value is added as an extra node."""
    tables: AnalysisSettings = DEFAULT_SETTINGS
    hysteresis_points: int = 65
    hysteresis: AnalysisSettings = SWEEP_SETTINGS
    hysteresis_std_tolerance: float = 0.10
    hysteresis_period_tolerance: float = 0.03
    lyapunov_threshold: float = 0.05
    """Minimum λ·P_ref (nats per period) to call a point chaotic."""
    max_period_jump: float = 0.15
    min_prominence: float = 0.15
    """Musicality: minimum spectral prominence of the tuning variable across the range."""
    min_chaotic_fraction: float = 0.6
    escape_margin_fraction: float = 0.03
    """Minimum distance kept from an unbounded or drifting parameter value."""
    default_neighborhood: int = 2
    """The default and this many sweep neighbors on each side must be chaotic."""
    prominence_threshold: float = 0.25
    """Below this spectral prominence the period is taken from return times (ADR 0010)."""
    drive_tolerance: float = 0.02
    """Use the drive period only if the tuning variable's measured period is this close."""
    period_outlier_tolerance: float = 0.05
    """P(u) points further than this (relative) from their running median are replaced."""
    period_median_window: int = 5
    steps_per_period: int = 256
    bounds_expansion: float = 1.0
    """Safety box = observed [min, max] widened by this many widths on each side."""
    max_refinements: int = 6


@dataclass
class SystemBuild:
    """Everything produced while building one entry (kept for plots and the report)."""

    system: SystemDef
    reference: ReferenceScale
    reference_point: PointResult
    period_method: str
    period_observable: str
    sweep_results: list[PointResult]
    hysteresis_values: list[float]
    hysteresis_flags: list[bool]
    selection: RangeSelection
    table_results: list[PointResult]
    entry: CatalogEntry
    notes: list[str]


def choose_tuning_observable(point: PointResult) -> str:
    """Pick the audible variable with the most prominent spectral peak at ``point``."""
    return max(point.variables, key=lambda v: point.variables[v].prominence)


def choose_period_method(
    system: SystemDef,
    point: PointResult,
    observable: str,
    prominence_threshold: float,
    drive_tolerance: float = 0.02,
) -> str:
    """How the system's characteristic period is measured (ADR 0010).

    Forced systems use the exact drive period, but only if the tuning variable's measured
    period is within ``drive_tolerance`` of it (some forced systems respond at a multiple of
    the drive). Otherwise, if the tuning variable's spectral peak holds at least
    ``prominence_threshold`` of its power, P is the period of the peak centroid; if not (a
    broadband spectrum), P is the mean return time between maxima.
    """
    stats = point.variables[observable]
    drive = system.drive_period()
    if drive is not None and abs(stats.centroid_period / drive - 1.0) <= drive_tolerance:
        return "drive"
    if stats.prominence >= prominence_threshold:
        return "peak_centroid"
    return "return_time"


def point_period(
    point: PointResult, variable: str, method: str, drive_period: float | None
) -> float:
    """Characteristic period at ``point`` measured on ``variable`` with ``method``."""
    if method == "drive":
        if drive_period is None:
            raise ValueError("drive method needs a drive period")
        return drive_period
    if not point.bounded:
        return math.nan
    stats = point.variables[variable]
    if method == "peak_centroid":
        return stats.centroid_period
    if method == "return_time":
        return stats.return_time
    raise ValueError(f"unknown period method {method!r}")


def robust_period_curve(
    periods: NDArray[np.float64], window: int, tolerance: float
) -> tuple[NDArray[np.float64], list[int]]:
    """Replace outliers of a measured P(u) curve by the running median of their neighbors.

    Narrow periodic windows can make a spectral estimate jump to a subharmonic at a single
    grid point (e.g. Lorenz near ρ ≈ 69.8). Pitch lock must follow the smooth loop period
    instead, so isolated points deviating more than ``tolerance`` (relative) from the running
    median of ``window`` points are replaced. At the ends the window is mirrored, so end
    points are judged by their real neighbors.

    Returns
    -------
    curve
        The corrected curve.
    corrected
        Indices of the replaced points.
    """
    from scipy.ndimage import median_filter

    median = median_filter(periods, size=window, mode="mirror")
    outlier = np.abs(periods / median - 1.0) > tolerance
    return np.where(outlier, median, periods), [int(i) for i in np.flatnonzero(outlier)]


def table_grid(n_points: int, u_default: float) -> NDArray[np.float64]:
    """Uniform grid on [0, 1] plus an exact node at ``u_default``.

    A uniform node closer than 1e-6 to the default is replaced by it (otherwise the two could
    round to the same parameter value).
    """
    uniform = np.linspace(0.0, 1.0, n_points)
    keep = np.abs(uniform - u_default) > 1e-6
    if not keep[0]:
        keep[0], u_default = True, 0.0
    if not keep[-1]:
        keep[-1], u_default = True, 1.0
    return np.unique(np.append(uniform[keep], u_default))


def _cut_period_jumps(
    selection: RangeSelection,
    p_grid: NDArray[np.float64],
    curve: NDArray[np.float64],
    p_default: float,
    max_jump: float,
) -> tuple[float, float, str, str]:
    """Shrink ``selection`` to the jump-free stretch of the smoothed P(u) around the default.

    Returns ``(lo, hi, lo_reason, hi_reason)``.
    """
    lo, hi = selection.lo, selection.hi
    why_lo, why_hi = selection.lo_reason, selection.hi_reason
    inside = np.flatnonzero((p_grid >= lo) & (p_grid <= hi))
    k_def = int(np.argmin(np.abs(p_grid - p_default)))
    for k in inside[:-1]:
        if abs(curve[k + 1] / curve[k] - 1.0) > max_jump:
            if k >= k_def and p_grid[k] < hi:
                hi, why_hi = float(p_grid[k]), f"period jump at {p_grid[k + 1]:.6g}"
            elif k < k_def and p_grid[k + 1] > lo:
                lo, why_lo = float(p_grid[k + 1]), f"period jump at {p_grid[k]:.6g}"
    return lo, hi, why_lo, why_hi


def _dysts_info(system: SystemDef) -> dict[str, Any]:
    try:
        import dysts.flows
    except ImportError:  # dysts is a dev-only dependency
        return {}
    model = getattr(dysts.flows, system.dysts_name)()
    keys = ("citation", "description", "doi", "period", "maximum_lyapunov_estimated")
    return {k: getattr(model, k, None) for k in keys}


def build_system(
    system: SystemDef,
    settings: BuildSettings | None = None,
    progress: Callable[[str], None] | None = None,
) -> SystemBuild:
    """Run the full pipeline for one system and return its catalog entry plus diagnostics."""
    settings = settings or BuildSettings()
    notes: list[str] = []

    def say(msg: str) -> None:
        notes.append(msg)
        if progress is not None:
            progress(f"[{system.name}] {msg}")

    drive = system.drive_period()
    reference = reference_scale(system, settings.sweep)
    ref_point = analyze_point(system, system.default_value, reference, settings.tables)
    observable = choose_tuning_observable(ref_point)
    method = choose_period_method(
        system, ref_point, observable, settings.prominence_threshold, settings.drive_tolerance
    )
    say(f"P_ref = {reference.period:.5g}; tuning on {observable} by {method}")

    def period_of(point: PointResult) -> float:
        return point_period(point, observable, method, drive)

    def drift_of(point: PointResult) -> float:
        return point.variables[observable].drift if point.bounded else math.inf

    def prominence_of(point: PointResult) -> float:
        return point.variables[observable].prominence if point.bounded else 0.0

    lo_c, hi_c = system.candidate_range
    criteria = RangeCriteria(
        lyapunov_threshold=settings.lyapunov_threshold,
        drift_threshold=settings.sweep.drift_threshold,
        max_period_jump=settings.max_period_jump,
        min_prominence=settings.min_prominence,
        min_chaotic_fraction=settings.min_chaotic_fraction,
        escape_margin=settings.escape_margin_fraction * (hi_c - lo_c),
    )

    def select(
        results: list[PointResult], ref_value: float, extra: Callable[[PointResult], str | None]
    ) -> RangeSelection:
        return select_playable_range(
            results, ref_value, reference.period, period_of, drift_of, prominence_of, criteria,
            extra,
        )  # fmt: skip

    # 3. Sweep the candidate range from the reference value.
    values = np.unique(
        np.append(np.linspace(lo_c, hi_c, settings.sweep_points), system.default_value)
    )
    sweep_results = sweep(system, values, reference, settings.sweep)
    hysteretic: list[tuple[float, float]] = []  # (lo, hi) stretches flagged so far

    def extra_unsafe(point: PointResult) -> str | None:
        for a, b in hysteretic:
            if a <= point.value <= b:
                return "direction-dependent (hysteresis)"
        return None

    selection = select(sweep_results, system.default_value, extra_unsafe)
    say(f"selected [{selection.lo:.5g}, {selection.hi:.5g}]")
    say(f"  low end: {selection.lo_reason}; high end: {selection.hi_reason}")

    # 4. Hysteresis test, repeated until the range is direction-independent.
    hyst_values: list[float] = []
    hyst_flags: list[bool] = []
    by_value = {r.value: r for r in sweep_results}
    for _ in range(settings.max_refinements):
        grid = np.linspace(selection.lo, selection.hi, settings.hysteresis_points)
        x_lo, x_hi = by_value[selection.lo].x_end, by_value[selection.hi].x_end
        flags = hysteresis(
            system, grid, reference, settings.hysteresis, x_lo, x_hi, observable, period_of,
            std_tolerance=settings.hysteresis_std_tolerance,
            period_tolerance=settings.hysteresis_period_tolerance,
        )  # fmt: skip
        hyst_values, hyst_flags = [float(v) for v in grid], flags
        if all(flags):
            break
        step = grid[1] - grid[0]
        bad = [float(v) for v, ok in zip(grid, flags, strict=True) if not ok]
        hysteretic.extend((v - step, v + step) for v in bad)
        say(f"hysteresis at {[round(v, 5) for v in bad]}; reselecting")
        selection = select(sweep_results, system.default_value, extra_unsafe)
        say(f"selected [{selection.lo:.5g}, {selection.hi:.5g}]")
    else:
        raise RuntimeError(f"{system.name}: the range stays direction-dependent")

    # 5. Default in the middle of the range; its state is on the attractor branch.
    i_def = choose_default(
        sweep_results, selection, reference.period, settings.lyapunov_threshold,
        settings.default_neighborhood,
    )  # fmt: skip
    p_default = float(sweep_results[i_def].value)
    x_default = sweep_results[i_def].x_end.copy()
    say(
        f"default {system.modulated_param} = {p_default:.5g} (dysts value {system.default_value:g})"
    )

    # 6. Fine tables by continuation from the default; re-select on them until stable.
    lo, hi = selection.lo, selection.hi
    for _ in range(settings.max_refinements):
        u_grid = table_grid(settings.table_points, (p_default - lo) / (hi - lo))
        p_grid = lo + u_grid * (hi - lo)
        table_results = sweep(
            system, p_grid, reference, settings.tables, start_value=p_default, start_state=x_default
        )
        measured = np.array([period_of(r) for r in table_results])
        curve, corrected = robust_period_curve(
            measured, settings.period_median_window, settings.period_outlier_tolerance
        )
        fine = select(table_results, p_default, extra_unsafe)
        new_lo, new_hi, why_lo, why_hi = _cut_period_jumps(
            fine, p_grid, curve, p_default, settings.max_period_jump
        )
        if math.isclose(new_lo, lo) and math.isclose(new_hi, hi):
            selection = RangeSelection(
                lo=lo, hi=hi, lo_reason=selection.lo_reason, hi_reason=selection.hi_reason,
                windows=fine.windows, chaotic_fraction=fine.chaotic_fraction,
            )  # fmt: skip
            break
        say(f"table pass: [{lo:.5g}, {hi:.5g}] → [{new_lo:.5g}, {new_hi:.5g}]")
        lo_reason = selection.lo_reason if math.isclose(new_lo, lo) else f"table pass: {why_lo}"
        hi_reason = selection.hi_reason if math.isclose(new_hi, hi) else f"table pass: {why_hi}"
        selection = RangeSelection(new_lo, new_hi, lo_reason, hi_reason)
        lo, hi = new_lo, new_hi
        if not lo <= p_default <= hi:
            raise RuntimeError(f"{system.name}: the table pass excluded the default")
    else:
        raise RuntimeError(f"{system.name}: the table pass did not converge")

    k_def = int(np.argmin(np.abs(p_grid - p_default)))
    x_default = table_results[k_def].x_end.copy()
    entry = _make_entry(
        system, settings, reference, method, observable, selection, u_grid, table_results,
        measured, curve, corrected, p_default, x_default, notes,
    )  # fmt: skip
    say(f"P(u) in [{entry.period_table.min():.5g}, {entry.period_table.max():.5g}]")
    return SystemBuild(
        system=system,
        reference=reference,
        reference_point=ref_point,
        period_method=method,
        period_observable=observable,
        sweep_results=sweep_results,
        hysteresis_values=hyst_values,
        hysteresis_flags=hyst_flags,
        selection=selection,
        table_results=table_results,
        entry=entry,
        notes=notes,
    )


def _make_entry(
    system: SystemDef,
    settings: BuildSettings,
    reference: ReferenceScale,
    method: str,
    observable: str,
    selection: RangeSelection,
    u_grid: NDArray[np.float64],
    results: list[PointResult],
    measured: NDArray[np.float64],
    period_table: NDArray[np.float64],
    corrected: list[int],
    p_default: float,
    x_default: NDArray[np.float64],
    notes: list[str],
) -> CatalogEntry:
    observables = {
        var: ObservableTable(
            mean=np.array([r.variables[var].mean for r in results]),
            std=np.array([r.variables[var].std for r in results]),
            peak=np.array([r.variables[var].peak for r in results]),
            prominence=np.array([r.variables[var].prominence for r in results]),
        )
        for var in system.audio_variables
    }
    h_max = min(reference.period, float(np.min(period_table))) / settings.steps_per_period

    lo = np.full(system.dim, -1.0)
    hi = np.full(system.dim, 2.0 * math.pi + 1.0)  # phase variables live in [0, 2π)
    for var in system.audio_variables:
        i = system.variable_index(var)
        vmin = min(r.variables[var].minimum for r in results)
        vmax = max(r.variables[var].maximum for r in results)
        span = vmax - vmin
        lo[i] = vmin - settings.bounds_expansion * span
        hi[i] = vmax + settings.bounds_expansion * span
    x0 = x_default.copy()
    for i in system.phase_indices:
        x0[i] = x0[i] % (2.0 * math.pi)

    lyap = [r.lyapunov for r in results]
    steps = np.abs(np.diff(period_table) / period_table[:-1])
    info: dict[str, Any] = {
        "display_name": system.display_name,
        "variables": list(system.variables),
        "audio_variables": list(system.audio_variables),
        "param_names": list(system.param_names),
        "default_params": list(system.default_params),
        "phase_indices": list(system.phase_indices),
        "equations_latex": system.equations_latex,
        "candidate_range": list(system.candidate_range),
        "reference_period": reference.period,
        "range_selection": {
            "lo_reason": selection.lo_reason,
            "hi_reason": selection.hi_reason,
            "periodic_windows": [list(w) for w in selection.windows],
            "chaotic_fraction": selection.chaotic_fraction,
        },
        "build_log": notes,
        "period_measured": measured.tolist(),
        "period_corrected_indices": corrected,
        "chaotic_fraction": float(
            np.mean([x * reference.period > settings.lyapunov_threshold for x in lyap])
        ),
        "lyapunov": lyap,
        "lyapunov_per_period": [x * reference.period for x in lyap],
        "max_relative_period_step": float(steps.max()) if steps.size else 0.0,
        "dysts": _dysts_info(system),
    }
    return CatalogEntry(
        name=system.name,
        param=system.modulated_param,
        p_min=selection.lo,
        p_max=selection.hi,
        p_default=p_default,
        p_reference=system.default_value,
        u_grid=u_grid,
        period_table=period_table,
        period_method=method,
        period_observable=observable,
        observables=observables,
        default_observable=observable,
        h_max=h_max,
        steps_per_period=settings.steps_per_period,
        bounds_lo=lo,
        bounds_hi=hi,
        initial_condition=x0,
        info=info,
    )


def build_catalog(
    systems: list[SystemDef],
    settings: BuildSettings | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[Catalog, dict[str, SystemBuild]]:
    """Build entries for ``systems`` and wrap them in a :class:`~chaotic_sound.catalog.Catalog`."""
    settings = settings or BuildSettings()
    builds = {s.name: build_system(s, settings, progress) for s in systems}
    metadata = {
        "generator": f"chaotic_sound {__version__}",
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "dysts_commit": DYSTS_COMMIT,
        "settings": asdict(settings),
    }
    catalog = Catalog(entries={k: b.entry for k, b in builds.items()}, metadata=metadata)
    return catalog, builds
