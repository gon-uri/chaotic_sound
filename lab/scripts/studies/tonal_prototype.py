"""Prototype of the owner's "tonality" knob idea (docs/ideas/tonal-knob.md).

Three ways to move a dynamical box from raw attractor (τ = 0) to tonal (τ = 1):

A. crossfade with a pure sine at f0 (the owner's baseline);
B. harmonic resonator bank: band-pass filters at k·f0 (k = 1..K) with decaying weights,
   applied to the raw signal, i.e. the owner's "multiply the attractor spectrum by a
   harmonic comb", done as filtering (time domain, causal, real-time friendly). τ sets
   both the mix and the sharpness (Q) of the resonators;
C. tuned feedback comb with damping (a Karplus-Strong-style string excited by the attractor):
   y[n] = x[n] + g·LP(y[n − D]), D = fs/f0. τ sets the feedback g (sharpness) and the mix.

Writes WAVs and a metrics table to lab/outputs/studies/tonal/. Usage (from lab/):

    uv run python scripts/studies/tonal_prototype.py

Methods B2 (resonators + envelope compression) and D (harmonic resynthesis) were added after
the first run; see docs/ideas/tonal-knob.md for the analysis.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numba import njit
from scipy.signal import lfilter, welch

from chaotic_sound.patch import Patch
from chaotic_sound.wav import write_wav

FS = 48_000
SECONDS = 3.0
OUT = Path(__file__).resolve().parents[2] / "outputs" / "studies" / "tonal"
TAUS = (0.0, 0.25, 0.5, 0.75, 1.0)


def raw_voice(system: str, note: str = "A3") -> tuple[np.ndarray, float]:
    p = Patch()
    osc = p.add_block("dynamical", "osc", system=system, note=note)
    p.add_block("output", "out", volume=1.0)
    p.connect("osc.out", "out.in")
    x = p.render(seconds=SECONDS, sample_rate=FS)[:, 0]
    return x, osc.frequency_hz  # type: ignore[attr-defined]


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x[FS // 4 :] ** 2)))


def match_rms(y: np.ndarray, ref: np.ndarray) -> np.ndarray:
    return y * (rms(ref) / max(rms(y), 1e-12))


# -- A. crossfade with a sine ---------------------------------------------------------


def method_a(x: np.ndarray, f0: float, tau: float) -> np.ndarray:
    t = np.arange(len(x)) / FS
    sine = math.sqrt(2) * rms(x) * np.sin(2 * np.pi * f0 * t)
    return (1 - tau) * x + tau * sine


# -- B. harmonic resonator bank -------------------------------------------------------


def resonator_bank(x: np.ndarray, f0: float, q: float, decay: float = 1.0) -> np.ndarray:
    """Sum of 2-pole band-pass resonators (RBJ, 0 dB peak) at k·f0 with weights k^-decay.

    Each resonator passes the attractor's own energy near k·f0, so the harmonic amplitudes
    (and their slow fluctuations) come from the attractor; weights only add a gentle tilt.
    """
    y = np.zeros_like(x)
    k = 1
    while k * f0 < 0.45 * FS:
        w0 = 2 * np.pi * k * f0 / FS
        alpha = np.sin(w0) / (2 * q)
        b = np.array([alpha, 0.0, -alpha])
        a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
        y += k ** (-decay) * lfilter(b / a[0], a / a[0], x)
        k += 1
    return y


def method_b(x: np.ndarray, f0: float, tau: float) -> np.ndarray:
    if tau == 0:
        return x
    q = 2.0 * 10 ** (2.5 * tau)  # τ: 0 → Q 2 (broad) … 1 → Q 630 (very sharp partials)
    tonal = match_rms(resonator_bank(x, f0, q), x)
    return (1 - tau) * x + tau * tonal


# -- C. damped feedback comb (Karplus–Strong-style resonator) --------------------------


@njit(cache=True)
def _comb(x: np.ndarray, delay: float, g: float, damp: float) -> np.ndarray:
    n = x.shape[0]
    size = int(delay) + 4
    buf = np.zeros(size)
    y = np.zeros(n)
    w = 0
    lp = 0.0
    for i in range(n):
        # read y[n − delay] with linear interpolation
        pos = w - delay
        while pos < 0:
            pos += size
        i0 = int(pos)
        frac = pos - i0
        d = buf[i0 % size] * (1 - frac) + buf[(i0 + 1) % size] * frac
        lp = (
            1 - damp
        ) * d + damp * lp  # one-pole low-pass in the loop: higher partials decay faster
        out = x[i] + g * lp
        buf[w] = out
        y[i] = out
        w = (w + 1) % size
    return y


def method_c(x: np.ndarray, f0: float, tau: float) -> np.ndarray:
    if tau == 0:
        return x
    g = 0.5 + 0.495 * tau  # τ: 0.5 (barely resonant) … 0.995 (string-like)
    # The loop low-pass adds about half a sample of delay; compensate so the comb stays tuned.
    delay = FS / f0 - 0.5 * 0.35 / (1 - 0.35)
    tonal = match_rms(_comb(x, delay, g, 0.35), x)
    return (1 - tau) * x + tau * tonal


# -- metrics ----------------------------------------------------------------------------


def harmonicity(y: np.ndarray, f0: float, width: float = 0.01) -> float:
    """Fraction of the power within ±1 % of the harmonics k·f0 (1 = purely harmonic)."""
    f, p = welch(y[FS // 4 :], fs=FS, nperseg=2**15)
    band = np.zeros_like(f, dtype=bool)
    k = 1
    while k * f0 < 0.45 * FS:
        band |= np.abs(f - k * f0) <= width * k * f0
        k += 1
    valid = f > 0.5 * f0
    return float(p[band & valid].sum() / p[valid].sum())


def fundamental_share(y: np.ndarray, f0: float) -> float:
    """Fraction of the harmonic power that sits in the fundamental (1 = sine-like)."""
    f, p = welch(y[FS // 4 :], fs=FS, nperseg=2**15)
    powers = []
    k = 1
    while k * f0 < 0.45 * FS:
        powers.append(p[np.abs(f - k * f0) <= 0.01 * k * f0].sum())
        k += 1
    total = sum(powers)
    return float(powers[0] / total) if total > 0 else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "| System | Method | τ | Harmonicity | Fundamental share |",
        "|---|---|---|---|---|",
    ]
    for system in ("lorenz", "rikitake", "chua"):
        x, f0 = raw_voice(system)
        for name, fn in (("A_sine", method_a), ("B_resonators", method_b), ("C_comb", method_c)):
            for tau in TAUS:
                y = fn(x, f0, tau)
                y = 0.9 * y / max(np.max(np.abs(y)), 1e-12)
                write_wav(OUT / f"{system}_{name}_tau{tau:.2f}.wav", np.column_stack([y, y]), FS)
                lines.append(
                    f"| {system} | {name} | {tau:.2f} | {harmonicity(y, f0):.2f} | "
                    f"{fundamental_share(y, f0):.2f} |"
                )
                print(lines[-1])
    (OUT / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")




# -- B2. resonator bank with envelope compression (brightness) -------------------------


def band_energies(x: np.ndarray, f0: float, kmax: int) -> np.ndarray:
    f, p = welch(x[FS // 4 :], fs=FS, nperseg=2**15)
    return np.array(
        [p[(f >= (k - 0.5) * f0) & (f < (k + 0.5) * f0)].sum() for k in range(1, kmax + 1)]
    )


def method_b2(
    x: np.ndarray, f0: float, tau: float, beta: float = 0.5, kmax: int = 16, max_gain: float = 31.6
) -> np.ndarray:
    """Like B, but harmonic k is re-weighted so its energy becomes ∝ E_k^β (β < 1 = brighter).

    The attractor still shapes the harmonics (its envelope is compressed, not replaced).
    Only the first `kmax` harmonics are used and gains are capped (+30 dB): boosting nearly
    empty high bands amplifies noise instead of adding harmonics (an earlier uncapped run
    dropped Lorenz's harmonicity to 0.16).
    In an engine the E_k would come from the catalog (tabulated per u), not be measured live.
    """
    if tau == 0:
        return x
    kmax = min(kmax, int(0.45 * FS // f0))
    e = band_energies(x, f0, kmax)
    weights = (e / e[0]) ** ((beta - 1) / 2)  # amplitude gain per harmonic
    q = 2.0 * 10 ** (2.5 * tau)
    y = np.zeros_like(x)
    for k in range(1, kmax + 1):
        w0 = 2 * np.pi * k * f0 / FS
        alpha = np.sin(w0) / (2 * q)
        b = np.array([alpha, 0.0, -alpha])
        a = np.array([1 + alpha, -2 * np.cos(w0), 1 - alpha])
        y += min(weights[k - 1], max_gain) * lfilter(b / a[0], a / a[0], x)
    return (1 - tau) * x + tau * match_rms(y, x)


# -- D. harmonic resynthesis -------------------------------------------------------------


def method_d(x: np.ndarray, f0: float, tau: float, kmax: int = 24) -> np.ndarray:
    """Move each harmonic band's energy onto a clean partial at k·f0.

    Band k = [k−½, k+½]·f0 is heterodyned to baseband and its magnitude envelope smoothed
    (time constant grows with τ). The partial's phase is k times a common phase, so the
    waveform is periodic at τ = 1; its harmonic amplitudes are the attractor's band energies,
    which include the noise between harmonics (richer than B, which discards it).
    """
    if tau == 0:
        return x
    from scipy.signal import butter, sosfilt

    n = len(x)
    t = np.arange(n) / FS
    sos = butter(4, 0.5 * f0, fs=FS, output="sos")  # isolates one band around k·f0
    smooth_s = 0.002 * 10 ** (3 * tau)  # 2 ms … 2 s envelope smoothing
    a_env = 1 - math.exp(-1 / (smooth_s * FS))
    y = np.zeros(n)
    for k in range(1, kmax + 1):
        if k * f0 >= 0.45 * FS:
            break
        base = x * np.exp(-2j * np.pi * k * f0 * t)
        c = sosfilt(sos, base.real) + 1j * sosfilt(sos, base.imag)
        mag = np.abs(c)
        mag_s = lfilter([a_env], [1, -(1 - a_env)], mag)
        y += 2 * mag_s * np.cos(2 * np.pi * k * f0 * t)
    return (1 - tau) * x + tau * match_rms(y, x)


def centroid_harmonic(y: np.ndarray, f0: float) -> float:
    """Spectral centroid in units of f0 (brightness)."""
    f, p = welch(y[FS // 4 :], fs=FS, nperseg=2**15)
    v = f > 0.5 * f0
    return float((f[v] * p[v]).sum() / p[v].sum() / f0)


def main2() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "| System | Method | τ | Harmonicity | Fundamental share | Centroid (×f0) |",
        "|---|---|---|---|---|---|",
    ]
    methods = (
        ("A_sine", method_a),
        ("B_resonators", method_b),
        ("B2_bright", method_b2),
        ("C_comb", method_c),
        ("D_resynth", method_d),
    )
    for system in ("lorenz", "rossler", "chua", "rikitake", "duffing"):
        x, f0 = raw_voice(system)
        for name, fn in methods:
            for tau in (0.0, 0.5, 1.0):
                y = fn(x, f0, tau)
                y = 0.9 * y / max(np.max(np.abs(y)), 1e-12)
                write_wav(OUT / f"{system}_{name}_tau{tau:.2f}.wav", np.column_stack([y, y]), FS)
                lines.append(
                    f"| {system} | {name} | {tau:.2f} | {harmonicity(y, f0):.2f} | "
                    f"{fundamental_share(y, f0):.2f} | {centroid_harmonic(y, f0):.2f} |"
                )
    (OUT / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main2()
