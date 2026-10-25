"""Study: integration resolution (classical RK4 steps per characteristic period).

Question: is ``steps_per_period = 256`` needed, sufficient or overkill?

For every catalog system at three knob positions (u = 0, the default, u = 1) the ODE is
integrated with a fixed RK4 step h = P(u)/N for N ∈ {16, …, 512} and a reference N = 2048,
where P(u) is the catalog period at that knob position. Two kinds of comparison:

(a) **Short horizon** (deterministic): from K points on the attractor, integrate exactly one
    period and compare with N = 16384. Shows the order of the method.
(b) **Long runs** (statistical): M independent realizations × R periods per N, paired by
    initial condition with the reference, compare the quantities that define what is heard:
    the characteristic period with the catalog's method (pitch), σ of every audible variable
    (loudness after normalization), spectral prominence, and the spectral envelope of the
    heard variable in 1/3-octave bands from 0.5 f₀ to 20 f₀ (timbre).

Sampling: the engine never takes an RK4 step longer than one audio sample, so a run with N
steps per period is recorded at S = min(N, 64) samples per period, and compared with the
reference recorded at the same S (the reference is decimated, aliasing included). For
N < 64 the envelope can therefore only be checked below 0.8 × the Nyquist of that grid.

Usage (from ``lab/``; about 5–8 minutes on 4 cores)::

    caffeinate -is uv run python scripts/studies/resolution.py [--quick]

Writes ``outputs/studies/resolution/results.json`` and the figures next to it.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.signal import welch

from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.catalog import Catalog, CatalogEntry, load_default_catalog
from chaotic_sound.integrate import trajectory
from chaotic_sound.pitch import note_to_hz
from chaotic_sound.systems import get_system, list_systems
from chaotic_sound.systems.base import SystemDef

LAB = Path(__file__).resolve().parents[2]
OUT = LAB / "outputs" / "studies" / "resolution"

NS = (16, 32, 64, 128, 256, 512)
N_REF = 2048
N_SHORT_REF = 16384
S_MAX = 64
"""Samples recorded per period (Nyquist at 32 f₀) when N ≥ 64."""
WELCH_PERIODS = 128
"""Welch segment length in periods (as the catalog tables)."""
F_MIN_RATIO = 0.25
"""Spectral content below F_MIN_RATIO / P_ref is ignored by the peak search (as the catalog)."""
SETTLE_PERIODS = 300
TRANSIENT_PERIODS = 50
IC_SPACING_PERIODS = 41
SHORT_K = 64
IC_KICK = 1e-6
"""Relative size (in σ) of the kick that makes each realization independent."""
SHORT_SPACING_PERIODS = 3
BAND_CENTERS = 2.0 ** (np.arange(-3, 14) / 3.0)
"""1/3-octave band centers in units of f₀ = 1/P(u): 0.5 … 20.2."""
BAND_HALF = 2.0 ** (1.0 / 6.0)
HF_BAND = (10.0, 20.0)
"""The "high-frequency" band of the task, in harmonics of f₀."""
NYQUIST_USE = 0.8
"""Bands are only compared when their upper edge is below this fraction of the Nyquist."""

PITCH_TOL_CENTS = 1.0
SIGMA_TOL = 0.005
ENVELOPE_TOL_DB = 1.0
AUDIBLE_FLOOR_DB = -90.0
"""Bands weaker than this (dB re the heard variable's total power) are not judged: at the
spec's −12 dBFS RMS they sit below −100 dBFS, under 16-bit quantization noise."""
NOTES = ("A2", "A4", "A5", "A6", "C8")
FS = 48_000.0


# --------------------------------------------------------------------------------------
# Integration helpers
# --------------------------------------------------------------------------------------


def run(
    system: SystemDef,
    params: NDArray[np.float64],
    x0: NDArray[np.float64],
    period: float,
    n_steps: int,
    samples_per_period: int,
    n_periods: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Integrate with h = period/n_steps exactly, recording ``samples_per_period`` per period."""
    steps = n_steps // samples_per_period
    assert steps * samples_per_period == n_steps
    dt = period / samples_per_period
    h_max = dt / steps * (1.0 + 1e-9)  # so that ceil(dt / h_max) == steps exactly
    n = round(n_periods * samples_per_period)
    return trajectory(system, params, x0, dt=dt, n_samples=n, h_max=h_max)


def setup(name: str, u: float) -> dict[str, Any]:
    cat = load_default_catalog()
    entry = cat[name]
    system = get_system(name)
    p_val = float(entry.param_value(u))
    params = system.params_array(**{system.modulated_param: p_val})
    period = float(entry.period(u))
    return {"entry": entry, "system": system, "params": params, "period": period, "p": p_val}


# --------------------------------------------------------------------------------------
# Tasks (run in worker processes)
# --------------------------------------------------------------------------------------


def prepare(name: str, u_label: str, u: float, n_real: int) -> dict[str, Any]:
    """Settle on the attractor, run the short-horizon test, and draw the realizations' ICs."""
    t0 = time.perf_counter()
    s = setup(name, u)
    system, params, period = s["system"], s["params"], s["period"]
    audio = [system.variable_index(v) for v in system.audio_variables]
    _, x = run(system, params, system.initial_state(), period, N_REF, S_MAX, SETTLE_PERIODS)
    seed, x = run(system, params, x, period, N_REF, S_MAX, SHORT_K * SHORT_SPACING_PERIODS)
    sigma = seed[:, audio].std(axis=0)
    starts = seed[S_MAX * SHORT_SPACING_PERIODS - 1 :: S_MAX * SHORT_SPACING_PERIODS]
    ends: dict[int, list[NDArray[np.float64]]] = {}
    for n in (*NS, N_REF, N_SHORT_REF):
        ends[n] = [run(system, params, x0, period, n, 1, 1)[1] for x0 in starts]
    ref = np.array(ends[N_SHORT_REF])
    short: dict[str, float] = {}
    for n in (*NS, N_REF):
        d = (np.array(ends[n]) - ref)[:, audio] / sigma
        short[str(n)] = float(np.sqrt(np.mean(d**2)))
    # Each realization starts from a point of one long reference trajectory plus a seeded
    # 1e-6·σ kick (as spec §4.2 step 9). Without the kick the N = 2048 runs would replay that
    # trajectory bit for bit, so the "independent" references would be shifted copies of one
    # record and their noise would not average out.
    rng = np.random.default_rng(zlib.crc32(f"{name}/{u_label}".encode()))
    ics = []
    for _ in range(n_real):
        _, x = run(system, params, x, period, N_REF, S_MAX, IC_SPACING_PERIODS)
        ic = x.copy()
        ic[audio] += IC_KICK * sigma * rng.standard_normal(len(audio))
        ics.append(ic)
    return {
        "system": name,
        "u_label": u_label,
        "u": u,
        "short_error": short,
        "ics": [ic.tolist() for ic in ics],
        "seconds": time.perf_counter() - t0,
    }


def stats(
    rec: NDArray[np.float64],
    dt: float,
    period: float,
    entry: CatalogEntry,
    system: SystemDef,
    p_ref: float,
    s: int,
) -> dict[str, Any]:
    """Pitch, level and timbre statistics of one record (system-time units)."""
    nperseg = WELCH_PERIODS * s
    f_min = F_MIN_RATIO / p_ref
    out: dict[str, Any] = {"sigma": {}, "mean": {}, "prominence": {}}
    for var in system.audio_variables:
        x = rec[:, system.variable_index(var)]
        out["sigma"][var] = float(x.std())
        out["mean"][var] = float(x.mean())
        out["prominence"][var] = spectral_peak(x, dt, nperseg=nperseg, f_min=f_min).prominence
    obs = rec[:, system.variable_index(entry.period_observable)]
    peak = spectral_peak(obs, dt, nperseg=nperseg, f_min=f_min)
    out["centroid_period"] = peak.centroid_period
    out["return_time"] = mean_return_time(obs, dt).mean
    method = entry.period_method
    if method == "peak_centroid":
        out["period"] = peak.centroid_period
    elif method == "return_time":
        out["period"] = out["return_time"]
    else:  # "drive": exact by construction, independent of the integration
        out["period"] = float(system.drive_period())
    heard = rec[:, system.variable_index(entry.default_observable)]
    freqs, psd = welch(heard, fs=1.0 / dt, nperseg=nperseg, noverlap=nperseg // 2, window="hann")
    df = freqs[1] - freqs[0]
    f0 = 1.0 / period
    total = float(np.sum(psd[1:]) * df)
    bands = []
    for c in BAND_CENTERS:
        sel = (freqs >= c * f0 / BAND_HALF) & (freqs < c * f0 * BAND_HALF)
        bands.append(float(np.sum(psd[sel]) * df))
    sel = (freqs >= HF_BAND[0] * f0) & (freqs < HF_BAND[1] * f0)
    out["bands"] = bands
    out["hf"] = float(np.sum(psd[sel]) * df)
    out["total_power"] = total
    return out


def realization(name: str, u_label: str, u: float, m: int, ic: list[float], periods: float):
    """All resolutions for one initial condition (paired with the reference)."""
    t0 = time.perf_counter()
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    p_ref = float(entry.info["reference_period"])
    x0 = np.asarray(ic, dtype=np.float64)
    res: dict[str, Any] = {"system": name, "u_label": u_label, "m": m, "by_n": {}, "ref": {}}
    for n in (*NS, N_REF):
        spp = min(n, S_MAX)
        _, x = run(system, params, x0, period, n, spp, TRANSIENT_PERIODS)
        rec, _ = run(system, params, x, period, n, spp, periods)
        audio = [system.variable_index(v) for v in system.audio_variables]
        lo, hi = entry.bounds_lo[audio], entry.bounds_hi[audio]
        sub = rec[:, audio]
        ok = bool(np.all(np.isfinite(rec)) and np.all(sub >= lo) and np.all(sub <= hi))
        if n != N_REF:
            res["by_n"][str(n)] = (
                stats(rec, period / spp, period, entry, system, p_ref, spp) if ok else None
            )
            continue
        for spp_ref in sorted({min(k, S_MAX) for k in NS}):
            dec = S_MAX // spp_ref
            sub_rec = rec[dec - 1 :: dec]
            res["ref"][str(spp_ref)] = stats(
                sub_rec, period / spp_ref, period, entry, system, p_ref, spp_ref
            )
    res["seconds"] = time.perf_counter() - t0
    return res


# --------------------------------------------------------------------------------------
# Aggregation: direct paired differences and a Richardson-type fit
# --------------------------------------------------------------------------------------


def mean_se(values: Any) -> tuple[float, float]:
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return math.nan, math.nan
    se = float(a.std(ddof=1) / math.sqrt(a.size)) if a.size > 1 else math.nan
    return float(a.mean()), se


def _db(x: float) -> float:
    return 10.0 * math.log10(x) if x > 0 else math.nan


def metrics(st: dict[str, Any], system: SystemDef, entry: CatalogEntry) -> dict[str, float]:
    """Scalars whose differences are the reported errors.

    ``cents*`` = −1200·log2(P), so a difference is the shift of the heard pitch in cents;
    ``sigma_*`` = 100·ln σ (difference ≈ relative error in %); ``band_k``/``hf`` in dB;
    ``prominence`` in percentage points.
    """

    def cents(p: float) -> float:
        return -1200.0 * math.log2(p) if p > 0 and math.isfinite(p) else math.nan

    m = {
        "cents": cents(st["period"]),
        "cents_centroid": cents(st["centroid_period"]),
        "cents_return_time": cents(st["return_time"]),
        "prominence": 100.0 * st["prominence"][entry.default_observable],
        "hf": _db(st["hf"]),
    }
    for v in system.audio_variables:
        m[f"sigma_{v}"] = 100.0 * math.log(st["sigma"][v])
    for k, b in enumerate(st["bands"]):
        m[f"band_{k}"] = _db(b)
    return m


def fit_bias(
    ns: list[int], d: list[float], var: list[float], order: float
) -> dict[str, float] | None:
    """Weighted fit d_N = a + c·N^-order; ``a`` absorbs the reference's own noise."""
    ok = [i for i in range(len(ns)) if math.isfinite(d[i]) and var[i] > 0]
    if len(ok) < 3:
        return None
    x = np.array([float(ns[i]) ** -order for i in ok])
    y = np.array([d[i] for i in ok])
    w = 1.0 / np.array([var[i] for i in ok])
    design = np.column_stack([np.ones_like(x), x])
    cov = np.linalg.inv(design.T @ (design * w[:, None]))
    a, c = cov @ (design.T @ (w * y))
    resid = y - (a + c * x)
    dof = len(ok) - 2
    chi2 = float(np.sum(w * resid**2) / dof) if dof > 0 else math.nan
    scale = max(1.0, chi2) if math.isfinite(chi2) else 1.0
    return {"a": float(a), "c": float(c), "se_c": float(math.sqrt(cov[1, 1] * scale)),
            "chi2_red": chi2, "n_min_fit": float(min(ns[i] for i in ok))}  # fmt: skip


def aggregate(name: str, reals: list[dict[str, Any]], order: float) -> dict[str, Any]:
    system = get_system(name)
    entry = load_default_catalog()[name]
    spps = sorted({min(n, S_MAX) for n in NS})
    ref = {s: [metrics(r["ref"][str(s)], system, entry) for r in reals] for s in spps}
    keys = list(ref[S_MAX][0])
    runs = {
        n: [metrics(r["by_n"][str(n)], system, entry) if r["by_n"][str(n)] else None for r in reals]
        for n in NS
    }
    ref64 = [r["ref"][str(S_MAX)] for r in reals]
    out: dict[str, Any] = {
        "realizations": len(reals),
        "ref": {
            "period": mean_se([r["period"] for r in ref64]),
            "cents_spread": float(np.std([m["cents"] for m in ref[S_MAX]], ddof=1)),
            "cents_rt_spread": float(np.std([m["cents_return_time"] for m in ref[S_MAX]], ddof=1)),
            "sigma": {v: mean_se([r["sigma"][v] for r in ref64]) for v in system.audio_variables},
            "prominence": mean_se([r["prominence"][entry.default_observable] for r in ref64]),
            "band_level_db": [
                _db(float(np.mean([r["bands"][b] / r["total_power"] for r in ref64])))
                for b in range(len(BAND_CENTERS))
            ],
            "hf_level_db": _db(float(np.mean([r["hf"] / r["total_power"] for r in ref64]))),
        },
        "failed": {str(n): sum(1 for m in runs[n] if m is None) for n in NS},
        "direct": {},
        "model": {},
        "fit": {},
    }
    for key in keys:
        d_mean, d_se, var = [], [], []
        for n in NS:
            s = min(n, S_MAX)
            pairs = [(a[key], b[key]) for a, b in zip(runs[n], ref[s], strict=True) if a]
            diffs = [a - b for a, b in pairs]
            mu, se = mean_se(diffs) if len(pairs) == len(reals) else (math.nan, math.nan)
            d_mean.append(mu)
            d_se.append(se)
            vals = np.array([a for a, _ in pairs])
            vals = vals[np.isfinite(vals)]
            var.append(float(vals.var(ddof=1) / vals.size) if vals.size > 1 else math.nan)
        fit = fit_bias(list(NS[1:]), d_mean[1:], var[1:], order)
        if fit is not None and fit["chi2_red"] > 10:  # N = 32 not asymptotic: drop it
            fit = fit_bias(list(NS[2:]), d_mean[2:], var[2:], order) or fit
        out["direct"][key] = [[m, s] for m, s in zip(d_mean, d_se, strict=True)]
        out["fit"][key] = fit
        out["model"][key] = (
            [[fit["c"] * n**-order, fit["se_c"] * n**-order] for n in NS] if fit else None
        )
    return out


def criterion_keys(name: str, agg: dict[str, Any], n: int, which: str, audible: bool) -> list[str]:
    system = get_system(name)
    if which == "pitch":
        return [] if load_default_catalog()[name].period_method == "drive" else ["cents"]
    if which == "sigma":
        return [f"sigma_{v}" for v in system.audio_variables]
    nyq = min(n, S_MAX) / 2.0
    levels = agg["ref"]["band_level_db"]
    return [
        f"band_{k}"
        for k, c in enumerate(BAND_CENTERS)
        if c * BAND_HALF < NYQUIST_USE * nyq and (not audible or levels[k] >= AUDIBLE_FLOOR_DB)
    ]


TOLS = {"pitch": PITCH_TOL_CENTS, "sigma": 100 * SIGMA_TOL, "envelope": ENVELOPE_TOL_DB}


def judge(name: str, agg: dict[str, Any], n: int, which: str, audible: bool = True):
    """Verdict on one criterion at one N.

    The bias is taken from the fit d_N = a + c·N^-p over all N (``a`` absorbs the noise of
    the finite reference, which is common to every N). A metric passes when the fitted bias
    is inside the tolerance at 95 % (|c·N^-p| + 2 SE) **and** the measured difference, taken
    relative to the fitted N → ∞ value (d_N − a), does not exceed the tolerance by more than
    2 SE (no contradiction from the data). Without a fit, or below the smallest N used in
    the fit, the measured shift alone (relative to ``a``) must be inside it at 95 %.
    """
    i = NS.index(n)
    tol = TOLS[which]
    if agg["failed"][str(n)]:
        return {"pass": False, "diverged": True, "ub": math.inf, "direct": math.inf}
    ub, worst_direct, ok, confirmed = 0.0, 0.0, True, True
    for key in criterion_keys(name, agg, n, which, audible):
        m, se = agg["direct"][key][i]
        model, fit = agg["model"][key], agg["fit"][key]
        r = m - fit["a"] if fit else m  # measured shift relative to the fitted N → ∞ value
        worst_direct = max(worst_direct, abs(r))
        confirmed &= abs(m) + 2 * se < tol
        if model and n >= fit["n_min_fit"]:  # never extrapolate the fit below its range
            b, bse = model[i]
            ub = max(ub, abs(b) + 2 * bse)
            ok &= abs(b) + 2 * bse < tol and abs(r) < tol + 2 * se
        else:
            ub = max(ub, abs(r) + 2 * se)
            ok &= abs(r) + 2 * se < tol
    return {"pass": bool(ok), "diverged": False, "ub": ub, "direct": worst_direct,
            "confirmed_direct": bool(confirmed)}  # fmt: skip


def judge_all(results: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {
            ul: {w: [judge(name, agg, n, w) for n in NS] for w in ("pitch", "sigma", "envelope")}
            for ul, agg in per_u.items()
        }
        for name, per_u in results.items()
    }


def verdicts(results: dict[str, Any]) -> dict[str, Any]:
    """Smallest N per system such that it and every larger N pass at all three knob positions."""
    table: dict[str, Any] = {}
    for name, per_u in results.items():
        row: dict[str, Any] = {}
        for which, audible in (("pitch", True), ("sigma", True), ("envelope", True),
                               ("envelope_strict", False)):  # fmt: skip
            crit = which.split("_")[0]
            flags = [all(judge(name, agg, n, crit, audible)["pass"] for agg in per_u.values())
                     for n in NS]  # fmt: skip
            best = None
            for n, f in zip(reversed(NS), reversed(flags), strict=True):
                if not f:
                    break
                best = n
            row[which] = best
        main = [row[k] for k in ("pitch", "sigma", "envelope")]
        row["all"] = None if None in main else max(main)
        table[name] = row
    return table


def short_order(short: dict[str, float]) -> float:
    """Convergence order from the one-period errors between N = 64 and 512."""
    return math.log2(short["64"] / short["512"]) / 3.0


def cost_table(cat: Catalog) -> dict[str, Any]:
    """RK4 sub-steps per sample with the engine's rule, for catalog N values and notes."""
    from chaotic_sound.blocks import Dynamical

    out: dict[str, Any] = {}
    for name, entry in cat.entries.items():
        per_n: dict[str, Any] = {}
        for n in (*NS, 1024):
            e = dataclasses.replace(
                entry, h_max=entry.h_max * entry.steps_per_period / n, steps_per_period=n
            )
            c = Catalog(entries={name: e})
            row: dict[str, Any] = {}
            for note in NOTES:
                b = Dynamical("osc", catalog=c, system=name, note=note)
                b.reset(FS)
                sub_def = b.substeps_per_sample()
                sub_max = max(b.substeps_per_sample(float(u)) for u in e.u_grid)
                f0 = note_to_hz(note)
                row[note] = {
                    "substeps_default": sub_def,
                    "substeps_max_over_u": sub_max,
                    "effective_n_default": sub_def * FS / f0,
                }
            row["naive_A4"] = math.ceil(n * note_to_hz("A4") / FS)
            per_n[str(n)] = row
        out[name] = {
            "per_n": per_n,
            "h_max_times_256": entry.h_max * entry.steps_per_period,
            "p_default": float(entry.period(entry.u_default)),
            "p_min": float(entry.period_table.min()),
            "p_max": float(entry.period_table.max()),
            "p_ref": float(entry.info["reference_period"]),
        }
    return out


# --------------------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------------------

SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
RAMP = ("#b7d3f6", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281")
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
U_LABELS = ("u=0", "default", "u=1")


def style(ax: Any) -> None:
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)


def plots(data: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(data["results"])
    disp = {n: get_system(n).display_name for n in names}
    u_style = {"u=0": ":", "default": "-", "u=1": "--"}

    # (a) short-horizon error
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    ns = np.array([*NS, N_REF], dtype=float)
    for name, color in zip(names, SERIES, strict=False):
        for ul in U_LABELS:
            err = np.array([data["short"][name][ul][str(int(n))] for n in ns])
            ax.plot(ns, err, u_style[ul], color=color, lw=2 if ul == "default" else 1.2,
                    marker="o" if ul == "default" else None, ms=4,
                    label=disp[name] if ul == "default" else None)  # fmt: skip
    for p, y0, lab in ((4.0, 3e-2, "∝ N⁻⁴"), (2.0, 3e-2, "∝ N⁻²")):
        guide = y0 * (ns / 16) ** -p
        ax.plot(ns, guide, color=MUTED, lw=1, alpha=0.5)
        ax.text(ns[-1], guide[-1], " " + lab, color=MUTED, fontsize=8, va="center")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("RK4 steps per period N", color=INK)
    ax.set_ylabel("RMS state error after one period (units of σ)", color=INK)
    ax.set_title("(a) One-period error vs N   (solid: default, dotted: u=0, dashed: u=1)",
                 fontsize=9)  # fmt: skip
    style(ax)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "short_horizon_error.png", dpi=150)
    plt.close(fig)

    # (b) long-run criteria: worst over u of the 95 % upper bound (line) and direct (markers)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
    titles = {
        "pitch": "pitch shift (cents)",
        "sigma": "σ error, worst variable (%)",
        "envelope": "band-level error ≤ 20 f₀, audible bands (dB)",
    }
    for ax, which in zip(axes, ("pitch", "sigma", "envelope"), strict=True):
        for name, color in zip(names, SERIES, strict=False):
            ub, direct = [], []
            for n in NS:
                js = [judge(name, data["results"][name][ul], n, which) for ul in U_LABELS]
                ub.append(max(j["ub"] for j in js))
                direct.append(max(j["direct"] for j in js))
            ub_a = np.where(np.isfinite(ub), ub, np.nan)
            dr_a = np.where(np.isfinite(direct), direct, np.nan)
            if which == "pitch" and data["results"][name]["default"]["model"]["cents"] is None:
                continue
            ax.plot(NS, np.maximum(ub_a, 1e-6), "-", color=color, lw=2, label=disp[name])
            ax.plot(NS, np.maximum(dr_a, 1e-6), "o", color=color, ms=5, mfc="none", mew=1.5)
        ax.axhline(TOLS[which], color=INK, lw=1, ls="--")
        ax.text(NS[-1], TOLS[which] * 1.25, "tolerance", color=INK, fontsize=8, ha="right")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xlabel("RK4 steps per period N", color=INK)
        ax.set_title(f"(b) {titles[which]}", fontsize=9)
        style(ax)
    axes[1].legend(
        fontsize=8,
        frameon=False,
        loc="lower left",
        title="line: 95% bound; ○: measured (vs fitted N→∞)",
        title_fontsize=7,
    )
    fig.tight_layout()
    fig.savefig(OUT / "long_run_errors.png", dpi=150)
    plt.close(fig)

    # (c) spectral envelope at the default
    cat = load_default_catalog()
    fig, axes = plt.subplots(2, len(names), figsize=(3.0 * len(names), 6.2), sharex=True)
    for j, name in enumerate(names):
        agg = data["results"][name]["default"]
        top, bot = axes[0, j], axes[1, j]
        top.semilogx(BAND_CENTERS, agg["ref"]["band_level_db"], "-o", color=INK, lw=1.5, ms=3)
        top.axhline(AUDIBLE_FLOOR_DB, color=MUTED, lw=1, ls=":")
        top.set_title(f"{disp[name]} — {cat[name].default_observable}", fontsize=9)
        for n, color in zip(NS, RAMP, strict=True):
            i = NS.index(n)
            y = np.array([agg["direct"][f"band_{k}"][i][0] for k in range(len(BAND_CENTERS))])
            keep = [f"band_{k}" in criterion_keys(name, agg, n, "envelope", False)
                    for k in range(len(BAND_CENTERS))]  # fmt: skip
            y = np.where(keep, y, np.nan)
            bot.semilogx(BAND_CENTERS, y, "-o", color=color, lw=1.5, ms=3, label=f"N={n}")
        bot.axhspan(-ENVELOPE_TOL_DB, ENVELOPE_TOL_DB, color=GRID, alpha=0.8, lw=0)
        bot.set_ylim(-5, 5)
        bot.set_xlabel("frequency / f₀", color=INK)
        style(top)
        style(bot)
    axes[0, 0].set_ylabel("reference band power (dB re total)", color=INK)
    axes[1, 0].set_ylabel("band level vs N=2048 (dB)", color=INK)
    axes[1, -1].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("(c) 1/3-octave spectral envelope of the heard variable at the default "
                 "(dotted: audibility floor)", fontsize=10)  # fmt: skip
    fig.tight_layout()
    fig.savefig(OUT / "envelope_default.png", dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

REALIZATION_FACTOR = {"thomas": 2, "duffing": 2}
"""Systems whose statistics converge slowly get more realizations."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="tiny run to test the script")
    parser.add_argument("--systems", nargs="*", default=list_systems())
    parser.add_argument("--realizations", type=int, default=8)
    parser.add_argument("--periods", type=float, default=12000.0)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--reanalyze", action="store_true",
                        help="recompute verdicts and figures from results.json")  # fmt: skip
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.reanalyze:
        data = json.loads((OUT / "results.json").read_text())
        data["judged"] = judge_all(data["results"])
        data["verdicts"] = verdicts(data["results"])
        (OUT / "results.json").write_text(json.dumps(data, indent=1, allow_nan=True) + "\n")
        plots(data)
        print(json.dumps(data["verdicts"], indent=1))
        return
    if args.quick:
        args.realizations, args.periods = 3, 600.0
    cat = load_default_catalog()
    t0 = time.perf_counter()
    points = []
    for name in args.systems:
        e = cat[name]
        for ul, u in (("u=0", 0.0), ("default", e.u_default), ("u=1", 1.0)):
            points.append((name, ul, float(u), args.realizations * REALIZATION_FACTOR.get(name, 1)))
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        preps = list(pool.map(prepare, *zip(*points, strict=True)))
        print(f"prepared {len(preps)} points in {time.perf_counter() - t0:.0f} s", flush=True)
        jobs = [
            (p["system"], p["u_label"], p["u"], m, ic, args.periods)
            for p in preps
            for m, ic in enumerate(p["ics"])
        ]
        # longest jobs first for better packing
        jobs.sort(key=lambda j: -(2.5 if j[0] in ("thomas", "duffing") else 1.0))
        reals = list(pool.map(realization, *zip(*jobs, strict=True)))
    print(f"ran {len(reals)} realizations in {time.perf_counter() - t0:.0f} s", flush=True)

    results: dict[str, Any] = {}
    short: dict[str, Any] = {}
    orders: dict[str, float] = {}
    consistency: dict[str, Any] = {}
    for p in preps:
        short.setdefault(p["system"], {})[p["u_label"]] = p["short_error"]
    for name, per_u in short.items():
        measured = [short_order(e) for e in per_u.values()]
        orders[name] = float(round(float(np.median(measured))))
    for p in preps:
        name, ul = p["system"], p["u_label"]
        rs = [r for r in reals if r["system"] == name and r["u_label"] == ul]
        rs.sort(key=lambda r: r["m"])
        results.setdefault(name, {})[ul] = agg = aggregate(name, rs, orders[name])
        e = cat[name]
        consistency.setdefault(name, {})[ul] = {
            "cents_vs_catalog": 1200 * math.log2(float(e.period(p["u"])) / agg["ref"]["period"][0]),
            "sigma_rel_vs_catalog": {
                v: agg["ref"]["sigma"][v][0] / float(e.std(v, p["u"])) - 1
                for v in agg["ref"]["sigma"]
            },
            "lyapunov_per_period_catalog": float(
                np.interp(p["u"], e.u_grid, np.asarray(e.info["lyapunov_per_period"]))
            ),
        }
    data = {
        "settings": {
            "NS": NS,
            "N_REF": N_REF,
            "N_SHORT_REF": N_SHORT_REF,
            "samples_per_period_max": S_MAX,
            "welch_periods": WELCH_PERIODS,
            "realizations": args.realizations,
            "realization_factor": REALIZATION_FACTOR,
            "periods_per_realization": args.periods,
            "transient_periods": TRANSIENT_PERIODS,
            "band_centers": BAND_CENTERS.tolist(),
            "audible_floor_db": AUDIBLE_FLOOR_DB,
            "wall_seconds": time.perf_counter() - t0,
        },
        "short": short,
        "short_order_measured": {
            n: {ul: short_order(e) for ul, e in per_u.items()} for n, per_u in short.items()
        },
        "fit_order": orders,
        "results": results,
        "judged": judge_all(results),
        "consistency": consistency,
        "verdicts": verdicts(results),
        "cost": cost_table(cat),
    }
    (OUT / "results.json").write_text(json.dumps(data, indent=1, allow_nan=True) + "\n")
    plots(data)
    print(json.dumps(data["verdicts"], indent=1))
    print(f"done in {time.perf_counter() - t0:.0f} s → {OUT}")


if __name__ == "__main__":
    main()
