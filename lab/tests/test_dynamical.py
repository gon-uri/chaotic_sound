"""Dynamical block: tuning accuracy, loudness, pitch lock, determinism, chunking."""

import numpy as np
import pytest

from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import Catalog
from chaotic_sound.pitch import cents_between
from chaotic_sound.systems import list_systems

FS = 48_000


def run(block: Dynamical, seconds: float, chunk: int = 512, inputs=None) -> np.ndarray:
    block.reset(FS)
    n = round(seconds * FS)
    out = np.empty((n, 2))
    pos = 0
    while pos < n:
        m = min(chunk, n - pos)
        ins = {} if inputs is None else {k: v[pos : pos + m] for k, v in inputs.items()}
        out[pos : pos + m] = block.process(m, ins)["out"]
        pos += m
    return out


def measured_frequency(block: Dynamical, x: np.ndarray) -> float:
    """Frequency the catalog's period method would measure on the rendered audio."""
    if block.entry.period_method == "return_time":
        return 1.0 / mean_return_time(x, 1.0 / FS).mean
    peak = spectral_peak(x, 1.0 / FS, nperseg=2**16, f_min=0.25 * block.frequency_hz)
    return peak.centroid_frequency


# Intrinsic spread of the pitch estimate over 2000 cycles (lab measurement, see
# docs/math/tuning.md): Rössler/Duffing < 1 cent, Lorenz/Chua ≈ 3 cents. Thomas is different:
# its pitch depends on the realization (−9 … +34 cents across seeds at the same note), so its
# tolerance reflects that spread rather than estimator noise.
TOLERANCE_CENTS = {"rossler": 5, "duffing": 5, "lorenz": 12, "chua": 12, "thomas": 35}


@pytest.mark.slow
@pytest.mark.parametrize("system", list_systems())
@pytest.mark.parametrize("note", ["A2", "A3", "A4"])
def test_tuned_to_the_note(catalog: Catalog, system: str, note: str) -> None:
    block = Dynamical("osc", catalog=catalog, system=system, note=note)
    seconds = 0.5 + 2000 / block.frequency_hz  # ≥ 2000 cycles, like the catalog analysis
    x = run(block, seconds)[FS // 2 :, 0]
    cents = cents_between(measured_frequency(block, x), block.frequency_hz)
    assert abs(cents) < TOLERANCE_CENTS[system], f"{system} {note}: {cents:+.1f} cents"
    assert block.resets == 0


@pytest.mark.parametrize("system", list_systems())
def test_loudness_is_normalized(catalog: Catalog, system: str) -> None:
    x = run(Dynamical("osc", catalog=catalog, system=system), 2.0)[FS // 4 :, 0]
    assert np.std(x) == pytest.approx(0.25, rel=0.1)
    assert abs(np.mean(x)) < 0.02
    assert np.max(np.abs(x)) < 1.0


def test_amp_scales_and_fades_in(catalog: Catalog) -> None:
    full = run(Dynamical("osc", catalog=catalog, amp=1.0), 0.5)
    half = run(Dynamical("osc", catalog=catalog, amp=0.5), 0.5)
    np.testing.assert_allclose(half[FS // 10 :], 0.5 * full[FS // 10 :], rtol=1e-6, atol=1e-9)
    # The amp smoother starts at 0, so the first samples are (almost) silent.
    assert np.max(np.abs(full[:10])) < 0.02


def test_chunking_does_not_change_output(catalog: Catalog) -> None:
    u = np.linspace(0, 1, FS // 2)
    a = 0.5 + 0.5 * np.sin(np.linspace(0, 20, FS // 2))
    block = Dynamical("osc", catalog=catalog, system="lorenz")
    whole = run(block, 0.5, chunk=FS, inputs={"param": u, "amp": a})
    parts = run(block, 0.5, chunk=129, inputs={"param": u, "amp": a})
    np.testing.assert_array_equal(whole, parts)


def test_deterministic_and_seeded(catalog: Catalog) -> None:
    a = run(Dynamical("one", catalog=catalog), 1.0)
    b = run(Dynamical("one", catalog=catalog), 1.0)
    c = run(Dynamical("two", catalog=catalog), 1.0)
    d = run(Dynamical("two", catalog=catalog, seed=Dynamical("one", catalog=catalog).seed), 1.0)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(a, d)
    # Same system and note, different seed: identical at first, then chaos separates them.
    assert np.max(np.abs(a[:200] - c[:200])) < 1e-3
    assert np.max(np.abs(a[-FS // 10 :] - c[-FS // 10 :])) > 0.1


@pytest.mark.slow
def test_pitch_lock_keeps_the_note_while_the_parameter_moves(catalog: Catalog) -> None:
    # Lorenz: P(u) changes by almost an octave across the range.
    for u in (0.1, 0.9):
        locked = Dynamical("osc", catalog=catalog, system="lorenz", note="A3", param=u)
        free = Dynamical(
            "osc", catalog=catalog, system="lorenz", note="A3", param=u, pitch_lock=False
        )
        f_locked = measured_frequency(locked, run(locked, 6.0)[FS // 2 :, 0])
        f_free = measured_frequency(free, run(free, 6.0)[FS // 2 :, 0])
        entry = locked.entry
        expected_ratio = float(entry.period(entry.u_default) / entry.period(u))
        assert abs(cents_between(f_locked, 220.0)) < TOLERANCE_CENTS["lorenz"]
        assert f_free / 220.0 == pytest.approx(expected_ratio, rel=0.02)


def test_stereo_uses_two_variables(catalog: Catalog) -> None:
    x = run(
        Dynamical("osc", catalog=catalog, system="rossler", observable="x", observable_right="y"),
        0.5,
    )
    assert not np.allclose(x[:, 0], x[:, 1])
    mono = run(Dynamical("osc", catalog=catalog, system="rossler"), 0.5)
    np.testing.assert_array_equal(mono[:, 0], mono[:, 1])


def test_cents_shift_the_pitch(catalog: Catalog) -> None:
    block = Dynamical("osc", catalog=catalog, note="A4", cents=50)
    assert block.frequency_hz == pytest.approx(440 * 2 ** (50 / 1200))


@pytest.mark.parametrize(
    "params",
    [
        {"system": "nope"},
        {"note": "H2"},
        {"cents": 150},
        {"param": 1.5},
        {"amp": -0.1},
        {"observable": "w"},
        {"system": "duffing", "observable": "z"},
        {"volume": 1.0},
    ],
)
def test_invalid_params(catalog: Catalog, params: dict) -> None:
    with pytest.raises(ValueError):
        Dynamical("osc", catalog=catalog, **params)
