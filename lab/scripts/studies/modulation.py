"""Study: how fast can a dynamical box's parameter be modulated (engine v0.3).

Pitch lock (k = P(u)·f₀) and loudness normalization (s(u)·(x − μ(u))) use catalog tables
measured at *fixed* parameter values, so they assume that the trajectory follows the
attractor adiabatically. This script drives u of Lorenz, Chua, Rössler and the Rikitake
dynamo (note A3, default observables) with a full-range sine LFO whose period goes from 20 s
down to 0.01 s, and measures against static references taken at fixed u:

(a) pitch, with two estimators:
    - *centroid*: power-weighted instantaneous frequency of the band-passed audio
      (f₀/1.6 … 1.6·f₀; equal to the band's spectral centroid in the window);
    - *loop rate*: inverse duration of each loop, from the maxima of the heard variable
      (a direct measure of the oscillation period that pitch lock controls).
    Both are calibrated with a time-warp test (static audio warped by a known ±50 c FM).
(b) loudness: phase-binned RMS against the static RMS at the same u, and the mean of
    s = (x_obs − μ(u))/σ(u) before the DC blocker (ideal: 0);
(c) the attractor: safety resets, the nearest-neighbour distance from the state to the
    static attractor clouds at the same u (in static σ units), and the use of the safety box.

Engine v0.3 smooths u with a one-pole of time constant τ = max(5 ms, 2/f₀) (ADR 0013). The
script bins the LFO cycle by the phase of the *smoothed* u (the exact discrete one-pole lag is
removed), so up- and down-sweep bins at equal u are paired correctly, and it counts the rate
with the swing that actually reaches the box.

Extra experiments:
- square-wave (jump) responses at A3 and A1, with the v0.3 slew and with the v0.2 slew
  (5 ms only, emulated by setting ``PARAM_SLEW_PERIODS = 0`` at run time; the engine code is
  not changed);
- a safety-reset probe for abrupt jumps at A0–A3 (all five systems; Chua with 9 seeds and
  both slews), the default modulator (T = 4 s) with square and ramp shapes, and low-note
  full-range sine/triangle drives on Chua;
- Chua with the non-default observable x (mirror single scrolls);
- Lorenz at A2/A3/A4 at the same number of periods per sweep;
- a bit-exact cross-check against ``Patch.render``; a few WAV examples.

Usage (from ``lab/``)::

    caffeinate -is uv run python scripts/studies/modulation.py

Writes figures, WAVs and ``results.json`` to ``outputs/studies/modulation/`` and prints the
Markdown tables used in ``docs/studies/modulation.md``. Runtime ≈ 2 minutes on an M1 Pro
(114 s in the last run, with 5 worker processes).
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
from scipy.fft import next_fast_len
from scipy.signal import butter, hilbert, sosfiltfilt, welch
from scipy.spatial import cKDTree
from scipy.stats import beta as beta_dist
from scipy.stats import fisher_exact

import chaotic_sound.blocks.dynamical as dynamical_module
from chaotic_sound.blocks import BlockContext, Dynamical
from chaotic_sound.blocks.modulator import shape_value
from chaotic_sound.catalog import load_default_catalog
from chaotic_sound.dsp import soft_clip
from chaotic_sound.patch import Patch
from chaotic_sound.pitch import note_to_hz
from chaotic_sound.systems import get_system
from chaotic_sound.wav import write_wav

Array = NDArray[np.float64]

ENGINE = "v0.3"
LAB = Path(__file__).resolve().parents[2]
# MODULATION_QUICK=1 runs a tiny version of every step (a smoke test of the pipeline, not
# a result); MODULATION_OUT redirects the outputs.
QUICK = os.environ.get("MODULATION_QUICK") == "1"
OUT = Path(os.environ.get("MODULATION_OUT", LAB / "outputs" / "studies" / "modulation"))
FS = 48_000
NOTE = "A3"
F0 = note_to_hz(NOTE)
SYSTEMS = ("lorenz", "chua", "rossler", "rikitake")
PROBE_SYSTEMS = (*SYSTEMS, "duffing")  # Duffing: safety only (its pitch is the drive)
PERIODS = (20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)
if QUICK:
    PERIODS = (5.0, 1.0, 0.1, 0.02)
SEEDS = (0, 1, 2)
PROBE_SEEDS_CHUA = tuple(range(2 if QUICK else 9))
TRANSIENT_S = 2.0
ANALYZE_MIN_S = 4.0 if QUICK else 30.0
N_BINS = 24
BAND = (1 / 1.6, 1.6)  # centroid band relative to f0
STATIC_GRID = np.linspace(0.0, 1.0, 9 if QUICK else 41)
STATIC_SECONDS = 2.0 if QUICK else 10.0
STATIC_SEED, STATIC_SEED_B, CALIB_SEED = 100, 101, 200
WARP_SEEDS = (300, 301, 302)
CLOUD_STRIDE = 4
QUERY_STRIDE = 16
NN_QUANTILE = 0.99  # the same quantile for the static threshold and the modulated runs
SYMMETRY = {
    "lorenz": np.array([-1.0, -1.0, 1.0]),
    "chua": np.array([-1.0, -1.0, -1.0]),
    "rikitake": np.array([-1.0, -1.0, 1.0]),
}
NAMES = {
    "lorenz": "Lorenz",
    "chua": "Chua",
    "rossler": "Rössler",
    "rikitake": "Rikitake",
    "duffing": "Duffing",
}
JUMP_LEVEL_PERIODS = 64  # oscillation periods per square-wave level
JUMP_EDGES = np.array([0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64], dtype=float)
PROBE_NOTES = ("A0", "A1", "A2", "A3")
PROBE_CYCLES = 3 if QUICK else 60
JUMP_CYCLES = 3 if QUICK else 40
DEFAULT_PROBE_S = 20.0 if QUICK else 240.0  # default-modulator probes, per seed
SMOOTH_PROBE_S = 5.0 if QUICK else 60.0  # smooth-shape probes, per seed
WARP_CENTS = 50.0
WARP_PERIODS = (2.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)
SLEWS = ("v0.3", "v0.2")
WORKERS = 5  # worker processes (each compiles the numba kernels once)

# Chart tokens (dataviz reference palette, light mode; categorical slots 1–4 in order).
COLORS = {"lorenz": "#2a78d6", "chua": "#eb6834", "rossler": "#1baf7a", "rikitake": "#eda100"}
SEQ = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update(
    {
        "figure.facecolor": "#fcfcfb",
        "axes.facecolor": "#fcfcfb",
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 1.6,
        "font.size": 9,
        "legend.frameon": False,
    }
)

CAT = load_default_catalog()
CTX = BlockContext(catalog=CAT)

# -- capture the trajectory from the real engine path ---------------------------------------
# Dynamical.process calls the module-level name ``render_tuned``; wrapping it records the
# per-sample parameter values and the state without touching the engine code.
_render_tuned = dynamical_module.render_tuned
_captured: dict[str, Array] = {}


def _capturing_render_tuned(*args: Any) -> Any:
    resets = _render_tuned(*args)
    _captured["p_values"] = args[4]
    _captured["traj"] = args[-1]
    return resets


dynamical_module.render_tuned = _capturing_render_tuned
SLEW_PERIODS_V03 = float(dynamical_module.PARAM_SLEW_PERIODS)
DECLICK_S = float(dynamical_module.DECLICK_TIME_S)


@contextmanager
def slew_mode(slew: str) -> Iterator[None]:
    """``"v0.3"``: the engine as is; ``"v0.2"``: parameter smoother of 5 ms only (emulated)."""
    old = dynamical_module.PARAM_SLEW_PERIODS
    dynamical_module.PARAM_SLEW_PERIODS = SLEW_PERIODS_V03 if slew == "v0.3" else 0.0
    try:
        yield
    finally:
        dynamical_module.PARAM_SLEW_PERIODS = old


def slew_tau(f0: float, slew: str = "v0.3") -> float:
    """Time constant (s) of the parameter smoother at a fixed pitch f0 (spec §4.2 step 2)."""
    return max(DECLICK_S, (SLEW_PERIODS_V03 if slew == "v0.3" else 0.0) / f0)


def slew_response(period_s: float, f0: float, slew: str = "v0.3") -> tuple[float, float]:
    """Gain |H| and phase lag θ (rad) of the discrete one-pole smoother for a sine of period T."""
    alpha = 1.0 - math.exp(-1.0 / (slew_tau(f0, slew) * FS))
    z1 = np.exp(-2j * np.pi / (period_s * FS))
    h = alpha / (1.0 - (1.0 - alpha) * z1)
    return float(abs(h)), float(-np.angle(h))


@dataclass
class Run:
    """One rendered box. ``audio`` is the left channel after the DC blocker."""

    audio: Array
    s: Array  # (x_obs − μ(u))/σ(u) before the DC blocker
    u: Array  # smoothed (slewed, clipped) knob actually used, per sample
    traj: Array
    resets: int
    obs_index: int
    reset_at: Array | None = None  # sample indices where the state equals the reset state


def make_box(system: str, note: str, seed: int, observable: str | None) -> Dynamical:
    params: dict[str, Any] = {"system": system, "note": note, "seed": seed}
    if observable is not None:
        params["observable"] = observable
    box = Dynamical("osc", context=CTX, **params)
    box.reset(FS)
    return box


def render(
    system: str,
    u_raw: Array,
    *,
    note: str = NOTE,
    seed: int = 0,
    observable: str | None = None,
    slew: str = "v0.3",
) -> Run:
    """Render a box driven by the control signal ``u_raw`` (one call: block size = n)."""
    box = make_box(system, note, seed, observable)
    with slew_mode(slew):
        audio = box.process(len(u_raw), {"param": u_raw})["out"][:, 0].copy()
    e = box.entry
    u = (_captured["p_values"] - e.p_min) / (e.p_max - e.p_min)
    traj = _captured["traj"]
    i = box.system.variable_index(box.observable)
    s = (traj[:, i] - e.mean(box.observable, u)) / e.std(box.observable, u)
    reset_at = np.flatnonzero(np.all(traj == box._x_reset, axis=1))
    return Run(audio, s, u, traj, box.resets, i, reset_at)


def lfo(shape: str, period_s: float, n: int, start: int = 0) -> Array:
    """Return the modulator's output (spec §4.1 recipe), loop mode, phase 0 at sample 0."""
    c = (start + np.arange(n, dtype=np.float64)) / FS / period_s
    return shape_value(shape, c - np.floor(c))


