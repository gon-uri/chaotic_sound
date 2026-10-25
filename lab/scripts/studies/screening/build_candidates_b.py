"""Screening batch B, step 4: full catalog build + engine pitch check for one candidate.

Usage (from ``lab/``; one job per process so jobs can run in parallel)::

    NUMBA_CACHE_DIR=<scratch>/<job> uv run python scripts/studies/screening/build_candidates_b.py JOB

``JOB`` is a key of :data:`JOBS`. Runs ``build_system`` with
``BuildSettings(sweep_points=121, table_points=33)``, then renders the system with the engine's
``Dynamical`` block (registered in-process only) at A3 for 4 s, for 6 seeds at three knob
positions, and measures the pitch of the audio with the catalog's period method.

Writes ``outputs/studies/screening/batch_b/builds/JOB.json`` and ``JOB.png``.
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LAB / "scripts"))

from dysts_adapter_b import make_system, register  # noqa: E402

from chaotic_sound.analysis.catalog_builder import BuildSettings, build_system  # noqa: E402
from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak  # noqa: E402
from chaotic_sound.blocks import Dynamical  # noqa: E402
from chaotic_sound.catalog import Catalog  # noqa: E402
from chaotic_sound.pitch import cents_between, note_to_hz  # noqa: E402

OUT = LAB / "outputs" / "studies" / "screening" / "batch_b" / "builds"

# job -> (dysts name, modulated parameter, candidate range, phase index, drive parameter)
JOBS: dict[str, tuple[str, str, tuple[float, float], int | None, str | None]] = {
    "chenlee_c": ("ChenLee", "c", (-0.8, -0.05), None, None),
    "chenlee_b": ("ChenLee", "b", (-15.0, -5.0), None, None),
    "forcedbrusselator_f": ("ForcedBrusselator", "f", (0.02, 0.15), 2, "w"),
    "hastingspowell_b1": ("HastingsPowell", "b1", (2.0, 6.2), None, None),
    "hastingspowell_a2": ("HastingsPowell", "a2", (0.05, 0.2), None, None),
    "hadley_g": ("Hadley", "g", (0.5, 1.5), None, None),
    "bouali_y0": ("Bouali", "y0", (2.5, 5.5), None, None),
    "rabinovichfabrikant_g": ("RabinovichFabrikant", "g", (0.7, 1.05), None, None),
    "hindmarshrose_c": ("HindmarshRose", "c", (0.0, 0.065), None, None),
}
SETTINGS = BuildSettings(sweep_points=121, table_points=33)
SEEDS = range(6)
FS = 48_000
NOTE = "A3"
SECONDS = 4.0


def measure_pitch(audio: np.ndarray, method: str, f0: float) -> dict[str, float]:
    """Frequency of the audio (Hz) by spectral-peak centroid and by mean return time."""
    dt = 1.0 / FS
    nperseg = int(round(128 * FS / f0))  # 128 note periods, as the analysis does
    peak = spectral_peak(audio, dt, nperseg=min(nperseg, audio.size // 2), f_min=0.25 * f0)
    ret = mean_return_time(audio, dt)
    return {
        "centroid_hz": peak.centroid_frequency,
        "peak_hz": peak.frequency,
        "prominence": peak.prominence,
        "return_hz": 1.0 / ret.mean if ret.mean > 0 else math.nan,
    }


def pitch_check(system_name: str, catalog: Catalog, method: str) -> dict[str, object]:
    f0 = note_to_hz(NOTE)
    entry = catalog[system_name]
    out: dict[str, object] = {}
    n = int(SECONDS * FS)
    for label, u in (("u0.1", 0.1), ("u_default", float(entry.u_default)), ("u0.9", 0.9)):
        cents_c, cents_r, proms, resets = [], [], [], []
        for seed in SEEDS:
            b = Dynamical("osc", catalog=catalog, system=system_name, note=NOTE, param=u, seed=seed)
            b.reset(FS)
            audio = np.asarray(b.process(n, {"param": None, "amp": None})["out"])
            if audio.ndim == 2:
                audio = audio[:, 0]
            audio = audio[int(0.25 * FS) :]  # skip the fade-in and DC-blocker settling
            m = measure_pitch(audio, method, f0)
            cents_c.append(cents_between(m["centroid_hz"], f0))
            cents_r.append(cents_between(m["return_hz"], f0))
            proms.append(m["prominence"])
            resets.append(b.resets)
        out[label] = {
            "u": u,
            "cents_centroid": cents_c,
            "cents_return": cents_r,
            "prominence": proms,
            "resets": resets,
            "substeps": int(b.substeps_per_sample()),
        }
    return out


def run(job: str) -> dict[str, object]:
    name, par, rng, phase, drive = JOBS[job]
    system = make_system(name, par, rng, phase_index=phase, drive_param=drive, name=job)
    t0 = time.time()
    row: dict[str, object] = {"job": job, "system": name, "param": par, "candidate_range": rng}
    try:
        build = build_system(system, SETTINGS, progress=print)
    except Exception as e:  # noqa: BLE001
        row.update(ok=False, error=f"{type(e).__name__}: {e}", seconds=time.time() - t0)
        traceback.print_exc()
        return row
    e = build.entry
    obs = build.period_observable
    prom_tab = {v: np.asarray(t.prominence) for v, t in e.observables.items()}
    best_var = max(prom_tab, key=lambda v: float(np.median(prom_tab[v])))
    lam_default = build.default_point.lyapunov * build.reference.period
    p_tab = np.asarray(e.period_table)
    row.update(
        ok=True,
        p_min=e.p_min,
        p_max=e.p_max,
        p_default=e.p_default,
        u_default=float(e.u_default),
        rel_width=(e.p_max - e.p_min) / abs(e.p_default),
        lo_reason=build.selection.lo_reason,
        hi_reason=build.selection.hi_reason,
        windows=[list(w) for w in build.selection.windows],
        trims=e.info["range_selection"]["trims"],
        chaotic_fraction=e.info["chaotic_fraction"],
        max_period_step=e.info["max_relative_period_step"],
        period_range=[float(p_tab.min()), float(p_tab.max())],
        period_method=build.period_method,
        period_observable=obs,
        reference_period=build.reference.period,
        lyapunov_per_period_default=lam_default,
        prominence_default={v: s.prominence for v, s in build.default_point.variables.items()},
        prominence_table_median={v: float(np.median(p)) for v, p in prom_tab.items()},
        prominence_table_min={v: float(np.min(p)) for v, p in prom_tab.items()},
        best_variable=best_var,
        corrected_points=e.info["period_corrected_indices"],
        h_max=e.h_max,
    )
    if drive is not None:
        # Ratio of the observable's spectral-peak period to the drive period over the table.
        ratios = [
            r.variables[obs].centroid_period
            / system.drive_period(system.params_array(**{par: r.value}))
            for r in build.table_results
        ]
        row["observable_period_over_drive"] = [float(np.min(ratios)), float(np.max(ratios))]
    try:
        from build_catalog import plot_build

        plot_build(build, OUT / f"{job}.png")
    except Exception as exc:  # noqa: BLE001
        row["plot_error"] = str(exc)
    register(system)
    catalog = Catalog(entries={job: e})
    row["pitch"] = pitch_check(job, catalog, build.period_method)
    row["seconds"] = time.time() - t0
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    job = sys.argv[1]
    row = run(job)
    (OUT / f"{job}.json").write_text(json.dumps(row, indent=1, default=float))
    print(json.dumps({k: v for k, v in row.items() if k != "pitch"}, default=float))
    if "pitch" in row:
        for label, d in row["pitch"].items():  # type: ignore[union-attr]
            c = np.array(d["cents_centroid"])
            r = np.array(d["cents_return"])
            print(
                f"  {label} (u={d['u']:.3f}, substeps {d['substeps']}): centroid {c.min():+.1f}…{c.max():+.1f} c, "
                f"return {r.min():+.1f}…{r.max():+.1f} c, prom {np.mean(d['prominence']):.2f}, resets {sum(d['resets'])}"
            )


if __name__ == "__main__":
    main()
