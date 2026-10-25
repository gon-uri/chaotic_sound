"""Study: aliasing versus note (when does a dynamical box need oversampling?).

Usage (from ``lab/``; about 6 minutes)::

    caffeinate -is uv run python scripts/studies/aliasing.py
    uv run python scripts/studies/aliasing.py --dc-check     # side check only (~1 min)

Question
--------
The engine point-samples the continuous tuned trajectory x(k·t) at fs, with no anti-alias
filter (spec §4.2 steps 5–6). Whatever power the trajectory has above fs/2 folds back into
the band. For which notes, systems, observables and parameter values is that power large
enough to matter, and what oversampling factor and decimator remove it?

Method
------
1. **Per-note renders (part A).** Each system (default parameter and observable) is rendered
   through the real :class:`Dynamical` block at ``fs_hi = 8 × 48 kHz`` for the notes A1…A7
   and C8, three seeds each. Chaos makes renders at different rates diverge, so the
   comparison is statistical. The folded PSD of a stationary process sampled at fs is
   S_fs(f) = Σ_m S(f + m·fs), so every aliasing measure is an exact functional of the
   high-rate PSD S(f):

   - ``R_nyq``  power above 24 kHz / total power (all of it folds somewhere at 48 kHz);
   - ``R_aud``  power that folds into 20 Hz–20 kHz / total power;
   - ``R_1_5k`` power folding into 1–5 kHz / signal power in 1–5 kHz;
   - ``R_A``    A-weighted folded power / A-weighted signal power (20 Hz–24 kHz);
   - per 1/3-octave band b (25 Hz … 20 kHz): folded power A_b, signal power S_b, the local
     ratio L_b = A_b / S_b (``L_max`` = worst band) and the alias level in dBFS;
   - ``M_max``: a crude, conservative audibility screen. In each band the alias is compared
     with max(S_b − (14.5 + z_b) dB, threshold in quiet), z_b the band's Bark number
     (tonal-masker offset of the MPEG psychoacoustic model 1, in-band masking only) and the
     Terhardt threshold in quiet at the calibration "full-scale sine = 96 dB SPL". M_max is
     the largest excess in dB; M_max ≤ 0 means "inaudible by this screen".

   dBFS here is 20·log10(RMS) re 1.0 (a full-scale sine is −3 dBFS; the box's nominal RMS
   0.25 is −12 dBFS). Band powers use the cumulative PSD (power spread uniformly within a
   bin), so bands narrower than a bin are handled exactly to that approximation.
2. **Checks.** (a) the A6, A7, C8 metrics are recomputed from 32× renders (content above
   192 kHz); (b) at A7 and C8 the PSD of a *native* 48 kHz render is compared with the
   prediction "high-rate PSD below 24 kHz + folded PSD".
3. **Universal spectra (part B).** With exact time rescaling the pre-DC-blocker spectrum at
   note f0 is S(f) = S₁(f/f0)/f0, a function of the harmonic number n = f/f0 only. One 8×
   render per case at the reference note A4 (where the 5 Hz DC blocker is negligible and RK4
   resolution ample; the blocker's known response is divided out) gives S₁ up to n = 436.
   Cases: three seeds at the default; every audible observable × u ∈ {0, ⅛, …, 1}. From S₁:
   the tail fraction G(n) = P(f > n·f0)/P_total and its −60/−80 dB crossings n_T, and every
   part-A measure at every semitone A2…C8, at 48 and 44.1 kHz, and for 2× and 4×
   oversampling with the half-band decimators of part C. Thresholds are given per scope:
   default (u, observable); default observable over the u grid; any observable over the grid.
4. **Decimators (part C).** Kaiser half-band FIRs (exact zeros on every other tap) with the
   fewest taps whose *measured* stopband meets 60/80/100 dB (β is scanned, not taken from
   ``kaiserord``). Residual alias for 2× and 4× is computed through the full multirate chain
   (images at the internal rate, decimator gain at every preimage).
5. **Direct checks (part D).** The scope-defining worst cases are re-rendered directly at
   the note where they cross a criterion, to confirm the universal-spectrum prediction.

PSD estimator: Welch, Hann window, on the second difference of the signal ("prewhitening"),
divided by |2 sin(πf/fs)|⁴, combined with the direct estimate below f0/2. Without
prewhitening, window leakage from the fundamental puts a false floor at −110 dB (Nuttall) to
−200 dB (Hann) in the 24 kHz fraction; with it the estimator floor is below −250 dB. Total
power is the time-domain variance.

Writes ``outputs/studies/aliasing/{results.json, dc_check.json, *.png}``.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# A private, throw-away numba cache. The engine no longer disk-caches the kernels that take
# the RHS as an argument (integrate.py docstring); this only keeps the study from writing
# its own cache entries into the source tree.
if "NUMBA_CACHE_DIR" not in os.environ:
    _numba_tmp = tempfile.mkdtemp(prefix="numba_aliasing_")
    os.environ["NUMBA_CACHE_DIR"] = _numba_tmp
    atexit.register(shutil.rmtree, _numba_tmp, ignore_errors=True)

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import firwin, freqz, welch

from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import load_default_catalog
from chaotic_sound.pitch import hz_to_midi, note_to_hz
from chaotic_sound.systems import get_system

OUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "studies" / "aliasing"

SYSTEMS = ("lorenz", "rossler", "chua", "thomas", "duffing")
NOTES = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "C8")
FS = 48_000.0
FS_441 = 44_100.0
OVERSAMPLE = 8
FS_HI = OVERSAMPLE * FS
FS_CHECK = 32 * FS
SEEDS = (11, 22, 33)
T_RENDER = 8.0  # seconds rendered per run
T_SKIP = 0.5  # discarded start: amp fade-in (5 ms) and DC-blocker settling (32 ms)
BIN_HZ = FS / 2**13  # 5.86 Hz: the same Welch resolution at every rate (part A)
REF_NOTE = "A4"  # reference note of the universal spectra (part B)
UNIV_NPERSEG = 2**18  # 1.46 Hz bins at 384 kHz = 1/300 harmonic at A4
AUDIBLE = (20.0, 20_000.0)
BAND_1_5K = (1_000.0, 5_000.0)
THRESHOLDS_DB = (-40.0, -60.0, -80.0, -100.0)
U_GRID = tuple(float(u) for u in np.linspace(0.0, 1.0, 9))
SCAN_MIDI = tuple(range(45, 109))  # A2 … C8, every semitone
FLOOR_DB = -150.0  # values below are reported as "< −150" (far below any audible effect)
DC_BLOCK_HZ = 5.0  # spec §4.2 step 6 (checked against the block module at start-up)

# Band-level audibility measures.
OUT_MS = 0.25**2  # nominal mean square of a box at amp = 1 (spec §3): −12 dBFS
SPL_PER_DBFS = 99.0  # calibration: full-scale sine (−3 dBFS) = 96 dB SPL
ALIAS_FLOOR_DBFS = -130.0  # bands whose alias is below this are ignored in L_max
L_CRIT_DB = -40.0  # local criterion: alias ≥ 40 dB below the signal in every band
CRIT_GLOBAL_DB = -80.0

# Colors: fixed categorical order of the reference palette (light mode), one per system.
COLORS = {
    "lorenz": "#2a78d6",
    "rossler": "#eb6834",
    "chua": "#1baf7a",
    "thomas": "#eda100",
    "duffing": "#e87ba4",
}
LABELS = {"lorenz": "Lorenz", "rossler": "Rössler", "chua": "Chua", "thomas": "Thomas",
          "duffing": "Duffing"}  # fmt: skip
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def midi_name(m: int) -> str:
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def highest_note_below(freq_hz: float) -> str:
    """Name of the highest 12-TET note whose frequency is ≤ ``freq_hz``."""
    return midi_name(math.floor(hz_to_midi(freq_hz) + 1e-9))


def db(x: float) -> float:
    return float(10.0 * np.log10(max(float(x), 1e-300)))


def render(system: str, note: str, fs: float, seconds: float, *, seed: int, param=None,
           observable=None, skip: float = T_SKIP) -> tuple[np.ndarray, Dynamical]:  # fmt: skip
    """Mono output of one Dynamical block (left channel), start discarded."""
    block = Dynamical("osc", catalog=CATALOG, system=system, note=note, seed=seed, param=param,
                      observable=observable)  # fmt: skip
    block.reset(fs)
    y = block.process(round(seconds * fs), {"param": None, "amp": None})["out"][:, 0]
    if block.resets:
        print(f"  WARNING: {block.resets} safety resets in {system} {note}")
    return y[round(skip * fs) :], block


def psd(y: np.ndarray, fs: float, order: int = 2, nperseg: int | None = None):
    """One-sided Welch PSD (Hann, 50 % overlap, BIN_HZ resolution by default).

    ``order > 0`` estimates the PSD of the ``order``-th difference and divides by its
    transfer function |2 sin(πf/fs)|^(2·order) (prewhitening against window leakage).
    """
    nperseg = nperseg or round(fs / BIN_HZ)
    d = np.diff(y, order) if order else y
    f, s = welch(d, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, window="hann")
    if order:
        h = (2.0 * np.sin(np.pi * f / fs)) ** (2 * order)
        s = np.where(f > 0, s / np.where(h > 0, h, 1.0), 0.0)
    return f, s


def combined_psd(y: np.ndarray, fs: float, f0: float, nperseg: int | None = None):
    """Direct estimate below f0/2 (where prewhitening amplifies leakage), prewhitened above."""
    f, s_direct = psd(y, fs, order=0, nperseg=nperseg)
    _, s_white = psd(y, fs, order=2, nperseg=nperseg)
    return f, np.where(f < 0.5 * f0, s_direct, s_white)


def dc_blocker_gain2(f: np.ndarray, fs: float) -> np.ndarray:
    """|H|² of the engine's DC blocker y[n] = x[n] − x[n−1] + R·y[n−1] (dsp.dc_block)."""
    r = math.exp(-2.0 * math.pi * DC_BLOCK_HZ / fs)
    c = np.cos(2.0 * np.pi * f / fs)
    return (2.0 - 2.0 * c) / (1.0 - 2.0 * r * c + r * r)


