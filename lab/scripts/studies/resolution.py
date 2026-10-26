"""Study: integration resolution (classical RK4 steps per characteristic period), engine v0.3.

Question: is the catalog's ``steps_per_period = 256`` needed, sufficient or overkill?
(The engine uses it as h_max = min(P_ref, P_min)/256; the catalog builder measures every
table node with h = P_ref/256, i.e. 256·P(u)/P_ref steps per local period.)

Every catalog system is integrated with a fixed RK4 step h = P(u)/N, with P(u) the catalog
period at that knob position, and compared with a reference N = 1024 (N = 16384 for (a)):

(a) **Short horizon** (deterministic): from 64 points on the attractor, integrate exactly
    one period. Shows the order of the method.
(b) **Long runs** (statistical) at u = 0, the default and u = 1: M realizations × 10 000
    periods per N, paired by initial condition with the reference. Measured: the period with
    the catalog's estimator (pitch), σ and the robust peak π (99.9th percentile of |x − μ|) of
    every audible variable (level: the engine scales by min(0.25/σ, 0.8/π), spec §4.2 step 6),
    the prominence, and the 1/3-octave envelope of the heard variable up to 20 f₀ (timbre).
    Verdicts use the **direct paired differences** only (pass: |d| + 2 SE < tolerance; fail:
    |d| − 2 SE > tolerance; otherwise open). A fit d_N = a + c·N^-p is kept as a cross-check
    and rejected when χ²_red > 3.
(b2) **Refinement**: points where (b) leaves a criterion open at N = 64, 128 or 256 and more
    realizations could resolve it get REFINE_M extra realizations at those N.
(c) **Stability scan**: survival over 3000 periods for N = 8 … 48.
(d) **Window sweep**: N = 64 and 128 against the reference over a u grid that includes every
    periodic window of the catalog, to find attractor switches inside the range.
(d2) **Follow-up** at every flagged sweep point: N = 64 … 512 with more ICs, plus the reference
    at u ± 1/4096 and u ± 1/1024, which expresses an integration error as a knob offset.
(e) **Engine path under modulation**: the v0.3 Dynamical block (parameter slew max(5 ms, 2/f),
    peak-limited level) with a 0 ↔ 1 square wave on the param input, with h_max set for
    N_cat ∈ {32, …, 256} against N_cat = 512, at C8 (where the smallest N_eff over u is within
    8 % of N_cat). The pitch input is not driven.
(f) **Chaos at the engine's step**: the largest Lyapunov exponent λ·P_ref (the catalog's chaos
    measure, chaotic if > 0.05) on a dense grid of N from 64 to 1024 (≈ 2.2 % apart, not only
    powers of two), at u = 0, the default, u = 1 and the (d2) points. Then, for N_cat ∈
    {64, 128, 256}, λ at the exact N_eff = n_sub·fs/f₀ of every semitone C0 … C8 that lies
    next to an N where the classification differs from the reference's. The statistics of
    (b)–(d) cannot see a switch between chaos and a periodic orbit that has nearly the same
    σ, prominence and band powers; (f) can.

Sampling in (b): the engine never takes an RK4 step longer than one audio sample, so a run
with N steps per period is recorded at S = min(N, 64) samples per period and compared with the
reference decimated to the same S (aliasing included).

Usage (from ``lab/``; about 9 minutes with 6 workers: 267 s for (a)–(e), 250 s for (f))::

    caffeinate -is uv run python scripts/studies/resolution.py [--quick] [--workers 6]

``--sweep-only`` reruns (d)–(d2) and merges them into an existing results.json (same catalog);
``--chaos-only`` does the same for (f); ``--reanalyze`` recomputes the verdicts and figures from
results.json.

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
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.signal import welch

from chaotic_sound.analysis.spectrum import mean_return_time, measure_pitch, spectral_peak
from chaotic_sound.catalog import (
    Catalog,
    CatalogEntry,
    default_catalog_path,
    load_default_catalog,
)
from chaotic_sound.integrate import max_lyapunov, trajectory
from chaotic_sound.pitch import NOTE_MAX, NOTE_MIN, midi_to_hz, midi_to_note, note_to_hz
from chaotic_sound.systems import get_system, list_systems
from chaotic_sound.systems.base import SystemDef

ENGINE_VERSION = "v0.3"
LAB = Path(__file__).resolve().parents[2]
OUT = LAB / "outputs" / "studies" / "resolution"

NS = (16, 32, 64, 128, 256, 512)
N_REF = 1024
"""Reference resolution of (b)–(f). Its one-period error is 15.6–16.4× below N = 512's (Chua:
2.9–6.7×), measured in (a)."""
N_SHORT_REF = 16384
S_MAX = 64
"""Samples recorded per period (Nyquist at 32 f₀) when N ≥ 64."""
WELCH_PERIODS = 128
"""Welch segment length in periods (as the catalog tables)."""
F_MIN_RATIO = 0.25
"""Spectral content below F_MIN_RATIO / P_ref is ignored by the peak search (as the catalog)."""
PEAK_PERCENTILE = 99.9
"""Robust peak π = this percentile of |x − μ| (as the catalog's peak tables)."""
SETTLE_PERIODS = 300
TRANSIENT_PERIODS = 50
IC_SPACING_PERIODS = 41
SHORT_K = 64
SHORT_SPACING_PERIODS = 3
IC_KICK = 1e-6
"""Relative size (in σ) of the kick that makes each realization independent (spec §4.2 step 9)."""
BAND_CENTERS = 2.0 ** (np.arange(-3, 14) / 3.0)
"""1/3-octave band centers in units of f₀ = 1/P(u): 0.5 … 20.2."""
BAND_HALF = 2.0 ** (1.0 / 6.0)
HF_BAND = (10.0, 20.0)
"""The "high-frequency" band, in harmonics of f₀ (cut at the Nyquist, 16 f₀, when S = 32)."""
NYQUIST_USE = 0.8
"""Bands are only compared when their upper edge is below this fraction of the Nyquist."""

PITCH_TOL_CENTS = 1.0
LEVEL_TOL = 0.005
ENVELOPE_TOL_DB = 1.0
AUDIBLE_FLOOR_DB = -90.0
"""Bands weaker than this (dB re the heard variable's total power) are not judged: at the
spec's −12 dBFS RMS they sit below −100 dBFS, under 16-bit quantization noise."""
RMS_TARGET, PEAK_TARGET = 0.25, 0.8
"""Level targets of the engine (blocks/dynamical.py): scale = min(RMS/σ, PEAK/π)."""
FIT_CHI2_MAX = 3.0

REFINE_NS = (64, 128, 256)
REFINE_M = 48
STAB_NS = (8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48)
STAB_M = 8
STAB_PERIODS = 3000
STAB_S = 4
SWEEP_NS = (64, 128)
SWEEP_K = 4
SWEEP_PERIODS = 2500
SWEEP_UNIFORM = 17
SWEEP_EDGE_DU = 1.0 / 256.0
"""Points just outside each window edge are this far (in u) from it (half a table step)."""
SWITCH_THRESHOLDS = {"prominence": 5.0, "sigma": 2.0, "cents": 5.0}
"""A difference at least this large (pp, %, ct) and 4 SE from zero flags an attractor switch."""
EDGE_NS = (64, 128, 256, 512)
EDGE_K = 8
EDGE_OFFSETS = (-1.0 / 1024.0, -1.0 / 4096.0, 1.0 / 4096.0, 1.0 / 1024.0)
"""Knob offsets at which the reference is also run, to measure the exact system's own
sensitivity at a flagged point (and so express an integration error as a knob offset)."""
EDGE_MAX = 8
MOD_NS = (32, 64, 128, 256)
MOD_N_REF = 512
MOD_NOTE = "C8"
"""At C8 (11.5 samples per period) the smallest N_eff over u is within 8 % of N_cat, so h_max is
what is tested; the slew there is 5 ms = 21 periods. At notes below ≈ 400 Hz, where the slew
max(5 ms, 2/f) is shortest in system time (2 periods), the sample grid alone already gives
≥ 120 steps per period whatever N_cat is."""
MOD_SECONDS = 12.0
MOD_SKIP_SECONDS = 1.0
MOD_SEEDS = 6
MOD_SQUARE_HZ = 1.0
NOTES = ("A2", "A4", "A5", "A6", "C8")
FS = 48_000.0
CHAOS_THRESHOLD = 0.05
"""The catalog's chaos criterion (BuildSettings.lyapunov_threshold, ADR 0012): λ·P_ref > this."""
CHAOS_GRID = tuple(sorted({round(64 * 2 ** (k / 32)) for k in range(129)}))
"""(f) N values: 64 … 1024 (= N_REF), about 2.2 % apart."""
CHAOS_K = 4
CHAOS_PERIODS = 3000.0
CHAOS_TRANSIENT = 1000.0
"""Periods run at the tested N before λ is measured, so the attractor of that N settles. At
Rössler u = 0 and N ≈ 130, after 300 periods 2–3 of 4 ICs still read above the threshold over
the next 1000 periods; after 1000, none does over the next 3000."""
CHAOS_NCATS = (64, 128, 256)
CHAOS_MIDI = tuple(range(NOTE_MIN, NOTE_MAX + 1))
"""The engine's note range, C0 … C8 (spec §4.2)."""


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
    entry = load_default_catalog()[name]
    system = get_system(name)
    entry.check_against(system)
    p_val = float(entry.param_value(u))
    params = system.params_array(**{system.modulated_param: p_val})
    return {
        "entry": entry,
        "system": system,
        "params": params,
        "period": float(entry.period(u)),
        "p": p_val,
    }


def in_bounds(rec: NDArray[np.float64], system: SystemDef, entry: CatalogEntry) -> bool:
    """Apply the engine's safety check: finite and inside the catalog bounds (audible variables)."""
    audio = [system.variable_index(v) for v in system.audio_variables]
    sub = rec[:, audio]
    lo, hi = entry.bounds_lo[audio], entry.bounds_hi[audio]
    return bool(np.all(np.isfinite(rec)) and np.all(sub >= lo) and np.all(sub <= hi))


def draw_ics(
    system: SystemDef,
    params: NDArray[np.float64],
    x: NDArray[np.float64],
    period: float,
    sigma: NDArray[np.float64],
    n: int,
    seed_text: str,
) -> list[NDArray[np.float64]]:
    """Points IC_SPACING_PERIODS apart on one reference trajectory, each with a seeded kick.

    Without the kick the reference runs would replay that trajectory bit for bit, so the
    "independent" references would be shifted copies of one record.
    """
    audio = [system.variable_index(v) for v in system.audio_variables]
    rng = np.random.default_rng(zlib.crc32(seed_text.encode()))
    ics = []
    for _ in range(n):
        _, x = run(system, params, x, period, N_REF, S_MAX, IC_SPACING_PERIODS)
        ic = x.copy()
        ic[audio] += IC_KICK * sigma * rng.standard_normal(len(audio))
        ics.append(ic)
    return ics


# --------------------------------------------------------------------------------------
# Tasks (run in worker processes)
# --------------------------------------------------------------------------------------


def prepare(name: str, u_label: str, u: float, n_real: int) -> dict[str, Any]:
    """Settle on the attractor, run the short-horizon test (a), and draw the ICs of (b)."""
    t0 = time.perf_counter()
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    audio = [system.variable_index(v) for v in system.audio_variables]
    # Start from the catalog's initial condition, as the engine does (spec §4.2 step 9).
    _, x = run(system, params, entry.initial_condition, period, N_REF, S_MAX, SETTLE_PERIODS)
    seed, x = run(system, params, x, period, N_REF, S_MAX, SHORT_K * SHORT_SPACING_PERIODS)
    sigma = seed[:, audio].std(axis=0)
    starts = seed[S_MAX * SHORT_SPACING_PERIODS - 1 :: S_MAX * SHORT_SPACING_PERIODS]
    ends = {
        n: np.array([run(system, params, x0, period, n, 1, 1)[1] for x0 in starts])
        for n in (*NS, N_REF, N_SHORT_REF)
    }
    short = {}
    for n in (*NS, N_REF):
        d = (ends[n] - ends[N_SHORT_REF])[:, audio] / sigma
        short[str(n)] = float(np.sqrt(np.mean(d**2)))
    ics = draw_ics(system, params, x, period, sigma, n_real, f"{name}/{u_label}")
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
    s: int,
    envelope: bool = True,
) -> dict[str, Any]:
    """Pitch, level and timbre statistics of one record (system-time units)."""
    p_ref = float(entry.info["reference_period"])
    nperseg = WELCH_PERIODS * s
    f_min = F_MIN_RATIO / p_ref
    out: dict[str, Any] = {"sigma": {}, "peak": {}, "prominence": {}}
    for var in system.audio_variables:
        x = rec[:, system.variable_index(var)]
        out["sigma"][var] = float(x.std())
        out["peak"][var] = float(np.percentile(np.abs(x - x.mean()), PEAK_PERCENTILE))
        out["prominence"][var] = spectral_peak(x, dt, nperseg=nperseg, f_min=f_min).prominence
    obs = rec[:, system.variable_index(entry.period_observable)]
    peak = spectral_peak(obs, dt, nperseg=nperseg, f_min=f_min)
    out["centroid_period"] = peak.centroid_period
    out["return_time"] = mean_return_time(obs, dt).mean
    if entry.period_method == "peak_centroid":
        out["period"] = peak.centroid_period
    elif entry.period_method == "return_time":
        out["period"] = out["return_time"]
    else:  # "drive": exact by construction, independent of the integration
        out["period"] = float(system.drive_period())
    if not envelope:
        return out
    heard = rec[:, system.variable_index(entry.default_observable)]
    freqs, psd = welch(heard, fs=1.0 / dt, nperseg=nperseg, noverlap=nperseg // 2, window="hann")
    df = freqs[1] - freqs[0]
    f0 = 1.0 / period
    out["total_power"] = float(np.sum(psd[1:]) * df)
    out["bands"] = [
        float(np.sum(psd[(freqs >= c * f0 / BAND_HALF) & (freqs < c * f0 * BAND_HALF)]) * df)
        for c in BAND_CENTERS
    ]
    sel = (freqs >= HF_BAND[0] * f0) & (freqs < HF_BAND[1] * f0)
    out["hf"] = float(np.sum(psd[sel]) * df)
    return out


def realization(
    name: str,
    u_label: str,
    u: float,
    m: int,
    ic: list[float],
    periods: float,
    ns: tuple[int, ...],
    stage: int,
) -> dict[str, Any]:
    """Run the resolutions ``ns`` and the reference from one initial condition (paired)."""
    t0 = time.perf_counter()
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    x0 = np.asarray(ic, dtype=np.float64)
    res: dict[str, Any] = {
        "system": name,
        "u_label": u_label,
        "m": m,
        "stage": stage,
        "by_n": {},
        "ref": {},
    }
    for n in (*ns, N_REF):
        spp = min(n, S_MAX)
        _, x = run(system, params, x0, period, n, spp, TRANSIENT_PERIODS)
        rec, _ = run(system, params, x, period, n, spp, periods)
        if n != N_REF:
            ok = in_bounds(rec, system, entry)
            res["by_n"][str(n)] = (
                stats(rec, period / spp, period, entry, system, spp) if ok else None
            )
            continue
        for spp_ref in sorted({min(k, S_MAX) for k in ns}):
            dec = S_MAX // spp_ref
            res["ref"][str(spp_ref)] = stats(
                rec[dec - 1 :: dec], period / spp_ref, period, entry, system, spp_ref
            )
    res["seconds"] = time.perf_counter() - t0
    return res


def stability_job(name: str, u_label: str, u: float, periods: float) -> dict[str, Any]:
    """(c) Survival over STAB_PERIODS for small N, plus the frozen-coefficient Rössler bound."""
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    audio = [system.variable_index(v) for v in system.audio_variables]
    _, x = run(system, params, entry.initial_condition, period, N_REF, S_MAX, SETTLE_PERIODS)
    seed, x = run(system, params, x, period, N_REF, S_MAX, 200)
    sigma = seed[:, audio].std(axis=0)
    ics = draw_ics(system, params, x, period, sigma, STAB_M, f"stab/{name}/{u_label}")
    survived = {}
    for n in STAB_NS:
        survived[str(n)] = sum(
            in_bounds(run(system, params, ic, period, n, STAB_S, periods)[0], system, entry)
            for ic in ics
        )
    out: dict[str, Any] = {"survived": survived, "of": STAB_M}
    if name == "rossler":
        # After a spike z relaxes at rate c − x; RK4 is stable for h·(c − x) < 2.785.
        c = float(params[system.param_names.index("c")])
        rate = float(np.max(c - seed[:, system.variable_index("x")]))
        out["max_c_minus_x"] = rate
        out["n_stab_frozen"] = period * rate / 2.785
    return out


def sweep_job(name: str, u: float, periods: float) -> dict[str, Any]:
    """(d) N = 64 and 128 against the reference at one knob position (attractor switches)."""
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    audio = [system.variable_index(v) for v in system.audio_variables]
    _, x = run(system, params, entry.initial_condition, period, N_REF, S_MAX, SETTLE_PERIODS)
    seed, x = run(system, params, x, period, N_REF, S_MAX, 100)
    sigma = seed[:, audio].std(axis=0)
    ics = draw_ics(system, params, x, period, sigma, SWEEP_K, f"sweep/{name}/{u:.6f}")
    rows: dict[str, list[dict[str, float] | None]] = {str(n): [] for n in (*SWEEP_NS, N_REF)}
    for ic in ics:
        for n in (*SWEEP_NS, N_REF):
            _, x1 = run(system, params, ic, period, n, S_MAX, TRANSIENT_PERIODS)
            rec, _ = run(system, params, x1, period, n, S_MAX, periods)
            if not in_bounds(rec, system, entry):
                rows[str(n)].append(None)
                continue
            st = stats(rec, period / S_MAX, period, entry, system, S_MAX, envelope=False)
            rows[str(n)].append(scalar_metrics(st, system, entry))
    return {"system": name, "u": u, "rows": rows}


def _settled_ics(name: str, u: float, k: int, tag: str) -> tuple[dict[str, Any], list[Any]]:
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    audio = [system.variable_index(v) for v in system.audio_variables]
    _, x = run(system, params, entry.initial_condition, period, N_REF, S_MAX, SETTLE_PERIODS)
    seed, x = run(system, params, x, period, N_REF, S_MAX, 100)
    sigma = seed[:, audio].std(axis=0)
    return s, draw_ics(system, params, x, period, sigma, k, f"{tag}/{name}/{u:.6f}")


def _scalar_run(s: dict[str, Any], ic: Any, n: int, periods: float) -> dict[str, float] | None:
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    _, x1 = run(system, params, ic, period, n, S_MAX, TRANSIENT_PERIODS)
    rec, _ = run(system, params, x1, period, n, S_MAX, periods)
    if not in_bounds(rec, system, entry):
        return None
    st = stats(rec, period / S_MAX, period, entry, system, S_MAX, envelope=False)
    return scalar_metrics(st, system, entry)


def edge_job(name: str, u: float, periods: float) -> dict[str, Any]:
    """Run (d2) at a flagged knob position.

    N = 64 … 512 against the reference from EDGE_K ICs, and the reference alone at
    u + EDGE_OFFSETS (the exact system's own sensitivity).
    """
    s, ics = _settled_ics(name, u, EDGE_K, "edge")
    rows = {str(n): [_scalar_run(s, ic, n, periods) for ic in ics] for n in (*EDGE_NS, N_REF)}
    neighbours = {}
    for du in EDGE_OFFSETS:
        u2 = min(max(u + du, 0.0), 1.0)
        s2, ics2 = _settled_ics(name, u2, EDGE_K, "edge-nb")
        neighbours[f"{du:+.6f}"] = [_scalar_run(s2, ic, N_REF, periods) for ic in ics2]
    return {"system": name, "u": u, "rows": rows, "neighbours": neighbours}


def modulation_job(name: str, n_cat: int, seed: int, seconds: float) -> dict[str, Any]:
    """(e) The v0.3 Dynamical block under a 0 ↔ 1 square wave on the param input."""
    from chaotic_sound.blocks import BlockContext, Dynamical

    cat = load_default_catalog()
    entry = cat[name]
    e = dataclasses.replace(
        entry, h_max=entry.h_max * entry.steps_per_period / n_cat, steps_per_period=n_cat
    )
    block = Dynamical(
        f"res-{name}",
        context=BlockContext(catalog=Catalog(entries={name: e})),
        system=name,
        note=MOD_NOTE,
        seed=seed,
    )
    block.reset(FS)
    n = round(seconds * FS)
    t = np.arange(n) / FS
    square = (np.floor(2.0 * MOD_SQUARE_HZ * t) % 2.0).astype(np.float64)
    out = block.process(n, {"param": square})["out"][:, 0]
    x = out[round(MOD_SKIP_SECONDS * FS) :]
    f0 = note_to_hz(MOD_NOTE)
    res: dict[str, Any] = {
        "system": name,
        "n_cat": n_cat,
        "seed": seed,
        "resets": block.diagnostics()["safety_resets"],
        "n_eff_min": min(block.substeps_per_sample(float(u)) for u in e.u_grid) * FS / f0,
    }
    if not np.all(np.isfinite(x)):
        return res
    freqs, psd = welch(x, fs=FS, nperseg=2**15, noverlap=2**14, window="hann")
    df = freqs[1] - freqs[0]
    total = float(np.sum(psd[1:]) * df)
    res["rms_db"] = 20.0 * math.log10(float(np.sqrt(np.mean(x**2))))
    res["bands_db"] = [
        _db(
            float(np.sum(psd[(freqs >= c * f0 / BAND_HALF) & (freqs < c * f0 * BAND_HALF)]) * df)
            / total
        )
        for c in BAND_CENTERS
    ]
    if entry.period_method != "drive":
        res["cents"] = 1200.0 * math.log2(measure_pitch(x, FS, entry.period_method, f0) / f0)
    return res


def chaos_ics(name: str, u: float) -> list[list[float]]:
    """(f) CHAOS_K initial conditions on the reference attractor at u."""
    _, ics = _settled_ics(name, u, CHAOS_K, "chaos")
    return [ic.tolist() for ic in ics]


def chaos_job(name: str, u: float, ics: list[list[float]], n: float, periods: float) -> list[float]:
    """(f) λ·P_ref with h = P(u)/n from each IC (n need not be an integer).

    Each run first spends CHAOS_TRANSIENT periods at this h, so λ is that of the attractor of
    the discretized system, not of the reference attractor it started on.
    """
    s = setup(name, u)
    system, params, period, entry = s["system"], s["params"], s["period"], s["entry"]
    p_ref = float(entry.info["reference_period"])
    return [
        p_ref
        * max_lyapunov(
            system,
            params,
            np.asarray(ic, dtype=np.float64),
            h=period / n,
            t_transient=CHAOS_TRANSIENT * period,
            t_measure=periods * period,
            t_renorm=0.25 * period,
        )
        for ic in ics
    ]


def engine_n_eff(cat: Catalog, name: str, u: float, n_cat: int) -> dict[int, float]:
    """N_eff = n_sub·fs/f₀ of the v0.3 Dynamical block at u, for every MIDI note in CHAOS_MIDI."""
    from chaotic_sound.blocks import BlockContext, Dynamical

    entry = cat[name]
    e = dataclasses.replace(
        entry, h_max=entry.h_max * entry.steps_per_period / n_cat, steps_per_period=n_cat
    )
    b = Dynamical("osc", context=BlockContext(catalog=Catalog(entries={name: e})), system=name)
    b.reset(FS)
    return {m: b.substeps_per_sample(u, midi_to_hz(m)) * FS / midi_to_hz(m) for m in CHAOS_MIDI}


def chaos_positions(results: dict[str, Any], edges: list[dict[str, Any]]) -> list[Any]:
    """(f) positions: u = 0, the default and u = 1 of every system, plus the (d2) points."""
    cat = load_default_catalog()
    pos = [
        (name, ul, u)
        for name in results
        for ul, u in (("u=0", 0.0), ("default", cat[name].u_default), ("u=1", 1.0))
    ]
    return pos + [(e["system"], f"edge {e['u']:.6f}", e["u"]) for e in edges]


def _is_chaotic(values: list[float]) -> bool:
    """Apply the catalog's criterion to the median over initial conditions."""
    return bool(np.median(values) > CHAOS_THRESHOLD)


def _runs(ns: tuple[int, ...], flags: list[bool]) -> list[list[int]]:
    """Contiguous runs [first N, last N] of grid points where ``flags`` is True."""
    runs: list[list[int]] = []
    for n, flag, before in zip(ns, flags, [False, *flags[:-1]], strict=True):
        if flag and not before:
            runs.append([n, n])
        elif flag:
            runs[-1][1] = n
    return runs


def run_chaos(
    pool: ProcessPoolExecutor, positions: list[Any], periods: float = CHAOS_PERIODS
) -> dict[str, Any]:
    """(f) The λ grid, then λ at the exact N_eff of the notes next to a differing grid N."""
    cat = load_default_catalog()
    f_ics = {p: pool.submit(chaos_ics, p[0], p[2]) for p in positions}
    ics = {p: f.result() for p, f in f_ics.items()}
    f_grid = {
        (p, n): pool.submit(chaos_job, p[0], p[2], ics[p], float(n), periods)
        for p in positions
        for n in CHAOS_GRID
    }
    grid = {key: f.result() for key, f in f_grid.items()}
    out: dict[str, Any] = {}
    f_notes: dict[tuple[Any, int], dict[int, Future[Any]]] = {}
    n_eff: dict[tuple[Any, int], dict[int, float]] = {}
    for p in positions:
        name, label, u = p
        ref_chaotic = _is_chaotic(grid[(p, N_REF)])
        differs = [_is_chaotic(grid[(p, n)]) != ref_chaotic for n in CHAOS_GRID]
        out.setdefault(name, {})[label] = {
            "u": u,
            "reference_chaotic": ref_chaotic,
            "grid": {str(n): grid[(p, n)] for n in CHAOS_GRID},
            "differing_bands": _runs(CHAOS_GRID, differs),
        }
        if label.startswith("edge"):
            continue
        for n_cat in CHAOS_NCATS:
            n_eff[(p, n_cat)] = engine_n_eff(cat, name, u, n_cat)
            f_notes[(p, n_cat)] = {}
            for m, ne in n_eff[(p, n_cat)].items():
                # Check the note directly if a grid point on either side of its N_eff differs.
                i = int(np.searchsorted(CHAOS_GRID, ne, side="right")) - 1
                if 0 <= i < len(CHAOS_GRID) - 1 and (differs[i] or differs[i + 1]):
                    f_notes[(p, n_cat)][m] = pool.submit(chaos_job, name, u, ics[p], ne, periods)
    for (p, n_cat), futures in f_notes.items():
        name, label, u = p
        e = cat[name]
        res = out[name][label]
        checked = [
            {
                "note": midi_to_note(m),
                "n_eff": n_eff[(p, n_cat)][m],
                "lyapunov_per_p_ref": f.result(),
                "chaotic": _is_chaotic(f.result()),
            }
            for m, f in futures.items()
        ]
        res.setdefault("engine", {})[str(n_cat)] = {
            # Smallest N_eff any pitch reaches at u: P(u)/h_max (the pitch input is continuous).
            "n_eff_min": float(e.period(u)) / (e.h_max * e.steps_per_period / n_cat),
            "n_eff_by_note": {midi_to_note(m): v for m, v in n_eff[(p, n_cat)].items()},
            "checked_notes": checked,
            "notes_differing": [
                c["note"] for c in checked if c["chaotic"] != res["reference_chaotic"]
            ],
        }
    return out


# --------------------------------------------------------------------------------------
# Aggregation: direct paired differences (verdicts) and a fit (cross-check only)
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


def _cents(p: float) -> float:
    return -1200.0 * math.log2(p) if p > 0 and math.isfinite(p) else math.nan


def scalar_metrics(st: dict[str, Any], system: SystemDef, entry: CatalogEntry) -> dict[str, float]:
    """Pitch, level and prominence scalars (see :func:`metrics`)."""
    m = {
        "cents": _cents(st["period"]),
        "cents_return_time": _cents(st["return_time"]),
        "prominence": 100.0 * st["prominence"][entry.default_observable],
    }
    for v in system.audio_variables:
        m[f"sigma_{v}"] = 100.0 * math.log(st["sigma"][v])
        m[f"peak_{v}"] = 100.0 * math.log(st["peak"][v])
    return m


def metrics(st: dict[str, Any], system: SystemDef, entry: CatalogEntry) -> dict[str, float]:
    """Scalars whose differences are the reported errors.

    ``cents*`` = −1200·log2(P), so a difference is the shift of the heard pitch in cents;
    ``sigma_*``/``peak_*`` = 100·ln(σ or π) (difference ≈ relative error in %);
    ``band_k``/``hf`` in dB; ``prominence`` in percentage points.
    """
    m = scalar_metrics(st, system, entry)
    m["hf"] = _db(st["hf"])
    for k, b in enumerate(st["bands"]):
        m[f"band_{k}"] = _db(b)
    return m


def fit_bias(
    ns: list[int], d: list[float], var: list[float], order: float
) -> dict[str, Any] | None:
    """Weighted fit d_N = a + c·N^-order (``a`` absorbs the reference's own noise).

    Cross-check only; ``accepted`` is False when χ²_red > FIT_CHI2_MAX.
    """
    ok = [i for i in range(len(ns)) if math.isfinite(d[i]) and var[i] > 0]
    if len(ok) < 3:
        return None
    x = np.array([float(ns[i]) ** -order for i in ok])
    y = np.array([d[i] for i in ok])
    w = 1.0 / np.array([var[i] for i in ok])
    design = np.column_stack([np.ones_like(x), x])
    cov = np.linalg.inv(design.T @ (design * w[:, None]))
    a, c = cov @ (design.T @ (w * y))
    chi2 = float(np.sum(w * (y - (a + c * x)) ** 2) / (len(ok) - 2)) if len(ok) > 2 else math.nan
    se_c = float(math.sqrt(cov[1, 1] * max(1.0, chi2)))
    return {
        "a": float(a),
        "c": float(c),
        "se_c": se_c,
        "chi2_red": chi2,
        "accepted": bool(chi2 <= FIT_CHI2_MAX),
        "bias_128": [float(c) * 128.0**-order, se_c * 128.0**-order],
    }


def level_keys(name: str, u: float) -> list[str]:
    """Return the statistic that sets each audible variable's level at u (σ or π).

    The engine scales by min(RMS_TARGET/σ, PEAK_TARGET/π) (spec §4.2 step 6).
    """
    entry, system = load_default_catalog()[name], get_system(name)
    keys = []
    for v in system.audio_variables:
        sigma, peak = float(entry.std(v, u)), float(entry.peak(v, u))
        keys.append(f"peak_{v}" if PEAK_TARGET / peak < RMS_TARGET / sigma else f"sigma_{v}")
    return keys


def aggregate(name: str, u: float, reals: list[dict[str, Any]], order: float) -> dict[str, Any]:
    system, entry = get_system(name), load_default_catalog()[name]
    reals = sorted(reals, key=lambda r: (r["stage"], r["m"]))
    stage1 = [r for r in reals if r["stage"] == 1]
    ref64 = [r["ref"][str(S_MAX)] for r in reals]
    ref_m = [metrics(r, system, entry) for r in ref64]
    out: dict[str, Any] = {
        "u": u,
        "level_keys": level_keys(name, u),
        "realizations": {},
        "failed": {},
        "direct": {},
        "fit": {},
        "ref": {
            "period": mean_se([r["period"] for r in ref64]),
            "cents_spread": float(np.std([m["cents"] for m in ref_m], ddof=1)),
            "cents_rt_spread": float(np.std([m["cents_return_time"] for m in ref_m], ddof=1)),
            "sigma": {v: mean_se([r["sigma"][v] for r in ref64]) for v in system.audio_variables},
            "peak": {v: mean_se([r["peak"][v] for r in ref64]) for v in system.audio_variables},
            "prominence": mean_se([r["prominence"][entry.default_observable] for r in ref64]),
            "band_level_db": [
                _db(float(np.mean([r["bands"][b] / r["total_power"] for r in ref64])))
                for b in range(len(BAND_CENTERS))
            ],
            "hf_level_db": _db(float(np.mean([r["hf"] / r["total_power"] for r in ref64]))),
        },
    }
    # Sampling bias of the catalog's estimator: same reference trajectories, decimated.
    for s in (16, 32):
        d = [
            _cents(r["ref"][str(s)]["period"]) - _cents(r["ref"][str(S_MAX)]["period"])
            for r in stage1
            if str(s) in r["ref"]
        ]
        out["ref"][f"estimator_bias_S{s}"] = mean_se(d)
    # Pooled long records (reference and N ≥ 256) for the catalog comparison.
    pooled = [r["period"] for r in ref64] + [
        r["by_n"][k]["period"] for r in reals for k in ("256", "512") if r["by_n"].get(k)
    ]
    out["ref"]["period_pooled"] = [*mean_se(pooled), len(pooled)]
    keys = list(ref_m[0])
    cache: dict[tuple[int, str, str], dict[str, float]] = {}

    def met(i: int, kind: str, n: str) -> dict[str, float]:
        if (i, kind, n) not in cache:
            st = reals[i]["by_n"][n] if kind == "run" else reals[i]["ref"][n]
            cache[(i, kind, n)] = metrics(st, system, entry)
        return cache[(i, kind, n)]

    for n in NS:
        rs = [r for r in reals if str(n) in r["by_n"]]
        out["realizations"][str(n)] = len(rs)
        out["failed"][str(n)] = sum(1 for r in rs if r["by_n"][str(n)] is None)
    paired: dict[int, list[tuple[dict[str, float], dict[str, float]]]] = {}
    for n in NS:
        s = str(min(n, S_MAX))
        paired[n] = [
            (met(i, "run", str(n)), met(i, "ref", s))
            for i, r in enumerate(reals)
            if r["by_n"].get(str(n))
        ]
    for key in keys:
        rows = []
        for n in NS:
            if out["failed"][str(n)] or len(paired[n]) < 2:
                rows.append([math.nan, math.nan])
                continue
            rows.append(list(mean_se([a[key] - b[key] for a, b in paired[n]])))
        out["direct"][key] = rows
        # Cross-check fit over N ≥ 64 on the stage-1 realizations (a common set at every N).
        d, var = [], []
        for n in NS[2:]:
            vals = [
                (met(i, "run", str(n))[key], met(i, "ref", str(S_MAX))[key])
                for i, r in enumerate(reals)
                if r["stage"] == 1 and r["by_n"].get(str(n))
            ]
            if len(vals) < len(stage1) or len(vals) < 2:
                d.append(math.nan)
                var.append(math.nan)
                continue
            a = np.array(vals)
            d.append(float(np.mean(a[:, 0] - a[:, 1])))
            var.append(float(a[:, 0].var(ddof=1) / len(a)))
        out["fit"][key] = fit_bias(list(NS[2:]), d, var, order)
    return out


def criterion_keys(name: str, agg: dict[str, Any], n: int, which: str, audible: bool) -> list[str]:
    system = get_system(name)
    if which == "pitch":
        return [] if load_default_catalog()[name].period_method == "drive" else ["cents"]
    if which == "level":
        return list(agg["level_keys"])
    if which in ("sigma", "peak"):
        return [f"{which}_{v}" for v in system.audio_variables]
    nyq = min(n, S_MAX) / 2.0
    levels = agg["ref"]["band_level_db"]
    return [
        f"band_{k}"
        for k, c in enumerate(BAND_CENTERS)
        if c * BAND_HALF < NYQUIST_USE * nyq and (not audible or levels[k] >= AUDIBLE_FLOOR_DB)
    ]


TOLS = {
    "pitch": PITCH_TOL_CENTS,
    "level": 100 * LEVEL_TOL,
    "sigma": 100 * LEVEL_TOL,
    "peak": 100 * LEVEL_TOL,
    "envelope": ENVELOPE_TOL_DB,
}


def judge(
    name: str, agg: dict[str, Any], n: int, which: str, audible: bool = True
) -> dict[str, Any]:
    """Verdict on one criterion at one N from the direct paired differences.

    ``pass``: every key has |d| + 2 SE < tolerance. ``fail``: some key has |d| − 2 SE >
    tolerance, or a run diverged. ``open`` otherwise (the data can neither confirm nor exclude).
    ``ub`` is the worst 95 % upper bound |d| + 2 SE, ``worst`` the worst |d|.
    """
    i = NS.index(n)
    tol = TOLS[which]
    if agg["failed"][str(n)]:
        return {"status": "fail", "diverged": True, "ub": math.inf, "worst": math.inf, "key": None}
    ub, lb, worst, worst_key = 0.0, -math.inf, 0.0, None
    for key in criterion_keys(name, agg, n, which, audible):
        m, se = agg["direct"][key][i]
        if not math.isfinite(m):
            continue
        se = se if math.isfinite(se) else 0.0
        if abs(m) + 2 * se > ub:
            ub, worst_key = abs(m) + 2 * se, key
        lb = max(lb, abs(m) - 2 * se)
        worst = max(worst, abs(m))
    status = "pass" if ub < tol else ("fail" if lb > tol else "open")
    return {"status": status, "diverged": False, "ub": ub, "worst": worst, "key": worst_key}


CRITERIA = ("pitch", "level", "envelope")


def judge_all(results: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {
            ul: {w: [judge(name, agg, n, w) for n in NS] for w in (*CRITERIA, "sigma", "peak")}
            for ul, agg in per_u.items()
        }
        for name, per_u in results.items()
    }


def verdicts(results: dict[str, Any]) -> dict[str, Any]:
    """Smallest passing N per system and criterion, over all three knob positions.

    ``confirmed``: smallest N that passes at every u while no larger N fails (a larger N may
    be ``open``: N = 512 has fewer realizations than the refined N, and the bias falls with N);
    ``not_excluded``: smallest N such that no N at or above it fails.
    """
    table: dict[str, Any] = {}
    for name, per_u in results.items():
        row: dict[str, Any] = {}
        for which, audible in [*((c, True) for c in CRITERIA), ("envelope_strict", False)]:
            crit = which.split("_")[0]
            st = [
                [judge(name, agg, n, crit, audible)["status"] for agg in per_u.values()] for n in NS
            ]
            confirmed = not_excluded = None
            for i, n in enumerate(NS):
                if all(x == "pass" for x in st[i]) and not any("fail" in t for t in st[i:]):
                    confirmed = n
                    break
            for n, s in zip(reversed(NS), reversed(st), strict=True):
                if "fail" in s:
                    break
                not_excluded = n
            row[which] = {"confirmed": confirmed, "not_excluded": not_excluded}
        conf = [row[c]["confirmed"] for c in CRITERIA]
        nex = [row[c]["not_excluded"] for c in CRITERIA]
        row["all"] = {
            "confirmed": None if None in conf else max(conf),
            "not_excluded": None if None in nex else max(nex),
        }
        table[name] = row
    return table


def refine_points(results: dict[str, Any], m1: dict[str, int], m2: int, cap: int) -> list[Any]:
    """Points where a criterion is open at N ∈ REFINE_NS and m2 more realizations could settle it.

    Settling is judged plausible when the expected SE after refinement, SE·√(M/(M + m2)), is
    below tolerance/2.5. Ordered by N = 128 first, then by how far the bound is from the
    tolerance.
    """
    cand = []
    for name, per_u in results.items():
        for ul, agg in per_u.items():
            best = None
            for n in REFINE_NS:
                i = NS.index(n)
                for which in ("pitch", "level"):
                    j = judge(name, agg, n, which)
                    if j["status"] != "open" or j["key"] is None:
                        continue
                    se = agg["direct"][j["key"]][i][1]
                    se_new = se * math.sqrt(m1[name] / (m1[name] + m2))
                    if se_new < TOLS[which] / 2.5:
                        prio = (0 if n == 128 else 1, j["ub"] / TOLS[which])
                        best = prio if best is None else min(best, prio)
            if best is not None:
                cand.append((best, name, ul))
    cand.sort()
    return [(name, ul) for _, name, ul in cand[:cap]]


def short_order(short: dict[str, float]) -> float:
    """Convergence order from the one-period errors between N = 64 and 512."""
    return math.log2(short["64"] / short["512"]) / 3.0


def summarize_sweep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per system: differences at each u and N, and the attractor switches found."""
    out: dict[str, Any] = {}
    for r in rows:
        name, u = r["system"], r["u"]
        ref = r["rows"][str(N_REF)]
        point: dict[str, Any] = {"u": u}
        for n in SWEEP_NS:
            runs = r["rows"][str(n)]
            pairs = [(a, b) for a, b in zip(runs, ref, strict=True) if a and b]
            if len(pairs) < len(runs):
                point[str(n)] = {"diverged": True}
                continue
            res: dict[str, Any] = {"diverged": False}
            for metric in ("cents", "prominence"):
                res[metric] = mean_se([a[metric] - b[metric] for a, b in pairs])
            worst = max(
                (k for k in pairs[0][0] if k.startswith("sigma_")),
                key=lambda k: abs(np.mean([a[k] - b[k] for a, b in pairs])),
            )
            res["sigma"] = mean_se([a[worst] - b[worst] for a, b in pairs])
            res["sigma_var"] = worst
            res["switch"] = [
                m
                for m, thr in SWITCH_THRESHOLDS.items()
                if abs(res[m][0]) > thr
                and abs(res[m][0]) > 4 * (res[m][1] or 0.0)
                and not (m == "cents" and load_default_catalog()[name].period_method == "drive")
            ]
            point[str(n)] = res
        refs = [b for b in ref if b]
        e = load_default_catalog()[name]
        point["ref_prominence"] = float(np.mean([b["prominence"] for b in refs]))
        if e.period_method != "drive":
            # 1200·log2(P_catalog(u)/P_reference): > 0 means a box tuned with the table is sharp.
            c_cat = _cents(float(e.period(u)))
            point["catalog_offset_cents"] = mean_se([b["cents"] - c_cat for b in refs])
        v = e.default_observable
        point["catalog_sigma_rel"] = float(
            np.mean([math.exp(b[f"sigma_{v}"] / 100.0) for b in refs]) / float(e.std(v, u)) - 1.0
        )
        out.setdefault(name, []).append(point)
    for name in out:
        out[name].sort(key=lambda p: p["u"])
    return out


def edge_points(sweep: dict[str, Any]) -> list[tuple[str, float]]:
    """Sweep points flagged at N = 64 or 128, the N = 128 flags first, at most EDGE_MAX."""
    cand = []
    for name, pts in sweep.items():
        for p in pts:
            f128 = bool(p["128"].get("diverged") or p["128"].get("switch"))
            f64 = bool(p["64"].get("diverged") or p["64"].get("switch"))
            if f128 or f64:
                size = 0.0 if p["64"].get("diverged") else abs(p["64"]["cents"][0])
                cand.append((0 if f128 else 1, -size, name, p["u"]))
    cand.sort()
    return [(name, u) for _, _, name, u in cand[:EDGE_MAX]]


def _diffs(pairs: list[Any], key: str) -> tuple[float, float]:
    return mean_se([a[key] - b[key] for a, b in pairs])


def summarize_edges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Paired differences at each N, and the reference's change over small knob offsets."""
    out = []
    for r in rows:
        ref = r["rows"][str(N_REF)]
        point: dict[str, Any] = {"system": r["system"], "u": r["u"], "by_n": {}, "reference": {}}
        sig_keys = [k for k in next(b for b in ref if b) if k.startswith("sigma_")]
        for n in EDGE_NS:
            runs = r["rows"][str(n)]
            pairs = [(a, b) for a, b in zip(runs, ref, strict=True) if a and b]
            if len(pairs) < len(runs):
                point["by_n"][str(n)] = {"diverged": True}
                continue
            worst = max(sig_keys, key=lambda k: abs(_diffs(pairs, k)[0]))
            point["by_n"][str(n)] = {"cents": _diffs(pairs, "cents"),
                                     "prominence": _diffs(pairs, "prominence"),
                                     "sigma": _diffs(pairs, worst), "sigma_var": worst}  # fmt: skip
        base = [b for b in ref if b]
        for du, nb in r["neighbours"].items():
            nb = [b for b in nb if b]
            res: dict[str, Any] = {}
            for key in ("cents", "prominence", *sig_keys):
                m1, s1 = mean_se([b[key] for b in nb])
                m0, s0 = mean_se([b[key] for b in base])
                res[key] = [m1 - m0, math.hypot(s1, s0)]
            point["reference"][du] = res
        out.append(point)
    return out


def sweep_grid(entry: CatalogEntry) -> list[float]:
    """Uniform points plus every catalog periodic window (center and just outside each edge)."""
    us = set(np.linspace(0.0, 1.0, SWEEP_UNIFORM).round(6).tolist())
    width = entry.p_max - entry.p_min
    for lo, hi in entry.info["range_selection"]["periodic_windows"]:
        ulo, uhi = (lo - entry.p_min) / width, (hi - entry.p_min) / width
        for v in ((ulo + uhi) / 2, ulo - SWEEP_EDGE_DU, uhi + SWEEP_EDGE_DU):
            if 0.0 <= v <= 1.0:
                us.add(round(float(v), 6))
    return sorted(us)


def summarize_modulation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in sorted({r["system"] for r in rows}):
        mine = [r for r in rows if r["system"] == name]
        ref = {r["seed"]: r for r in mine if r["n_cat"] == MOD_N_REF}
        per: dict[str, Any] = {}
        for n in (*MOD_NS, MOD_N_REF):
            rs = sorted((r for r in mine if r["n_cat"] == n), key=lambda r: r["seed"])
            entry: dict[str, Any] = {
                "resets": int(sum(r["resets"] for r in rs)),
                "renders_with_resets": sum(1 for r in rs if r["resets"]),
            }
            if n != MOD_N_REF and all("rms_db" in r for r in rs):
                entry["rms_db"] = mean_se([r["rms_db"] - ref[r["seed"]]["rms_db"] for r in rs])
                if "cents" in rs[0]:
                    entry["cents"] = mean_se([r["cents"] - ref[r["seed"]]["cents"] for r in rs])
                levels = np.mean([ref[r["seed"]]["bands_db"] for r in rs], axis=0)
                worst = (0.0, 0.0)
                for k, lev in enumerate(levels):
                    if not lev >= AUDIBLE_FLOOR_DB:
                        continue
                    d = mean_se([r["bands_db"][k] - ref[r["seed"]]["bands_db"][k] for r in rs])
                    if abs(d[0]) > abs(worst[0]):
                        worst = d
                entry["worst_band_db"] = worst
            if n == MOD_N_REF:
                entry["rms_db_abs"] = mean_se([r["rms_db"] for r in rs if "rms_db" in r])
                entry["cents_abs"] = mean_se([r.get("cents", math.nan) for r in rs])
                entry["cents_spread"] = float(
                    np.std([r.get("cents", math.nan) for r in rs], ddof=1)
                )
            per[str(n)] = entry
        out[name] = per
    return out


def cost_table(cat: Catalog) -> dict[str, Any]:
    """RK4 sub-steps per sample with the engine's rule, for catalog N values and notes."""
    from chaotic_sound.blocks import BlockContext, Dynamical

    out: dict[str, Any] = {}
    for name, entry in cat.entries.items():
        per_n: dict[str, Any] = {}
        for n in (*NS, 1024):
            e = dataclasses.replace(
                entry, h_max=entry.h_max * entry.steps_per_period / n, steps_per_period=n
            )
            ctx = BlockContext(catalog=Catalog(entries={name: e}))
            row: dict[str, Any] = {}
            for note in NOTES:
                b = Dynamical("osc", context=ctx, system=name, note=note)
                b.reset(FS)
                sub_def = b.substeps_per_sample()
                row[note] = {
                    "substeps_default": sub_def,
                    "substeps_max_over_u": max(b.substeps_per_sample(float(u)) for u in e.u_grid),
                    "effective_n_default": sub_def * FS / note_to_hz(note),
                }
            row["naive_A4"] = math.ceil(n * note_to_hz("A4") / FS)
            per_n[str(n)] = row
        out[name] = {
            "per_n": per_n,
            "p_default": float(entry.period(entry.u_default)),
            "p_min": float(entry.period_table.min()),
            "u_at_p_min": float(entry.u_grid[int(np.argmin(entry.period_table))]),
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
            ax.plot(
                ns,
                err,
                u_style[ul],
                color=color,
                lw=2 if ul == "default" else 1.2,
                marker="o" if ul == "default" else None,
                ms=4,
                label=disp[name] if ul == "default" else None,
            )
    for p, lab in ((4.0, "∝ N⁻⁴"), (2.0, "∝ N⁻²")):
        guide = 3e-2 * (ns / 16) ** -p
        ax.plot(ns, guide, color=MUTED, lw=1, alpha=0.5)
        ax.text(ns[-1], guide[-1], " " + lab, color=MUTED, fontsize=8, va="center")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("RK4 steps per period N", color=INK)
    ax.set_ylabel("RMS state error after one period (units of σ)", color=INK)
    ax.set_title(
        "(a) One-period error vs N   (solid: default, dotted: u=0, dashed: u=1)", fontsize=9
    )
    style(ax)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "short_horizon_error.png", dpi=150)
    plt.close(fig)

    # (b) long-run criteria: worst over u of the direct 95 % bound (line) and |d| (markers)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
    titles = {
        "pitch": "pitch shift (cents)",
        "level": "level error, governing σ or π, worst variable (%)",
        "envelope": "band-level error ≤ 20 f₀, audible bands (dB)",
    }
    for ax, which in zip(axes, CRITERIA, strict=True):
        for name, color in zip(names, SERIES, strict=False):
            if which == "pitch" and not criterion_keys(name, {}, 64, "pitch", True):
                continue
            ub, worst = [], []
            for n in NS:
                js = [judge(name, data["results"][name][ul], n, which) for ul in U_LABELS]
                ub.append(max(j["ub"] for j in js))
                worst.append(max(j["worst"] for j in js))
            ub_a = np.where(np.isfinite(ub), ub, np.nan)
            w_a = np.where(np.isfinite(worst), worst, np.nan)
            ax.plot(NS, np.maximum(ub_a, 1e-6), "-", color=color, lw=2, label=disp[name])
            ax.plot(NS, np.maximum(w_a, 1e-6), "o", color=color, ms=5, mfc="none", mew=1.5)
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
        title="line: |d| + 2 SE (worst u); ○: |d|",
        title_fontsize=7,
    )
    fig.tight_layout()
    fig.savefig(OUT / "long_run_errors.png", dpi=150)
    plt.close(fig)

    # (b) spectral envelope at the default
    cat = load_default_catalog()
    fig, axes = plt.subplots(
        2, len(names), figsize=(3.0 * len(names), 6.2), sharex=True, squeeze=False
    )
    for j, name in enumerate(names):
        agg = data["results"][name]["default"]
        top, bot = axes[0, j], axes[1, j]
        top.semilogx(BAND_CENTERS, agg["ref"]["band_level_db"], "-o", color=INK, lw=1.5, ms=3)
        top.axhline(AUDIBLE_FLOOR_DB, color=MUTED, lw=1, ls=":")
        top.set_title(f"{disp[name]} — {cat[name].default_observable}", fontsize=9)
        for n, color in zip(NS, RAMP, strict=True):
            i = NS.index(n)
            y = np.array([agg["direct"][f"band_{k}"][i][0] for k in range(len(BAND_CENTERS))])
            keep = [
                f"band_{k}" in criterion_keys(name, agg, n, "envelope", False)
                for k in range(len(BAND_CENTERS))
            ]
            bot.semilogx(
                BAND_CENTERS,
                np.where(keep, y, np.nan),
                "-o",
                color=color,
                lw=1.5,
                ms=3,
                label=f"N={n}",
            )
        bot.axhspan(-ENVELOPE_TOL_DB, ENVELOPE_TOL_DB, color=GRID, alpha=0.8, lw=0)
        bot.set_ylim(-5, 5)
        bot.set_xlabel("frequency / f₀", color=INK)
        style(top)
        style(bot)
    axes[0, 0].set_ylabel("reference band power (dB re total)", color=INK)
    axes[1, 0].set_ylabel(f"band level vs N={N_REF} (dB)", color=INK)
    axes[1, -1].legend(fontsize=7, frameon=False, loc="lower left")
    fig.suptitle(
        "(b) 1/3-octave spectral envelope of the heard variable at the default "
        "(dotted: audibility floor)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "envelope_default.png", dpi=150)
    plt.close(fig)

    # (d) window sweep
    sweep = data["sweep"]
    fig, axes = plt.subplots(
        2, len(names), figsize=(3.0 * len(names), 5.4), sharex=True, squeeze=False
    )
    for j, name in enumerate(names):
        e = cat[name]
        width = e.p_max - e.p_min
        for ax, metric, lab in (
            (axes[0, j], "prominence", "Δ prominence (pp)"),
            (axes[1, j], "sigma", "Δσ, worst variable (%)"),
        ):
            for lo, hi in e.info["range_selection"]["periodic_windows"]:
                a, b = (lo - e.p_min) / width, (hi - e.p_min) / width
                ax.axvspan(a - 0.003, b + 0.003, color=GRID, lw=0)
            for n, color in zip(SWEEP_NS, (RAMP[1], RAMP[4]), strict=True):
                pts = [p for p in sweep[name] if not p[str(n)].get("diverged")]
                us = [p["u"] for p in pts]
                ys = [p[str(n)][metric][0] for p in pts]
                ax.plot(us, ys, "o", color=color, ms=3, label=f"N={n}")
                sw = [(p["u"], p[str(n)][metric][0]) for p in pts if metric in p[str(n)]["switch"]]
                if sw:
                    ax.plot(*zip(*sw, strict=True), "x", color="#c0392b", ms=7, mew=1.5)
            ax.axhline(0, color=MUTED, lw=0.8)
            if j == 0:
                ax.set_ylabel(lab, color=INK)
            style(ax)
        axes[0, j].set_title(disp[name], fontsize=9)
        axes[1, j].set_xlabel("knob u", color=INK)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle(
        f"(d) N = 64 and 128 against N = {N_REF} across the range (grey: catalog "
        "periodic windows; ×: attractor switch)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "window_sweep.png", dpi=150)
    plt.close(fig)

    # (f) λ·P_ref against N at the three knob positions
    if "chaos" not in data:
        return
    fig, axes = plt.subplots(1, len(names), figsize=(3.0 * len(names), 3.6), squeeze=False)
    for ax, name in zip(axes[0], names, strict=True):
        for ul, color in zip(U_LABELS, (SERIES[0], SERIES[1], SERIES[2]), strict=True):
            g = data["chaos"][name][ul]["grid"]
            ns = np.array([float(n) for n in g])
            vals = np.array(list(g.values()))
            ax.fill_between(ns, vals.min(axis=1), vals.max(axis=1), color=color, alpha=0.2, lw=0)
            ax.plot(ns, np.median(vals, axis=1), "-", color=color, lw=1.2, label=ul)
        ax.axhline(CHAOS_THRESHOLD, color=INK, lw=1, ls="--")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("RK4 steps per period N", color=INK)
        ax.set_title(disp[name], fontsize=9)
        style(ax)
    axes[0, 0].set_ylabel("λ·P_ref (median, band: min–max over ICs)", color=INK)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle(
        f"(f) Largest Lyapunov exponent against N (dashed: catalog chaos threshold "
        f"{CHAOS_THRESHOLD})",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "chaos_vs_n.png", dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def finish_sweep(
    pool: ProcessPoolExecutor, f_sweep: list[Future[Any]], periods: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Collect (d), then run (d2) at the flagged points."""
    sweep = summarize_sweep([f.result() for f in f_sweep])
    pts = edge_points(sweep)
    print(f"edge follow-up at {pts}", flush=True)
    f_edge = [pool.submit(edge_job, name, u, periods) for name, u in pts]
    return sweep, summarize_edges([f.result() for f in f_edge])


def sweep_only(args: argparse.Namespace) -> None:
    """Rerun (d) and (d2) only and merge them into an existing results.json (same catalog)."""
    data = json.loads((OUT / "results.json").read_text())
    cat = load_default_catalog()
    if cat.metadata.get("generated") != data["catalog_generated"]:
        raise RuntimeError("results.json was made with another catalog; run the full study")
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        f_sweep = [pool.submit(sweep_job, name, u, SWEEP_PERIODS) for name in data["results"]
                   for u in sweep_grid(cat[name])]  # fmt: skip
        data["sweep"], data["edges"] = finish_sweep(pool, f_sweep, SWEEP_PERIODS)
    data["judged"] = judge_all(data["results"])
    data["verdicts"] = verdicts(data["results"])
    data["settings"]["timing_seconds"]["sweep_only_rerun"] = time.perf_counter() - t0
    data["settings"]["edges"] = {"ns": EDGE_NS, "ics": EDGE_K, "offsets": EDGE_OFFSETS}
    (OUT / "results.json").write_text(json.dumps(data, indent=1, allow_nan=True) + "\n")
    plots(data)
    print(f"sweep and edges done in {time.perf_counter() - t0:.0f} s")


def chaos_settings() -> dict[str, Any]:
    return {
        "grid": CHAOS_GRID,
        "ics": CHAOS_K,
        "periods": CHAOS_PERIODS,
        "transient_periods": CHAOS_TRANSIENT,
        "threshold": CHAOS_THRESHOLD,
        "n_cats": CHAOS_NCATS,
    }


def chaos_only(args: argparse.Namespace) -> None:
    """Rerun (f) only and merge it into an existing results.json (same catalog)."""
    data = json.loads((OUT / "results.json").read_text())
    cat = load_default_catalog()
    if cat.metadata.get("generated") != data["catalog_generated"]:
        raise RuntimeError("results.json was made with another catalog; run the full study")
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        data["chaos"] = run_chaos(pool, chaos_positions(data["results"], data["edges"]))
    data["settings"]["timing_seconds"]["chaos_only_rerun"] = time.perf_counter() - t0
    data["settings"]["chaos"] = chaos_settings()
    (OUT / "results.json").write_text(json.dumps(data, indent=1, allow_nan=True) + "\n")
    plots(data)
    print(f"chaos check done in {time.perf_counter() - t0:.0f} s")


REALIZATION_FACTOR = {"duffing": 2}
"""Duffing's well-hopping makes its statistics converge slowly: more realizations."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="tiny run to test the script")
    parser.add_argument("--systems", nargs="*", default=list_systems())
    parser.add_argument("--realizations", type=int, default=16)
    parser.add_argument("--periods", type=float, default=10000.0)
    parser.add_argument("--refine-max", type=int, default=8)
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument(
        "--sweep-only", action="store_true", help="rerun only (d) and (d2), merge into results.json"
    )
    parser.add_argument(
        "--chaos-only", action="store_true", help="rerun only (f), merge into results.json"
    )
    parser.add_argument(
        "--reanalyze", action="store_true", help="recompute verdicts and figures from results.json"
    )
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
    if args.sweep_only:
        sweep_only(args)
        return
    if args.chaos_only:
        chaos_only(args)
        return
    refine_m, stab_periods, sweep_periods, mod_seconds, chaos_periods = (
        REFINE_M,
        STAB_PERIODS,
        SWEEP_PERIODS,
        MOD_SECONDS,
        CHAOS_PERIODS,
    )
    if args.quick:
        args.realizations, args.periods, refine_m = 3, 600.0, 3
        stab_periods, sweep_periods, mod_seconds, chaos_periods = 300.0, 300.0, 3.0, 200.0
    cat = load_default_catalog()
    generated = cat.metadata.get("generated")
    t0 = time.perf_counter()
    m1 = {n: args.realizations * REALIZATION_FACTOR.get(n, 1) for n in args.systems}
    points = [
        (name, ul, float(u), m1[name] + refine_m)
        for name in args.systems
        for ul, u in (("u=0", 0.0), ("default", cat[name].u_default), ("u=1", 1.0))
    ]
    timing: dict[str, float] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        preps = list(pool.map(prepare, *zip(*points, strict=True)))
        timing["prepare"] = time.perf_counter() - t0
        jobs = [
            (p["system"], p["u_label"], p["u"], m, p["ics"][m], args.periods, NS, 1)
            for p in preps
            for m in range(m1[p["system"]])
        ]
        jobs.sort(key=lambda j: -(2.5 if j[0] == "duffing" else 1.0))
        f1: list[Future[Any]] = [pool.submit(realization, *j) for j in jobs]
        f_stab = {
            (p[0], p[1]): pool.submit(stability_job, p[0], p[1], p[2], stab_periods) for p in points
        }
        f_sweep = [
            pool.submit(sweep_job, name, u, sweep_periods)
            for name in args.systems
            for u in sweep_grid(cat[name])
        ]
        f_mod = [
            pool.submit(modulation_job, name, n, seed, mod_seconds)
            for name in args.systems
            for n in (*MOD_NS, MOD_N_REF)
            for seed in range(1, MOD_SEEDS + 1)
        ]
        reals1 = [f.result() for f in f1]
        timing["stage1"] = time.perf_counter() - t0
        print(f"stage 1: {len(reals1)} realizations in {timing['stage1']:.0f} s", flush=True)

        short: dict[str, Any] = {}
        for p in preps:
            short.setdefault(p["system"], {})[p["u_label"]] = p["short_error"]
        orders = {
            n: float(round(float(np.median([short_order(e) for e in per_u.values()]))))
            for n, per_u in short.items()
        }
        by_point = {(p["system"], p["u_label"]): p for p in preps}

        def collect(reals: list[dict[str, Any]]) -> dict[str, Any]:
            res: dict[str, Any] = {}
            for (name, ul), p in by_point.items():
                rs = [r for r in reals if r["system"] == name and r["u_label"] == ul]
                res.setdefault(name, {})[ul] = aggregate(name, p["u"], rs, orders[name])
            return res

        results1 = collect(reals1)
        chosen = refine_points(results1, m1, refine_m, args.refine_max)
        print(f"refining {chosen}", flush=True)
        jobs2 = [
            (
                name,
                ul,
                by_point[(name, ul)]["u"],
                m,
                by_point[(name, ul)]["ics"][m],
                args.periods,
                REFINE_NS,
                2,
            )
            for name, ul in chosen
            for m in range(m1[name], m1[name] + refine_m)
        ]
        reals2 = list(pool.map(realization, *zip(*jobs2, strict=True))) if jobs2 else []
        timing["stage2"] = time.perf_counter() - t0
        stability = {f"{k[0]}/{k[1]}": f.result() for k, f in f_stab.items()}
        sweep, edges = finish_sweep(pool, f_sweep, sweep_periods)
        mod_rows = [f.result() for f in f_mod]
        timing["before_chaos"] = time.perf_counter() - t0
        positions = chaos_positions({n: None for n in args.systems}, edges)
        chaos = run_chaos(pool, positions, chaos_periods)
    timing["total"] = time.perf_counter() - t0
    print(f"all jobs done in {timing['total']:.0f} s", flush=True)

    now = Catalog.load(default_catalog_path()).metadata.get("generated")
    if now != generated:
        raise RuntimeError(f"the catalog changed during the run ({generated} → {now}); rerun")
    results = collect(reals1 + reals2)
    consistency: dict[str, Any] = {}
    for (name, ul), p in by_point.items():
        e, agg = cat[name], results[name][ul]
        u = p["u"]
        p_pool, se_pool, n_pool = agg["ref"]["period_pooled"]
        offset = 1200 * math.log2(float(e.period(u)) / p_pool)
        spread2000 = agg["ref"]["cents_spread"] * math.sqrt(args.periods / 2000.0)
        consistency.setdefault(name, {})[ul] = {
            "cents_vs_catalog": offset,
            "cents_vs_catalog_se": 1200 / math.log(2) * se_pool / p_pool,
            "records_pooled": n_pool,
            "spread_10000_cents": agg["ref"]["cents_spread"],
            "spread_2000_cents_scaled": spread2000,
            "z_vs_2000_record": offset / spread2000 if spread2000 > 0 else math.nan,
            "sigma_rel_vs_catalog": {
                v: agg["ref"]["sigma"][v][0] / float(e.std(v, u)) - 1 for v in agg["ref"]["sigma"]
            },
            "peak_rel_vs_catalog": {
                v: agg["ref"]["peak"][v][0] / float(e.peak(v, u)) - 1 for v in agg["ref"]["peak"]
            },
            "lyapunov_per_period_catalog": float(
                np.interp(u, e.u_grid, np.asarray(e.info["lyapunov_per_period"]))
            ),
            "param_value": float(e.param_value(u)),
            "period_catalog": float(e.period(u)),
        }
    data = {
        "engine": ENGINE_VERSION,
        "catalog_generated": generated,
        "catalog_steps_per_period": {n: cat[n].steps_per_period for n in args.systems},
        "settings": {
            "NS": NS,
            "N_REF": N_REF,
            "N_SHORT_REF": N_SHORT_REF,
            "samples_per_period_max": S_MAX,
            "welch_periods": WELCH_PERIODS,
            "realizations_stage1": m1,
            "refine_realizations": refine_m,
            "refine_ns": REFINE_NS,
            "refined_points": chosen,
            "periods_per_realization": args.periods,
            "transient_periods": TRANSIENT_PERIODS,
            "band_centers": BAND_CENTERS.tolist(),
            "audible_floor_db": AUDIBLE_FLOOR_DB,
            "stability": {"ns": STAB_NS, "realizations": STAB_M, "periods": stab_periods},
            "sweep": {
                "ns": SWEEP_NS,
                "ics": SWEEP_K,
                "periods": sweep_periods,
                "thresholds": SWITCH_THRESHOLDS,
            },
            "edges": {"ns": EDGE_NS, "ics": EDGE_K, "offsets": EDGE_OFFSETS},
            "chaos": {**chaos_settings(), "periods": chaos_periods},
            "modulation": {
                "ns": MOD_NS,
                "n_ref": MOD_N_REF,
                "note": MOD_NOTE,
                "seconds": mod_seconds,
                "seeds": MOD_SEEDS,
                "square_hz": MOD_SQUARE_HZ,
            },
            "workers": args.workers,
            "timing_seconds": timing,
        },
        "short": short,
        "short_order_measured": {
            n: {ul: short_order(e) for ul, e in per_u.items()} for n, per_u in short.items()
        },
        "fit_order": orders,
        "results": results,
        "judged": judge_all(results),
        "verdicts": verdicts(results),
        "consistency": consistency,
        "stability": stability,
        "sweep": sweep,
        "edges": edges,
        "chaos": chaos,
        "modulation": summarize_modulation(mod_rows),
        "cost": cost_table(cat),
    }
    (OUT / "results.json").write_text(json.dumps(data, indent=1, allow_nan=True) + "\n")
    plots(data)
    print(json.dumps(data["verdicts"], indent=1))
    print(f"done in {time.perf_counter() - t0:.0f} s → {OUT}")


if __name__ == "__main__":
    main()
