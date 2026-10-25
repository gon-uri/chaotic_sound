import math

import numpy as np
import pytest

from chaotic_sound.analysis.catalog_builder import (
    BuildSettings,
    build_system,
    choose_period_method,
    robust_period_curve,
    table_grid,
)
from chaotic_sound.analysis.spectrum import mean_return_time, measure_pitch, spectral_peak
from chaotic_sound.analysis.sweep import (
    QUICK_SETTINGS,
    PointResult,
    RangeCriteria,
    VariableStats,
    choose_default,
    select_playable_range,
)
from chaotic_sound.systems import get_system


def test_spectral_peak_of_a_sine() -> None:
    dt = 0.01
    t = np.arange(200_000) * dt
    f = 1.2345
    est = spectral_peak(np.sin(2 * np.pi * f * t), dt, nperseg=8192)
    # Parabolic interpolation on a Hann window: error well below the bin width (0.0122).
    assert est.frequency == pytest.approx(f, abs=2e-3)
    assert est.centroid_frequency == pytest.approx(f, abs=2e-3)
    assert est.centroid_period == pytest.approx(1 / est.centroid_frequency)
    assert est.prominence > 0.95


def test_spectral_peak_ignores_low_frequencies() -> None:
    dt = 0.01
    t = np.arange(100_000) * dt
    x = 5 * np.sin(2 * np.pi * 0.05 * t) + np.sin(2 * np.pi * 2.0 * t)
    assert spectral_peak(x, dt, nperseg=8192, f_min=0.5).frequency == pytest.approx(2.0, abs=5e-3)


def test_spectral_peak_never_extrapolates_below_f_min() -> None:
    # A strong low tone whose descending flank is the largest bin above f_min.
    dt = 0.01
    t = np.arange(100_000) * dt
    x = np.sin(2 * np.pi * 0.30 * t)
    f_min = 0.32
    est = spectral_peak(x, dt, nperseg=4096, f_min=f_min)
    assert est.frequency >= f_min - 0.5 / (4096 * dt)


def test_return_time_of_a_sine() -> None:
    dt = 0.013
    t = np.arange(50_000) * dt
    rt = mean_return_time(np.cos(2 * np.pi * t / 3.7), dt)
    assert rt.mean == pytest.approx(3.7, rel=1e-4)
    assert rt.std < 1e-3


@pytest.mark.parametrize("method", ["drive", "peak_centroid", "return_time"])
def test_measure_pitch_on_a_tone(method: str) -> None:
    fs = 48_000
    t = np.arange(fs * 4) / fs
    x = np.sin(2 * np.pi * 221.0 * t) + 0.3 * np.sin(2 * np.pi * 442.0 * t)
    assert measure_pitch(x, fs, method, 220.0) == pytest.approx(221.0, rel=2e-4)


def test_robust_period_curve_replaces_isolated_outliers_including_ends() -> None:
    trend = np.linspace(1.0, 0.5, 20)
    p = trend.copy()
    p[7] *= 1.4
    p[0] *= 1.3
    p[-1] *= 0.7
    curve, fixed = robust_period_curve(p, window=5, tolerance=0.05)
    assert fixed == [0, 7, 19]
    good = np.delete(np.arange(20), fixed)
    np.testing.assert_array_equal(curve[good], p[good])
    # Replaced points take a neighbour's value: within one grid step (≈ 3–5 %) of the trend.
    np.testing.assert_allclose(curve[fixed], trend[fixed], rtol=0.06)


def test_table_grid_has_exact_default_node_and_no_near_duplicates() -> None:
    g = table_grid(129, 0.123456)
    assert 0.123456 in g and g[0] == 0.0 and g[-1] == 1.0 and len(g) == 130
    assert np.all(np.diff(g) > 1e-6)
    g2 = table_grid(129, 0.5 + 1e-9)  # within 1e-6 of the uniform node 0.5: replaced
    assert len(g2) == 129 and 0.5 + 1e-9 in g2
    assert np.all(np.diff(g2) > 1e-6)


# -- range selection on synthetic sweeps ---------------------------------------------------


def point(
    value: float,
    lam: float,
    *,
    period: float = 1.0,
    bounded: bool = True,
    drift: float = 0.0,
    prominence: float = 0.5,
) -> PointResult:
    stats = VariableStats(0.0, 1.0, -1.0, 1.0, period, period, prominence, period, drift, 3.0)
    return PointResult(
        value=value,
        bounded=bounded,
        stationary=True,
        lyapunov=lam,
        variables={"x": stats} if bounded else {},
    )


