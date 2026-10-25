"""Our system definitions must match dysts exactly (ADR 0007)."""

import numpy as np
import pytest

from chaotic_sound.systems import SYSTEMS, get_system, list_systems

dysts_flows = pytest.importorskip("dysts.flows")


@pytest.mark.parametrize("name", list_systems())
def test_defaults_match_dysts(name: str) -> None:
    system = get_system(name)
    ref = getattr(dysts_flows, system.dysts_name)()
    assert set(ref.params) == set(system.param_names)
    for pname, value in zip(system.param_names, system.default_params, strict=True):
        assert value == pytest.approx(ref.params[pname], rel=0, abs=0), pname
    np.testing.assert_array_equal(system.initial_state(), np.asarray(ref.ic, dtype=float))


@pytest.mark.parametrize("name", list_systems())
def test_rhs_matches_dysts(name: str) -> None:
    system = get_system(name)
    ref = getattr(dysts_flows, system.dysts_name)()
    rng = np.random.default_rng(1234)
    p = system.params_array()
    out = np.empty(system.dim)
    scale = np.maximum(np.abs(system.initial_state()), 1.0)
    for _ in range(50):
        x = system.initial_state() + scale * rng.normal(size=system.dim)
        system.rhs(x, p, out)
        expected = np.asarray(ref.rhs(x, 0.0), dtype=float)
        # Same formula in float64: only reassociation round-off can differ.
        np.testing.assert_allclose(out, expected, rtol=1e-12, atol=1e-12)


def test_registry() -> None:
    assert list_systems() == ["lorenz", "rossler", "chua", "thomas", "duffing"]
    assert set(SYSTEMS) == set(list_systems())
    with pytest.raises(KeyError):
        get_system("nope")


def test_systemdef_helpers() -> None:
    lorenz = get_system("lorenz")
    assert lorenz.modulated_index == 1
    assert lorenz.default_value == 28.0
    np.testing.assert_array_equal(lorenz.params_array(rho=35), [10.0, 35.0, 2.667])
    with pytest.raises(KeyError):
        lorenz.params_array(nope=1.0)
    duffing = get_system("duffing")
    assert duffing.audio_variables == ("x", "y")
    assert duffing.drive_period() == pytest.approx(2 * np.pi / 1.4)
    assert lorenz.drive_period() is None


@pytest.mark.parametrize("name", list_systems())
def test_period_hint_is_dysts_period(name: str) -> None:
    system = get_system(name)
    ref = getattr(dysts_flows, system.dysts_name)()
    assert system.period_hint == pytest.approx(ref.period, rel=1e-4)
