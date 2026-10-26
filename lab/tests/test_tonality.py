"""Tonality: harmonic resynthesis (spec §4.2 step 7, ADR 0015)."""

import math

import numpy as np
import pytest
from scipy.signal import welch

from chaotic_sound.blocks import BlockContext, Dynamical
from chaotic_sound.blocks.dynamical import TONALITY_DEFAULT
from chaotic_sound.dsp import TONAL_HARMONICS, TONAL_MIX_EXPONENT, TONAL_Q, tonal, tonal_state
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


def kernel(r: np.ndarray, f: float, tau: float) -> np.ndarray:
    out = np.empty_like(r)
    scalars, coef, filt, bands = tonal_state()
    tonal(r, np.full(r.size, f), np.full(r.size, tau), float(FS), scalars, coef, filt, bands,
          *TONAL_Q, TONAL_MIX_EXPONENT, out)  # fmt: skip
    return out


def harmonicity(y: np.ndarray, f0: float) -> float:
    """Fraction of the power within ±1 % of the harmonics k·f0 (1 = purely harmonic)."""
    f, p = welch(y, fs=FS, nperseg=2**15)
    band = np.zeros_like(f, dtype=bool)
    for k in range(1, int(0.45 * FS // f0) + 1):
        band |= np.abs(f - k * f0) <= 0.01 * k * f0
    valid = f > 0.5 * f0
    return float(p[band & valid].sum() / p[valid].sum())


def test_default_is_point_three() -> None:
    assert TONALITY_DEFAULT == 0.3
    assert Dynamical("osc").params.tonality == 0.3


def test_zero_tonality_returns_the_raw_signal_exactly() -> None:
    r = np.random.default_rng(1).normal(size=4096)
    np.testing.assert_array_equal(kernel(r, 220.0, 0.0), r)


@pytest.mark.parametrize("k", [1, 3, 8])
def test_a_harmonic_tone_keeps_its_amplitude(k: int) -> None:
    """A·cos(kθ + ψ) comes out as a partial of the same amplitude (power is preserved)."""
    f0 = 220.0
    t = np.arange(FS) / FS
    r = 0.3 * np.cos(2 * np.pi * k * f0 * t + 0.7)
    y = kernel(r, f0, 1.0)[FS // 2 :]
    assert np.sqrt(np.mean(y**2)) == pytest.approx(0.3 / math.sqrt(2), rel=0.01)
    assert harmonicity(y, f0) > 0.999
    # Phase tracking: the partial also keeps the tone's phase. At τ = 0.5 (T_τ = 63 ms) the
    # tonal part t = (m − g·r)/g has the tone's phase. (Its amplitude is up to 13 % high
    # here: each neighbouring band sees the tone at −24 dB and, tracking its phase, adds it
    # back at the tone's frequency. That is < 1 dB of power and documented in ADR 0015.)
    g = 0.5**TONAL_MIX_EXPONENT
    m = kernel(r, f0, 0.5)[FS // 2 :]
    t_part = (m - g * r[FS // 2 :]) / g
    ref = np.exp(-1j * (2 * np.pi * k * f0 * t[FS // 2 :] + 0.7))
    assert abs(np.angle(np.mean(t_part * ref))) < 0.05


def test_partials_stay_below_the_limit() -> None:
    """Partial k fades out between 0.40·fs and 0.45·fs: nothing above 0.45·fs is added."""
    f0 = 4000.0  # k = 5 is at 20 kHz (weight 0.83), k = 6 at 24 kHz (weight 0)
    t = np.arange(FS) / FS
    r = sum(0.1 * np.cos(2 * np.pi * k * f0 * t) for k in range(1, 6))
    y = kernel(r, f0, 1.0)[FS // 2 :]
    f, p = welch(y, fs=FS, nperseg=2**14)
    assert p[f > 0.45 * FS].sum() < 1e-12 * p.sum()


@pytest.mark.parametrize("system", list_systems())
def test_tonality_makes_every_system_harmonic_at_the_same_level(
    context: BlockContext, system: str
) -> None:
    """Harmonicity rises with τ (≥ 0.85 at τ = 1), the level stays within ±2 dB, and the
    tonal partials do not beat against the raw signal (the 50 ms level stays steady)."""
    h, level, wobble = [], [], []
    for tau in (0.0, 0.3, 1.0):
        block = Dynamical("osc", context=context, system=system, tonality=tau)
        y = run(block, 3.0, chunk=4096)[FS:, 0]
        h.append(harmonicity(y, block.frequency_hz))
        level.append(np.sqrt(np.mean(y**2)))
        seg = y[: y.size // 2400 * 2400].reshape(-1, 2400)  # 50 ms windows
        wobble.append(float(np.std(10 * np.log10(np.mean(seg**2, axis=1)))))
    assert h[0] < h[1] < h[2], (system, h)
    # At τ = 1 the partials keep the attractor's slow phase wander (ADR 0015): measured
    # 0.90-1.00 of the power within ±1 % of the harmonics.
    assert h[2] > 0.85, (system, h)
    for v in level[1:]:
        assert abs(20 * math.log10(v / level[0])) < 2.0, (system, level)
    # Beating would show as a level wobble well above the attractor's own (measured: raw
    # 0.4-0.9 dB; magnitude-only resynthesis 2-4 dB at τ = 0.3; phase-tracked 0.3-1.6 dB).
    assert wobble[1] < wobble[0] + 1.0, (system, wobble)


def test_full_tonality_is_heard_from_the_start(context: BlockContext) -> None:
    """The running-mean start (spec step 7.4) gives sound within a few periods, not seconds."""
    y = run(Dynamical("osc", context=context, system="lorenz", tonality=1.0), 1.0)[:, 0]
    early = np.sqrt(np.mean(y[round(0.02 * FS) : round(0.07 * FS)] ** 2))
    steady = np.sqrt(np.mean(y[FS // 2 :] ** 2))
    assert early > 0.4 * steady


def test_tonality_input_overrides_the_knob(context: BlockContext) -> None:
    n = FS
    cable = run(Dynamical("a", context=context, tonality=0.0), 1.0, inputs={"tonality": np.ones(n)})
    knob = run(Dynamical("a", context=context, tonality=1.0), 1.0)
    np.testing.assert_allclose(cable, knob, rtol=0, atol=1e-12)


def test_tonality_follows_the_heard_pitch_without_pitch_lock(context: BlockContext) -> None:
    """With pitch lock off the partials sit on the actual fundamental f·P(u_default)/P(u)."""
    block = Dynamical("osc", context=context, system="lorenz", param=1.0, pitch_lock=False,
                      tonality=1.0)  # fmt: skip
    y = run(block, 2.0, chunk=4096)[FS // 2 :, 0]
    e = block.entry
    f_a = block.frequency_hz * float(e.period(e.u_default)) / float(e.period(1.0))
    assert abs(f_a / block.frequency_hz - 1) > 0.2  # far from the nominal note
    assert harmonicity(y, f_a) > 0.85


def test_chunk_size_does_not_matter_with_a_modulated_tonality(context: BlockContext) -> None:
    n = FS // 2
    tau = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * np.arange(n) / FS)
    a = run(Dynamical("v", context=context, system="rikitake"), 0.5, chunk=1,
            inputs={"tonality": tau})  # fmt: skip
    b = run(Dynamical("v", context=context, system="rikitake"), 0.5, chunk=4096,
            inputs={"tonality": tau})  # fmt: skip
    np.testing.assert_array_equal(a, b)


def test_stereo_channels_have_their_own_tonality_state(context: BlockContext) -> None:
    stereo = run(Dynamical("v", context=context, system="lorenz", observable="x",
                           observable_right="z"), 0.5)  # fmt: skip
    mono_z = run(Dynamical("v", context=context, system="lorenz", observable="z"), 0.5)
    np.testing.assert_array_equal(stereo[:, 1], mono_z[:, 0])


@pytest.mark.slow
@pytest.mark.parametrize("system", list_systems())
def test_tonality_stays_in_tune(context: BlockContext, system: str) -> None:
    """The mix keeps the note (seed average, the catalog's pitch estimator, A3 at 48 kHz).

    Measured (ADR 0015): within 2 cents at τ = 1 for every system, and within 3 cents at
    τ = 0.3 except Lorenz, whose broad spectrum reads up to about 10 cents sharp there.
    """
    from test_dynamical import seeds_cents

    full = float(np.mean(seeds_cents(context, system, "A3", FS, tonality=1.0)))
    default = float(np.mean(seeds_cents(context, system, "A3", FS, tonality=0.3)))
    assert abs(full) < 3.0, (system, full)
    assert abs(default) < (14.0 if system == "lorenz" else 4.0), (system, default)


def test_constants() -> None:
    assert TONAL_HARMONICS == 8
    assert TONAL_MIX_EXPONENT == 0.75
