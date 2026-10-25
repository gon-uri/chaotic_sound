"""Study: how fast can a dynamical box's parameter be modulated.

Pitch lock (k = P(u)·f₀) and loudness normalization ((x − μ(u))/σ(u)) use catalog tables
measured at *fixed* parameter values, so they assume that the trajectory follows the attractor
adiabatically. This script drives u of Lorenz, Chua and Rössler (note A3) with a full-range
sine LFO whose period goes from 20 s down to 0.05 s (plus 0.02 s and 0.01 s, beyond the brief)
and measures, against static references taken at fixed u:

(a) pitch: the power-weighted instantaneous frequency of the audio (Hilbert transform of the
    band-passed signal, f₀/1.6 … 1.6·f₀). Weighted by |analytic signal|², its average over a
    window equals the spectral centroid of that band in the window. Phase-binned over the LFO
    cycle and compared with the note and with the static value at the same u(t);
(b) loudness: phase-binned RMS of the audio, and the mean of the normalized observable
    s = (x_obs − μ(u))/σ(u) before the DC blocker (ideal: 0);
(c) the attractor: safety resets, the nearest-neighbour distance from the state to static
    attractor clouds at the same u (in units of the static σ), and the use of the safety box.

Extra experiments: square-wave (jump) responses; a safety-reset probe for abrupt jumps at low
notes (A0–A3), with two mitigations; Chua with the non-default observable x (mirror single
scrolls); Lorenz at A2/A3/A4 to check that the rate is best counted per oscillation period;
a bit-exact cross-check against ``Patch.render``; a few WAV examples.

Usage (from ``lab/``)::

    caffeinate -is uv run python scripts/studies/modulation.py

Writes figures, WAVs and ``results.json`` to ``outputs/studies/modulation/`` and prints the
Markdown tables used in ``docs/studies/modulation.md``. Runtime ≈ 3–4 minutes on an M1.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# numba's on-disk cache for kernels that take the RHS dispatcher as an argument
# (render_tuned) gains one index entry per process and, in this environment, crashed with
# "ReferenceError: underlying object has vanished" when re-saving the index. Use a private,
# throw-away cache directory (reported as an engine issue in docs/studies/modulation.md).
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="chaotic_sound_numba_"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
from scipy.fft import next_fast_len
from scipy.signal import butter, hilbert, sosfiltfilt, welch
from scipy.spatial import cKDTree

import chaotic_sound.blocks.dynamical as dynamical_module
from chaotic_sound.blocks import Dynamical
from chaotic_sound.blocks.modulator import shape_value
from chaotic_sound.catalog import load_default_catalog
from chaotic_sound.dsp import one_pole, one_pole_coefficient, soft_clip
from chaotic_sound.patch import Patch
from chaotic_sound.pitch import note_to_hz
from chaotic_sound.wav import write_wav

Array = NDArray[np.float64]

LAB = Path(__file__).resolve().parents[2]
OUT = LAB / "outputs" / "studies" / "modulation"
FS = 48_000
NOTE = "A3"
F0 = note_to_hz(NOTE)
SYSTEMS = ("lorenz", "chua", "rossler")
PERIODS = (20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05)
EXTRA_PERIODS = (0.02, 0.01)  # beyond the brief: audio-rate side; the declick limits the depth
ALL_PERIODS = PERIODS + EXTRA_PERIODS
SEEDS = (0, 1, 2)
TRANSIENT_S = 2.0
ANALYZE_MIN_S = 30.0
N_BINS = 24
BAND = (1 / 1.6, 1.6)  # pitch band relative to f0
STATIC_GRID = np.linspace(0.0, 1.0, 41)
STATIC_SECONDS = 10.0
STATIC_SEED = 100
CALIB_SEED = 200
CLOUD_STRIDE = 4
QUERY_STRIDE = 16
SYMMETRY = {"lorenz": np.array([-1.0, -1.0, 1.0]), "chua": np.array([-1.0, -1.0, -1.0])}
NAMES = {"lorenz": "Lorenz", "chua": "Chua", "rossler": "Rössler"}
JUMP_LEVEL_PERIODS = 64  # oscillation periods per square-wave level
JUMP_EDGES = np.array([0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64], dtype=float)
PROBE_NOTES = ("A0", "A1", "A2", "A3")
PROBE_CYCLES = 60

# Chart tokens (dataviz reference palette, light mode).
COLORS = {"lorenz": "#2a78d6", "chua": "#eb6834", "rossler": "#1baf7a"}
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


@dataclass
class Run:
    """One rendered box. ``audio`` is the left channel after the DC blocker."""

    audio: Array
    s: Array  # (x_obs − μ(u))/σ(u) before the DC blocker; audio ≈ 0.25·s, high-passed
    u: Array  # smoothed (declicked, clipped) knob actually used, per sample
    traj: Array
    resets: int
    reset_index: Array  # samples at which a safety reset happened
    obs_index: int


def make_box(system: str, note: str, seed: int, observable: str | None) -> Dynamical:
    params: dict[str, Any] = {"system": system, "note": note, "seed": seed}
    if observable is not None:
        params["observable"] = observable
    box = Dynamical("osc", catalog=CAT, **params)
    box.reset(FS)
    return box


def render(
    system: str, u_raw: Array, *, note: str = NOTE, seed: int = 0, observable: str | None = None
) -> Run:
    """Render a box driven by the control signal ``u_raw`` (one call: block size = n)."""
    box = make_box(system, note, seed, observable)
    audio = box.process(len(u_raw), {"param": u_raw, "amp": None})["out"][:, 0].copy()
    e = box.entry
    u = (_captured["p_values"] - e.p_min) / (e.p_max - e.p_min)
    traj = _captured["traj"]
    i = box.system.variable_index(box.observable)
    s = (traj[:, i] - e.mean(box.observable, u)) / e.std(box.observable, u)
    resets_at = np.flatnonzero(np.all(traj == box._x_reset, axis=1))
    return Run(audio, s, u, traj, box.resets, resets_at, i)


def lfo(shape: str, period_s: float, n: int, start: int = 0) -> Array:
    """Return the modulator's output (spec §4.1), loop mode, phase 0 at sample 0."""
    t = (start + np.arange(n)) / FS
    return shape_value(shape, np.mod(t / period_s, 1.0))


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


