"""Stress and pitch tests of the recommended ranges (fifth-system screening summary).

For each job: ``build_system`` at production resolution (241/129), then the engine's
``Dynamical`` block (system registered in-process only), 8 seeds per case:

- holds at u = 0, u_default, 1 (A3, 8 s);
- full-range sine LFO sweeps: slow (A3, T = 4 s, 24 s), medium (A3, T = 1 s, 12 s),
  fast (A1, T = 0.25 s, 12 s, about 14 cycles per sweep).

Per run: safety resets, the fraction of 0.25 s windows (after the first second) whose RMS is
below 0.1 (40 % of the 0.25 target: "quiet"), the RMS of the last second, and the peak in
units of the target RMS. Pitch: cents at A3 at u_default (6 seeds, 2000 cycles) and at
u = 0, 0.25, 0.5, 0.75, 1 (4 seeds, 1000 cycles), estimator as in ``fifth_system_verify.py``.

Run from ``lab/``::

    NUMBA_CACHE_DIR=<scratch> caffeinate -is uv run python \
        scripts/studies/screening/fifth_system_stress.py [job ...]

Writes ``outputs/studies/screening/fifth_system/stress.json``.
"""

from __future__ import annotations

import json
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fifth_system_verify import OUT, make_system

from chaotic_sound.analysis.catalog_builder import BuildSettings, build_system
from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak

# job -> (dysts class, param, candidate range, phase index, drive param, (sweep, table) points)
JOBS: dict[str, tuple[str, str, tuple[float, float], int | None, str | None, tuple[int, int]]] = {
    "rikitake_a_0.144-4_121": ("RikitakeDynamo", "a", (0.02, 4.0), None, None, (121, 33)),
    "rikitake_a_0.02-4": ("RikitakeDynamo", "a", (0.02, 4.0), None, None, (241, 129)),
    "rikitake_a_0.5-4": ("RikitakeDynamo", "a", (0.5, 4.0), None, None, (241, 129)),
    "rikitake_a_0.75-3": ("RikitakeDynamo", "a", (0.75, 3.0), None, None, (241, 129)),
    "rucklidge_b_4.6-8.5": ("Rucklidge", "b", (4.6, 8.5), None, None, (241, 129)),
    "halvorsen_a": ("Halvorsen", "a", (0.7, 2.1), None, None, (241, 129)),
    "rikitake_mu": ("RikitakeDynamo", "mu", (0.2, 3.0), None, None, (241, 129)),
    "rikitake_mu_0.2-1.8": ("RikitakeDynamo", "mu", (0.2, 1.8), None, None, (241, 129)),
}
SEEDS = tuple(range(1, 9))
FS = 48_000