def select(points, reference=5.0, **kw):
    criteria = RangeCriteria(**{"min_points": 2, **kw})
    return select_playable_range(
        points, reference, 1.0,
        lambda r: r.variables["x"].centroid_period if r.bounded else math.nan,
        lambda r: r.variables["x"].drift if r.bounded else math.inf,
        lambda r: r.variables["x"].prominence if r.bounded else 0.0,
        criteria,
    )  # fmt: skip


def test_windows_of_any_width_inside_and_periodic_tails_trimmed() -> None:
    lams = [0.0, 0.0, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0]
    pts = [point(float(v), lam) for v, lam in enumerate(lams)]
    sel = select(pts, min_chaotic_fraction=0.6)
    assert (sel.lo, sel.hi) == (2.0, 11.0)  # periodic ends trimmed, wide window kept
    assert sel.windows == ((5.0, 7.0),)
    assert sel.chaotic_fraction == pytest.approx(7 / 10)
    assert "trimmed" in sel.lo_reason and "trimmed" in sel.hi_reason
    # Asking for more chaos rejects the run.
    with pytest.raises(RuntimeError):
        select(pts, min_chaotic_fraction=0.8)


def test_escape_margin_jumps_and_musicality_cut_the_range() -> None:
    pts = [point(float(v), 0.5) for v in range(10)] + [point(10.0, math.nan, bounded=False)]
    sel = select(pts, escape_margin=2.5)
    assert sel.hi == 7.0 and "margin" in sel.hi_reason
    jumpy = [point(float(v), 0.5, period=1.0 if v < 7 else 1.5) for v in range(10)]
    assert select(jumpy).hi == 6.0
    flat = [point(float(v), 0.5, prominence=0.05 if v == 8 else 0.5) for v in range(10)]
    sel = select(flat, min_prominence=0.15)
    assert sel.hi == 7.0 and "not pitched" in sel.hi_reason


def test_drift_is_unsafe_and_reference_run_wins() -> None:
    pts = [point(float(v), 0.5, drift=0.5 if v == 4 else 0.0) for v in range(12)]
    near = select(pts, reference=8.0)
    assert (near.lo, near.hi) == (5.0, 11.0)
    far = select(pts, reference=1.0)
    assert (far.lo, far.hi) == (0.0, 3.0)
    assert select(pts, reference=4.0).hi == 11.0  # reference unsafe: widest run


def test_choose_default_avoids_window_edges() -> None:
    lams = [0.5, 0.5, 0.5, 0.5, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    pts = [point(float(v), lam) for v, lam in enumerate(lams)]
    sel = select(pts)
    i = choose_default(pts, sel, 1.0, 0.05, neighborhood=2)
    assert pts[i].value == 7.0  # the middle (5) touches the window at 4


def test_drive_method_requires_a_matching_period() -> None:
    duffing = get_system("duffing")
    drive = duffing.drive_period()
    assert drive is not None
    match = point(0.4, 0.5, period=drive * 1.005).variables
    sub = point(0.4, 0.5, period=drive * 2.0).variables
    p_match = PointResult(0.4, True, True, 0.5, match)
    p_sub = PointResult(0.4, True, True, 0.5, sub)
    assert choose_period_method(duffing, p_match, "x", 0.25) == "drive"
    assert choose_period_method(duffing, p_sub, "x", 0.25) == "peak_centroid"


@pytest.mark.slow
def test_build_system_smoke() -> None:
    settings = BuildSettings(sweep_points=41, sweep=QUICK_SETTINGS, table_points=17,
                             tables=QUICK_SETTINGS, hysteresis_points=9,
                             hysteresis=QUICK_SETTINGS)  # fmt: skip
    build = build_system(get_system("rossler"), settings)
    e = build.entry
    e.check_against(get_system("rossler"))
    assert e.p_min < e.p_default < e.p_max
    assert e.u_default in e.u_grid
    assert e.period_method == "peak_centroid" and e.default_observable == "x"
    assert e.h_max == pytest.approx(min(build.reference.period, e.period_table.min()) / 256)
    assert np.all(e.period_table > 5.0) and np.all(e.period_table < 6.5)
