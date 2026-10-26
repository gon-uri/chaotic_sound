"""Dynamical block: tuning, loudness, amp curve, pitch input, slew, seeding, chunking."""

import math

import numpy as np
import pytest

from chaotic_sound.analysis.spectrum import measure_pitch
from chaotic_sound.blocks import BlockContext, Dynamical
from chaotic_sound.blocks.dynamical import AMP_EXPONENT, IC_PERTURBATION, PEAK_TARGET, RMS_TARGET
from chaotic_sound.pitch import cents_between, note_to_hz
from chaotic_sound.rng import stable_seed
from chaotic_sound.systems import list_systems

FS = 48_000


def run(block: Dynamical, seconds: float, chunk: int = 512, inputs=None, fs: int = FS):
    block.reset(fs)
    n = round(seconds * fs)
    out = np.empty((n, 2))
    pos = 0
    while pos < n:
        m = min(chunk, n - pos)
        ins = {} if inputs is None else {k: v[pos : pos + m] for k, v in inputs.items()}
        out[pos : pos + m] = block.process(m, ins)["out"]
        pos += m
    return out


def pitch_cents(block: Dynamical, x: np.ndarray, fs: int = FS, target: float | None = None):
    f0 = block.frequency_hz if target is None else target
    return cents_between(measure_pitch(x, fs, block.entry.period_method, f0), f0)


# Measured over 6 seeds × A2/A3/A4 at 44.1 and 48 kHz (docs/math/tuning.md §6): the bias is
# below 3.5 cents and single renders stay within 8 cents. Tolerances: bias ≈ 1.5× the worst
# measured mean, single render ≈ 1.5× the worst measured value. A uniform detune of
# 4 cents fails Rössler/Duffing/Lorenz.
BIAS_CENTS = {"rossler": 1.0, "duffing": 1.0, "lorenz": 2.5, "chua": 5.0, "rikitake": 5.0}
SINGLE_CENTS = {"rossler": 2.0, "duffing": 2.0, "lorenz": 5.0, "chua": 11.0, "rikitake": 12.0}