def fold(f: np.ndarray, fs: float) -> np.ndarray:
    """Frequency at which a component at ``f`` appears after sampling at ``fs``."""
    r = np.mod(f, fs)
    return np.where(r > fs / 2, fs - r, r)


def a_weight(f: np.ndarray) -> np.ndarray:
    """A-weighting as a power gain (IEC 61672, 0 dB at 1 kHz)."""
    f2 = np.asarray(f, dtype=np.float64) ** 2
    ra = (12194.0**2 * f2**2) / (
        (f2 + 20.6**2) * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194.0**2)
    )
    return (ra * 10 ** (2.0 / 20.0)) ** 2


def alias_metrics(f: np.ndarray, s: np.ndarray, total: float, fs_out: float = FS) -> dict:
    """Broad-band aliasing functionals of a high-rate PSD for sampling at ``fs_out``."""
    df = f[1] - f[0]
    hi = f > fs_out / 2
    fa = fold(f, fs_out)
    lo_band = (f >= BAND_1_5K[0]) & (f <= BAND_1_5K[1])
    al_band = hi & (fa >= BAND_1_5K[0]) & (fa <= BAND_1_5K[1])
    aud = hi & (fa >= AUDIBLE[0]) & (fa <= AUDIBLE[1])
    w = a_weight(f)
    wa = a_weight(fa)
    return {
        "R_nyq": db(s[hi].sum() * df / total),
        "R_aud": db(s[aud].sum() * df / total),
        "R_1_5k": db(s[al_band].sum() / s[lo_band].sum()),
        "R_A": db((wa[hi] * s[hi]).sum() / (w[~hi] * s[~hi]).sum()),
    }


def tail_curve(f: np.ndarray, s: np.ndarray, total: float, f0: float):
    """Harmonic number n and tail fraction G(n) = P(f > n·f0) / P_total in dB."""
    df = f[1] - f[0]
    g = np.cumsum(s[::-1])[::-1] * df / total
    return f / f0, 10.0 * np.log10(np.maximum(g, 1e-300))


def crossing(n: np.ndarray, g_db: np.ndarray, level: float) -> float:
    """Smallest harmonic number with G(n) ≤ level (linear interpolation in n)."""
    below = np.nonzero(g_db <= level)[0]
    if below.size == 0:
        return float("inf")
    i = below[0]
    if i == 0:
        return float(n[0])
    n0, n1, g0, g1 = n[i - 1], n[i], g_db[i - 1], g_db[i]
    return float(n0 + (level - g0) * (n1 - n0) / (g1 - g0))


def psd_slope(n: np.ndarray, s: np.ndarray, f0: float) -> float:
    """Log-log slope of the PSD (dB per octave) over 16 ≤ n ≤ 128."""
    m = (n >= 16) & (n <= 128) & (s > 0)
    p = np.polyfit(np.log2(n[m]), 10 * np.log10(s[m] * f0), 1)
    return float(p[0])


# --------------------------------------------------------------------------------------
# Band-level machinery: cumulative spectra, 1/3-octave bands, multirate folding
# --------------------------------------------------------------------------------------


def third_octave_bands() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Base-10 1/3-octave bands, centres 25 Hz … 20 kHz; the top band is cut at 20 kHz."""
    k = np.arange(14, 44)
    fc = 1000.0 * 10 ** ((k - 30) / 10)
    return fc, fc * 10**-0.05, np.minimum(fc * 10**0.05, AUDIBLE[1])


BANDS_FC, BANDS_LO, BANDS_HI = third_octave_bands()


def bark(f: np.ndarray) -> np.ndarray:
    """Critical-band rate (Zwicker & Terhardt 1980)."""
    return 13.0 * np.arctan(0.00076 * f) + 3.5 * np.arctan((f / 7500.0) ** 2)


def threshold_in_quiet(f: np.ndarray) -> np.ndarray:
    """Terhardt's approximation of the threshold in quiet, dB SPL."""
    k = f / 1000.0
    return 3.64 * k**-0.8 - 6.5 * np.exp(-0.6 * (k - 3.3) ** 2) + 1e-3 * k**4