# -- signal analysis -------------------------------------------------------------------------


def inst_freq(x: Array, f0: float, band: tuple[float, float] = BAND) -> tuple[Array, Array]:
    """Instantaneous frequency (Hz) and weight |z|² of the band-passed analytic signal."""
    sos = butter(2, [band[0] * f0, band[1] * f0], btype="bandpass", fs=FS, output="sos")
    y = sosfiltfilt(sos, x)
    z = hilbert(y, N=next_fast_len(len(y)))[: len(y)]
    f = np.gradient(np.unwrap(np.angle(z))) * FS / (2 * np.pi)
    return f, np.abs(z) ** 2


def lowpass(x: Array, fc: float) -> Array:
    sos = butter(4, fc, btype="lowpass", fs=FS, output="sos")
    return sosfiltfilt(sos, x)


def cents(f: Any, ref: Any) -> Any:
    return 1200.0 * np.log2(np.asarray(f) / np.asarray(ref))


def loop_times(x: Array) -> Array:
    """Return the times (s) of the local maxima of ``x`` (one per loop, parabolic refinement)."""
    mid = x[1:-1]
    k = np.flatnonzero((mid > x[:-2]) & (mid >= x[2:])) + 1
    a, b, c = x[k - 1], x[k], x[k + 1]
    den = a - 2 * b + c
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.where(den < 0, 0.5 * (a - c) / den, 0.0)
    return (k + d) / FS


def loops(x: Array, i0: int, i1: int) -> tuple[Array, Array, Array]:
    """Loops whose start lies in samples [i0, i1): (start time, mid time, duration), in s."""
    lt = loop_times(x)
    st, d = lt[:-1], np.diff(lt)
    m = (st * FS >= i0) & (st * FS < i1)
    return st[m], st[m] + 0.5 * d[m], d[m]


def bin_of(phase: Array) -> Array:
    return np.minimum((np.mod(phase, 1.0) * N_BINS).astype(int), N_BINS - 1)


def box_usage(system: str, traj: Array) -> float:
    """Max over time and variables of |x − centre| / half-width of the safety box.

    Phase variables (Duffing's wrapped drive phase) are left out: they always fill [0, 2π).
    """
    e = CAT[system]
    keep = [i for i in range(traj.shape[1]) if i not in get_system(system).phase_indices]
    c = 0.5 * (e.bounds_hi + e.bounds_lo)[keep]
    h = 0.5 * (e.bounds_hi - e.bounds_lo)[keep]
    return float(np.max(np.abs(traj[:, keep] - c) / h))


