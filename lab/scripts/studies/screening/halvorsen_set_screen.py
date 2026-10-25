"""Screening set "Halvorsen": full catalog pipeline + tuning test for each candidate.

Candidates: Halvorsen, Aizawa, Dadras, SprottB, SprottD, ShimizuMorioka, Lorenz84, BurkeShaw
(dysts flows). The modulated parameter of each comes from ``halvorsen_set_explore.py``
(coarse sweeps of every plausible parameter); a few systems get two parameters.

Per candidate:

1. Our RHS vs dysts at 50 random points.
2. ``build_system`` with ``BuildSettings(sweep_points=121, table_points=33)``: P_ref, tuning
   observable and period method, chaotic range [p_min, p_max], P(u), μ(u), σ(u).
3. Tuning test with the engine's ``Dynamical`` block (system registered in-process only):
   A3, ≥ 2000 cycles, pitch measured as in ``tests/test_dynamical.py``; 4 seeds at the
   default and 2 seeds at u = 0.1, 0.5, 0.9 (pitch lock on).
4. A figure: λ·P_ref and prominence along the sweep, with the selected range, and P(u).

Run from lab/:  caffeinate -is uv run python scripts/studies/screening/halvorsen_set_screen.py
Writes lab/outputs/studies/screening/halvorsen_set/{results.json, <name>.png, overview.png}
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
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from halvorsen_set_adapter import (
    make_system,
    register,
    use_uncached_kernels,
    verify_rhs,
)

from chaotic_sound.analysis.catalog_builder import BuildSettings, build_system
from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import Catalog
from chaotic_sound.pitch import cents_between

OUT = Path(__file__).parents[3] / "outputs" / "studies" / "screening" / "halvorsen_set"
FS = 48_000
SETTINGS = BuildSettings(sweep_points=121, table_points=33)
COLORS = {"x": "#2a78d6", "y": "#eb6834", "z": "#1baf7a"}  # categorical slots 1-3

# name, dysts class, modulated parameter, candidate range, custom kernel key
CONFIGS: list[tuple[str, str, str, tuple[float, float], str | None]] = [
    ("halvorsen_a", "Halvorsen", "a", (0.7, 2.1), None),
    ("halvorsen_b", "Halvorsen", "b", (2.0, 6.0), None),
    ("aizawa_e", "Aizawa", "e", (0.05, 0.45), None),
    ("dadras_o", "Dadras", "o", (1.35, 4.05), None),
    ("sprottb_c", "SprottB", "c", (0.5, 1.5), "sprottb_c"),
    ("sprottd_a", "SprottD", "a", (1.5, 4.5), "sprottd"),
    ("shimizu_a", "ShimizuMorioka", "a", (0.425, 1.275), None),
    ("shimizu_b", "ShimizuMorioka", "b", (0.1, 0.75), None),
    ("lorenz84_f", "Lorenz84", "f", (2.415, 7.245), None),
    ("burkeshaw_e", "BurkeShaw", "e", (6.5, 19.5), None),
]


def run_block(block: Dynamical, seconds: float, chunk: int = 4096) -> np.ndarray:
    block.reset(FS)
    n = round(seconds * FS)
    out = np.empty(n)
    pos = 0
    while pos < n:
        m = min(chunk, n - pos)
        out[pos : pos + m] = block.process(m, {})["out"][:, 0]
        pos += m
    return out


def measured_frequency(block: Dynamical, x: np.ndarray) -> float:
    """Measure the pitch like tests/test_dynamical.py::measured_frequency."""
    if block.entry.period_method == "return_time":
        return 1.0 / mean_return_time(x, 1.0 / FS).mean
    peak = spectral_peak(x, 1.0 / FS, nperseg=2**16, f_min=0.25 * block.frequency_hz)
    return peak.centroid_frequency


def tuning_test(name: str, catalog: Catalog) -> dict:
    entry = catalog[name]
    cases = [(None, s) for s in (0, 1, 2, 3)] + [(u, s) for u in (0.1, 0.5, 0.9) for s in (0, 1)]
    rows = []
    for u, seed in cases:
        block = Dynamical("osc", catalog=catalog, system=name, note="A3", param=u, seed=seed)
        seconds = 0.5 + 2000 / block.frequency_hz
        t0 = time.time()
        x = run_block(block, seconds)[FS // 2 :]
        elapsed = time.time() - t0
        cents = cents_between(measured_frequency(block, x), block.frequency_hz)
        rows.append(
            {
                "u": entry.u_default if u is None else u,
                "seed": seed,
                "cents": float(cents),
                "resets": int(block.resets),
                "rms": float(np.std(x)),
                "peak": float(np.max(np.abs(x))),
                "realtime_factor": seconds / elapsed,
                "substeps": int(block.substeps_per_sample()),
            }
        )
    default = [r["cents"] for r in rows[:4]]
    across = [r["cents"] for r in rows]
    return {
        "rows": rows,
        "default_cents_min": min(default),
        "default_cents_max": max(default),
        "all_cents_min": min(across),
        "all_cents_max": max(across),
        "total_resets": sum(r["resets"] for r in rows),
        "realtime_factor_median": float(np.median([r["realtime_factor"] for r in rows])),
        "substeps_a3": rows[0]["substeps"],
    }


def plot_build(name: str, build, path: Path) -> None:  # type: ignore[no-untyped-def]
    system, entry, sel = build.system, build.entry, build.selection
    ref = build.reference.period
    res = build.sweep_results
    vals = np.array([r.value for r in res])
    lam = np.array([r.lyapunov * ref if r.bounded else np.nan for r in res])
    fig, axes = plt.subplots(3, 1, figsize=(7.5, 8.0), constrained_layout=True)
    axes[1].sharex(axes[0])
    ax = axes[0]
    ax.axvspan(sel.lo, sel.hi, color="#2a78d6", alpha=0.10, lw=0)
    ax.plot(vals, lam, color="#0b0b0b", lw=1.2)
    unb = vals[[not r.bounded for r in res]]
    if unb.size:
        ax.plot(unb, np.zeros_like(unb), "x", color="#e34948", ms=5, label="unbounded")
        ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.axhline(SETTINGS.lyapunov_threshold, color="#52514e", lw=0.8, ls="--")
    ax.axvline(system.default_value, color="#52514e", lw=0.8, ls=":")
    ax.set_ylabel("λ·P_ref (nats)")
    ax.set_title(
        f"{system.display_name}: sweep of {system.modulated_param} "
        f"(shaded: selected range [{sel.lo:.4g}, {sel.hi:.4g}])",
        fontsize=10,
    )
    ax = axes[1]
    for var in system.audio_variables:
        prom = [r.variables[var].prominence if r.bounded else np.nan for r in res]
        ax.plot(vals, prom, color=COLORS[var], lw=1.2, label=var)
    ax.axvspan(sel.lo, sel.hi, color="#2a78d6", alpha=0.10, lw=0)
    ax.axhline(0.3, color="#52514e", lw=0.8, ls="--")
    ax.set_ylabel("spectral prominence")
    ax.set_xlabel(system.modulated_param)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper right")
    ax = axes[2]
    p_grid = entry.p_min + entry.u_grid * (entry.p_max - entry.p_min)
    measured = np.array(entry.info["period_measured"])
    ax.plot(p_grid, measured, "o", color="#52514e", ms=3, label="measured")
    ax.plot(p_grid, entry.period_table, color="#2a78d6", lw=1.5, label="P(u) table")
    ax.set_xlabel(f"{system.modulated_param} (selected range)")
    ax.set_ylabel(f"P ({entry.period_method} on {entry.period_observable})")
    ax.legend(frameon=False, fontsize=8)
    for a in axes:
        a.grid(True, color="#e6e5e0", lw=0.6)
        a.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def summarize(name: str, build, rhs_err: float) -> dict:  # type: ignore[no-untyped-def]
    system, entry, sel = build.system, build.entry, build.selection
    d = system.default_value
    dp = build.default_point
    obs = entry.period_observable
    prom_table = entry.observables[obs].prominence
    p_def = float(entry.period(entry.u_default))
    res = build.sweep_results
    unb = [r.value for r in res if not r.bounded]
    nearest_escape = min((abs(v - d) for v in unb), default=math.inf)
    steps = entry.info["max_relative_period_step"]
    return {
        "name": name,
        "display_name": system.display_name,
        "param": system.modulated_param,
        "default": d,
        "candidate_range": list(system.candidate_range),
        "rhs_err": rhs_err,
        "P_ref": build.reference.period,
        "observable": obs,
        "period_method": entry.period_method,
        "prominence_default": {v: s.prominence for v, s in dp.variables.items()},
        "prominence_obs_table_min": float(prom_table.min()),
        "prominence_obs_table_median": float(np.median(prom_table)),
        "lyap_default": dp.lyapunov,
        "lyap_P_ref_default": dp.lyapunov * build.reference.period,
        "lyap_P_tune_default": dp.lyapunov * p_def,
        "p_min": entry.p_min,
        "p_max": entry.p_max,
        "rel_width": (entry.p_max - entry.p_min) / d,
        "u_default": entry.u_default,
        "lo_reason": sel.lo_reason,
        "hi_reason": sel.hi_reason,
        "windows": [list(w) for w in sel.windows],
        "trims": entry.info["range_selection"]["trims"],
        "chaotic_fraction": entry.info["chaotic_fraction"],
        "P_default": p_def,
        "P_min": float(entry.period_table.min()),
        "P_max": float(entry.period_table.max()),
        "P_span_cents": float(
            1200 * math.log2(entry.period_table.max() / entry.period_table.min())
        ),
        "max_period_step": steps,
        "period_corrected_indices": entry.info["period_corrected_indices"],
        "unbounded_in_sweep": len(unb),
        "unbounded_values_minmax": [min(unb), max(unb)] if unb else None,
        "nearest_escape_from_default": nearest_escape,
        "h_max": entry.h_max,
    }


LABEL_OFFSETS = {  # (dx, dy) in points, to keep labels apart
    "halvorsen_a": (6, 4),
    "halvorsen_b": (-62, 4),
    "sprottb_c": (6, -11),
    "burkeshaw_e": (-30, 7),
    "chua": (6, -12),
}


def overview(results: list[dict], path: Path) -> None:
    from chaotic_sound.catalog import load_default_catalog

    fig, ax = plt.subplots(figsize=(7.0, 4.6), constrained_layout=True)
    for r in (r for r in results if "error" not in r):
        x = r["rel_width"]
        y = r["prominence_default"][r["observable"]]
        ax.plot(x, y, "o", color="#2a78d6", ms=8, mec="#fcfcfb", mew=1.5)
        ax.annotate(r["name"], (x, y), xytext=LABEL_OFFSETS.get(r["name"], (6, 4)),
                    textcoords="offset points", fontsize=8)  # fmt: skip
    for k, e in load_default_catalog().entries.items():
        x = (e.p_max - e.p_min) / e.p_default
        y = float(np.interp(e.u_default, e.u_grid, e.observables[e.period_observable].prominence))
        ax.plot(x, y, "s", color="#52514e", ms=6, mfc="none")
        ax.annotate(k, (x, y), xytext=LABEL_OFFSETS.get(k, (6, -11)), textcoords="offset points",
                    fontsize=8, color="#52514e")  # fmt: skip
    ax.axhline(0.3, color="#52514e", lw=0.8, ls="--")
    ax.set_xscale("log")
    ax.set_xlabel("relative width of the chaotic range, (p_max − p_min)/p_default")
    ax.set_ylabel("prominence of the tuning variable at default")
    ax.set_title("Pitch vs. usable range (dots: candidates; squares: current catalog)", fontsize=10)
    ax.grid(True, color="#e6e5e0", lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    if sys.argv[1:] == ["--overview"]:  # redraw the overview from results.json
        overview(json.loads((OUT / "results.json").read_text()), OUT / "overview.png")
        return
    use_uncached_kernels()
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    results_name = "results_partial.json" if only else "results.json"  # keep the full set
    results = []
    entries = {}
    t_all = time.time()
    for name, dysts_name, param, cand, custom in CONFIGS:
        if only and name not in only:
            continue
        t0 = time.time()
        system = make_system(dysts_name, param, cand, name=name, custom=custom)
        err = verify_rhs(system)
        try:
            build = build_system(system, SETTINGS, progress=print)
        except Exception as exc:
            traceback.print_exc(limit=1)
            results.append({"name": name, "display_name": dysts_name, "param": param,
                            "error": f"{type(exc).__name__}: {exc}"})  # fmt: skip
            continue
        row = summarize(name, build, err)
        entries[name] = build.entry
        t_build = time.time() - t0
        register(system)
        row["tuning"] = tuning_test(name, Catalog(entries={name: build.entry}))
        row["seconds_build"] = t_build
        row["seconds_total"] = time.time() - t0
        plot_build(name, build, OUT / f"{name}.png")
        results.append(row)
        tt = row["tuning"]
        print(
            f"== {name}: range [{row['p_min']:.4g}, {row['p_max']:.4g}] rel={row['rel_width']:.3f} "
            f"chaotic={row['chaotic_fraction']:.2f} obs={row['observable']} "
            f"prom={row['prominence_default'][row['observable']]:.2f} "
            f"step={row['max_period_step']:.3f} cents default "
            f"[{tt['default_cents_min']:+.1f}, {tt['default_cents_max']:+.1f}] all "
            f"[{tt['all_cents_min']:+.1f}, {tt['all_cents_max']:+.1f}] resets={tt['total_resets']} "
            f"({row['seconds_total']:.0f}s)",
            flush=True,
        )
        (OUT / results_name).write_text(json.dumps(results, indent=1, default=float))
    (OUT / results_name).write_text(json.dumps(results, indent=1, default=float))
    if not only:
        overview(results, OUT / "overview.png")
        Catalog(entries=entries, metadata={"study": "screening halvorsen_set"}).save(
            OUT / "catalog_screening.json"
        )
    print(f"total {time.time() - t_all:.0f}s")


if __name__ == "__main__":
    main()