def run_job(job: str) -> dict[str, Any]:
    from chaotic_sound import systems as reg
    from chaotic_sound.blocks import Dynamical
    from chaotic_sound.catalog import Catalog
    from chaotic_sound.pitch import cents_between

    name, par, cand, phase, drive, (ns, nt) = JOBS[job]
    t0 = time.time()
    system = make_system(name, par, cand, phase, drive)
    build = build_system(system, BuildSettings(sweep_points=ns, table_points=nt))
    e = build.entry
    reg.SYSTEMS[system.name] = system
    cat = Catalog(entries={system.name: e})
    obs = e.period_observable
    prom = e.observables[obs].prominence
    P = e.period_table

    def render(note: str, u: np.ndarray | float | None, seconds: float, seed: int) -> Any:
        b = Dynamical("osc", catalog=cat, system=system.name, note=note, seed=seed, param=None)
        b.reset(FS)
        n = round(seconds * FS)
        if u is None or np.isscalar(u):
            uu = np.full(n, e.u_default if u is None else float(u))  # type: ignore[arg-type]
        else:
            uu = np.asarray(u)
        x = b.process(n, {"param": uu, "amp": None})["out"][:, 0]
        return x, b

    def stats(x: np.ndarray, b: Any) -> dict[str, Any]:
        w = FS // 4
        rms = np.array([np.std(x[k : k + w]) for k in range(FS, len(x) - w + 1, w)])
        return {
            "resets": int(b.resets),
            "quiet_fraction": float(np.mean(rms < 0.1)),
            "min_window_rms": float(rms.min()),
            "last_second_rms": float(np.std(x[-FS:])),
            "peak_over_target": float(np.max(np.abs(x[FS // 2 :])) / 0.25),
        }

    def lfo(seconds: float, period_s: float) -> np.ndarray:
        t = np.arange(round(seconds * FS)) / FS
        return 0.5 - 0.5 * np.cos(2 * np.pi * t / period_s)

    cases = {
        "hold_u0_A3": ("A3", 0.0, 8.0),
        "hold_udef_A3": ("A3", None, 8.0),
        "hold_u1_A3": ("A3", 1.0, 8.0),
        "sweep_T4_A3": ("A3", lfo(24.0, 4.0), 24.0),
        "sweep_T1_A3": ("A3", lfo(12.0, 1.0), 12.0),
        "sweep_T0.25_A1": ("A1", lfo(12.0, 0.25), 12.0),
    }
    stress = {}
    for cname, (note, u, secs) in cases.items():
        stress[cname] = [stats(*render(note, u, secs, s)) for s in SEEDS]

    def pitch(u: float | None, seed: int, cycles: float) -> float:
        b = Dynamical("osc", catalog=cat, system=system.name, note="A3", seed=seed, param=u)
        b.reset(FS)
        n = round((0.5 + cycles / b.frequency_hz) * FS)
        x = b.process(n, {"param": None, "amp": None})["out"][FS // 2 :, 0]
        if e.period_method == "return_time":
            f = 1.0 / mean_return_time(x, 1.0 / FS).mean
        else:
            f = spectral_peak(x, 1.0 / FS, nperseg=2**16, f_min=0.25 * b.frequency_hz)
            f = f.centroid_frequency
        return float(cents_between(f, b.frequency_hz))

    pitch_default = [pitch(None, s, 2000) for s in SEEDS[:6]]
    pitch_across = {str(u): [pitch(u, s, 1000) for s in SEEDS[:4]] for u in (0, 0.25, 0.5, 0.75, 1)}
    b = Dynamical("osc", catalog=cat, system=system.name, note="A3")
    b.reset(FS)
    lam = np.array(e.info["lyapunov_per_period"])
    return {
        "job": job,
        "build_points": [ns, nt],
        "candidate_range": list(cand),
        "p_min": e.p_min,
        "p_max": e.p_max,
        "p_default": e.p_default,
        "u_default": float(e.u_default),
        "rel_width": (e.p_max - e.p_min) / abs(e.p_default),
        "lo_reason": e.info["range_selection"]["lo_reason"],
        "hi_reason": e.info["range_selection"]["hi_reason"],
        "windows": e.info["range_selection"]["accepted_windows"],
        "trims": e.info["range_selection"]["trims"],
        "corrected": e.info["period_corrected_indices"],
        "chaotic_fraction": e.info["chaotic_fraction"],
        "method": e.period_method,
        "observable": obs,
        "prominence_default": float(np.interp(e.u_default, e.u_grid, prom)),
        "prominence_table": [float(prom.min()), float(np.median(prom)), float(prom.max())],
        "lyap_per_period": [float(lam.min()), float(np.median(lam)), float(lam.max())],
        "period_range": [float(P.min()), float(P.max())],
        "max_period_step": e.info["max_relative_period_step"],
        "monotone": bool(np.all(np.diff(P) <= 0) or np.all(np.diff(P) >= 0)),
        "h_max": e.h_max,
        "substeps_A3": [
            b.substeps_per_sample(0.0),
            b.substeps_per_sample(),
            b.substeps_per_sample(1.0),
        ],
        "stress": stress,
        "pitch_default": pitch_default,
        "pitch_across": pitch_across,
        "seconds": time.time() - t0,
    }


def main() -> None:
    t0 = time.time()
    jobs = sys.argv[1:] or list(JOBS)  # optional job names: re-run those, merge into the file
    with get_context("spawn").Pool(len(jobs)) as pool:
        res = pool.map(run_job, jobs)
    path = OUT / "stress.json"
    if sys.argv[1:] and path.exists():
        old = {r["job"]: r for r in json.loads(path.read_text())}
        old.update({r["job"]: r for r in res})
        merged = [old[j] for j in JOBS if j in old]
    else:
        merged = res
    path.write_text(json.dumps(merged, indent=1, default=float))
    for r in res:
        print(
            f"== {r['job']}: [{r['p_min']:.4g}, {r['p_max']:.4g}] udef={r['u_default']:.3f} "
            f"rel={r['rel_width']:.3f} chaos={r['chaotic_fraction']:.3f} win={len(r['windows'])} "
            f"prom def={r['prominence_default']:.3f} table={np.round(r['prominence_table'], 3)} "
            f"λP={np.round(r['lyap_per_period'], 3)} P={np.round(r['period_range'], 3)} "
            f"step={r['max_period_step']:.3f} mono={r['monotone']} trims={r['trims']} "
            f"corr={r['corrected']} substeps={r['substeps_A3']} ({r['seconds']:.0f}s)"
        )
        d = np.array(r["pitch_default"])
        print(
            f"   pitch default [{d.min():+.1f}, {d.max():+.1f}] across",
            {u: [round(v, 1) for v in c] for u, c in r["pitch_across"].items()},
        )
        for c, runs in r["stress"].items():
            print(
                f"   {c:15s} resets={sum(x['resets'] for x in runs)} "
                f"quiet runs={sum(x['quiet_fraction'] > 0 for x in runs)}/8 "
                f"max quiet frac={max(x['quiet_fraction'] for x in runs):.2f} "
                f"min last-s RMS={min(x['last_second_rms'] for x in runs):.3f} "
                f"peak={max(x['peak_over_target'] for x in runs):.2f}"
            )
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