def updown(v: Array) -> tuple[Array, Array]:
    """Split a profile binned by the phase ψ of the smoothed u into hysteresis and symmetric.

    u(ψ) = ½ − ½|H|·cos 2πψ, so bin k (u rising) and bin N − 1 − k (u falling) have the same
    u. Returns (up − down)/2 (odd in du/dt) and (up + down)/2.
    """
    up, down = v[: N_BINS // 2], v[::-1][: N_BINS // 2]
    return 0.5 * (up - down), 0.5 * (up + down)


def rms(v: Any) -> float:
    return float(np.sqrt(np.mean(np.square(v))))


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    a = 1.0 - level
    lo = 0.0 if k == 0 else float(beta_dist.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta_dist.ppf(1 - a / 2, k + 1, n - k))
    return lo, hi


# -- static references -----------------------------------------------------------------------


@dataclass
class StaticRef:
    """Measurements at fixed u on ``STATIC_GRID`` (the adiabatic reference)."""

    system: str
    u: Array
    cents: Array  # centroid pitch vs the note
    loop_cents: Array  # mean loop rate (maxima of the observable) vs the note
    mean_s: Array
    std_s: Array
    rms: Array
    box_usage: Array
    peak: Array  # 99.9th percentile of |audio|
    trees: list[cKDTree] = field(repr=False)
    scales: list[Array] = field(repr=False)
    threshold: float = math.nan  # NN_QUANTILE of an independent static run (σ units)
    ref_err_cents: float = math.nan  # error of one static reference (centroid), RMS over u
    ref_err_loop: float = math.nan  # same for the loop rate
    ref_diff_max: tuple[float, float] = (math.nan, math.nan)
    psd_f: Array | None = None
    psd: Array | None = None  # time-weighted mean static PSD for a full-range sine sweep

    def cents_at(self, u: Array) -> Array:
        """Interpolate the static centroid pitch (cents re the note) at u."""
        return np.interp(u, self.u, self.cents)

    def loop_at(self, u: Array) -> Array:
        """Interpolate the static loop-rate pitch (cents re the note) at u."""
        return np.interp(u, self.u, self.loop_cents)

    def rms_at(self, u: Array) -> Array:
        """Interpolate the static audio RMS at u."""
        return np.interp(u, self.u, self.rms)


def static_point(system: str, u0: float, seed: int, seconds: float) -> tuple[Run, dict]:
    n_tr = FS
    n = int(seconds * FS) + n_tr
    r = render(system, np.full(n, u0), seed=seed)
    f, w = inst_freq(r.audio, F0)
    f, w = f[n_tr : -FS // 10], w[n_tr : -FS // 10]
    _, _, d = loops(r.traj[:, r.obs_index], n_tr, n)
    a = r.audio[n_tr:]
    return r, {
        "cents": float(cents(np.sum(w * f) / np.sum(w), F0)),
        "loop": float(cents(len(d) / np.sum(d), F0)),
        "mean_s": float(np.mean(r.s[n_tr:])),
        "std_s": float(np.std(r.s[n_tr:])),
        "rms": rms(a),
        "box": box_usage(system, r.traj[n_tr:]),
        "peak": float(np.quantile(np.abs(a), 0.999)),
    }


def nn_distance(ref: StaticRef, traj: Array, u: Array) -> Array:
    """Distance (in static σ units) from each state to the static clouds bracketing u."""
    g = len(ref.u)
    j = np.clip(np.floor(u * (g - 1)).astype(int), 0, g - 2)
    d = np.full(len(u), np.inf)
    for k in np.unique(j):
        m = j == k
        for gi in (k, k + 1):
            dd, _ = ref.trees[gi].query(traj[m] / ref.scales[gi], k=1)
            d[m] = np.minimum(d[m], dd)
    return d


def build_static(system: str) -> StaticRef:
    keys = ("cents", "loop", "mean_s", "std_s", "rms", "box", "peak")
    rows: dict[str, list[float]] = {k: [] for k in keys}
    trees, scales, psds = [], [], []
    pf = np.zeros(0)
    for u0 in STATIC_GRID:
        r, m = static_point(system, float(u0), STATIC_SEED, STATIC_SECONDS)
        for k in keys:
            rows[k].append(m[k])
        cloud = r.traj[FS::CLOUD_STRIDE]
        scale = cloud.std(axis=0)
        if system in SYMMETRY:
            cloud = np.vstack([cloud, cloud * SYMMETRY[system]])
        trees.append(cKDTree(cloud / scale))
        scales.append(scale)
        pf, pp = welch(r.audio[FS:], fs=FS, nperseg=2**15)
        psds.append(pp)
    # Time-weighted static spectrum of a full-range sine sweep (arcsine density of u).
    edges = np.concatenate([[0.0], 0.5 * (STATIC_GRID[1:] + STATIC_GRID[:-1]), [1.0]])
    wts = np.diff(np.arccos(1 - 2 * edges)) / np.pi  # P(u in cell) for u = (1 − cos θ)/2
    ref = StaticRef(
        system,
        STATIC_GRID.copy(),
        *(np.array(rows[k]) for k in keys),
        trees=trees,
        scales=scales,
        psd_f=pf,
        psd=np.tensordot(wts, np.array(psds), axes=1),
    )
    # NN threshold: the same quantile as reported for the modulated runs, from an
    # independent static run at the grid midpoints.
    mids = 0.5 * (STATIC_GRID[1:] + STATIC_GRID[:-1])
    dists = []
    n_c = 5 * FS
    for um in mids:
        r = render(system, np.full(n_c, um), seed=CALIB_SEED)
        tr = r.traj[FS::QUERY_STRIDE]
        dists.append(nn_distance(ref, tr, np.full(len(tr), um)))
    ref.threshold = float(np.quantile(np.concatenate(dists), NN_QUANTILE))
    # Error of the static reference itself: a second seed on every other grid point.
    sub = np.arange(0, len(STATIC_GRID), 2)
    dc, dl = [], []
    for g in sub:
        _, m = static_point(system, float(STATIC_GRID[g]), STATIC_SEED_B, STATIC_SECONDS)
        dc.append(m["cents"] - ref.cents[g])
        dl.append(m["loop"] - ref.loop_cents[g])
    ref.ref_err_cents = rms(dc) / math.sqrt(2)
    ref.ref_err_loop = rms(dl) / math.sqrt(2)
    ref.ref_diff_max = (float(np.max(np.abs(dc))), float(np.max(np.abs(dl))))
    return ref


# -- estimator calibration (time warp) -------------------------------------------------------


def complex_gain(est: Array, true: Array) -> complex:
    """Ratio of the first phase harmonics of two binned profiles."""
    e = np.exp(-2j * np.pi * (np.arange(N_BINS) + 0.5) / N_BINS)
    return complex(np.sum((est - est.mean()) * e) / np.sum((true - true.mean()) * e))


def estimator_gain(system: str) -> dict[str, dict[str, list[float]]]:
    """Warp static runs (u = 0.5) by a known ±50 c sine FM and measure both estimators.

    y(t) = x(Φ(t)) with Φ' = 2^{c(t)/1200}, c(t) = 50·sin(2πt/T): the heard pitch moves by
    exactly c(t). Returns |gain| and phase (deg) of the first harmonic per estimator (complex
    mean over ``WARP_SEEDS`` static runs) and the seed spread of |gain|.
    """
    n_src = int((ANALYZE_MIN_S + 2 * TRANSIENT_S + 4) * FS)
    n = int((ANALYZE_MIN_S + 2 * TRANSIENT_S) * FS)
    t, tt = np.arange(n_src) / FS, np.arange(n) / FS
    ph = (np.arange(N_BINS) + 0.5) / N_BINS
    truth = WARP_CENTS * np.sinc(1 / N_BINS) * np.sin(2 * np.pi * ph)  # bin-averaged sine
    g_all: dict[str, list[list[complex]]] = {"centroid": [], "loop": []}
    for seed in WARP_SEEDS:
        r = render(system, np.full(n_src, 0.5), seed=seed)
        x_obs = r.traj[:, r.obs_index]
        g_seed: dict[str, list[complex]] = {"centroid": [], "loop": []}
        for T in WARP_PERIODS:
            c_true = WARP_CENTS * np.sin(2 * np.pi * tt / T)
            phi = TRANSIENT_S + np.concatenate([[0.0], np.cumsum(2.0 ** (c_true[:-1] / 1200))]) / FS
            aw, xw = np.interp(phi, t, r.audio), np.interp(phi, t, x_obs)
            i0 = round(TRANSIENT_S * FS)
            i1 = min(i0 + round(max(2, math.ceil(ANALYZE_MIN_S / T)) * T * FS), n - FS // 10)
            f, w = inst_freq(aw, F0)
            b = bin_of(np.arange(i0, i1) / FS / T)
            wb = np.bincount(b, w[i0:i1], N_BINS)
            cb = cents(np.bincount(b, w[i0:i1] * f[i0:i1], N_BINS) / wb, F0)
            _, mid, d = loops(xw, i0, i1)
            bl = bin_of(mid / T)
            lb = cents(np.bincount(bl, None, N_BINS) / np.bincount(bl, d, N_BINS), F0)
            g_seed["centroid"].append(complex_gain(cb, truth))
            g_seed["loop"].append(complex_gain(lb, truth))
        for k in g_all:
            g_all[k].append(g_seed[k])
    out: dict[str, dict[str, list[float]]] = {}
    for k, gs in g_all.items():
        g = np.array(gs)
        gm = g.mean(axis=0)
        out[k] = {
            "abs": np.abs(gm).tolist(),
            "deg": np.degrees(np.angle(gm)).tolist(),
            "abs_sd": np.abs(g).std(axis=0, ddof=1).tolist(),
        }
    return out


# -- modulated runs --------------------------------------------------------------------------


def analysis_window(period_s: float) -> tuple[int, int]:
    n_cyc = max(2, math.ceil(ANALYZE_MIN_S / period_s))
    i0 = round(TRANSIENT_S * FS)
    return i0, i0 + round(n_cyc * period_s * FS)


def analyze_modulated(
    ref: StaticRef, system: str, run: Run, period_s: float, f0: float = F0
) -> dict:
    """Phase-binned errors of a sine-modulated run against the static reference."""
    i0, i1 = analysis_window(period_s)
    h_gain, lag = slew_response(period_s, f0)
    sl = slice(i0, i1)
    psi = np.arange(i0, i1) / FS / period_s - lag / (2 * np.pi)  # phase of the smoothed u
    b = bin_of(psi)
    u, a, s = run.u[sl], run.audio[sl], run.s[sl]
    cnt = np.bincount(b, None, N_BINS)
    # (a) centroid pitch
    f, w = inst_freq(run.audio, f0)
    ff, ww = f[sl], w[sl]
    f_ref = f0 * 2.0 ** (ref.cents_at(u) / 1200.0)
    W = np.bincount(b, ww, N_BINS)
    f_bin = np.bincount(b, ww * ff, N_BINS) / W
    fref_bin = np.bincount(b, ww * f_ref, N_BINS) / W
    dev_c = cents(f_bin, fref_bin)
    abs_c = cents(f_bin, f0)
    # (a) loop-rate pitch (each loop compared with the static loop rate at u at its midpoint)
    _, mid, d = loops(run.traj[:, run.obs_index], i0, i1)
    u_mid = run.u[np.minimum(np.round(mid * FS).astype(int), len(run.u) - 1)]
    bl = bin_of(mid / period_s - lag / (2 * np.pi))
    pred = np.bincount(bl, 1.0 / (f0 * 2.0 ** (ref.loop_at(u_mid) / 1200.0)), N_BINS)
    dev_l = cents(pred / np.bincount(bl, d, N_BINS), 1.0)
    # (b) loudness against the static RMS at the same u
    rms_bin = np.sqrt(np.bincount(b, a**2, N_BINS) / cnt)
    rms_ref = np.sqrt(np.bincount(b, ref.rms_at(u) ** 2, N_BINS) / cnt)
    level = 20 * np.log10(rms_bin / rms_ref)
    mean_s = np.bincount(b, s, N_BINS) / cnt
    lf_sync = np.bincount(b, lowpass(run.audio, f0 / 2)[sl], N_BINS) / cnt
    # (c) attractor
    dist = nn_distance(ref, run.traj[sl][::QUERY_STRIDE], u[::QUERY_STRIDE])
    hyst_c, sym_c = updown(dev_c)
    hyst_l, sym_l = updown(dev_l)
    lh, _ = updown(level)
    return {
        "u_min": float(u.min()),
        "u_max": float(u.max()),
        "slew_gain": h_gain,
        "slew_lag_deg": math.degrees(lag),
        "resets": int(run.resets),
        "pitch_abs_bins": abs_c.tolist(),
        "pitch_dev_bins": dev_c.tolist(),
        "loop_dev_bins": dev_l.tolist(),
        "level_bins": level.tolist(),
        "pitch_abs_rms": rms(abs_c),
        "pitch_dev_rms": rms(dev_c),
        "pitch_dev_max": float(np.max(np.abs(dev_c))),
        "pitch_hyst_rms": rms(hyst_c),
        "pitch_sym_rms": rms(sym_c),
        "pitch_mean_dev": float(cents(np.sum(ww * ff), np.sum(ww * f_ref))),
        "loop_dev_rms": rms(dev_l),
        "loop_dev_max": float(np.max(np.abs(dev_l))),
        "loop_hyst_rms": rms(hyst_l),
        "loop_sym_rms": rms(sym_l),
        "loop_mean_dev": float(cents(np.sum(pred), np.sum(d))),
        # mean over the bins where the smoothed u rises (ψ < ½) and where it falls
        "loop_dev_rise": float(np.mean(dev_l[: N_BINS // 2])),
        "loop_dev_fall": float(np.mean(dev_l[N_BINS // 2 :])),
        "level_all_db": float(20 * np.log10(rms(a) / rms(ref.rms_at(u)))),
        "level_bin_max_db": float(np.max(np.abs(level))),
        "level_hyst_rms_db": rms(lh),
        "mean_s_max": float(np.max(np.abs(mean_s))),
        "lf_sync_rms": rms(lf_sync),
        "peak_q999": float(np.quantile(np.abs(a), 0.999)),
        "nn_q99": float(np.quantile(dist, NN_QUANTILE)),
        "nn_max": float(np.max(dist)),
        "box_usage": box_usage(system, run.traj[sl]),
    }


def seed_stats(rows: list[dict], key: str) -> tuple[Any, Any]:
    v = np.array([r[key] for r in rows], dtype=float)
    return v.mean(axis=0), v.std(axis=0, ddof=1)


# -- jumps (square-wave modulation) ----------------------------------------------------------


def jump_response(
    loop_ref: tuple[Array, Array],
    system: str,
    note: str,
    seed: int,
    slew: str,
    n_cycles: int = JUMP_CYCLES,
) -> dict:
    """Square wave 0 ↔ 1, each level held 64 periods: loop-rate pitch after each jump.

    ``err``: each loop against the static loop rate at the smoothed u at its midpoint
    (non-adiabatic error). ``glide``: against the static loop rate at the destination
    (what the ear hears as a glide or chirp). ``loop_ref`` = (u grid, static loop cents).
    ``err_clean``: ``err`` over the jumps whose 64-period window holds no safety reset
    (equal to ``err`` when there was no reset); ``jumps_with_reset`` counts the others.
    """
    f0 = note_to_hz(note)
    period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    n = round((n_cycles + 1) * period_s * FS)
    run = render(system, lfo("square", period_s, n), note=note, seed=seed, slew=slew)
    st, mid, d = loops(run.traj[:, run.obs_index], 0, n)
    u_mid = run.u[np.minimum(np.round(mid * FS).astype(int), n - 1)]
    t_ref = 1.0 / (f0 * 2.0 ** (np.interp(u_mid, *loop_ref) / 1200.0))
    nb = len(JUMP_EDGES) - 1
    reset_at = run.reset_at if run.reset_at is not None else np.zeros(0, dtype=int)
    out: dict[str, Any] = {"resets": int(run.resets)}
    # square: u = 1 for φ < ½, so u jumps 0→1 at φ = 0 ("up") and 1→0 at φ = ½ ("down").
    for name, phase0, u_dest in (("up", 0.0, 1.0), ("down", 0.5, 0.0)):
        f_dest = f0 * 2.0 ** (float(np.interp(u_dest, *loop_ref)) / 1200.0)
        errs, glides, s_first, peaks, hit = [], [], [], [], []
        for t_j in (np.arange(1, n_cycles + 1) + phase0) * period_s:
            m = (st >= t_j) & (st < t_j + 0.5 * period_s)
            k = np.clip(np.digitize((st[m] - t_j) * f0, JUMP_EDGES) - 1, 0, nb - 1)
            sums, cnts = np.bincount(k, d[m], nb), np.bincount(k, None, nb)
            with np.errstate(divide="ignore", invalid="ignore"):
                errs.append(cents(np.bincount(k, t_ref[m], nb) / sums, 1.0))
                glides.append(cents(cnts / sums, f_dest))
            i_j = round(t_j * FS)
            i_end = i_j + int(0.5 * period_s * FS)
            s_first.append(float(np.mean(run.s[i_j : i_j + int(FS / f0)])))
            peaks.append(float(np.max(np.abs(run.audio[i_j:i_end]))))
            hit.append(bool(np.any((reset_at >= i_j) & (reset_at < i_end))))
        rec: dict[str, Any] = {}
        clean = ~np.array(hit)
        for key, arr in (
            ("err", np.array(errs)),
            ("glide", np.array(glides)),
            ("err_clean", np.array(errs)[clean]),
        ):
            ok = np.sum(np.isfinite(arr), axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                rec[f"{key}_mean"] = np.nanmean(arr, axis=0).tolist()
                rec[f"{key}_se"] = (np.nanstd(arr, axis=0) / np.sqrt(ok)).tolist()
        rec["jumps_with_reset"] = int(np.sum(hit))
        rec["mean_s_first_period"] = float(np.mean(s_first))
        rec["peak_abs_mean"] = float(np.mean(peaks))
        rec["peak_abs_max"] = float(np.max(peaks))
        out[name] = rec
    return out


def jump_summary(js: list[dict], direction: str, key: str) -> tuple[Array, Array]:
    c = np.mean([j[direction][f"{key}_mean"] for j in js], axis=0)
    se = np.sqrt(np.mean(np.square([j[direction][f"{key}_se"] for j in js]), axis=0) / len(js))
    return c, se


def settle_periods(c: Array, se: Array, tol: float = 20.0) -> float:
    """First bin edge (periods) after which every bin is within max(tol, 2·SE) of 0.

    A result equal to the last edge (64) means that the last bin is still outside: the
    error did not settle within the level, and the tables print it as "> 64".
    """
    bad = np.flatnonzero(np.abs(c) > np.maximum(tol, 2 * se))
    return float(JUMP_EDGES[bad[-1] + 1]) if bad.size else 0.0


def fmt_settle(periods: float) -> str:
    return f"> {JUMP_EDGES[-1]:.0f}" if periods >= JUMP_EDGES[-1] else f"{periods:.0f}"


# -- safety probes ---------------------------------------------------------------------------


def reset_probe(
    system: str,
    note: str,
    seed: int,
    *,
    shape: str = "square",
    period_s: float | None = None,
    seconds: float | None = None,
    slew: str = "v0.3",
) -> dict:
    """Count safety resets under a full-range modulator (default: square, 64 periods/level)."""
    f0 = note_to_hz(note)
    if period_s is None:
        period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    if seconds is None:
        seconds = (PROBE_CYCLES + 1) * period_s
    n_total = round(seconds * FS)
    box = make_box(system, note, seed, None)
    e = box.entry
    chunk = 10 * FS
    resets_at: list[int] = []
    usage, u_lo, u_hi = 0.0, 1.0, 0.0
    pos = 0
    with slew_mode(slew):
        while pos < n_total:
            m = min(chunk, n_total - pos)
            box.process(m, {"param": lfo(shape, period_s, m, start=pos)})
            traj = _captured["traj"]
            resets_at += (pos + np.flatnonzero(np.all(traj == box._x_reset, axis=1))).tolist()
            usage = max(usage, box_usage(system, traj))
            u = (_captured["p_values"] - e.p_min) / (e.p_max - e.p_min)
            if pos + m > TRANSIENT_S * FS:
                u = u[max(0, round(TRANSIENT_S * FS) - pos) :]
                u_lo, u_hi = min(u_lo, float(u.min())), max(u_hi, float(u.max()))
            pos += m
    phase = np.mod(np.array(resets_at) / FS / period_s, 1.0)
    return {
        "resets": int(box.resets),
        # Cycle starts after t = 0, i.e. the jumps of a square or ramp shape in one direction
        # (the smoother starts at the first control value, so t = 0 is not a jump).
        "jumps": math.ceil(seconds / period_s - 1e-9) - 1,
        "seconds": seconds,
        "box_usage": usage,
        "u_range": [u_lo, u_hi],
        "reset_samples": resets_at,
        "reset_periods_after_cycle_start": (phase * period_s * f0).tolist(),
    }


# -- Chua with observable x -----------------------------------------------------------------


def chua_x_check(seed: int, period_s: float = 5.0, n_cycles: int = 6) -> dict:
    """Single-scroll episodes (u < 0.1) of a sine sweep: which scroll, and the offset in s.

    ``alt`` gives the mean of s for x and z under three normalizations of the same
    trajectory: the catalog's (μ, σ); μ = 0 with the catalog σ; and μ = 0 with
    σ' = √(σ² + μ²), the moments of the two mirror scrolls pooled.
    """
    e = CAT["chua"]
    n = round((n_cycles + 0.5) * period_s * FS)
    run = render("chua", lfo("sine", period_s, n), seed=seed, observable="x")
    x = run.traj[:, 0]
    low = run.u < 0.1
    starts = np.flatnonzero(~low[:-1] & low[1:]) + 1
    stops = np.flatnonzero(low[:-1] & ~low[1:]) + 1
    signs, offsets, peaks = [], [], []
    alt: dict[str, dict[str, list[float]]] = {
        v: {"catalog": [], "mu0": [], "mu0_pooled_sigma": []} for v in ("x", "z")
    }
    for st in starts:
        en = stops[stops > st]
        if not en.size or st < TRANSIENT_S * FS:
            continue
        sl = slice(st, en[0])
        signs.append(int(np.sign(np.mean(x[sl]))))
        offsets.append(float(np.mean(run.s[sl])))
        peaks.append(float(np.max(np.abs(run.audio[st - FS // 5 : en[0] + FS // 5]))))
        u = run.u[sl]
        for v, i in (("x", 0), ("z", 2)):
            xv, mu, sd = run.traj[sl, i], e.mean(v, u), e.std(v, u)
            alt[v]["catalog"].append(float(np.mean((xv - mu) / sd)))
            alt[v]["mu0"].append(float(np.mean(xv / sd)))
            alt[v]["mu0_pooled_sigma"].append(float(np.mean(xv / np.sqrt(sd**2 + mu**2))))
    return {
        "signs": signs,
        "mean_s": offsets,
        "peak_abs": peaks,
        "catalog_mu_x_u0": float(e.mean("x", 0.0)),
        "alt": alt,
    }


def chua_x_rows() -> list[dict]:
    """Worker: :func:`chua_x_check` for every seed."""
    return [chua_x_check(sd) for sd in SEEDS]


# -- figures ---------------------------------------------------------------------------------


def fig_profiles(results: dict, refs: dict[str, StaticRef], path: Path) -> None:
    show = [T for T in (20.0, 1.0, 0.2, 0.1, 0.05, 0.02) if str(T) in results[SYSTEMS[0]]]
    fig, axes = plt.subplots(4, len(SYSTEMS), figsize=(13, 10.5), sharex=True)
    ph = (np.arange(N_BINS) + 0.5) / N_BINS
    labels = (
        "centroid pitch − note (c)",
        "centroid − static at same u (c)",
        "loop rate − static at same u (c)",
        "RMS re static at same u (dB)",
    )
    keys = ("pitch_abs_bins", "pitch_dev_bins", "loop_dev_bins", "level_bins")
    for col, system in enumerate(SYSTEMS):
        for k, T in enumerate(show):
            rows = results[system][str(T)]
            hg = rows[0]["slew_gain"]
            lab = f"T = {T:g} s (swing {hg:.2f})"
            for row, key in enumerate(keys):
                axes[row, col].plot(ph, seed_stats(rows, key)[0], color=SEQ[k], label=lab)
        u_slow = 0.5 * (1 - np.cos(2 * np.pi * ph))
        axes[0, col].plot(ph, refs[system].cents_at(u_slow), color=MUTED, lw=1.2, ls="--")
        axes[0, col].set_title(NAMES[system], loc="left", fontsize=10)
        axes[-1, col].set_xlabel("phase ψ of the slewed u")
        for row in range(4):
            ax = axes[row, col]
            ax.axhline(0, color=AXIS, lw=0.8)
            ax.axvline(0.5, color=GRID, lw=0.8)
            if col == 0:
                ax.set_ylabel(labels[row])
    axes[0, 0].plot([], [], color=MUTED, ls="--", lw=1.2, label="static (full swing)")
    axes[0, 0].legend(fontsize=7, loc="lower left", ncol=1)
    fig.suptitle(
        f"Full-range sine LFO on u at {NOTE}, engine {ENGINE}: phase-binned pitch and loudness, "
        f"mean of {len(SEEDS)} seeds (u rises for ψ < 0.5, then falls; swing = range of the "
        "slewed u)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_summary(results: dict, refs: dict[str, StaticRef], path: Path) -> None:
    panels = (
        ("pitch_dev_rms", "centroid − static, RMS over phase (c)", False),
        ("loop_dev_rms", "loop rate − static, RMS over phase (c)", False),
        ("level_bin_max_db", "max |RMS re static| over phase (dB)", False),
        ("mean_s_max", "max |mean s| over phase (before DC blocker)", True),
        ("nn_q99", "99th pct distance to static attractor / static 99th pct", True),
        ("box_usage", "max safety-box usage", False),
    )
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.4))
    ceiling = 1 / (2 * np.pi)
    for ax, (key, label, logy) in zip(axes.flat, panels, strict=True):
        ax.axvline(ceiling, color=AXIS, ls="--", lw=1.0)
        for system in SYSTEMS:
            rows_t = [results[system][str(T)] for T in PERIODS]
            r_eff = np.array(
                [2 * rs[0]["slew_gain"] / (F0 * T) for rs, T in zip(rows_t, PERIODS, strict=True)]
            )
            m = np.array([seed_stats(rs, key)[0] for rs in rows_t])
            sd = np.array([seed_stats(rs, key)[1] for rs in rows_t])
            if key == "nn_q99":
                m, sd = m / refs[system].threshold, sd / refs[system].threshold
            ax.errorbar(
                r_eff, m, yerr=sd, color=COLORS[system], marker="o", ms=4, lw=1.6, capsize=2,
                label=NAMES[system],
            )  # fmt: skip
        ax.set_xscale("log")
        if logy:
            ax.set_yscale("log")
        ax.set_ylabel(label)
        ax.set_xlabel("sweeps per oscillation period of the slewed u, 2·swing/(f₀T)")
    axes[0, 0].legend(loc="upper left")
    axes[0, 0].annotate(
        "v0.3 slew ceiling 1/(2π)", (ceiling, axes[0, 0].get_ylim()[1]), xytext=(-4, -12),
        textcoords="offset points", ha="right", fontsize=7.5, color=INK2,
    )  # fmt: skip
    fig.suptitle(
        f"Errors vs modulation rate (sine, full range, {NOTE}, engine {ENGINE}: T = 20 s at left; "
        "faster LFOs pile up below the slew ceiling; bars: seed spread)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_jumps(jumps: dict, path: Path) -> None:
    fig, axes = plt.subplots(2, len(SYSTEMS), figsize=(13, 6.2), sharex=True)
    x = np.sqrt(np.maximum(JUMP_EDGES[:-1], 0.25) * JUMP_EDGES[1:])
    for col, system in enumerate(SYSTEMS):
        for row, (name, title) in enumerate((("up", "u jumps 0 → 1"), ("down", "u jumps 1 → 0"))):
            ax = axes[row, col]
            for slew, color in (("v0.2", MUTED), ("v0.3", COLORS[system])):
                for note, ls in (("A3", "-"), ("A1", "--")):
                    c, se = jump_summary(jumps[system][f"{note}|{slew}"], name, "err")
                    ax.errorbar(
                        x, c, yerr=2 * se, color=color, ls=ls, marker="o", ms=3, capsize=2,
                        label=f"{note}, {slew} slew",
                    )  # fmt: skip
            ax.axhline(0, color=AXIS, lw=0.8)
            ax.set_title(f"{NAMES[system]}: {title}", loc="left", fontsize=9.5)
            ax.set_xscale("log")
            if col == 0:
                ax.set_ylabel("loop rate − static at current u (c)")
            if row == 1:
                ax.set_xlabel("time after the jump (oscillation periods)")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(
        "Square-wave modulation: non-adiabatic pitch error after a full-range jump "
        "(v0.3 slew max(5 ms, 2 periods) vs v0.2's 5 ms; bars: ±2 SE)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_spectra(spectra: dict, refs: dict[str, StaticRef], path: Path) -> None:
    show = [T for T in (20.0, 0.2, 0.05, 0.02) if str(T) in spectra[SYSTEMS[0]]]
    fig, axes = plt.subplots(len(show), len(SYSTEMS), figsize=(13, 8), sharex=True, squeeze=False)
    for col, system in enumerate(SYSTEMS):
        ref = refs[system]
        for row, T in enumerate(show):
            ax = axes[row, col]
            f, p = spectra[system][str(T)]
            ax.semilogy(ref.psd_f, ref.psd, color=MUTED, lw=1.0, label="static, time-weighted")
            ax.semilogy(f, p, color=COLORS[system], lw=1.0, label=f"T = {T:g} s")
            ax.set_xlim(0, 3.2 * F0)
            ax.set_ylim(1e-9, 1e-2)
            if row == 0:
                ax.set_title(NAMES[system], loc="left", fontsize=10)
            if col == 0:
                ax.set_ylabel("PSD (1/Hz)")
            ax.legend(fontsize=7, loc="upper right")
        axes[-1, col].set_xlabel("frequency (Hz)")
    fig.suptitle(
        f"Long-term audio spectra under full-range sine modulation ({NOTE} = 220 Hz, engine "
        f"{ENGINE}) vs the time-weighted average of static spectra (full swing)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_gain(gains: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    fm = 1.0 / np.array(WARP_PERIODS)
    for ax, (est, title) in zip(
        axes, (("centroid", "centroid"), ("loop", "loop rate")), strict=True
    ):
        for system in SYSTEMS:
            ax.plot(fm, gains[system][est]["abs"], color=COLORS[system], marker="o", ms=4,
                    label=NAMES[system])  # fmt: skip
        ax.axhline(1, color=AXIS, lw=0.8)
        ax.set_xscale("log")
        ax.set_title(f"{title} estimator", loc="left", fontsize=10)
        ax.set_xlabel("FM rate (Hz)")
    axes[0].set_ylabel("|measured / true| deviation")
    axes[0].legend(fontsize=7.5)
    fig.suptitle(
        f"Estimator calibration: static audio at u = 0.5 warped by a known ±{WARP_CENTS:g} c "
        f"sine FM ({NOTE})",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def render_switch(
    system: str, u_raw: Array, note: str, seed: int, i_split: int, slew_after: str
) -> Run:
    """Render with the v0.2 slew up to sample ``i_split``, then with ``slew_after``.

    Both variants reach ``i_split`` in exactly the same state, so they show the same jump
    from the same point on the attractor. ``resets`` counts the resets after ``i_split``.
    """
    box = make_box(system, note, seed, None)
    e = box.entry
    parts = []
    before = 0
    for (a, b), slew in (((0, i_split), "v0.2"), ((i_split, len(u_raw)), slew_after)):
        with slew_mode(slew):
            audio = box.process(b - a, {"param": u_raw[a:b]})["out"][:, 0].copy()
        parts.append((audio, _captured["p_values"].copy(), _captured["traj"].copy()))
        if b == i_split:
            before = box.resets
    audio = np.concatenate([q[0] for q in parts])
    u = (np.concatenate([q[1] for q in parts]) - e.p_min) / (e.p_max - e.p_min)
    traj = np.concatenate([q[2] for q in parts])
    i = box.system.variable_index(box.observable)
    s = (traj[:, i] - e.mean(box.observable, u)) / e.std(box.observable, u)
    return Run(audio, s, u, traj, box.resets - before, i)


def fig_escape(note: str, seed: int, sample: int, path: Path) -> dict:
    """Chua: one jump that escapes with the v0.2 slew, and the same jump with the v0.3 slew."""
    f0 = note_to_hz(note)
    period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    n = sample + int(6 * FS / f0)
    t_jump = math.floor(sample / FS / period_s) * period_s
    i_split = round(t_jump * FS) - FS // 1000  # 1 ms before the jump
    i0 = max(0, int((t_jump - 4 / f0) * FS))
    t = (np.arange(i0, n) / FS - t_jump) * f0
    e = CAT["chua"]
    u_raw = lfo("square", period_s, n)
    runs = {s: render_switch("chua", u_raw, note, seed, i_split, s) for s in SLEWS}
    fig, axes = plt.subplots(4, 1, figsize=(8.5, 8), sharex=True)
    for s, ls in (("v0.2", "--"), ("v0.3", "-")):
        axes[0].plot(t, runs[s].u[i0:], color=INK2, ls=ls, label=f"{s} slew")
    axes[0].set_ylabel("u (after the slew)")
    axes[0].legend(fontsize=7.5, loc="lower right")
    for ax, s in ((axes[1], "v0.2"), (axes[2], "v0.3")):
        for j, (var, c) in enumerate((("x", COLORS["chua"]), ("y", "#2a78d6"), ("z", "#1baf7a"))):
            ax.plot(t, runs[s].traj[i0:, j] / e.bounds_hi[j], color=c, lw=1.1, label=var)
        ax.axhline(1, color=AXIS, ls="--", lw=0.8)
        ax.axhline(-1, color=AXIS, ls="--", lw=0.8)
        ax.set_ylabel(f"state / bound ({s})")
        ax.legend(fontsize=7.5, ncol=3, loc="upper left")
    for s, c in (("v0.2", MUTED), ("v0.3", COLORS["chua"])):
        axes[3].plot(t, runs[s].audio[i0:], color=c, lw=0.9, label=f"{s} slew")
    axes[3].set_ylabel("audio (before Output)")
    axes[3].legend(fontsize=7.5, loc="upper left")
    axes[3].set_xlabel("time after the jump (oscillation periods)")
    axes[0].set_title(
        f"Chua, {note}, seed {seed}: one u 0 → 1 jump from the same state; v0.2 slew (escape, "
        "reset) vs v0.3 slew",
        loc="left",
        fontsize=9.5,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return {s: int(runs[s].resets) for s in SLEWS}  # resets after the split


# -- main ------------------------------------------------------------------------------------


def to_jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [to_jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return to_jsonable(x.tolist())
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating | float):
        v = float(x)
        return v if math.isfinite(v) else None
    return x


def system_study(system: str) -> dict:
    """Run the static reference, estimator calibration, sine sweep and jumps of one system."""
    t0 = time.time()
    ref = build_static(system)
    gains = estimator_gain(system)
    results: dict[str, list[dict]] = {}
    spectra: dict[str, tuple[Array, Array]] = {}
    for T in PERIODS:
        i0, i1 = analysis_window(T)
        rows = []
        for seed in SEEDS:
            run = render(system, lfo("sine", T, i1 + FS // 10), seed=seed)
            rows.append(analyze_modulated(ref, system, run, T))
            if seed == SEEDS[0]:
                spectra[str(T)] = welch(run.audio[i0:i1], fs=FS, nperseg=2**15)
                if T in (1.0, 0.1, 0.02):
                    clip = soft_clip(run.audio[i0 : i0 + 6 * FS])
                    write_wav(OUT / "wav" / f"{system}_sine_T{T:g}s_{NOTE}.wav", clip, FS)
        results[str(T)] = rows
    # The rate counted per oscillation period: Lorenz at three notes, same N = f0·T/2.
    scaling: dict[str, list[dict]] = {}
    if system == "lorenz":
        for n_osc in (11.0, 55.0):
            for note in ("A2", "A3", "A4"):
                f0 = note_to_hz(note)
                T = 2 * n_osc / f0
                _, i1 = analysis_window(T)
                scaling[f"{n_osc:g}|{note}"] = [
                    analyze_modulated(
                        ref,
                        "lorenz",
                        render("lorenz", lfo("sine", T, i1 + FS // 10), note=note, seed=sd),
                        T,
                        f0=f0,
                    )
                    for sd in SEEDS
                ]
    loop_ref = (ref.u, ref.loop_cents)
    jumps = {
        f"{note}|{slew}": [jump_response(loop_ref, system, note, sd, slew) for sd in SEEDS]
        for note in ("A3", "A1")
        for slew in SLEWS
    }
    ref.trees, ref.scales = [], []  # not needed by the caller; keeps the result small
    print(f"{system}: study done in {time.time() - t0:.0f} s", flush=True)
    return {
        "ref": ref,
        "gains": gains,
        "results": results,
        "spectra": spectra,
        "scaling": scaling,
        "jumps": jumps,
    }


def probe_cases() -> list[tuple[str, str, str, tuple[int, ...], dict[str, Any]]]:
    """(key, system, note, seeds, keyword arguments of :func:`reset_probe`) for every case."""
    cases: list[tuple[str, str, str, tuple[int, ...], dict[str, Any]]] = []
    for system in PROBE_SYSTEMS:
        seeds = PROBE_SEEDS_CHUA if system == "chua" else SEEDS
        for note in PROBE_NOTES:
            cases.append((f"{system}|{note}|square 64 per.|v0.3", system, note, seeds, {}))
    for note in ("A0", "A1"):
        key = f"chua|{note}|square 64 per.|v0.2"
        cases.append((key, "chua", note, PROBE_SEEDS_CHUA, {"slew": "v0.2"}))
    # The default modulator (period_s = 4 s) with discontinuous shapes, 240 s per seed.
    for note in ("A0", "A1"):
        for shape in ("square", "ramp_up", "ramp_down"):
            for slew in SLEWS:
                if slew == "v0.2" and (note != "A0" or shape == "ramp_up"):
                    continue  # v0.2 baseline only where v0.2 escaped most
                kw = {"shape": shape, "period_s": 4.0, "seconds": DEFAULT_PROBE_S, "slew": slew}
                cases.append((f"chua|{note}|{shape} T=4 s|{slew}", "chua", note, SEEDS, kw))
    # Smooth shapes at full range on Chua at low notes, 60 s per seed.
    for note in ("A0", "A1"):
        for shape, T in (("sine", 0.1), ("sine", 0.2), ("sine", 0.5), ("sine", 1.0),
                         ("sine", 2.0), ("triangle", 0.2), ("triangle", 0.5)):  # fmt: skip
            kw = {"shape": shape, "period_s": T, "seconds": SMOOTH_PROBE_S}
            cases.append((f"chua|{note}|{shape} T={T:g} s|v0.3", "chua", note, SEEDS, kw))
    return cases


def probe_task(system: str, note: str, seeds: tuple[int, ...], kw: dict[str, Any]) -> list[dict]:
    """Worker: one probe case over all its seeds."""
    return [reset_probe(system, note, sd, **kw) for sd in seeds]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "wav").mkdir(exist_ok=True)
    for old in (OUT / "wav").glob("*.wav"):  # regenerated below; drop files of older runs
        old.unlink()
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=WORKERS, mp_context=get_context("spawn")) as pool:
        studies = {s: pool.submit(system_study, s) for s in SYSTEMS}
        cases = probe_cases()
        probe_futures = {key: pool.submit(probe_task, *args) for key, *args in cases}
        chua_x_future = pool.submit(chua_x_rows)
        done = {s: f.result() for s, f in studies.items()}
        probe = {key: f.result() for key, f in probe_futures.items()}
        chua_x = chua_x_future.result()
    print(f"workers done ({time.time() - t_start:.0f} s)", flush=True)
    refs: dict[str, StaticRef] = {s: d["ref"] for s, d in done.items()}
    gains = {s: d["gains"] for s, d in done.items()}
    results = {s: d["results"] for s, d in done.items()}
    spectra = {s: d["spectra"] for s, d in done.items()}
    jumps = {s: d["jumps"] for s, d in done.items()}
    scaling = done["lorenz"]["scaling"]

    # Cross-check against the full Patch path (chunked rendering, Output block).
    p = Patch(catalog=CAT)
    p.add_block("dynamical", "osc", system="lorenz", note=NOTE, seed=0)
    p.add_block("modulator", "lfo", shape="sine", period_s=0.05, mode="loop")
    p.add_block("output", "out", volume=1.0)
    p.connect("lfo.out", "osc.param")
    p.connect("osc.out", "out.in")
    audio_patch = p.render(seconds=3.0, sample_rate=FS)[:, 0]
    direct = render("lorenz", lfo("sine", 0.05, len(audio_patch)), seed=0).audio
    lin = np.abs(direct) < 0.9
    patch_check = {
        "max_abs_diff_below_knee": float(np.max(np.abs(audio_patch[lin] - direct[lin]))),
        "safety_resets": dict(p.last_render.safety_resets) if p.last_render else None,
    }

    # Escape example (v0.2 slew) for the figure and WAVs, with the same jump under v0.3.
    escape = None
    for note in ("A1", "A0"):
        rows = probe[f"chua|{note}|square 64 per.|v0.2"]
        for sd, row in zip(PROBE_SEEDS_CHUA, rows, strict=True):
            if row["reset_samples"] and escape is None:
                escape = (note, sd, int(row["reset_samples"][0]))
    escape_resets = None
    if escape is not None:
        escape_resets = fig_escape(*escape, OUT / "fig5_chua_escape.png")
        note, sd, smp = escape
        period_s = 2.0 * JUMP_LEVEL_PERIODS / note_to_hz(note)
        i_end = smp + 2 * FS
        i_beg = max(0, i_end - 12 * FS)
        t_jump = math.floor(smp / FS / period_s) * period_s
        i_split = round(t_jump * FS) - FS // 1000
        for slew in SLEWS:
            run = render_switch("chua", lfo("square", period_s, i_end), note, sd, i_split, slew)
            name = f"chua_square_{note}_seed{sd}_{slew.replace('.', '')}slew.wav"
            write_wav(OUT / "wav" / name, soft_clip(run.audio[i_beg:]), FS)

    summary = {
        "engine": ENGINE,
        "catalog_generated": CAT.metadata.get("generated"),
        "settings": {
            "fs": FS,
            "note": NOTE,
            "periods": PERIODS,
            "seeds": SEEDS,
            "n_bins": N_BINS,
            "band": BAND,
            "static_grid_points": len(STATIC_GRID),
            "static_seconds": STATIC_SECONDS,
            "slew_tau_s": {n: slew_tau(note_to_hz(n)) for n in ("A0", "A1", "A2", "A3", "A4")},
            "ranges": {
                s: [CAT[s].param, CAT[s].p_min, CAT[s].p_max, CAT[s].p_default]
                for s in PROBE_SYSTEMS
            },
        },
        "static": {
            s: {
                "u": r.u,
                "cents": r.cents,
                "loop_cents": r.loop_cents,
                "mean_s": r.mean_s,
                "std_s": r.std_s,
                "rms": r.rms,
                "box_usage": r.box_usage,
                "peak_q999": r.peak,
                "nn_threshold_q99": r.threshold,
                "ref_err_cents": r.ref_err_cents,
                "ref_err_loop": r.ref_err_loop,
                "ref_diff_max": r.ref_diff_max,
            }
            for s, r in refs.items()
        },
        "estimator_gain": {"fm_hz": [1 / T for T in WARP_PERIODS], **gains},
        "modulated": results,
        "scaling": scaling,
        "jumps": jumps,
        "reset_probe": probe,
        "chua_x": chua_x,
        "patch_check": patch_check,
        "escape_example": escape,
        "escape_example_resets": escape_resets,
    }
    (OUT / "results.json").write_text(json.dumps(to_jsonable(summary), indent=1))
    fig_profiles(results, refs, OUT / "fig1_phase_profiles.png")
    fig_summary(results, refs, OUT / "fig2_rate_summary.png")
    fig_jumps(jumps, OUT / "fig3_jump_response.png")
    fig_spectra(spectra, refs, OUT / "fig4_spectra.png")
    fig_gain(gains, OUT / "fig6_estimator_gain.png")
    print_tables(summary, refs)
    print(f"\ntotal wall time {time.time() - t_start:.0f} s")


def fmt_ms(rows: list[dict], key: str, fmt: str) -> str:
    m, sd = seed_stats(rows, key)
    return f"{fmt.format(m)} ± {fmt.format(sd).lstrip('+')}"


def print_tables(summary: dict, refs: dict[str, StaticRef]) -> None:
    res = summary["modulated"]
    print(f"\nengine {summary['engine']}, catalog generated {summary['catalog_generated']}")
    print("\n### Static references (fixed u, 41 points, 10 s each)\n")
    print(
        "| system | centroid − note (c) | loop rate − note (c) | ref. error centroid / loop (c) |"
        " RMS min … max | peak q99.9 | NN q99 (σ) | box usage |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for s, r in refs.items():
        print(
            f"| {s} | {r.cents.min():+.0f} … {r.cents.max():+.0f} | {r.loop_cents.min():+.0f} "
            f"… {r.loop_cents.max():+.0f} | {r.ref_err_cents:.1f} / {r.ref_err_loop:.1f} "
            f"(max diff {r.ref_diff_max[0]:.0f} / {r.ref_diff_max[1]:.0f}) | "
            f"{r.rms.min():.3f} … {r.rms.max():.3f} | {r.peak.max():.2f} | {r.threshold:.3f} | "
            f"{r.box_usage.max():.2f} |"
        )
    print("\n### Estimator gain (time warp, ±50 c sine FM): |G| (phase °)\n")
    fm = summary["estimator_gain"]["fm_hz"]
    print("| system | estimator | " + " | ".join(f"{f:g} Hz" for f in fm) + " |")
    print("|---|---|" + "---|" * len(fm))
    for s in SYSTEMS:
        for est in ("centroid", "loop"):
            g = summary["estimator_gain"][s][est]
            print(
                f"| {s} | {est} | "
                + " | ".join(
                    f"{a:.2f} ± {sd:.2f} ({d:+.0f}°)"
                    for a, sd, d in zip(g["abs"], g["abs_sd"], g["deg"], strict=True)
                )
                + " |"
            )
    pitch_cols = (
        ("pitch_abs_rms", "{:.0f}"),
        ("pitch_dev_rms", "{:.1f}"),
        ("pitch_hyst_rms", "{:.1f}"),
        ("pitch_sym_rms", "{:.1f}"),
        ("pitch_dev_max", "{:.0f}"),
        ("loop_dev_rms", "{:.1f}"),
        ("loop_hyst_rms", "{:.1f}"),
        ("loop_sym_rms", "{:.1f}"),
        ("loop_dev_max", "{:.0f}"),
        ("loop_mean_dev", "{:+.1f}"),
        ("loop_dev_rise", "{:+.1f}"),
        ("loop_dev_fall", "{:+.1f}"),
        ("pitch_mean_dev", "{:+.1f}"),
    )
    level_cols = (
        ("level_all_db", "{:+.2f}"),
        ("level_bin_max_db", "{:.2f}"),
        ("level_hyst_rms_db", "{:.2f}"),
        ("mean_s_max", "{:.3f}"),
        ("lf_sync_rms", "{:.4f}"),
        ("peak_q999", "{:.2f}"),
        ("nn_q99", "{:.3f}"),
        ("nn_max", "{:.2f}"),
        ("box_usage", "{:.2f}"),
    )
    for title, cols in (("pitch", pitch_cols), ("loudness and attractor", level_cols)):
        for system in SYSTEMS:
            print(f"\n### {system}: {title} (sine, full range, {NOTE}; mean ± sd, 3 seeds)\n")
            print("| T (s) | r_eff | u range | resets | " + " | ".join(k for k, _ in cols))
            print("|" + "---|" * (4 + len(cols)))
            for T in PERIODS:
                rows = res[system][str(T)]
                umin = np.mean([r["u_min"] for r in rows])
                umax = np.mean([r["u_max"] for r in rows])
                r_eff = 2 * (umax - umin) / (F0 * T)
                print(
                    f"| {T:g} | {r_eff:.2g} | {umin:.2f}–{umax:.2f} | "
                    f"{sum(r['resets'] for r in rows)} | "
                    + " | ".join(fmt_ms(rows, k, f) for k, f in cols)
                    + " |"
                )
    print("\n### Rate per oscillation period: Lorenz at three notes\n")
    print(
        "| N = f0·T/2 | note | T (s) | u range | centroid − static RMS (c) |"
        " loop − static RMS (c) |"
    )
    print("|---|---|---|---|---|---|")
    for k, rows in summary["scaling"].items():
        n_osc, note = k.split("|")
        T = 2 * float(n_osc) / note_to_hz(note)
        print(
            f"| {n_osc} | {note} | {T:.3g} | {np.mean([r['u_min'] for r in rows]):.2f}–"
            f"{np.mean([r['u_max'] for r in rows]):.2f} | {fmt_ms(rows, 'pitch_dev_rms', '{:.1f}')}"
            f" | {fmt_ms(rows, 'loop_dev_rms', '{:.1f}')} |"
        )
    print("\n### Jumps (square 0 ↔ 1, 64 periods per level, 40 jumps × 3 seeds per direction)\n")
    print(
        "| system | note | slew | jump | err 1st period (c) | max |err| (c) | err 12–32 / 32–64"
        " per. (c) | settles to ±20 c (periods) | glide 1st / 2–3 per. (c) | mean s 1st |"
        " peak mean / max | jumps with a reset | max |err| / settles, reset-free jumps |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for system in SYSTEMS:
        for key, js in summary["jumps"][system].items():
            note, slew = key.split("|")
            for d in ("up", "down"):
                c, se = jump_summary(js, d, "err")
                g, _ = jump_summary(js, d, "glide")
                tail1 = np.mean(c[8:10])
                tail2 = np.mean(c[10:12])
                n_hit = sum(j[d]["jumps_with_reset"] for j in js)
                clean = "same"
                if n_hit:
                    cc, sc = jump_summary(js, d, "err_clean")
                    clean = f"{np.nanmax(np.abs(cc)):.0f} / {fmt_settle(settle_periods(cc, sc))}"
                print(
                    f"| {system} | {note} | {slew} | {'0→1' if d == 'up' else '1→0'} | "
                    f"{c[0]:+.0f} | "
                    f"{np.nanmax(np.abs(c)):.0f} | {tail1:+.0f} / {tail2:+.0f} | "
                    f"{fmt_settle(settle_periods(c, se))} | {g[0]:+.0f} / {g[2]:+.0f} | "
                    f"{np.mean([j[d]['mean_s_first_period'] for j in js]):+.2f} | "
                    f"{np.mean([j[d]['peak_abs_mean'] for j in js]):.2f} / "
                    f"{np.max([j[d]['peak_abs_max'] for j in js]):.2f} | "
                    f"{n_hit} / {len(js) * JUMP_CYCLES} | {clean} |"
                )
    print(
        "\n### Safety probes (modulator 0 ↔ 1; u range after the slew; 95 % Clopper–Pearson"
        " interval per cycle)\n"
    )
    print(
        "| case | seeds | resets / jumps | rate per jump (95 % CI) | resets per min | max box usage"
        " | u range | resets at (periods after cycle start) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for k, rows in summary["reset_probe"].items():
        n_r = sum(r["resets"] for r in rows)
        n_c = sum(r["jumps"] for r in rows)
        minutes = sum(r["seconds"] for r in rows) / 60
        smooth = "sine" in k or "triangle" in k
        if smooth:
            rate = "(no jumps)"
        else:
            lo, hi = clopper_pearson(min(n_r, n_c), n_c)
            rate = f"{100 * n_r / n_c:.1f} % ({100 * lo:.1f}–{100 * hi:.1f} %)"
        after = sorted(round(x, 1) for r in rows for x in r["reset_periods_after_cycle_start"])
        ur = (min(r["u_range"][0] for r in rows), max(r["u_range"][1] for r in rows))
        print(
            f"| {k} | {len(rows)} | {n_r} / {'–' if smooth else n_c} | {rate} | "
            f"{n_r / minutes:.2f} | {max(r['box_usage'] for r in rows):.2f} | "
            f"{ur[0]:.2f}–{ur[1]:.2f} | {after[:12]}{' …' if len(after) > 12 else ''} |"
        )
    pr = summary["reset_probe"]
    for note in ("A0", "A1"):
        a = pr[f"chua|{note}|square 64 per.|v0.2"]
        b = pr[f"chua|{note}|square 64 per.|v0.3"]
        ka, na = sum(r["resets"] for r in a), sum(r["jumps"] for r in a)
        kb, nb = sum(r["resets"] for r in b), sum(r["jumps"] for r in b)
        _, pval = fisher_exact([[ka, na - ka], [kb, nb - kb]])
        print(f"Fisher exact, Chua {note} v0.2 vs v0.3 (square 64 per.): p = {pval:.2g}")
    print("\n### Chua, observable x, sine T = 5 s: single-scroll episodes (u < 0.1)\n")
    for k, c in enumerate(summary["chua_x"]):
        print(
            f"seed {k}: signs {c['signs']}, mean s {np.round(c['mean_s'], 2).tolist()}, "
            f"peak |audio| {np.round(c['peak_abs'], 2).tolist()} (catalog μ_x(0) "
            f"{c['catalog_mu_x_u0']:+.2f})"
        )
    signs = np.concatenate([c["signs"] for c in summary["chua_x"]])
    for v in ("x", "z"):
        for norm in ("catalog", "mu0", "mu0_pooled_sigma"):
            vals = np.concatenate([c["alt"][v][norm] for c in summary["chua_x"]])
            per_scroll = ", ".join(
                f"x {'>' if sg > 0 else '<'} 0 scroll: {np.mean(vals[signs == sg]):+.2f}"
                for sg in (-1, 1)
                if np.any(signs == sg)
            )
            print(f"mean s of {v}, normalization {norm}: {per_scroll}")
    e = CAT["chua"]
    g = np.asarray(e.u_grid)
    mu_x = np.array([float(e.mean("x", ug)) for ug in g])
    last = int(np.argmax(np.abs(mu_x) < 0.5)) - 1  # single scroll at low u: |μ_x| ≈ 1.2
    print(
        f"single-scroll μ_x table ends between u = {g[last]:.3f} "
        f"({e.param} = {float(e.param_value(g[last])):.2f}) and u = {g[last + 1]:.3f} "
        f"({e.param} = {float(e.param_value(g[last + 1])):.2f})"
    )
    print("\npatch check:", summary["patch_check"])
    print("escape example:", summary["escape_example"], summary["escape_example_resets"])


if __name__ == "__main__":
    main()
