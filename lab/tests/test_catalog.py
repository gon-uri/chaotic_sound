import numpy as np
import pytest

from chaotic_sound.catalog import Catalog
from chaotic_sound.systems import get_system, list_systems


def test_committed_catalog_is_complete_and_sane(catalog: Catalog) -> None:
    assert set(catalog.entries) == set(list_systems())
    for name, e in catalog.entries.items():
        system = get_system(name)
        assert e.param == system.modulated_param
        assert e.p_min < e.p_max
        assert e.p_min <= e.p_default <= e.p_max, name
        assert 0.0 <= e.u_default <= 1.0
        assert np.all(np.diff(e.u_grid) > 0) and e.u_grid[0] == 0 and e.u_grid[-1] == 1
        assert np.all(e.period_table > 0)
        assert e.default_observable in system.audio_variables
        assert set(e.observables) == set(system.audio_variables)
        for table in e.observables.values():
            assert np.all(table.std > 0)
        assert e.h_max > 0
        assert np.all(e.bounds_lo < e.initial_condition) and np.all(
            e.initial_condition < e.bounds_hi
        )
        # Pitch lock needs a smooth tuning curve (ADR 0010).
        steps = np.abs(np.diff(e.period_table) / e.period_table[:-1])
        assert steps.max() <= 0.15, name


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


def test_version_check(catalog: Catalog) -> None:
    d = catalog.to_dict()
    d["catalog_version"] = 999
    with pytest.raises(ValueError, match="version"):
        Catalog.from_dict(d)
    with pytest.raises(KeyError):
        catalog["nope"]
