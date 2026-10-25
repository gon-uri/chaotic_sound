"""How fast can the knob move before a voice goes quiet? (fifth-system screening summary)

``fifth_system_stress.py`` found that the Rikitake dynamo, swept over its whole range in about
14 cycles (A1, T = 0.25 s), can be left near one of its equilibria. These are linear centres for
every a and μ (characteristic polynomial (λ + 2μ)(λ² + k² + k⁻²), with k² the root of
μk⁴ − a k² − μ = 0), so a trajectory left close to one spirals out only very slowly and the
voice stays quiet for a long time. This script measures the effect against the sweep rate,
for full-range sine LFOs (N system cycles per LFO period) and for square / ramp LFOs (jumps
between u = 0 and 1, smoothed by the block's 5 ms declick), with the leaders for comparison.

A run is "quiet" in a 0.25 s window if the window RMS is below 0.1 (40 % of the target 0.25).
8 seeds per case, at A1 (N cycles per LFO period = N / 55 Hz).

Run from ``lab/``::

    NUMBA_CACHE_DIR=<scratch> caffeinate -is uv run python \
        scripts/studies/screening/fifth_system_rate.py [candidates [job ...]|catalog]

Writes ``outputs/studies/screening/fifth_system/rate.json`` (candidates) or
``rate_catalog.json`` (the same cases for the five systems of the shipped catalog).
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

JOBS: dict[str, tuple[str, str, tuple[float, float]]] = {
    "rikitake_a_0.5-4": ("RikitakeDynamo", "a", (0.5, 4.0)),
    "rikitake_a_0.75-3": ("RikitakeDynamo", "a", (0.75, 3.0)),
    "rikitake_mu_0.5-2.1": ("RikitakeDynamo", "mu", (0.2, 3.0)),
    "rikitake_mu_0.5-1.8": ("RikitakeDynamo", "mu", (0.2, 1.8)),
    "rucklidge_b_4.6-8.5": ("Rucklidge", "b", (4.6, 8.5)),
    "halvorsen_a": ("Halvorsen", "a", (0.7, 2.1)),
}
CATALOG = ("lorenz", "rossler", "chua", "duffing", "thomas")
CYCLES = (7, 14, 28, 55, 110, 220)
SEEDS = tuple(range(1, 9))
FS = 48_000
F_A1 = 55.0


def shape(kind: str, t: np.ndarray, period_s: float) -> np.ndarray:
    ph = np.mod(t / period_s, 1.0)
    if kind == "sine":
        return 0.5 - 0.5 * np.cos(2 * np.pi * ph)
    if kind == "square":
        return (ph >= 0.5).astype(float)
    if kind == "ramp":
        return ph
    raise ValueError(kind)


def run_job(job: str) -> dict[str, Any]:
    from chaotic_sound import systems as reg
    from chaotic_sound.blocks import Dynamical
    from chaotic_sound.catalog import Catalog

    t0 = time.time()
    if job.startswith("catalog:"):  # baseline: a system of the shipped catalog
        from chaotic_sound.catalog import load_default_catalog

        cat = load_default_catalog()
        sys_name = job.split(":", 1)[1]
        e = cat[sys_name]
    else:
        name, par, cand = JOBS[job]
        system = make_system(name, par, cand)
        build = build_system(system, BuildSettings(sweep_points=241, table_points=129))
        e = build.entry
        reg.SYSTEMS[system.name] = system
        sys_name = system.name
        cat = Catalog(entries={sys_name: e})
    out: dict[str, Any] = {
        "job": job,
        "p_min": e.p_min,
        "p_max": e.p_max,
        "u_default": float(e.u_default),
        "cases": {},
    }
    for kind in ("sine", "square", "ramp"):
        for n_cyc in CYCLES:
            period_s = n_cyc / F_A1
            seconds = max(12.0, 3 * period_s)
            t = np.arange(round(seconds * FS)) / FS
            u = shape(kind, t, period_s)
            runs = []
            for s in SEEDS:
                b = Dynamical("osc", catalog=cat, system=sys_name, note="A1", seed=s)
                b.reset(FS)
                x = b.process(len(t), {"param": u, "amp": None})["out"][:, 0]
                w = FS // 4
                rms = np.array([np.std(x[k : k + w]) for k in range(FS, len(x) - w + 1, w)])
                runs.append(
                    {
                        "resets": int(b.resets),
                        "quiet_fraction": float(np.mean(rms < 0.1)),
                        "last_second_rms": float(np.std(x[-FS:])),
                        "peak_over_target": float(np.max(np.abs(x[FS // 2 :])) / 0.25),
                    }
                )
            out["cases"][f"{kind}_{n_cyc}"] = runs
    out["seconds"] = time.time() - t0
    return out


def main() -> None:
    t0 = time.time()
    stage = sys.argv[1] if len(sys.argv) > 1 else "candidates"
    if stage == "candidates":
        jobs = sys.argv[2:] or list(JOBS)
    else:
        jobs = [f"catalog:{n}" for n in CATALOG]
    with get_context("spawn").Pool(len(jobs)) as pool:
        res = pool.map(run_job, jobs)
    path = OUT / ("rate.json" if stage == "candidates" else "rate_catalog.json")
    if stage == "candidates" and sys.argv[2:] and path.exists():  # merge re-run jobs
        old = {r["job"]: r for r in json.loads(path.read_text())}
        old.update({r["job"]: r for r in res})
        res_all = [old[j] for j in JOBS if j in old]
    else:
        res_all = res
    path.write_text(json.dumps(res_all, indent=1, default=float))
    for r in res:
        print(f"== {r['job']} [{r['p_min']:.4g}, {r['p_max']:.4g}] ({r['seconds']:.0f}s)")
        for c, runs in r["cases"].items():
            q = [x["quiet_fraction"] for x in runs]
            print(
                f"   {c:11s} quiet runs {sum(v > 0 for v in q)}/8, mean quiet frac "
                f"{np.mean(q):.3f}, max {max(q):.2f}, min last-s RMS "
                f"{min(x['last_second_rms'] for x in runs):.3f}, resets "
                f"{sum(x['resets'] for x in runs)}, peak {max(x['peak_over_target'] for x in runs):.2f}"
            )
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