MASK_OFFSET_DB = 14.5 + bark(BANDS_FC)
ATH_DB_SPL = threshold_in_quiet(BANDS_FC)


@dataclass
class CumSpectrum:
    """Cumulative power of a PSD for exact band integrals (power uniform within a bin).

    ``edges`` are bin edges (Hz, or harmonic numbers for a universal spectrum), ``c`` and
    ``g`` the power fractions below and above each edge (``g`` is summed from the top so
    that tiny tail powers keep full relative precision).
    """

    edges: np.ndarray
    c: np.ndarray
    g: np.ndarray
    split: float  # intervals starting above this use g, below it c

    @classmethod
    def from_psd(cls, f: np.ndarray, s: np.ndarray, total: float, split: float) -> CumSpectrum:
        df = f[1] - f[0]
        p = s * df / total
        edges = np.concatenate(([0.0], (np.arange(1, f.size + 1) - 0.5) * df))
        c = np.concatenate(([0.0], np.cumsum(p)))
        g = np.concatenate((np.cumsum(p[::-1])[::-1], [0.0]))
        return cls(edges, c, g, split)

    def at(self, f0: float) -> CumSpectrum:
        """A universal spectrum (axis in harmonics) evaluated at fundamental ``f0``."""
        return CumSpectrum(self.edges * f0, self.c, self.g, self.split * f0)

    @property
    def f_max(self) -> float:
        return float(self.edges[-1])

    def power(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        a = np.clip(a, 0.0, self.f_max)
        b = np.clip(b, 0.0, self.f_max)
        lower = np.interp(b, self.edges, self.c) - np.interp(a, self.edges, self.c)
        upper = np.interp(a, self.edges, self.g) - np.interp(b, self.edges, self.g)
        return np.maximum(np.where(a >= self.split, upper, lower), 0.0)


@dataclass
class HalfBand:
    """A half-band decimate-by-2 stage running at ``rate`` (its input rate)."""

    rate: float
    taps: np.ndarray
    beta: float
    stopband_db: float
    _f: np.ndarray
    _h2: np.ndarray

    def gain2(self, f: np.ndarray) -> np.ndarray:
        return np.interp(f, self._f, self._h2)

    @property
    def nonzero(self) -> int:
        return int(np.sum(np.abs(self.taps) > 1e-12))

    @property
    def delay_ms(self) -> float:
        return (self.taps.size - 1) / 2 / self.rate * 1e3


def design_halfband(rate: float, f_pass: float, atten_db: float) -> HalfBand:
    """Fewest-tap Kaiser half-band (4k+3 taps) whose measured stopband meets ``atten_db``.

    The stopband starts at rate/2 − f_pass. For a half-band, passband ripple equals stopband
    ripple, so minimizing the stopband maximum over β also minimizes the passband error.
    """
    f_stop = rate / 2 - f_pass
    for numtaps in range(7, 400, 4):
        best = None
        for beta in np.arange(2.0, 14.0, 0.05):
            taps = firwin(numtaps, rate / 4, window=("kaiser", beta), fs=rate)
            w, h = freqz(taps, worN=1 << 15, fs=rate)
            stop = 20 * np.log10(np.max(np.abs(h[w >= f_stop])))
            if best is None or stop < best[0]:
                best = (stop, beta, taps)
        if best[0] <= -atten_db:
            w, h = freqz(best[2], worN=1 << 17, fs=rate)
            return HalfBand(rate, best[2], float(best[1]), float(best[0]), w, np.abs(h) ** 2)
    raise RuntimeError("no half-band design found")


def fold_into_bands(spec: CumSpectrum, lo: np.ndarray, hi: np.ndarray, fs_out: float,
                    stages: tuple[HalfBand, ...] = (), sub: int = 16):  # fmt: skip
    """True and aliased power fractions that land in the output bands [lo, hi] (Hz).

    The trajectory is sampled at fs_out·2^len(stages), then decimated by the half-band
    ``stages``, listed from the output upwards (stages[0] runs at 2·fs_out). Each band is
    split into ``sub`` pieces so that the decimator gain is evaluated per piece; every
    preimage of every piece is integrated with the cumulative spectrum.
    """
    t = np.linspace(0.0, 1.0, sub + 1)
    a0 = lo[:, None] + (hi - lo)[:, None] * t[None, :-1]
    b0 = lo[:, None] + (hi - lo)[:, None] * t[None, 1:]
    paths = [(a0, b0, np.ones_like(a0), True)]
    rate = fs_out
    for st in stages:  # preimages at twice the rate: identity and mirror about the old rate
        new = []
        for pa, pb, gw, is_true in paths:
            new.append((pa, pb, gw * st.gain2(0.5 * (pa + pb)), is_true))
            ma, mb = rate - pb, rate - pa
            new.append((ma, mb, gw * st.gain2(0.5 * (ma + mb)), False))
        paths = new
        rate *= 2
    m = np.arange(0, int(np.ceil(spec.f_max / rate)) + 2, dtype=np.float64)[:, None, None]
    true = np.zeros(lo.size)
    alias = np.zeros(lo.size)
    for pa, pb, gw, is_true in paths:
        up = spec.power(m * rate + pa, m * rate + pb) * gw  # m ≥ 0, upper images
        dn = spec.power(m[1:] * rate - pb, m[1:] * rate - pa) * gw  # m ≥ 1, lower images
        alias += dn.sum(axis=(0, 2)) + up[1:].sum(axis=(0, 2))
        (true if is_true else alias)[:] += up[0].sum(axis=1)
    return true, alias


def band_measures(true: np.ndarray, alias: np.ndarray) -> dict:
    """L_max (worst local alias/signal ratio) and M_max (screen excess), with their bands."""
    a_dbfs = 10 * np.log10(np.maximum(alias * OUT_MS, 1e-300))
    s_dbfs = 10 * np.log10(np.maximum(true * OUT_MS, 1e-300))
    ratio = a_dbfs - s_dbfs
    valid = a_dbfs > ALIAS_FLOOR_DBFS
    if valid.any():
        i = int(np.argmax(np.where(valid, ratio, -np.inf)))
        l_max, l_band, l_lev = float(ratio[i]), float(BANDS_FC[i]), float(a_dbfs[i])
    else:
        l_max, l_band, l_lev = -math.inf, math.nan, math.nan
    thr = np.maximum(s_dbfs + SPL_PER_DBFS - MASK_OFFSET_DB, ATH_DB_SPL)
    margin = a_dbfs + SPL_PER_DBFS - thr
    j = int(np.argmax(margin))
    return {"L_max": l_max, "L_band_hz": l_band, "L_alias_dbfs": l_lev,
            "M_max": float(margin[j]), "M_band_hz": float(BANDS_FC[j]),
            "M_alias_dbfs": float(a_dbfs[j])}  # fmt: skip


# All bands of one evaluation: the 30 1/3-octave bands plus [20 Hz, 20 kHz] for R_aud.
EVAL_LO = np.concatenate((BANDS_LO, [AUDIBLE[0]]))
EVAL_HI = np.concatenate((BANDS_HI, [AUDIBLE[1]]))


def evaluate(spec: CumSpectrum, fs_out: float, stages: tuple[HalfBand, ...] = ()) -> dict:
    """R_aud, L_max and M_max of one spectrum for one output rate and decimator chain."""
    true, alias = fold_into_bands(spec, EVAL_LO, EVAL_HI, fs_out, stages, sub=16 if stages else 1)
    out = band_measures(true[:-1], alias[:-1])
    out["R_aud"] = db(alias[-1])
    return out


# --------------------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------------------


def part_a() -> dict:
    """Per-note renders at 8× (three seeds), broad-band and band-level measures."""
    out: dict = {}
    spectra: dict = {}
    for system in SYSTEMS:
        out[system] = {}
        for note in NOTES:
            runs = []
            for k, seed in enumerate(SEEDS):
                y, block = render(system, note, FS_HI, T_RENDER, seed=seed)
                f0 = block.frequency_hz
                f, s = combined_psd(y, FS_HI, f0)
                total = float(np.var(y))
                m = alias_metrics(f, s, total)
                spec = CumSpectrum.from_psd(f, s, total, split=f0)
                bands = evaluate(spec, FS)
                m.update({key: bands[key] for key in ("L_max", "M_max")})
                m["var_over_target"] = total / OUT_MS
                m["psd_closure"] = float(s.sum() * (f[1] - f[0]) / total)
                _, s1 = psd(y, FS_HI, order=1)  # estimator check: first-difference prewhitening
                m["R_nyq_order1"] = db(s1[f > FS / 2].sum() * (f[1] - f[0]) / total)
                runs.append((m, bands))
                if k == 0:
                    spectra[(system, note)] = (f, s, total, f0)
            b48 = Dynamical("osc", catalog=CATALOG, system=system, note=note)
            b48.reset(FS)
            keys = [key for key in runs[0][0] if key not in ("var_over_target", "psd_closure")]
            row = {"f0": note_to_hz(note), "substeps_48k": b48.substeps_per_sample()}
            for key in keys:
                vals = [r[0][key] for r in runs]
                fin = [v for v in vals if math.isfinite(v)]
                mean = db(np.mean([10 ** (v / 10) for v in fin])) if fin else -math.inf
                row[key] = {"mean": mean, "min": min(vals), "max": max(vals)}
            row["var_over_target"] = float(np.mean([r[0]["var_over_target"] for r in runs]))
            row["psd_closure"] = float(np.mean([r[0]["psd_closure"] for r in runs]))
            row["bands_seed0"] = runs[0][1]
            out[system][note] = row
            r = row
            print(f"  {system:8s} {note:3s} R_nyq {r['R_nyq']['mean']:8.1f} "
                  f"[{r['R_nyq']['min']:.1f}, {r['R_nyq']['max']:.1f}]  R_aud "
                  f"{r['R_aud']['mean']:8.1f}  L_max {r['L_max']['max']:7.1f} "
                  f"@{r['bands_seed0']['L_band_hz']:7.0f} Hz  M_max {r['M_max']['max']:7.1f}  "
                  f"(order-1 {r['R_nyq_order1']['mean']:8.1f}, closure {r['psd_closure']:.3f}, "
                  f"n_sub {r['substeps_48k']})")  # fmt: skip
    return {"metrics": out, "spectra": spectra}


def part_checks(spectra: dict) -> dict:
    """32× re-computation for the top notes; native-48 kHz PSD versus the fold prediction."""
    res: dict = {"os32": {}, "native48": {}}
    native_curves = {}
    for system in SYSTEMS:
        for note in ("A6", "A7", "C8"):
            y, block = render(system, note, FS_CHECK, 3.0, seed=SEEDS[0])
            f, s = combined_psd(y, FS_CHECK, block.frequency_hz)
            m = alias_metrics(f, s, float(np.var(y)))
            res["os32"][f"{system}/{note}"] = m
            print(f"  32x {system:8s} {note}: R_nyq {m['R_nyq']:7.1f}  R_aud {m['R_aud']:7.1f}")
        for note in ("A7", "C8"):
            f_hi, s_hi, total_hi, _ = spectra[(system, note)]
            # Prediction on the 48 kHz grid: bins of the 8× grid map exactly onto it.
            k_out = np.rint(fold(f_hi, FS) / BIN_HZ).astype(int)
            pred = np.bincount(k_out, weights=s_hi, minlength=k_out.max() + 1)
            pred_true = np.where(f_hi <= FS / 2, s_hi, 0.0)[: pred.size]
            y48, block48 = render(system, note, FS, T_RENDER, seed=SEEDS[0])
            f48, s48 = combined_psd(y48, FS, block48.frequency_hz)
            total48 = float(np.var(y48))
            n = min(pred.size, f48.size)
            band = {}
            for lo, hi in ((5e3, 10e3), (10e3, 16e3), (16e3, 20e3), (20e3, 23.5e3)):
                m = (f48[:n] >= lo) & (f48[:n] < hi)
                meas = db(s48[:n][m].sum() / total48 * BIN_HZ)
                p = db(pred[:n][m].sum() / total_hi * BIN_HZ)
                u = db(pred_true[:n][m].sum() / total_hi * BIN_HZ)
                band[f"{lo / 1e3:g}-{hi / 1e3:g}k"] = {
                    "measured": meas, "predicted": p, "unaliased": u,
                    "alias_contribution_db": p - u, "mismatch_db": meas - p,
                    # The check discriminates only where aliasing adds clearly more than the
                    # measured-vs-predicted scatter (0.13 dB over all bands and cases).
                    "discriminating": bool(p - u > 0.3 and p - u > 2 * abs(meas - p)),
                }  # fmt: skip
            res["native48"][f"{system}/{note}"] = band
            native_curves[(system, note)] = (f48[:n], s48[:n] / total48, pred[:n] / total_hi,
                                             pred_true[:n] / total_hi)  # fmt: skip
            txt = "  ".join(f"{k}: {v['measured']:.2f}/{v['predicted']:.2f}/{v['unaliased']:.2f}"
                            for k, v in band.items())  # fmt: skip
            print(f"  native48 {system:8s} {note} (meas/pred/true dB): {txt}")
    return {"results": res, "curves": native_curves}


def universal_cases() -> list[tuple[str, str, float, int, bool]]:
    """(system, observable, u, seed, is_default) for every part-B render."""
    cases = []
    for system in SYSTEMS:
        entry = CATALOG[system]
        cases += [(system, entry.default_observable, entry.u_default, s, True) for s in SEEDS]
        for obs in get_system(system).audio_variables:
            cases += [(system, obs, u, SEEDS[0], False) for u in U_GRID]
    return cases


def part_b(designs: dict) -> dict:
    """Universal spectra at A4: tails, n_T, and a semitone scan of every measure."""
    configs = {
        "48k": (FS, ()),
        "44.1k": (FS_441, ()),
        "48k_2x": (FS, (designs["hb80"],)),
        "48k_4x": (FS, (designs["hb80"], designs["hb80_stage1"])),
    }
    runs = []
    curves = {}
    f_ref = note_to_hz(REF_NOTE)
    for system, obs, u, seed, is_default in universal_cases():
        y, block = render(system, REF_NOTE, FS_HI, T_RENDER, seed=seed, param=u, observable=obs)
        f0 = block.frequency_hz
        total = float(np.var(y))
        f, s = combined_psd(y, FS_HI, f0, nperseg=UNIV_NPERSEG)
        n, g = tail_curve(f, s, total, f0)
        run = {"system": system, "observable": obs, "u": u, "seed": seed, "default": is_default,
               **{f"n{abs(int(t))}": crossing(n, g, t) for t in THRESHOLDS_DB}}  # fmt: skip
        if system == "chua":
            run["psd_slope_db_per_octave"] = psd_slope(n, s, f0)
        # Pre-blocker universal spectrum: divide out the DC blocker's known response.
        h2 = dc_blocker_gain2(f, FS_HI)
        s_pre = np.where(f > 0, s / np.where(h2 > 0, h2, 1.0), 0.0)
        univ = CumSpectrum.from_psd(f / f_ref, s_pre * f_ref, total, split=1.0)
        scan: dict = {}
        for midi in SCAN_MIDI:
            note = midi_name(midi)
            spec = univ.at(note_to_hz(note))
            row = {"R_nyq": db(spec.power(np.array([FS / 2]), np.array([spec.f_max]))[0])}
            for cname, (fs_out, stages) in configs.items():
                ev = evaluate(spec, fs_out, stages)
                row[cname] = {k: ev[k] for k in ("R_aud", "L_max", "M_max", "M_band_hz",
                                                  "L_band_hz", "L_alias_dbfs")}  # fmt: skip
            scan[note] = row
        run["scan"] = scan
        runs.append(run)
        if is_default and seed == SEEDS[0]:
            curves[system] = (n, g, s * f0 / total, scan)
        print(f"  {system:8s} {obs} u={u:.3f} seed {seed}: n60 {run['n60']:.2f} "
              f"n80 {run['n80']:.2f} n100 {run['n100']:.2f}"
              + (f"  slope {run['psd_slope_db_per_octave']:.1f} dB/oct"
                 if "psd_slope_db_per_octave" in run else ""))  # fmt: skip
    return {"runs": runs, "curves": curves, "configs": list(configs)}


CRITERIA = {
    # name: (config, key, limit)
    "R_nyq<=-80": (None, "R_nyq", CRIT_GLOBAL_DB),
    "R_aud<=-80": ("48k", "R_aud", CRIT_GLOBAL_DB),
    "L<=-40": ("48k", "L_max", L_CRIT_DB),
    "screen<=0": ("48k", "M_max", 0.0),
    "44.1k R_aud<=-80": ("44.1k", "R_aud", CRIT_GLOBAL_DB),
    "44.1k screen<=0": ("44.1k", "M_max", 0.0),
    "2x R_aud<=-80": ("48k_2x", "R_aud", CRIT_GLOBAL_DB),
    "2x L<=-40": ("48k_2x", "L_max", L_CRIT_DB),
    "2x screen<=0": ("48k_2x", "M_max", 0.0),
    "4x R_aud<=-80": ("48k_4x", "R_aud", CRIT_GLOBAL_DB),
    "4x L<=-40": ("48k_4x", "L_max", L_CRIT_DB),
    "4x screen<=0": ("48k_4x", "M_max", 0.0),
}


def highest_passing(scan: dict, config: str | None, key: str, limit: float) -> int:
    """MIDI number of the highest note below the first failing semitone (109 = none fails)."""
    for midi in SCAN_MIDI:
        row = scan[midi_name(midi)]
        v = row[key] if config is None else row[config][key]
        if v > limit:
            return midi - 1
    return SCAN_MIDI[-1] + 1


def thresholds(runs: list) -> dict:
    """Highest safe note per system, scope and criterion, plus the case that sets it."""
    scopes = {
        "default": lambda r: r["default"],
        "default_obs_all_u": lambda r: (r["default"] or r["observable"] ==
                                        CATALOG[r["system"]].default_observable),
        "any_obs_all_u": lambda r: True,
    }  # fmt: skip
    out: dict = {}
    for system in SYSTEMS:
        out[system] = {}
        for sname, sel in scopes.items():
            rs = [r for r in runs if r["system"] == system and sel(r)]
            d: dict = {}
            for t in (60, 80):
                worst = max(rs, key=lambda r: r[f"n{t}"])
                d[f"n{t}"] = worst[f"n{t}"]
                d[f"n{t}_case"] = f"{worst['observable']}, u={worst['u']:.3f}"
            for cname, (config, key, limit) in CRITERIA.items():
                vals = [(highest_passing(r["scan"], config, key, limit), r) for r in rs]
                midi, r = min(vals, key=lambda v: v[0])
                d[cname] = {"note": midi_name(midi) if midi <= SCAN_MIDI[-1] else "> C8",
                            "midi": midi, "case": f"{r['observable']}, u={r['u']:.3f}, "
                            f"seed {r['seed']}"}  # fmt: skip
            out[system][sname] = d
    return out


def part_c_designs() -> dict:
    """Half-band decimators for 2× and 4× at 48 kHz, and 2× at 44.1 kHz."""
    designs = {
        "hb60": design_halfband(2 * FS, AUDIBLE[1], 60.0),
        "hb80": design_halfband(2 * FS, AUDIBLE[1], 80.0),
        "hb100": design_halfband(2 * FS, AUDIBLE[1], 100.0),
        # 4× first stage (192 → 96 kHz): keep 0–20 kHz, stop from 96 − 20 = 76 kHz
        "hb80_stage1": design_halfband(
            4 * FS, 2 * FS / 2 - AUDIBLE[1] - (FS - 2 * AUDIBLE[1]), 80.0
        ),  # fmt: skip
        "hb60_44k1": design_halfband(2 * FS_441, AUDIBLE[1], 60.0),
        "hb80_44k1": design_halfband(2 * FS_441, AUDIBLE[1], 80.0),
    }
    for name, d in designs.items():
        print(f"  {name:12s} rate {d.rate / 1e3:6.1f} kHz: {d.taps.size} taps ({d.nonzero} "
              f"non-zero), beta {d.beta:.2f}, stopband {d.stopband_db:.1f} dB, delay "
              f"{d.delay_ms:.3f} ms")  # fmt: skip
    return designs


def part_c(spectra: dict, designs: dict, univ_curves: dict) -> dict:
    """Residual audible alias (R_aud) for 2× and 4× with the designed decimators."""
    out: dict = {"designs": {k: {"rate": d.rate, "numtaps": int(d.taps.size),
                                 "nonzero": d.nonzero, "beta": d.beta,
                                 "stopband_db": d.stopband_db, "delay_ms": d.delay_ms}
                             for k, d in designs.items()}, "residual": {}}  # fmt: skip
    chains = {"1x": (), "2x_hb60": (designs["hb60"],), "2x_hb80": (designs["hb80"],),
              "4x_hb80": (designs["hb80"], designs["hb80_stage1"])}  # fmt: skip
    for (system, note), (f, s, total, f0) in spectra.items():
        if note not in ("A6", "A7", "C8"):
            continue
        direct = CumSpectrum.from_psd(f, s, total, split=f0)
        row = {}
        for cname, stages in chains.items():
            # 4× needs content up to 172 kHz and beyond: use the universal spectrum (n ≤ 436).
            if cname.startswith("4x"):
                row[cname] = univ_curves[system][3][note]["48k_4x"]["R_aud"]
            else:
                row[cname] = evaluate(direct, FS, stages)["R_aud"]
        out["residual"][f"{system}/{note}"] = row
        print(f"  {system:8s} {note}: " + "  ".join(f"{k} {v:7.1f}" for k, v in row.items()))
    return out


def part_d(thr: dict) -> dict:
    """Direct 8× renders of the scope-defining worst cases at and above their threshold."""
    out: dict = {}
    seen = set()
    for scope in ("default_obs_all_u", "any_obs_all_u"):
        for cname in ("R_aud<=-80", "screen<=0"):
            midi, system = min((thr[s][scope][cname]["midi"], s) for s in SYSTEMS)
            case = thr[system][scope][cname]["case"]
            obs = case.split(",")[0]
            u = float(case.split("u=")[1].split(",")[0])
            for m in (midi, midi + 1):
                key = (system, obs, round(u, 3), m)
                if key in seen or m > SCAN_MIDI[-1]:
                    continue
                seen.add(key)
                note = midi_name(m)
                y, block = render(system, note, FS_HI, T_RENDER, seed=SEEDS[0], param=u,
                                  observable=obs)  # fmt: skip
                f, s = combined_psd(y, FS_HI, block.frequency_hz)
                spec = CumSpectrum.from_psd(f, s, float(np.var(y)), split=block.frequency_hz)
                ev = evaluate(spec, FS)
                ev["R_nyq"] = db(spec.power(np.array([FS / 2]), np.array([spec.f_max]))[0])
                out[f"{system}/{obs}/u={u:g}/{note}"] = ev
                print(f"  direct {system} {obs} u={u:g} {note}: R_nyq {ev['R_nyq']:.1f} R_aud "
                      f"{ev['R_aud']:.1f}  L_max {ev['L_max']:.1f}  M_max {ev['M_max']:.1f} "
                      f"@{ev['M_band_hz']:.0f} Hz")  # fmt: skip
    return out


def pitch_lock_reach() -> dict:
    """With pitch lock off, the fundamental is f0·P(u_default)/P(u): its highest value."""
    out = {}
    us = np.linspace(0.0, 1.0, 401)
    for system in SYSTEMS:
        e = CATALOG[system]
        ratio = float(e.period(e.u_default) / min(e.period(u) for u in us))
        out[system] = {"max_ratio": ratio, "semitones": 12 * math.log2(ratio)}
    return out


# --------------------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------------------


def style(ax) -> None:
    ax.grid(True, color=GRID, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#8a8984")
    ax.tick_params(colors=INK2, labelsize=9)


def fig_vs_note(metrics: dict, curves: dict) -> None:
    """R_nyq and L_max versus note: semitone scan (lines) and direct renders (dots)."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharex=True)
    midis = np.array(SCAN_MIDI)
    direct_m = [round(hz_to_midi(note_to_hz(n))) for n in NOTES]
    for ax, key, title, lim in (
        (axes[0], "R_nyq", "Power above 24 kHz (folds at 48 kHz), dB re total", (FLOOR_DB, 0)),
        (axes[1], "L_max", "Worst 1/3-octave band: alias / signal in that band, dB", (-120, 10)),
    ):
        for system in SYSTEMS:
            scan = curves[system][3]
            if key == "R_nyq":
                v = [scan[midi_name(m)]["R_nyq"] for m in midis]
            else:
                v = [scan[midi_name(m)]["48k"]["L_max"] for m in midis]
            v = np.clip(np.array(v, dtype=float), lim[0] - 10, None)
            ax.plot(midis, v, "-", color=COLORS[system], lw=2, label=LABELS[system])
            d = [metrics[system][n][key]["max" if key == "L_max" else "mean"] for n in NOTES]
            ax.plot(direct_m, np.clip(np.array(d, dtype=float), lim[0] - 10, None), "o",
                    color=COLORS[system], ms=6, mec="white", mew=1.0)  # fmt: skip
        levels = (-60, -80) if key == "R_nyq" else (L_CRIT_DB,)
        for level in levels:
            ax.axhline(level, color=INK2, lw=0.8, ls="--")
            ax.text(46, level + 1.5, f"{level:.0f} dB", fontsize=8, color=INK2)
        ax.set_ylim(*lim)
        ax.set_xlim(45, 108)
        ax.set_xticks(direct_m, NOTES)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_xlabel("note (default parameter and observable)", fontsize=9)
        style(ax)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.text(0.01, 0.005, "Lines: every semitone, from the universal A4 spectrum. Dots: direct "
             f"8× renders at the note (R_nyq mean, L_max worst of {len(SEEDS)} seeds). "
             f"L_max ignores bands whose alias is below {ALIAS_FLOOR_DBFS:.0f} dBFS.",
             fontsize=8, color=INK2)  # fmt: skip
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT_DIR / "aliasing_vs_note.png", dpi=150)
    plt.close(fig)


def fig_bands(spectra: dict) -> None:
    """Band levels (signal, alias, masked threshold) at C8 for Rössler and Lorenz."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.0), sharey=True)
    for ax, (system, note) in zip(axes, (("rossler", "A7"), ("rossler", "C8"),
                                         ("lorenz", "C8")), strict=True):  # fmt: skip
        f, s, total, f0 = spectra[(system, note)]
        spec = CumSpectrum.from_psd(f, s, total, split=f0)
        true, alias = fold_into_bands(spec, BANDS_LO, BANDS_HI, FS, sub=1)
        s_db = 10 * np.log10(np.maximum(true * OUT_MS, 1e-300))
        a_db = 10 * np.log10(np.maximum(alias * OUT_MS, 1e-300))
        thr = np.maximum(s_db - MASK_OFFSET_DB, ATH_DB_SPL - SPL_PER_DBFS)
        ax.step(BANDS_FC, s_db, where="mid", color="#8a8984", lw=2.2, label="signal in band")
        ax.step(BANDS_FC, a_db, where="mid", color=COLORS[system], lw=2.0,
                label="folded (alias) power in band")  # fmt: skip
        ax.step(BANDS_FC, thr, where="mid", color=INK, lw=1.0, ls="--",
                label="screen threshold (masking or quiet)")  # fmt: skip
        ax.set_xscale("log")
        ax.set_ylim(-170, 0)
        ax.set_xlim(20, 22000)
        ax.set_title(f"{LABELS[system]}, {note}", fontsize=10, loc="left", color=INK)
        ax.set_xlabel("1/3-octave band centre (Hz)", fontsize=9)
        style(ax)
    axes[0].set_ylabel("band power, dBFS (box at −12 dBFS RMS)", fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.text(0.01, 0.01, "Default parameter and observable, 8× render, seed 11. Threshold in "
             "quiet drawn at the calibration full-scale sine = 96 dB SPL.",
             fontsize=8, color=INK2)  # fmt: skip
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(OUT_DIR / "band_levels.png", dpi=150)
    plt.close(fig)


def fig_screen(runs: list) -> None:
    """Screen excess M_max versus note: default vs worst over u and observables; 1× vs 2×."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    midis = np.array(SCAN_MIDI)
    for ax, config, title in ((axes[0], "48k", "1× at 48 kHz"),
                              (axes[1], "48k_2x", "2× + 63-tap half-band")):  # fmt: skip
        for system in SYSTEMS:
            rs = [r for r in runs if r["system"] == system]
            dflt = [r for r in rs if r["default"]]
            v_def = np.max([[r["scan"][midi_name(m)][config]["M_max"] for m in midis]
                            for r in dflt], axis=0)  # fmt: skip
            v_all = np.max([[r["scan"][midi_name(m)][config]["M_max"] for m in midis]
                            for r in rs], axis=0)  # fmt: skip
            ax.plot(midis, v_def, "-", color=COLORS[system], lw=2, label=LABELS[system])
            ax.plot(midis, v_all, ":", color=COLORS[system], lw=1.6)
        ax.axhline(0, color=INK2, lw=0.8, ls="--")
        ax.set_ylim(-80, 50)
        ax.set_xlim(57, 108)
        ticks = [57, 69, 81, 93, 105, 108]
        ax.set_xticks(ticks, [midi_name(m) for m in ticks])
        ax.set_title(f"Screen excess M_max, {title}, dB", fontsize=10, loc="left", color=INK)
        ax.set_xlabel("note", fontsize=9)
        style(ax)
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.text(
        0.01,
        0.005,
        "Solid: default parameter and observable. Dotted: worst over u grid "
        "and all audible observables. Above 0 dB the alias exceeds in-band masking and the "
        "threshold in quiet (96 dB SPL full-scale sine).",
        fontsize=8,
        color=INK2,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT_DIR / "screen_vs_note.png", dpi=150)
    plt.close(fig)


def fig_tail(curves: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for system in SYSTEMS:
        n, g, s, _ = curves[system]
        m = (n >= 1) & (n <= 300)
        axes[0].plot(n[m], g[m], color=COLORS[system], lw=2, label=LABELS[system])
        k = max(1, round(0.25 / (n[1] - n[0])))  # smooth to ~¼ harmonic for display
        ss = np.convolve(s, np.ones(k) / k, mode="same")
        mm = (n >= 0.3) & (n <= 300)
        axes[1].plot(n[mm], 10 * np.log10(np.maximum(ss[mm], 1e-300)), color=COLORS[system],
                     lw=1.4, label=LABELS[system])  # fmt: skip
    for level in (-60, -80):
        axes[0].axhline(level, color=INK2, lw=0.8, ls="--")
        axes[0].text(1.05, level + 2, f"{level} dB", fontsize=8, color=INK2)
    for note in ("A5", "A6", "A7", "C8"):  # where a note's 48 kHz fold point sits
        n_fold = FS / 2 / note_to_hz(note)
        axes[0].axvline(n_fold, color="#8a8984", lw=0.7, ls=":")
        axes[0].text(n_fold * 1.03, -195, f"{note}", fontsize=7.5, color=INK2, rotation=90,
                     va="bottom")  # fmt: skip
    nn = np.array([16.0, 128.0])
    axes[1].plot(nn, -85.0 - 24 * np.log2(nn / 16), color=INK2, lw=1.0, ls="--")
    axes[1].text(30, -95, "−24 dB/octave (∝ f⁻⁸)", fontsize=8, color=INK2)
    axes[0].set_title("Tail fraction G(n) = P(f > n·f₀) / P_total, dB", fontsize=10, loc="left")
    axes[1].set_title("PSD per unit harmonic, dB re total (¼-harmonic smoothing)",
                      fontsize=10, loc="left")  # fmt: skip
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("harmonic number n = f / f₀", fontsize=9)
        ax.set_ylim(-200, 5)
        style(ax)
    axes[0].set_xlim(1, 300)
    axes[1].set_xlim(0.3, 300)
    axes[0].legend(frameon=False, fontsize=9, loc="lower left")
    fig.text(0.01, 0.035, f"Universal curves ({REF_NOTE} renders at 8×): at 48 kHz a note f₀ "
             "folds from n = 24 000/f₀ (dotted verticals). Default parameter and observable.",
             fontsize=8, color=INK2)  # fmt: skip
    fig.text(
        0.01,
        0.005,
        "Hann + 2nd-difference prewhitening; for the smooth systems the curves "
        "below ≈ −220 dB are the estimator floor, not signal.",
        fontsize=8,
        color=INK2,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT_DIR / "tail_universal.png", dpi=150)
    plt.close(fig)


def fig_native(curves: dict) -> None:
    fig, axes = plt.subplots(1, len(SYSTEMS), figsize=(14, 3.6), sharey=True)
    for ax, system in zip(axes, SYSTEMS, strict=True):
        f, meas, pred, true = curves[(system, "C8")]

        def sm(v: np.ndarray) -> np.ndarray:
            return np.convolve(v, np.ones(16) / 16, mode="same")

        m = f > 100
        alias = np.maximum(pred - true, 0.0)
        ax.plot(f[m] / 1e3, 10 * np.log10(np.maximum(sm(true)[m] * BIN_HZ, 1e-300)),
                color="#8a8984", lw=2.2, label="true spectrum (8× render, ≤ 24 kHz)")  # fmt: skip
        ax.plot(f[m] / 1e3, 10 * np.log10(np.maximum(sm(meas)[m] * BIN_HZ, 1e-300)),
                color=COLORS[system], lw=1.0, label="native 48 kHz render")  # fmt: skip
        ax.plot(f[m] / 1e3, 10 * np.log10(np.maximum(sm(alias)[m] * BIN_HZ, 1e-300)),
                color=INK, lw=1.0, ls="--", label="predicted folded part alone")  # fmt: skip
        ax.set_title(f"{LABELS[system]}, C8", fontsize=10, loc="left")
        ax.set_xlabel("frequency (kHz)", fontsize=9)
        ax.set_ylim(-160, 0)
        style(ax)
    axes[0].set_ylabel("power per 5.9 Hz bin, dB re total", fontsize=9)
    axes[0].legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.text(0.01, 0.01, "C8, default parameter and observable, 16-bin (94 Hz) smoothing. "
             "The native render follows true + folded; the dashed curve is what aliasing adds.",
             fontsize=8, color=INK2)  # fmt: skip
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(OUT_DIR / "native48_vs_prediction.png", dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------------------


def dc_check() -> dict:
    """Side check: output power at low notes with the 5 Hz DC blocker versus 0.01 Hz.

    Patches the module constant ``DC_BLOCK_HZ`` of the block module *in this process only*
    (the engine source is not modified). 60 s renders at 48 kHz with the first 20 s
    discarded (the 0.01 Hz blocker has a 16 s time constant), three seeds. Also reports the
    share of the output power below 10 and 20 Hz (Welch, 0.09 Hz bins).
    """
    import chaotic_sound.blocks.dynamical as dyn

    original = dyn.DC_BLOCK_HZ
    out: dict = {}
    try:
        for system in ("thomas", "duffing", "lorenz", "rossler", "chua"):
            for note in ("A1", "A2", "A4"):
                res = {}
                for label, cutoff in (("5Hz", original), ("0.01Hz", 0.01)):
                    dyn.DC_BLOCK_HZ = cutoff
                    v, b10, b20 = [], [], []
                    for s in SEEDS:
                        y = render(system, note, FS, 60.0, seed=s, skip=20.0)[0]
                        v.append(float(np.var(y)) / OUT_MS)
                        f, p = welch(y, fs=FS, nperseg=2**19, noverlap=2**18, window="hann")
                        tot = p.sum()
                        b10.append(float(p[f < 10].sum() / tot))
                        b20.append(float(p[f < 20].sum() / tot))
                    res[label] = {"var_over_target": float(np.mean(v)),
                                  "frac_below_10Hz": float(np.mean(b10)),
                                  "frac_below_20Hz": float(np.mean(b20))}  # fmt: skip
                a, b = res["5Hz"], res["0.01Hz"]
                res["loss_db"] = db(a["var_over_target"] / b["var_over_target"])
                # Audible (≥ 20 Hz) power, relative to the target, with each blocker.
                res["audible_var_over_target_5Hz"] = a["var_over_target"] * (
                    1 - a["frac_below_20Hz"]
                )
                res["audible_var_over_target_0.01Hz"] = b["var_over_target"] * (
                    1 - b["frac_below_20Hz"])  # fmt: skip
                out[f"{system}/{note}"] = res
                print(f"  {system:8s} {note}: var/target {a['var_over_target']:.3f} (5 Hz) vs "
                      f"{b['var_over_target']:.3f} (0.01 Hz): {res['loss_db']:+.2f} dB; below "
                      f"20 Hz {a['frac_below_20Hz']:.3f} / {b['frac_below_20Hz']:.3f}; audible "
                      f"var/target {res['audible_var_over_target_5Hz']:.3f} / "
                      f"{res['audible_var_over_target_0.01Hz']:.3f}")  # fmt: skip
    finally:
        dyn.DC_BLOCK_HZ = original
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import chaotic_sound.blocks.dynamical as dyn

    assert dyn.DC_BLOCK_HZ == DC_BLOCK_HZ, "DC blocker cut-off changed in the engine"
    if "--dc-check" in sys.argv:
        print("Side check: DC blocker and output power at low notes")
        (OUT_DIR / "dc_check.json").write_text(json.dumps(dc_check(), indent=1))
        return
    t0 = time.time()
    print("Part C (designs first): half-band decimators")
    designs = part_c_designs()
    print(f"  ({time.time() - t0:.0f} s)\nPart A: per-note renders at 8x")
    a = part_a()
    print(f"  ({time.time() - t0:.0f} s)\nChecks: 32x and native 48 kHz")
    checks = part_checks(a["spectra"])
    print(f"  ({time.time() - t0:.0f} s)\nPart B: universal spectra at {REF_NOTE}")
    b = part_b(designs)
    thr = thresholds(b["runs"])
    for system in SYSTEMS:
        for scope, d in thr[system].items():
            print(f"  {system:8s} {scope:18s} n80 {d['n80']:6.2f} ({d['n80_case']}) " + "  ".join(
                f"{c}: {d[c]['note']}" for c in CRITERIA))  # fmt: skip
    print(f"  ({time.time() - t0:.0f} s)\nPart C: residual alias with oversampling")
    c = part_c(a["spectra"], designs, b["curves"])
    print(f"  ({time.time() - t0:.0f} s)\nPart D: direct checks of the worst cases")
    d = part_d(thr)
    # Universal-vs-direct agreement at the part-A notes (default case, seed 11).
    agree = {}
    for system in SYSTEMS:
        scan = b["curves"][system][3]
        for note in ("A5", "A6", "A7", "C8"):
            m = a["metrics"][system][note]
            bs = m["bands_seed0"]
            u_row = scan[note]
            agree[f"{system}/{note}"] = {
                "R_nyq": [m["R_nyq"]["mean"], u_row["R_nyq"]],
                "R_aud": [m["R_aud"]["mean"], u_row["48k"]["R_aud"]],
                "L_max": [bs["L_max"], u_row["48k"]["L_max"]],
                "M_max": [bs["M_max"], u_row["48k"]["M_max"]],
            }
    runs_out = []
    for r in b["runs"]:
        rr = {k: v for k, v in r.items() if k != "scan"}
        rr["scan"] = {note: row for note, row in r["scan"].items()
                      if note in ("A4", "A5", "A6", "A7", "C8") or r["default"]}  # fmt: skip
        runs_out.append(rr)
    results = {
        "settings": {"fs": FS, "fs_hi": FS_HI, "fs_check": FS_CHECK, "seeds": SEEDS,
                     "t_render_s": T_RENDER, "t_skip_s": T_SKIP, "bin_hz": BIN_HZ,
                     "ref_note": REF_NOTE, "univ_bin_hz": FS_HI / UNIV_NPERSEG,
                     "u_grid": U_GRID, "out_ms": OUT_MS, "spl_per_dbfs": SPL_PER_DBFS,
                     "alias_floor_dbfs": ALIAS_FLOOR_DBFS, "l_crit_db": L_CRIT_DB},
        "per_note": a["metrics"],
        "checks": checks["results"],
        "universal_runs": runs_out,
        "thresholds": thr,
        "criteria": {k: list(v) for k, v in CRITERIA.items()},
        "oversampling": c,
        "direct_worst_cases": d,
        "universal_vs_direct": agree,
        "pitch_lock_off_reach": pitch_lock_reach(),
    }  # fmt: skip
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=1))
    fig_vs_note(a["metrics"], b["curves"])
    fig_bands(a["spectra"])
    fig_screen(b["runs"])
    fig_tail(b["curves"])
    fig_native(checks["curves"])
    print(f"Done in {time.time() - t0:.0f} s; wrote {OUT_DIR}")


CATALOG = load_default_catalog()

if __name__ == "__main__":
    main()