def seeds_cents(
    context, system: str, note: str, fs: int, n_seeds: int = 4, tonality: float = 0.0
) -> list[float]:
    """Pitch error per seed. tonality=0 by default: this measures the catalog's tuning of the
    raw signal (time rescaling); the tonality mix has its own test (test_tonality.py)."""
    result = []
    for seed in range(n_seeds):
        block = Dynamical(
            "osc", context=context, system=system, note=note, seed=seed, tonality=tonality
        )
        seconds = 0.5 + 2000 / block.frequency_hz  # ≥ 2000 cycles, like the catalog analysis
        result.append(pitch_cents(block, run(block, seconds, chunk=8192, fs=fs)[fs // 2 :, 0], fs))
    return result


@pytest.mark.slow
@pytest.mark.parametrize("system", list_systems())
@pytest.mark.parametrize(
    ("note", "fs"), [("A2", 48_000), ("A3", 48_000), ("A4", 48_000), ("A3", 44_100), ("A3", 96_000)]
)
def test_tuned_to_the_note(context: BlockContext, system: str, note: str, fs: int) -> None:
    cents = seeds_cents(context, system, note, fs)
    assert abs(float(np.mean(cents))) < BIAS_CENTS[system], cents
    assert max(abs(c) for c in cents) < SINGLE_CENTS[system], cents


@pytest.mark.parametrize("system", list_systems())
@pytest.mark.parametrize("u", [0.0, 0.5, 1.0])
def test_loudness_is_normalized_across_the_range(
    context: BlockContext, system: str, u: float
) -> None:
    for obs in Dynamical("probe", context=context, system=system).system.audio_variables:
        # tonality=0: this checks the level normalization of the raw signal (spec §4.2 step 7);
        # the tonality mix is tested in test_tonality.py.
        block = Dynamical(
            "osc", context=context, system=system, param=u, observable=obs, tonality=0.0
        )
        x = run(block, 1.5)[FS // 4 :, 0]
        e = block.entry
        expected = min(RMS_TARGET, PEAK_TARGET * float(e.std(obs, u) / e.peak(obs, u)))
        # Chaotic statistics over ~1 s (≥ 100 cycles at A3) fluctuate by a few percent.
        assert np.std(x) == pytest.approx(expected, rel=0.15), (system, obs)
        assert np.std(x) <= RMS_TARGET * 1.15
        assert abs(np.mean(x)) < 0.05


def test_perceptual_and_linear_amp_curves(context: BlockContext) -> None:
    full = run(Dynamical("osc", context=context, amp=1.0), 0.5)[FS // 10 :]
    half = run(Dynamical("osc", context=context, amp=0.5), 0.5)[FS // 10 :]
    lin_full = run(Dynamical("osc", context=context, amp=1.0, amp_curve="linear"), 0.5)[FS // 10 :]
    lin = run(Dynamical("osc", context=context, amp=0.5, amp_curve="linear"), 0.5)[FS // 10 :]
    # Perceptual: halving the knob is −10 dB (half as loud); linear: −6 dB. (Compare each curve
    # with itself: the fade-in differs between curves and the DC blocker remembers it.)
    np.testing.assert_allclose(half, 0.5**AMP_EXPONENT * full, rtol=1e-9, atol=1e-12)
    assert 20 * math.log10(0.5**AMP_EXPONENT) == pytest.approx(-10.0)
    np.testing.assert_allclose(lin, 0.5 * lin_full, rtol=1e-9, atol=1e-12)


def test_amp_fades_in_and_param_has_no_initial_glide(context: BlockContext) -> None:
    out = run(Dynamical("osc", context=context, system="lorenz", param=1.0), 0.05)
    assert np.max(np.abs(out[:10])) < 0.01  # amp smoother starts at 0
    # A constant cable equal to the knob must give the same sound from the first sample
    # (the u smoother starts at the first control value: no glide from 0).
    n = FS // 10
    knob = run(Dynamical("osc", context=context, system="lorenz", param=0.3), n / FS)
    cable = run(
        Dynamical("osc", context=context, system="lorenz", param=0.9),
        n / FS,
        inputs={"param": np.full(n, 0.3)},
    )
    np.testing.assert_array_equal(knob, cable)  # the cable overrides the knob exactly
    amp_cable = run(
        Dynamical("osc", context=context, amp=1.0), n / FS, inputs={"amp": np.full(n, 0.4)}
    )
    amp_knob = run(Dynamical("osc", context=context, amp=0.4), n / FS)
    np.testing.assert_array_equal(amp_cable, amp_knob)


def test_param_slew_is_at_least_two_periods(context: BlockContext) -> None:
    """A square jump of u reaches 63 % after max(5 ms, 2/f0) (spec §4.2 step 1)."""
    seen = {}

    class Spy(Dynamical):
        def _normalized(self, traj, observable, u):  # type: ignore[override]
            seen.setdefault("u", []).append(u.copy())
            return super()._normalized(traj, observable, u)

    for note in ("A1", "A5"):
        seen.clear()
        f0 = note_to_hz(note)
        n = FS // 4
        u_in = np.where(np.arange(n) < 100, 0.0, 1.0)
        run(Spy("osc", context=context, note=note), n / FS, inputs={"param": u_in})
        u = np.concatenate(seen["u"])
        tau = max(0.005, 2.0 / f0)
        k63 = int(np.argmax(u >= 1 - math.exp(-1))) - 100
        assert k63 / FS == pytest.approx(tau, rel=0.02, abs=2 / FS)


def test_pitch_input_overrides_the_note(context: BlockContext) -> None:
    n = round(FS * (0.5 + 2000 / 220))
    q = np.full(n, 0.5)  # A1..A5 → the middle is A3 = 220 Hz
    block = Dynamical("osc", context=context, system="rossler", note="C6")
    x = run(block, n / FS, chunk=8192, inputs={"pitch": q})[FS // 2 :, 0]
    assert abs(pitch_cents(block, x, target=220.0)) < 2.0
    # Custom range: 0 → pitch_min exactly.
    low = Dynamical("osc", context=context, system="rossler", pitch_min="E2", pitch_max="E4")
    n2 = round(FS * (0.5 + 2000 / 82.4))
    x2 = run(low, n2 / FS, chunk=8192, inputs={"pitch": np.zeros(n2)})[FS // 2 :, 0]
    assert abs(pitch_cents(low, x2, target=note_to_hz("E2"))) < 2.0


def test_chunking_does_not_change_output(context: BlockContext) -> None:
    n = FS // 2
    inputs = {
        "param": np.linspace(0, 1, n),
        "amp": 0.5 + 0.5 * np.sin(np.linspace(0, 20, n)),
        "pitch": 0.5 + 0.3 * np.sin(np.linspace(0, 7, n)),
    }
    whole = run(Dynamical("osc", context=context, system="lorenz"), 0.5, chunk=n, inputs=inputs)
    parts = run(Dynamical("osc", context=context, system="lorenz"), 0.5, chunk=129, inputs=inputs)
    ones = run(
        Dynamical("osc", context=context, system="lorenz"),
        0.01,
        chunk=1,
        inputs={k: v[: FS // 100] for k, v in inputs.items()},
    )
    np.testing.assert_array_equal(whole, parts)
    np.testing.assert_array_equal(whole[: FS // 100], ones)


def test_seeding_is_portable_and_small(context: BlockContext) -> None:
    # The seed hash is pinned (CRC-32 of the UTF-8 id, & 0x7FFFFFFF): engines must agree.
    assert stable_seed("osc") == 1818447832 and stable_seed("lorenz") == 286405065
    block = Dynamical("osc", context=context, system="chua")
    x0 = block.initial_state()
    e = block.entry
    rel = (x0 - e.initial_condition) / np.array([float(e.std(v, e.u_default)) for v in "xyz"])
    assert 0 < np.max(np.abs(rel)) < 6 * IC_PERTURBATION
    np.testing.assert_array_equal(
        x0, Dynamical("osc", context=context, system="chua").initial_state()
    )


def test_deterministic_and_seeded(context: BlockContext) -> None:
    a = run(Dynamical("one", context=context), 1.0)
    b = run(Dynamical("one", context=context), 1.0)
    c = run(Dynamical("two", context=context), 1.0)
    d = run(Dynamical("two", context=context, seed=stable_seed("one")), 1.0)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(a, d)
    # Same system and note, different seed: identical at first, then chaos separates them.
    assert np.max(np.abs(a[:200] - c[:200])) < 1e-3
    assert np.max(np.abs(a[-FS // 10 :] - c[-FS // 10 :])) > 0.1


@pytest.mark.slow
def test_pitch_lock_keeps_the_note_while_the_parameter_moves(context: BlockContext) -> None:
    # Lorenz: P(u) changes by almost an octave across the range.
    for u in (0.1, 0.9):
        # tonality=0: the raw signal's pitch (the tonality mix follows it, test_tonality.py).
        locked = Dynamical("osc", context=context, system="lorenz", note="A3", param=u,
                           tonality=0.0)  # fmt: skip
        free = Dynamical("osc", context=context, system="lorenz", note="A3", param=u,
                         pitch_lock=False, tonality=0.0)  # fmt: skip
        f_locked = measure_pitch(run(locked, 6.0)[FS // 2 :, 0], FS, "peak_centroid", 220)
        f_free = measure_pitch(run(free, 6.0)[FS // 2 :, 0], FS, "peak_centroid", 220)
        e = locked.entry
        expected_ratio = float(e.period(e.u_default) / e.period(u))
        assert abs(cents_between(f_locked, 220.0)) < SINGLE_CENTS["lorenz"]
        assert f_free / 220.0 == pytest.approx(expected_ratio, rel=0.01)


def test_stereo_maps_each_variable_to_its_channel(context: BlockContext) -> None:
    st = run(
        Dynamical("osc", context=context, system="rossler", observable="x", observable_right="y"),
        0.5,
    )
    mono_x = run(Dynamical("osc", context=context, system="rossler", observable="x"), 0.5)
    mono_y = run(Dynamical("osc", context=context, system="rossler", observable="y"), 0.5)
    np.testing.assert_array_equal(st[:, 0], mono_x[:, 0])
    np.testing.assert_array_equal(st[:, 1], mono_y[:, 0])
    np.testing.assert_array_equal(mono_x[:, 0], mono_x[:, 1])


def test_dc_blocker_removes_an_offset(context: BlockContext, monkeypatch) -> None:
    block = Dynamical("osc", context=context, system="rossler")
    e = block.entry
    mean = e.observables["x"].mean
    # Pretend the catalog mean is off by one σ: the raw signal gets a 0.25 offset.
    shifted = type(e.observables["x"])(
        mean=mean - e.observables["x"].std,
        std=e.observables["x"].std,
        peak=e.observables["x"].peak,
        prominence=e.observables["x"].prominence,
    )
    monkeypatch.setitem(e.observables, "x", shifted)
    x = run(block, 2.0)[FS:, 0]
    assert abs(np.mean(x)) < 0.01  # the 5 Hz blocker removed the 0.25 offset


def test_process_edge_cases(context: BlockContext) -> None:
    block = Dynamical("osc", context=context)
    block.reset(FS)
    assert block.process(0, {})["out"].shape == (0, 2)
    with pytest.raises(ValueError, match="samples"):
        block.process(10, {"param": np.zeros(9)})
    with pytest.raises(ValueError, match=r"Nyquist|below"):
        Dynamical("osc", context=context, note="C8").reset(8000)


@pytest.mark.parametrize(
    "params",
    [
        {"system": "nope"},
        {"system": "thomas"},
        {"note": "H2"},
        {"note": "C9"},
        {"note": "B-1"},
        {"cents": 150},
        {"param": 1.5},
        {"amp": -0.1},
        {"observable": "w"},
        {"system": "duffing", "observable": "z"},
        {"volume": 1.0},
        {"pitch_lock": "false"},
        {"pitch_lock": 1},
        {"seed": -1},
        {"seed": 1.5},
        {"seed": True},
        {"seed": 2**31},
        {"amp": True},
        {"amp": "1"},
        {"amp_curve": "dB"},
        {"pitch_min": "A5", "pitch_max": "A1"},
        {"note": 440},
    ],
)
def test_invalid_params(context: BlockContext, params: dict) -> None:
    with pytest.raises(ValueError):
        Dynamical("osc", context=context, **params)
