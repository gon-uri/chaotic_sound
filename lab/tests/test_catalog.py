import math

import numpy as np
import pytest

from chaotic_sound.catalog import Catalog
from chaotic_sound.systems import get_system, list_systems


def test_committed_catalog_is_complete_and_sane(catalog: Catalog) -> None:
    assert set(catalog.entries) == set(list_systems())
    for name, e in catalog.entries.items():
        system = get_system(name)
        e.check_against(system)
        assert e.p_reference == system.default_value
        assert e.u_default in e.u_grid  # exact node at the default
        assert 0.3 <= e.u_default <= 0.7, name  # default near the middle (ADR 0012)
        assert np.all(e.period_table > 0)
        for table in e.observables.values():
            assert np.all(table.std > 0) and np.all(table.peak > table.std)
        # spec §4.2 step 5: h_max = min(P_ref, min P(u)) / steps_per_period
        expected = min(e.info["reference_period"], float(e.period_table.min())) / e.steps_per_period
        assert e.h_max == pytest.approx(expected)
        assert np.all(e.bounds_lo < e.initial_condition) and np.all(
            e.initial_condition < e.bounds_hi
        )
        # Pitch lock needs a smooth tuning curve; musicality needs a pitched tuning variable.
        steps = np.abs(np.diff(e.period_table) / e.period_table[:-1])
        assert steps.max() <= 0.15, name
        assert e.observables[e.period_observable].prominence.min() >= 0.15, name
        assert e.info["range_selection"]["chaotic_fraction"] >= 0.6, name


def test_forced_system_uses_the_exact_drive_period(catalog: Catalog) -> None:
    e = catalog["duffing"]
    assert e.period_method == "drive"
    drive = get_system("duffing").drive_period()
    np.testing.assert_allclose(e.period_table, drive, rtol=0, atol=0)
    assert drive == pytest.approx(2 * math.pi / 1.4)


def test_round_trip(catalog: Catalog) -> None:
    again = Catalog.from_dict(catalog.to_dict())
    for name in catalog.entries:
        a, b = catalog[name], again[name]
        np.testing.assert_array_equal(a.period_table, b.period_table)
        assert a.to_dict() == b.to_dict()


def test_interpolation(catalog: Catalog) -> None:
    e = catalog["lorenz"]
    assert e.param_value(0.0) == pytest.approx(e.p_min)
    assert e.param_value(1.0) == pytest.approx(e.p_max)
    assert e.param_value(2.0) == pytest.approx(e.p_max)  # clipped
    assert e.period(0.0) == pytest.approx(e.period_table[0])
    mid = 0.5 * (e.u_grid[3] + e.u_grid[4])
    assert e.period(mid) == pytest.approx(0.5 * (e.period_table[3] + e.period_table[4]))


def test_version_and_consistency_checks(catalog: Catalog) -> None:
    d = catalog.to_dict()
    d["catalog_version"] = 999
    with pytest.raises(ValueError, match="version"):
        Catalog.from_dict(d)
    with pytest.raises(KeyError):
        catalog["nope"]
    with pytest.raises(ValueError, match=r"does not fit|param"):
        catalog["lorenz"].check_against(get_system("rossler"))
