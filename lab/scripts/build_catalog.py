"""Build ``catalog/systems.json`` and diagnostic plots (ADR 0003, ADR 0010).

Usage (from ``lab/``; takes about a minute)::

    caffeinate -is uv run python scripts/build_catalog.py [--systems lorenz rossler ...]

With ``--systems``, only those entries are rebuilt and merged into the existing catalog.

Writes:

- ``../catalog/systems.json``: the catalog consumed by engines (committed);
- ``outputs/catalog/<system>.png``: sweep diagnostics (Lyapunov exponent, period, levels);
- ``outputs/catalog/summary.md``: a Markdown table of the results, for the docs.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from chaotic_sound.analysis.catalog_builder import SystemBuild, build_catalog, point_period
from chaotic_sound.catalog import Catalog, default_catalog_path
from chaotic_sound.integrate import trajectory
from chaotic_sound.systems import get_system, list_systems

LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "outputs" / "catalog"


def plot_build(build: SystemBuild, path: Path) -> None:
    """Four-panel diagnostic figure for one system."""
    system, entry, ref = build.system, build.entry, build.reference
    vals = np.array([r.value for r in build.sweep_results])
    lam = np.array([r.lyapunov * ref.period if r.bounded else np.nan for r in build.sweep_results])
    obs = build.period_observable
    drive = system.drive_period()

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(
        f"{system.display_name}: {system.modulated_param} ∈ [{entry.p_min:.4g}, {entry.p_max:.4g}]"
        f"  (default {entry.p_default:g}, tuning on {obs} by {build.period_method})"
    )
    for ax in axes.flat[:3]:
        ax.axvspan(entry.p_min, entry.p_max, color="tab:green", alpha=0.12, label="chosen range")
        ax.axvline(entry.p_default, color="k", lw=0.8, ls="--", label="dysts default")
        for w in build.selection.windows:
            ax.axvspan(w[0] - 1e-9, w[1] + 1e-9, color="tab:red", alpha=0.25)
        ax.set_xlabel(system.modulated_param)

    ax = axes[0, 0]
    ax.plot(vals, lam, ".-", ms=3, lw=0.6)
    unb = [r.value for r in build.sweep_results if not r.bounded]
    if unb:
        ax.plot(unb, np.zeros(len(unb)), "rx", label="unbounded")
    ax.axhline(0.05, color="tab:red", lw=0.6, ls=":", label="chaos threshold")
    ax.set_ylabel("λ_max · P_ref  (nats per period)")
    ax.set_title("Largest Lyapunov exponent (sweep, with continuation)")
    ax.legend(fontsize=7)

    ax = axes[0, 1]
    if build.period_method != "drive":
        peak = [
            r.variables[obs].centroid_period if r.bounded else np.nan for r in build.sweep_results
        ]
        ret = [r.variables[obs].return_time if r.bounded else np.nan for r in build.sweep_results]
        ax.plot(vals, peak, ".", ms=3, label=f"peak centroid of {obs} (sweep)")
        ax.plot(vals, ret, ".", ms=3, label=f"return time of {obs} (sweep)")
    p_grid = entry.param_value(entry.u_grid)
    ax.plot(p_grid, entry.period_table, "k-", lw=1.5, label="catalog P(u)")
    measured = np.array(entry.info["period_measured"])
    fixed = entry.info["period_corrected_indices"]
    if fixed:
        ax.plot(p_grid[fixed], measured[fixed], "rx", label="outliers replaced")
    if drive is not None:
        ax.axhline(drive, color="tab:purple", lw=0.8, label="drive period 2π/ω")
    lo, hi = np.nanmin(entry.period_table), np.nanmax(entry.period_table)
    ax.set_ylim(lo * 0.7, hi * 1.4)
    ax.set_ylabel("characteristic period P (system time)")
    ax.set_title("Tuning curve")
    ax.legend(fontsize=7)

    ax = axes[1, 0]
    for var, table in entry.observables.items():
        ax.plot(p_grid, table.std / table.std[0], "-", label=f"σ_{var}(u)/σ_{var}(0)")
        ax.plot(p_grid, table.prominence, ":", label=f"prominence {var}")
    ax.set_title("Loudness normalization and pitch clarity (tables)")
    ax.legend(fontsize=7)

    ax = axes[1, 1]
    dt = ref.period / 64
    _, x = trajectory(system, dt=dt, n_samples=64 * 20, h_max=entry.h_max)
    traj, _ = trajectory(system, x0=x, dt=dt, n_samples=64 * 150, h_max=entry.h_max)
    audio = list(system.audio_variables)
    i, j = system.variable_index(audio[0]), system.variable_index(audio[-1])
    if system.name == "lorenz":
        i, j = 0, 2
    ax.plot(traj[:, i], traj[:, j], lw=0.3)
    ax.set_xlabel(system.variables[i])
    ax.set_ylabel(system.variables[j])
    ax.set_title("Attractor at the default parameter")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def summary_table(builds: dict[str, SystemBuild]) -> str:
    """Markdown summary of the build (pasted into docs/math/tuning.md)."""
    rows = [
        "| System | Param | Range | u(default) | Tuning on | Method | P(u) range | "
        "Chaotic | Windows | Sub-steps @A4 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for b in builds.values():
        e = b.entry
        substeps = math.ceil(float(np.max(e.period_table)) * 440.0 / 48_000.0 / e.h_max)
        rows.append(
            f"| {b.system.display_name} | {e.param} | [{e.p_min:.4g}, {e.p_max:.4g}] | "
            f"{e.u_default:.3f} | {b.period_observable} | {b.period_method} | "
            f"{e.period_table.min():.4g}–{e.period_table.max():.4g} | "
            f"{100 * e.info['chaotic_fraction']:.0f}% | {len(b.selection.windows)} | {substeps} |"
        )
    rows.append("")
    for b in builds.values():
        sel = b.entry.info["range_selection"]
        rows.append(
            f"- **{b.system.display_name}**: low end: {sel['lo_reason']}; "
            f"high end: {sel['hi_reason']}."
            + (f" Trims: {'; '.join(sel['trims'])}." if sel["trims"] else "")
        )
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--systems", nargs="*", default=list_systems())
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--output", type=Path, default=default_catalog_path())
    args = parser.parse_args()

    start = time.time()
    systems = [get_system(n) for n in args.systems]
    catalog, builds = build_catalog(systems, progress=print)
    if set(args.systems) != set(list_systems()) and args.output.exists():
        # Partial build: keep the other systems' entries from the existing catalog.
        old = Catalog.load(args.output)
        merged = {**old.entries, **catalog.entries}
        catalog = Catalog(entries={k: merged[k] for k in list_systems() if k in merged},
                          metadata=catalog.metadata)  # fmt: skip
        print(f"merged {sorted(builds)} into the existing catalog")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    catalog.save(args.output)
    print(f"wrote {args.output}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.md").write_text(summary_table(builds))
    if not args.no_plots:
        for name, build in builds.items():
            plot_build(build, OUT / f"{name}.png")
        print(f"plots in {OUT}")
    # Sanity: the period function used by the builder is importable for notebooks.
    assert callable(point_period)
    print(f"done in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
