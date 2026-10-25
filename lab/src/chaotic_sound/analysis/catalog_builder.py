"""Build catalog entries from parameter sweeps (ADR 0003, ADR 0010).

Pipeline for one system:

1. :func:`~chaotic_sound.analysis.sweep.reference_scale` measures P_ref at the default.
2. At the default parameter, the most pitched audible variable (largest spectral prominence)
   becomes the *tuning observable*, and :func:`choose_period_method` decides how the
   system's characteristic period is measured on it.
3. A sweep over the system's ``candidate_range`` feeds
   :func:`~chaotic_sound.analysis.sweep.select_chaotic_range`.
4. A more accurate pass on a uniform u grid over the chosen range produces the tables:
   the system's P(u), and μ(u), σ(u) of every audible variable.

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
    RangeSelection,
    ReferenceScale,
    analyze_point,
    reference_scale,
    select_chaotic_range,
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
    table_points: int = 33
    tables: AnalysisSettings = DEFAULT_SETTINGS
    lyapunov_threshold: float = 0.05
    """Minimum λ·P_ref (nats per period) to call a point chaotic."""
    max_period_jump: float = 0.15
    max_window_fraction: float = 0.03
    """Widest periodic window accepted inside the range."""
    period_outlier_tolerance: float = 0.05
    """P(u) points further than this (relative) from their running median are replaced."""
    period_median_window: int = 5
    escape_margin_fraction: float = 0.03
    """Minimum distance kept from an unbounded or drifting parameter value."""
    prominence_threshold: float = 0.25
    """Below this spectral prominence the period is taken from return times (ADR 0010)."""
    steps_per_period: int = 256
    bounds_expansion: float = 1.0
    """Safety box = observed [min, max] widened by this many widths on each side."""


@dataclass
class SystemBuild:
    """Everything produced while building one entry (kept for plots and the report)."""

    system: SystemDef
    reference: ReferenceScale
    default_point: PointResult
    period_method: str
    period_observable: str
    sweep_results: list[PointResult]
    selection: RangeSelection
    table_results: list[PointResult]
    entry: CatalogEntry


def choose_tuning_observable(default_point: PointResult) -> str:
    """Pick the audible variable with the most prominent spectral peak at the default."""
    return max(default_point.variables, key=lambda v: default_point.variables[v].prominence)


def choose_period_method(
    system: SystemDef, default_point: PointResult, observable: str, prominence_threshold: float
) -> str:
    """How the system's characteristic period is measured (ADR 0010).

    Forced systems use the exact drive period. Otherwise, if the tuning observable's spectral
    peak holds at least ``prominence_threshold`` of its power, P is the peak period; if not
    (a broadband spectrum, e.g. Thomas), P is the mean return time between maxima.
    """
    if system.drive_period() is not None:
        return "drive"
    if default_point.variables[observable].prominence >= prominence_threshold:
        return "spectral_peak"
    return "return_time"


def point_period(
    point: PointResult, variable: str, method: str, drive_period: float | None
) -> float:
    """Characteristic period at ``point`` measured on ``variable`` with ``method``."""
    if method == "drive":
        if drive_period is None:
            raise ValueError("drive method needs a drive period")
        return drive_period
    stats = point.variables[variable]
    if method == "spectral_peak":
        return stats.peak_period
    if method == "return_time":
        return stats.return_time
    raise ValueError(f"unknown period method {method!r}")


def robust_period_curve(
    periods: NDArray[np.float64], window: int, tolerance: float
) -> tuple[NDArray[np.float64], list[int]]:
    """Replace outliers of a measured P(u) curve by the running median of their neighbors.

    Narrow periodic windows can make a spectral-peak estimate jump to a subharmonic at a
    single grid point (e.g. Lorenz near ρ ≈ 69.8). Pitch lock must follow the smooth loop
    period instead, so isolated points deviating more than ``tolerance`` (relative) from the
    running median of ``window`` points are replaced.

    Returns
    -------
    curve
        The corrected curve.
    corrected
        Indices of the replaced points.
    """
    from scipy.ndimage import median_filter

    median = median_filter(periods, size=window, mode="nearest")
    outlier = np.abs(periods / median - 1.0) > tolerance
    return np.where(outlier, median, periods), [int(i) for i in np.flatnonzero(outlier)]


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

    def say(msg: str) -> None:
        if progress is not None:
            progress(f"[{system.name}] {msg}")

    drive = system.drive_period()
    reference = reference_scale(system, settings.sweep)
    default_point = analyze_point(system, system.default_value, reference, settings.tables)
    observable = choose_tuning_observable(default_point)
    method = choose_period_method(system, default_point, observable, settings.prominence_threshold)
    say(f"P_ref = {reference.period:.5g}; tuning on {observable} by {method}")

    def period_of(point: PointResult) -> float:
        return point_period(point, observable, method, drive)

    def drift_of(point: PointResult) -> float:
        return point.variables[observable].drift if point.bounded else math.inf

    lo_c, hi_c = system.candidate_range
    width = hi_c - lo_c
    values = np.unique(
        np.append(np.linspace(lo_c, hi_c, settings.sweep_points), system.default_value)
    )
    sweep_results = sweep(system, values, reference, settings.sweep)
    selection = select_chaotic_range(
        sweep_results,
        system.default_value,
        reference.period,
        period_of,
        drift_of,
        drift_threshold=settings.sweep.drift_threshold,
        lyapunov_threshold=settings.lyapunov_threshold,
        max_period_jump=settings.max_period_jump,
        max_window_width=settings.max_window_fraction * width,
        escape_margin=settings.escape_margin_fraction * width,
    )
    say(
        f"range [{selection.lo:.5g}, {selection.hi:.5g}] "
        f"(low end: {selection.lo_reason}; high end: {selection.hi_reason})"
    )
    if not selection.hi > selection.lo:
        raise RuntimeError(f"{system.name}: the selected range is empty")

    lo, hi = selection.lo, selection.hi
    trims: list[str] = []
    for _ in range(4):
        u_grid = np.linspace(0.0, 1.0, settings.table_points)
        p_grid = lo + u_grid * (hi - lo)
        table_results = sweep(system, p_grid, reference, settings.tables)
        bad = [r.value for r in table_results if drift_of(r) > settings.tables.drift_threshold]
        if bad:
            raise RuntimeError(f"{system.name}: unsafe points inside the selected range: {bad}")
        measured = np.array([period_of(r) for r in table_results])
        curve, corrected = robust_period_curve(
            measured, settings.period_median_window, settings.period_outlier_tolerance
        )
        steps = np.abs(np.diff(curve) / curve[:-1])
        jumps = np.flatnonzero(steps > settings.max_period_jump)
        if jumps.size == 0:
            break
        # Trim at the jumps closest to the default on each side, then recompute.
        i_def = int(np.argmin(np.abs(p_grid - system.default_value)))
        above = [int(k) for k in jumps if k >= i_def]
        below = [int(k) for k in jumps if k < i_def]
        new_lo = float(p_grid[max(below) + 1]) if below else lo
        new_hi = float(p_grid[min(above)]) if above else hi
        trims.append(
            f"P(u) step of {100 * steps.max():.0f}%: [{lo:.5g}, {hi:.5g}] → "
            f"[{new_lo:.5g}, {new_hi:.5g}]"
        )
        say(trims[-1])
        lo, hi = new_lo, new_hi
    else:
        raise RuntimeError(f"{system.name}: P(u) still jumps after trimming the range")
    selection = RangeSelection(
        lo=lo,
        hi=hi,
        lo_reason=selection.lo_reason if lo == selection.lo else "trimmed: P(u) jump",
        hi_reason=selection.hi_reason if hi == selection.hi else "trimmed: P(u) jump",
        windows=tuple(w for w in selection.windows if lo <= w[0] and w[1] <= hi),
    )

    entry = _make_entry(
        system, settings, reference, method, observable, selection, u_grid, table_results,
        measured, curve, corrected, trims,
    )  # fmt: skip
    say(f"P(u) in [{entry.period_table.min():.5g}, {entry.period_table.max():.5g}]")
    return SystemBuild(
        system=system,
        reference=reference,
        default_point=default_point,
        period_method=method,
        period_observable=observable,
        sweep_results=sweep_results,
        selection=selection,
        table_results=table_results,
        entry=entry,
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
    trims: list[str],
) -> CatalogEntry:
    observables = {
        var: ObservableTable(
            mean=np.array([r.variables[var].mean for r in results]),
            std=np.array([r.variables[var].std for r in results]),
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

    lyap = [r.lyapunov for r in results]
    chaotic_fraction = float(
        np.mean([x * reference.period > settings.lyapunov_threshold for x in lyap])
    )
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
            "accepted_windows": [list(w) for w in selection.windows],
            "trims": trims,
        },
        "period_measured": measured.tolist(),
        "period_corrected_indices": corrected,
        "chaotic_fraction": chaotic_fraction,
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
        p_default=system.default_value,
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
        initial_condition=system.initial_state(),
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
