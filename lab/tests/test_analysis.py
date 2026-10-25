import math

import numpy as np
import pytest

from chaotic_sound.analysis.catalog_builder import robust_period_curve
from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.analysis.sweep import PointResult, VariableStats, select_chaotic_range


def test_spectral_peak_of_a_sine() -> None:
    dt = 0.01
    t = np.arange(200_000) * dt
    f = 1.2345
    est = spectral_peak(np.sin(2 * np.pi * f * t), dt, nperseg=8192)
    # Parabolic interpolation on a Hann window: error well below the bin width (0.0122).
    assert est.frequency == pytest.approx(f, abs=2e-3)
    # The centroid of a symmetric peak sits on the peak too.
    assert est.centroid_frequency == pytest.approx(f, abs=2e-3)
    assert est.centroid_period == pytest.approx(1 / est.centroid_frequency)
    assert est.prominence > 0.95


def test_spectral_peak_ignores_low_frequencies() -> None:
    dt = 0.01
    t = np.arange(100_000) * dt
    x = 5 * np.sin(2 * np.pi * 0.05 * t) + np.sin(2 * np.pi * 2.0 * t)
    assert spectral_peak(x, dt, nperseg=8192, f_min=0.5).frequency == pytest.approx(2.0, abs=5e-3)


def test_return_time_of_a_sine() -> None:
    dt = 0.013
    t = np.arange(50_000) * dt
    rt = mean_return_time(np.cos(2 * np.pi * t / 3.7), dt)
    assert rt.mean == pytest.approx(3.7, rel=1e-4)
    assert rt.std < 1e-3


def test_robust_period_curve_replaces_isolated_outliers() -> None:
    p = np.linspace(1.0, 0.5, 20)
    p[7] *= 1.4
    curve, fixed = robust_period_curve(p, window=5, tolerance=0.05)
    assert fixed == [7]
    assert curve[7] == pytest.approx(np.median(p[5:10]))
    np.testing.assert_array_equal(np.delete(curve, 7), np.delete(p, 7))


def point(
    value: float, lam: float, period: float = 1.0, bounded: bool = True, drift: float = 0.0
) -> PointResult:
    stats = VariableStats(0.0, 1.0, -1.0, 1.0, period, period, 0.5, period, drift)
    return PointResult(
        value=value,
        bounded=bounded,
        stationary=True,
        lyapunov=lam,
        variables={"x": stats} if bounded else {},
    )


def select(points, **kw):
    return select_chaotic_range(
        points,
        5.0,
        1.0,
        lambda r: r.variables["x"].peak_period,
        lambda r: r.variables["x"].drift if r.bounded else math.inf,
        **kw,
    )


def test_range_stops_at_wide_window_and_accepts_narrow_one() -> None:
    lams = {1: 0.0, 2: 0.0, 3: 0.5, 4: 0.5, 5: 0.5, 6: 0.0, 7: 0.5, 8: 0.5, 9: 0.0, 10: 0.0}
    pts = [point(float(v), lam) for v, lam in lams.items()]
    sel = select(pts, max_window_width=1.5)
    assert (sel.lo, sel.hi) == (3.0, 8.0)
    assert sel.windows == ((6.0, 6.0),)
    strict = select(pts, max_window_width=0.0)
    assert (strict.lo, strict.hi) == (3.0, 5.0)


def test_range_keeps_margin_from_escape_and_stops_at_jumps() -> None:
    pts = [point(float(v), 0.5) for v in range(1, 10)] + [point(10.0, math.nan, bounded=False)]
    sel = select(pts, escape_margin=2.5)
    assert sel.hi == 7.0 and "unbounded" in sel.hi_reason
    jumpy = [point(float(v), 0.5, period=1.0 if v < 7 else 1.5) for v in range(1, 10)]
    assert select(jumpy).hi == 6.0


def test_default_must_be_chaotic() -> None:
    with pytest.raises(RuntimeError):
        select([point(4.0, 0.5), point(5.0, 0.0), point(6.0, 0.5)])