def box_usage(system: str, traj: Array) -> float:
    """Max over time and variables of |x − centre| / half-width of the safety box."""
    e = CAT[system]
    c = 0.5 * (e.bounds_hi + e.bounds_lo)
    h = 0.5 * (e.bounds_hi - e.bounds_lo)
    return float(np.max(np.abs(traj - c) / h))


# -- static references -----------------------------------------------------------------------


@dataclass
class StaticRef:
    """Measurements at fixed u on ``STATIC_GRID`` (the adiabatic reference)."""

    system: str
    u: Array
    cents: Array  # power-weighted pitch vs the note
    loop_cents: Array  # mean loop rate (maxima of the observable) vs the note
    mean_s: Array
    std_s: Array
    rms: Array
    box_usage: Array
    peak: Array
    trees: list[cKDTree] = field(repr=False)
    scales: list[Array] = field(repr=False)
    threshold: float = math.nan
    psd_f: Array | None = None
    psd: Array | None = None  # time-weighted mean static PSD for a full-range sine sweep

    def cents_at(self, u: Array) -> Array:
        """Interpolate the static pitch (cents re the note) at u."""
        return np.interp(u, self.u, self.cents)


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
    n_tr = FS
    n = int(STATIC_SECONDS * FS) + n_tr
    rows: dict[str, list[float]] = {
        k: [] for k in ("cents", "loop", "mean_s", "std_s", "rms", "box", "peak")
    }
    trees, scales, psds = [], [], []
    pf = np.zeros(0)
    for u0 in STATIC_GRID:
        r = render(system, np.full(n, u0), seed=STATIC_SEED)
        a, s, tr = r.audio[n_tr:], r.s[n_tr:], r.traj[n_tr:]
        f, w = inst_freq(r.audio, F0)
        f, w = f[n_tr : -FS // 10], w[n_tr : -FS // 10]
        rows["cents"].append(float(cents(np.sum(w * f) / np.sum(w), F0)))
        lt = loop_times(tr[:, r.obs_index])
        rows["loop"].append(float(cents(1.0 / np.mean(np.diff(lt)), F0)))
        rows["mean_s"].append(float(np.mean(s)))
        rows["std_s"].append(float(np.std(s)))
        rows["rms"].append(float(np.sqrt(np.mean(a**2))))
        rows["box"].append(box_usage(system, tr))
        rows["peak"].append(float(np.max(np.abs(a))))
        cloud = tr[::CLOUD_STRIDE]
        scale = cloud.std(axis=0)
        if system in SYMMETRY:
            cloud = np.vstack([cloud, cloud * SYMMETRY[system]])
        trees.append(cKDTree(cloud / scale))
        scales.append(scale)
        pf, pp = welch(a, fs=FS, nperseg=2**15)
        psds.append(pp)
    # Time-weighted static spectrum of a full-range sine sweep (arcsine density of u).
    edges = np.concatenate([[0.0], 0.5 * (STATIC_GRID[1:] + STATIC_GRID[:-1]), [1.0]])
    wts = np.diff(np.arccos(1 - 2 * edges)) / np.pi  # P(u in cell) for u = (1 − cos θ)/2
    ref = StaticRef(
        system,
        STATIC_GRID.copy(),
        *(np.array(rows[k]) for k in ("cents", "loop", "mean_s", "std_s", "rms", "box", "peak")),
        trees=trees,
        scales=scales,
        psd_f=pf,
        psd=np.tensordot(wts, np.array(psds), axes=1),
    )
    # Threshold: 99.9 % quantile of the distances of an independent run at the grid midpoints.
    mids = 0.5 * (STATIC_GRID[1:] + STATIC_GRID[:-1])
    dists = []
    n_c = 4 * FS + n_tr
    for um in mids:
        r = render(system, np.full(n_c, um), seed=CALIB_SEED)
        tr = r.traj[n_tr::QUERY_STRIDE]
        dists.append(nn_distance(ref, tr, np.full(len(tr), um)))
    ref.threshold = float(np.quantile(np.concatenate(dists), 0.999))
    return ref


# -- modulated runs --------------------------------------------------------------------------


def analysis_window(period_s: float) -> tuple[int, int]:
    n_cyc = max(2, math.ceil(ANALYZE_MIN_S / period_s))
    i0 = round(TRANSIENT_S * FS)
    return i0, i0 + round(n_cyc * period_s * FS)


def updown(v: Array) -> tuple[Array, Array]:
    """Split a phase profile into hysteresis (up − down)/2 and symmetric (up + down)/2 parts.

    Bin k (u rising, φ < ½) and bin N − 1 − k (u falling) have the same u for the sine LFO.
    """
    up, down = v[: N_BINS // 2], v[::-1][: N_BINS // 2]
    return 0.5 * (up - down), 0.5 * (up + down)


def analyze_modulated(
    ref: StaticRef, system: str, run: Run, period_s: float, f0: float = F0
) -> dict:
    i0, i1 = analysis_window(period_s)
    f, w = inst_freq(run.audio, f0)
    sl = slice(i0, i1)
    ph = np.mod((np.arange(i0, i1) / FS) / period_s, 1.0)
    b = np.minimum((ph * N_BINS).astype(int), N_BINS - 1)
    u, a, s, ff, ww = run.u[sl], run.audio[sl], run.s[sl], f[sl], w[sl]
    f_ref = f0 * 2.0 ** (ref.cents_at(u) / 1200.0)
    W = np.bincount(b, ww, N_BINS)
    cnt = np.bincount(b, None, N_BINS)
    f_bin = np.bincount(b, ww * ff, N_BINS) / W
    fref_bin = np.bincount(b, ww * f_ref, N_BINS) / W
    dev = cents(f_bin, fref_bin)
    abs_c = cents(f_bin, f0)
    static_c = cents(fref_bin, f0)
    mean_s = np.bincount(b, s, N_BINS) / cnt
    rms_bin = np.sqrt(np.bincount(b, a**2, N_BINS) / cnt)
    level = 20 * np.log10(rms_bin / 0.25)
    lf = lowpass(run.audio, f0 / 2)[sl]
    lf_sync = np.bincount(b, lf, N_BINS) / cnt
    d = nn_distance(ref, run.traj[sl][::QUERY_STRIDE], u[::QUERY_STRIDE])
    hyst, sym = updown(dev)
    lh, _ = updown(level)
    return {
        "u_min": float(u.min()),
        "u_max": float(u.max()),
        "resets": int(run.resets),
        "pitch_abs_bins": abs_c.tolist(),
        "pitch_dev_bins": dev.tolist(),
        "level_bins": level.tolist(),
        "pitch_abs_rms": float(np.sqrt(np.mean(abs_c**2))),
        "pitch_abs_max": float(np.max(np.abs(abs_c))),
        "pitch_static_rms": float(np.sqrt(np.mean(static_c**2))),
        "pitch_mean_dev": float(cents(np.sum(ww * ff), np.sum(ww * f_ref))),
        "pitch_dev_rms": float(np.sqrt(np.mean(dev**2))),
        "pitch_dev_max": float(np.max(np.abs(dev))),
        "pitch_hyst_rms": float(np.sqrt(np.mean(hyst**2))),
        "pitch_sym_rms": float(np.sqrt(np.mean(sym**2))),
        "level_all_db": float(20 * np.log10(np.sqrt(np.mean(a**2)) / 0.25)),
        "level_bin_max_db": float(np.max(np.abs(level))),
        "level_hyst_rms_db": float(np.sqrt(np.mean(lh**2))),
        "mean_s_max": float(np.max(np.abs(mean_s))),
        "lf_sync_rms": float(np.sqrt(np.mean(lf_sync**2))),
        "peak_abs": float(np.max(np.abs(a))),
        "excursion_frac": float(np.mean(d > ref.threshold)),
        "nn_q99": float(np.quantile(d, 0.99)),
        "nn_max": float(np.max(d)),
        "box_usage": box_usage(system, run.traj[sl]),
    }


def seed_stats(rows: list[dict], key: str) -> tuple[Any, Any]:
    v = np.array([r[key] for r in rows], dtype=float)
    return v.mean(axis=0), v.std(axis=0, ddof=1)


# -- jumps (square-wave modulation) ----------------------------------------------------------


def jump_response(ref: StaticRef, system: str, note: str, seed: int, n_cycles: int = 40) -> dict:
    """Square wave 0 ↔ 1 (each level held 64 oscillation periods): loop-rate pitch vs time."""
    f0 = note_to_hz(note)
    period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    n = round((n_cycles + 1) * period_s * FS)
    run = render(system, lfo("square", period_s, n), note=note, seed=seed)
    lt = loop_times(run.traj[:, run.obs_index])
    per, t_start = np.diff(lt), lt[:-1]
    nb = len(JUMP_EDGES) - 1
    out: dict[str, Any] = {"resets": int(run.resets)}
    # square: u = 1 for φ < ½, so u jumps 0→1 at φ = 0 ("up") and 1→0 at φ = ½ ("down").
    for name, phase0 in (("up", 0.0), ("down", 0.5)):
        per_jump, s_first, peaks = [], [], []
        for t_j in (np.arange(1, n_cycles + 1) + phase0) * period_s:
            m = (t_start >= t_j) & (t_start < t_j + 0.5 * period_s)
            k = np.digitize((t_start[m] - t_j) * f0, JUMP_EDGES) - 1
            k = np.clip(k, 0, nb - 1)
            sums = np.bincount(k, per[m], nb)
            cnts = np.bincount(k, None, nb)
            with np.errstate(divide="ignore", invalid="ignore"):
                per_jump.append(cents(cnts / sums, f0))
            i_j = round(t_j * FS)
            s_first.append(float(np.mean(run.s[i_j : i_j + int(FS / f0)])))
            peaks.append(float(np.max(np.abs(run.audio[i_j : i_j + int(0.5 * period_s * FS)]))))
        c = np.array(per_jump)
        out[name] = {
            "cents_mean": np.nanmean(c, axis=0).tolist(),
            "cents_se": (np.nanstd(c, axis=0) / np.sqrt(np.sum(np.isfinite(c), axis=0))).tolist(),
            "mean_s_first_period": float(np.mean(s_first)),
            "peak_abs_mean": float(np.mean(peaks)),
            "peak_abs_max": float(np.max(peaks)),
        }
    out["static_loop_cents"] = {
        "u0": float(ref.loop_cents[0]),
        "u1": float(ref.loop_cents[-1]),
    }
    return out


def settle_periods(c: Array, se: Array, tol: float = 10.0) -> tuple[float, float]:
    """Settling time (periods) to the late value (mean of the 32–64-period bins).

    Returns (late value, first bin edge after which every bin is within max(tol, 2·SE)).
    """
    c, se = np.asarray(c), np.asarray(se)
    late = float(np.mean(c[-2:]))
    ok = np.abs(c - late) <= np.maximum(tol, 2 * se)
    bad = np.flatnonzero(~ok)
    return late, float(JUMP_EDGES[bad[-1] + 1]) if bad.size else 0.0


def reset_probe(
    system: str, note: str, seed: int, *, lo: float = 0.0, hi: float = 1.0, smooth: float = 0.0
) -> dict:
    """Count safety resets for a square wave lo ↔ hi; ``smooth`` = extra one-pole (periods)."""
    f0 = note_to_hz(note)
    period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    n_total = round((PROBE_CYCLES + 1) * period_s * FS)
    box = make_box(system, note, seed, None)
    chunk = 10 * FS
    state = np.zeros(1)
    alpha = one_pole_coefficient(smooth / f0, FS) if smooth > 0 else 1.0
    resets_at, usage = [], 0.0
    pos = 0
    while pos < n_total:
        m = min(chunk, n_total - pos)
        u_raw = lo + (hi - lo) * lfo("square", period_s, m, start=pos)
        if smooth > 0:
            if pos == 0:
                state[0] = u_raw[0]
            u_s = np.empty(m)
            one_pole(u_raw, state, alpha, u_s)
            u_raw = u_s
        box.process(m, {"param": u_raw, "amp": None})
        traj = _captured["traj"]
        resets_at += (pos + np.flatnonzero(np.all(traj == box._x_reset, axis=1))).tolist()
        usage = max(usage, box_usage(system, traj))
        pos += m
    phase = np.mod(np.array(resets_at) / FS / period_s, 1.0)
    return {
        "resets": int(box.resets),
        "jumps_up": PROBE_CYCLES,
        "box_usage": usage,
        "reset_samples": resets_at,
        "reset_phase_periods_after_up": (phase * period_s * f0).tolist(),
    }


# -- Chua with observable x -----------------------------------------------------------------


def chua_x_check(seed: int, period_s: float = 5.0, n_cycles: int = 6) -> dict:
    """Single-scroll episodes (u < 0.1) of a sine sweep: which scroll, and the offset in s."""
    n = round((n_cycles + 0.5) * period_s * FS)
    run = render("chua", lfo("sine", period_s, n), seed=seed, observable="x")
    x = run.traj[:, 0]
    low = run.u < 0.1
    starts = np.flatnonzero(~low[:-1] & low[1:]) + 1
    stops = np.flatnonzero(low[:-1] & ~low[1:]) + 1
    signs, offsets, peaks = [], [], []
    for st in starts:
        en = stops[stops > st]
        if not en.size or st < TRANSIENT_S * FS:
            continue
        sl = slice(st, en[0])
        signs.append(int(np.sign(np.mean(x[sl]))))
        offsets.append(float(np.mean(run.s[sl])))
        peaks.append(float(np.max(np.abs(run.audio[st - FS // 5 : en[0] + FS // 5]))))
    return {"signs": signs, "mean_s": offsets, "peak_abs": peaks}


# -- figures ---------------------------------------------------------------------------------


def fig_profiles(results: dict, refs: dict[str, StaticRef], path: Path) -> None:
    show = (20.0, 1.0, 0.2, 0.1, 0.05, 0.02)
    fig, axes = plt.subplots(3, 3, figsize=(11, 8.4), sharex=True)
    ph = (np.arange(N_BINS) + 0.5) / N_BINS
    u_phase = 0.5 * (1 - np.cos(2 * np.pi * ph))
    for col, system in enumerate(SYSTEMS):
        ax0, ax1, ax2 = axes[:, col]
        ax0.plot(ph, refs[system].cents_at(u_phase), color=MUTED, lw=1.2, ls="--")
        for k, T in enumerate(show):
            rows = results[system][str(T)]
            lab = f"T = {T:g} s" + (" *" if T < 0.05 else "")
            ax0.plot(ph, seed_stats(rows, "pitch_abs_bins")[0], color=SEQ[k], label=lab)
            ax1.plot(ph, seed_stats(rows, "pitch_dev_bins")[0], color=SEQ[k], label=lab)
            ax2.plot(ph, seed_stats(rows, "level_bins")[0], color=SEQ[k], label=lab)
        ax0.set_title(NAMES[system], loc="left", fontsize=10)
        if col == 0:
            ax0.set_ylabel("pitch − note (cents)")
            ax1.set_ylabel("pitch − static pitch at same u (cents)")
            ax2.set_ylabel("audio RMS re 0.25 (dB)")
        ax2.set_xlabel("LFO phase  (u rises 0 → 1 until 0.5, then falls)")
        for ax in (ax0, ax1, ax2):
            ax.axhline(0, color=AXIS, lw=0.8)
            ax.axvline(0.5, color=GRID, lw=0.8)
    axes[0, 0].plot([], [], color=MUTED, ls="--", lw=1.2, label="static (fixed u)")
    axes[0, 0].legend(fontsize=7.5, loc="lower left", ncol=2)
    fig.suptitle(
        f"Full-range sine modulation of u at {NOTE}: phase-binned pitch and loudness, mean of "
        f"{len(SEEDS)} seeds (* = beyond the brief)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_summary(results: dict, path: Path) -> None:
    rate = np.array([2.0 / (F0 * T) for T in ALL_PERIODS])
    panels = (
        ("pitch_dev_rms", "pitch − static, RMS over LFO phase (cents)", False),
        ("level_bin_max_db", "max |RMS level re 0.25| over LFO phase (dB)", False),
        ("lf_sync_rms", "modulation-locked component < f₀/2, RMS", True),
        ("nn_q99", "99th pct distance to static attractor (σ)", True),
    )
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for ax, (key, label, logy) in zip(axes.flat, panels, strict=True):
        ax.axvspan(2 / (F0 * 0.05) * 1.4, rate.max() * 1.4, color="#f1f0ec", zorder=0)
        for system in SYSTEMS:
            m = np.array([seed_stats(results[system][str(T)], key)[0] for T in ALL_PERIODS])
            sd = np.array([seed_stats(results[system][str(T)], key)[1] for T in ALL_PERIODS])
            ax.errorbar(
                rate, m, yerr=sd, color=COLORS[system], marker="o", ms=4, lw=1.6, capsize=2,
                label=NAMES[system],
            )  # fmt: skip
        ax.set_xscale("log")
        if logy:
            ax.set_yscale("log")
        ax.set_ylabel(label)
        ax.set_xlabel("full-range sweeps per oscillation period, 2/(f₀T)")
    axes[0, 0].legend(loc="upper left")
    fig.suptitle(
        f"Errors vs modulation rate (sine, full range, {NOTE}: T = 20 s at left … 0.01 s at "
        "right; shaded: beyond the brief; bars: seed spread)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_jumps(jumps: dict, path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(11, 6), sharex=True)
    x = np.sqrt(np.maximum(JUMP_EDGES[:-1], 0.25) * JUMP_EDGES[1:])
    for col, system in enumerate(SYSTEMS):
        for row, (name, title) in enumerate((("up", "u jumps 0 → 1"), ("down", "u jumps 1 → 0"))):
            ax = axes[row, col]
            for note, ls in (("A3", "-"), ("A1", "--")):
                js = jumps[system][note]
                c = np.mean([j[name]["cents_mean"] for j in js], axis=0)
                se = np.sqrt(np.mean(np.square([j[name]["cents_se"] for j in js]), axis=0) / 3)
                key = "u1" if name == "up" else "u0"
                ref = js[0]["static_loop_cents"][key]
                ax.errorbar(
                    x, c - ref, yerr=2 * se, color=COLORS[system], ls=ls, marker="o", ms=3,
                    capsize=2, label=note,
                )  # fmt: skip
            ax.axhline(0, color=AXIS, lw=0.8)
            ax.set_title(f"{NAMES[system]}: {title}", loc="left", fontsize=9.5)
            ax.set_xscale("log")
            if col == 0:
                ax.set_ylabel("loop-rate pitch − static (cents)")
            if row == 1:
                ax.set_xlabel("time after the jump (oscillation periods)")
        axes[0, col].legend(fontsize=7.5)
    fig.suptitle(
        "Square-wave modulation (5 ms declick): pitch after a full-range jump, relative to the "
        "static loop rate at the new u (bars: ±2 SE)",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_spectra(spectra: dict, refs: dict[str, StaticRef], path: Path) -> None:
    show = (20.0, 0.2, 0.05, 0.02)
    fig, axes = plt.subplots(len(show), 3, figsize=(11, 8), sharex=True)
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
        f"Long-term audio spectra under full-range sine modulation ({NOTE} = 220 Hz) vs the "
        "time-weighted average of static spectra",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_escape(note: str, seed: int, sample: int, path: Path) -> None:
    """Chua: an escape after an abrupt 0 → 1 jump, ending in a safety reset."""
    f0 = note_to_hz(note)
    period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
    n = sample + int(6 * FS / f0)
    run = render("chua", lfo("square", period_s, n), note=note, seed=seed)
    t_jump = math.floor(sample / FS / period_s) * period_s
    i0 = max(0, int((t_jump - 6 / f0) * FS))
    t = (np.arange(i0, n) / FS - t_jump) * f0
    e = CAT["chua"]
    fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
    axes[0].plot(t, run.u[i0:], color=INK2)
    axes[0].set_ylabel("u (after declick)")
    for j, (var, c) in enumerate((("x", COLORS["chua"]), ("y", "#2a78d6"), ("z", "#1baf7a"))):
        axes[1].plot(t, run.traj[i0:, j] / e.bounds_hi[j], color=c, lw=1.2, label=var)
    axes[1].axhline(1, color=AXIS, ls="--", lw=0.8)
    axes[1].axhline(-1, color=AXIS, ls="--", lw=0.8)
    axes[1].set_ylabel("state / safety bound")
    axes[1].legend(fontsize=7.5, ncol=3, loc="upper left")
    axes[2].plot(t, run.audio[i0:], color=COLORS["chua"], lw=1.0)
    axes[2].set_ylabel("audio (before Output)")
    axes[2].set_xlabel("time after the jump (oscillation periods)")
    axes[0].set_title(
        f"Chua at {note}: escape after an abrupt u 0 → 1 jump (seed {seed}) and safety reset",
        loc="left",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# -- main ------------------------------------------------------------------------------------


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    refs: dict[str, StaticRef] = {}
    for system in SYSTEMS:
        t0 = time.time()
        refs[system] = r = build_static(system)
        print(
            f"static {system}: cents [{r.cents.min():+.1f}, {r.cents.max():+.1f}], NN thr "
            f"{r.threshold:.3f} ({time.time() - t0:.1f} s)",
            flush=True,
        )

    results: dict[str, dict[str, list[dict]]] = {s: {} for s in SYSTEMS}
    spectra: dict[str, dict[str, tuple[Array, Array]]] = {s: {} for s in SYSTEMS}
    for system in SYSTEMS:
        t0 = time.time()
        for T in ALL_PERIODS:
            i0, i1 = analysis_window(T)
            rows = []
            for seed in SEEDS:
                run = render(system, lfo("sine", T, i1 + FS // 10), seed=seed)
                rows.append(analyze_modulated(refs[system], system, run, T))
                if seed == SEEDS[0]:
                    spectra[system][str(T)] = welch(run.audio[i0:i1], fs=FS, nperseg=2**15)
                    if system in ("lorenz", "rossler") and T in (1.0, 0.1, 0.05, 0.02):
                        clip = soft_clip(run.audio[i0 : i0 + 6 * FS])
                        write_wav(OUT / "wav" / f"{system}_sine_T{T:g}s_{NOTE}.wav", clip, FS)
            results[system][str(T)] = rows
        print(f"modulated {system}: {time.time() - t0:.1f} s", flush=True)

    # The rate counted per oscillation period: Lorenz at three notes, same N = f0·T/2.
    scaling: dict[str, list[dict]] = {}
    for n_osc in (11.0, 55.0):
        for note in ("A2", "A3", "A4"):
            f0 = note_to_hz(note)
            T = 2 * n_osc / f0
            _, i1 = analysis_window(T)
            scaling[f"{n_osc:g}|{note}"] = [
                analyze_modulated(
                    refs["lorenz"],
                    "lorenz",
                    render("lorenz", lfo("sine", T, i1 + FS // 10), note=note, seed=sd),
                    T,
                    f0=f0,
                )
                for sd in SEEDS
            ]
    print(f"scaling done ({time.time() - t_start:.0f} s)", flush=True)

    jumps: dict[str, dict[str, list[dict]]] = {s: {} for s in SYSTEMS}
    for system in SYSTEMS:
        for note in ("A3", "A1"):
            jumps[system][note] = [jump_response(refs[system], system, note, sd) for sd in SEEDS]
    print(f"jumps done ({time.time() - t_start:.0f} s)", flush=True)

    probe: dict[str, list[dict]] = {}
    for system in SYSTEMS:
        for note in PROBE_NOTES:
            probe[f"{system}|{note}|0-1"] = [reset_probe(system, note, sd) for sd in SEEDS]
    for note in ("A0", "A1"):
        probe[f"chua|{note}|0-0.9"] = [reset_probe("chua", note, sd, hi=0.9) for sd in SEEDS]
        probe[f"chua|{note}|0-1 smooth 2 periods"] = [
            reset_probe("chua", note, sd, smooth=2.0) for sd in SEEDS
        ]
    print(f"probe done ({time.time() - t_start:.0f} s)", flush=True)

    chua_x = [chua_x_check(sd) for sd in SEEDS]

    # Cross-check against the full Patch path (chunked rendering, Output block).
    p = Patch()
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

    # Escape example for the figure and a WAV.
    escape = None
    for note in ("A1", "A0"):
        for sd, row in zip(SEEDS, probe[f"chua|{note}|0-1"], strict=True):
            if row["reset_samples"] and escape is None:
                escape = (note, sd, int(row["reset_samples"][0]))
    if escape is not None:
        fig_escape(*escape, OUT / "fig5_chua_escape.png")
        note, sd, smp = escape
        f0 = note_to_hz(note)
        period_s = 2.0 * JUMP_LEVEL_PERIODS / f0
        i_end = smp + 2 * FS
        i_beg = max(0, i_end - 12 * FS)
        run = render("chua", lfo("square", period_s, i_end), note=note, seed=sd)
        write_wav(OUT / "wav" / f"chua_square_{note}_escape.wav", soft_clip(run.audio[i_beg:]), FS)

    summary = {
        "settings": {
            "fs": FS,
            "note": NOTE,
            "periods": PERIODS,
            "extra_periods": EXTRA_PERIODS,
            "seeds": SEEDS,
            "n_bins": N_BINS,
            "band": BAND,
            "static_grid_points": len(STATIC_GRID),
            "static_seconds": STATIC_SECONDS,
        },
        "static": {
            s: {
                "u": r.u.tolist(),
                "cents": r.cents.tolist(),
                "loop_cents": r.loop_cents.tolist(),
                "mean_s": r.mean_s.tolist(),
                "std_s": r.std_s.tolist(),
                "rms": r.rms.tolist(),
                "box_usage": r.box_usage.tolist(),
                "peak_abs": r.peak.tolist(),
                "nn_threshold": r.threshold,
            }
            for s, r in refs.items()
        },
        "modulated": results,
        "scaling": scaling,
        "jumps": jumps,
        "reset_probe": probe,
        "chua_x": chua_x,
        "patch_check": patch_check,
        "escape_example": escape,
    }
    (OUT / "results.json").write_text(json.dumps(summary, indent=1))
    fig_profiles(results, refs, OUT / "fig1_phase_profiles.png")
    fig_summary(results, OUT / "fig2_rate_summary.png")
    fig_jumps(jumps, OUT / "fig3_jump_response.png")
    fig_spectra(spectra, refs, OUT / "fig4_spectra.png")
    print_tables(summary, refs)
    print(f"\ntotal wall time {time.time() - t_start:.0f} s")


def fmt_ms(rows: list[dict], key: str, fmt: str) -> str:
    m, sd = seed_stats(rows, key)
    return f"{fmt.format(m)} ± {fmt.format(sd).lstrip('+')}"


def print_tables(summary: dict, refs: dict[str, StaticRef]) -> None:
    res = summary["modulated"]
    print("\n### Static references (fixed u, 41 points, 10 s each)\n")
    print(
        "| system | pitch − note, min … max (c) | loop-rate pitch − note (c) | RMS min … max |"
        " max mean s | NN threshold (σ) | box usage | peak audio |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for s, r in refs.items():
        print(
            f"| {s} | {r.cents.min():+.0f} … {r.cents.max():+.0f} | {r.loop_cents.min():+.0f} "
            f"… {r.loop_cents.max():+.0f} | {r.rms.min():.3f} … {r.rms.max():.3f} | "
            f"{np.max(np.abs(r.mean_s)):.3f} | {r.threshold:.3f} | {r.box_usage.max():.2f} | "
            f"{r.peak.max():.2f} |"
        )
    pitch_cols = (
        ("pitch_abs_rms", "{:.0f}"),
        ("pitch_static_rms", "{:.0f}"),
        ("pitch_dev_rms", "{:.1f}"),
        ("pitch_hyst_rms", "{:.1f}"),
        ("pitch_sym_rms", "{:.1f}"),
        ("pitch_dev_max", "{:.0f}"),
        ("pitch_mean_dev", "{:+.1f}"),
    )
    level_cols = (
        ("level_all_db", "{:+.2f}"),
        ("level_bin_max_db", "{:.2f}"),
        ("level_hyst_rms_db", "{:.2f}"),
        ("mean_s_max", "{:.3f}"),
        ("lf_sync_rms", "{:.4f}"),
        ("excursion_frac", "{:.3f}"),
        ("nn_q99", "{:.3f}"),
        ("nn_max", "{:.2f}"),
        ("box_usage", "{:.2f}"),
    )
    for title, cols in (("pitch", pitch_cols), ("loudness and attractor", level_cols)):
        for system in SYSTEMS:
            print(f"\n### {system}: {title} (sine, full range, {NOTE}; mean ± sd, 3 seeds)\n")
            print("| T (s) | sweeps/period | u range | resets | " + " | ".join(k for k, _ in cols))
            print("|" + "---|" * (4 + len(cols)))
            for T in ALL_PERIODS:
                rows = res[system][str(T)]
                umin = np.mean([r["u_min"] for r in rows])
                umax = np.mean([r["u_max"] for r in rows])
                print(
                    f"| {T:g} | {2 / (F0 * T):.2g} | {umin:.2f}–{umax:.2f} | "
                    f"{sum(r['resets'] for r in rows)} | "
                    + " | ".join(fmt_ms(rows, k, f) for k, f in cols)
                    + " |"
                )
    print("\n### Rate per oscillation period: Lorenz at three notes\n")
    print("| N = f0·T/2 | note | T (s) | u range | pitch − static RMS (c) | hysteresis RMS (c) |")
    print("|---|---|---|---|---|---|")
    for k, rows in summary["scaling"].items():
        n_osc, note = k.split("|")
        T = 2 * float(n_osc) / note_to_hz(note)
        print(
            f"| {n_osc} | {note} | {T:.3g} | {np.mean([r['u_min'] for r in rows]):.2f}–"
            f"{np.mean([r['u_max'] for r in rows]):.2f} | {fmt_ms(rows, 'pitch_dev_rms', '{:.1f}')}"
            f" | {fmt_ms(rows, 'pitch_hyst_rms', '{:.1f}')} |"
        )
    print("\n### Jumps (square 0 ↔ 1, 64 periods per level, 40 jumps × 3 seeds per direction)\n")
    print(
        "| system | note | jump | pitch in 1st period − static (c) | late (32–64 per.) − static"
        " (c) | settles within (periods) | mean s, 1st period | peak audio mean / max |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for system in SYSTEMS:
        for note in ("A3", "A1"):
            js = summary["jumps"][system][note]
            for d, key in (("up", "u1"), ("down", "u0")):
                c = np.mean([j[d]["cents_mean"] for j in js], axis=0)
                se = np.sqrt(np.mean(np.square([j[d]["cents_se"] for j in js]), axis=0) / 3)
                ref = js[0]["static_loop_cents"][key]
                late, settle = settle_periods(c, se)
                print(
                    f"| {system} | {note} | {'0→1' if d == 'up' else '1→0'} | {c[0] - ref:+.0f} | "
                    f"{late - ref:+.0f} | {settle:.0f} | "
                    f"{np.mean([j[d]['mean_s_first_period'] for j in js]):+.2f} | "
                    f"{np.mean([j[d]['peak_abs_mean'] for j in js]):.2f} / "
                    f"{np.max([j[d]['peak_abs_max'] for j in js]):.2f} |"
                )
    print("\n### Safety-reset probe (square, 64 periods per level, 60 up-jumps × 3 seeds)\n")
    print("| case | resets / up-jumps | max box usage | resets at (periods after up-jump) |")
    print("|---|---|---|---|")
    for k, rows in summary["reset_probe"].items():
        n_r = sum(r["resets"] for r in rows)
        n_j = sum(r["jumps_up"] for r in rows)
        after = sorted(round(x, 1) for r in rows for x in r["reset_phase_periods_after_up"])
        print(f"| {k} | {n_r} / {n_j} | {max(r['box_usage'] for r in rows):.2f} | {after} |")
    print("\n### Chua, observable x, sine T = 5 s: single-scroll episodes (u < 0.1)\n")
    for k, c in enumerate(summary["chua_x"]):
        print(
            f"seed {k}: signs {c['signs']}, mean s {np.round(c['mean_s'], 2).tolist()}, "
            f"peak |audio| {np.round(c['peak_abs'], 2).tolist()}"
        )
    print("\npatch check:", summary["patch_check"])
    print("escape example:", summary["escape_example"])


if __name__ == "__main__":
    main()
