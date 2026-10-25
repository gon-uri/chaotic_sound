"""Fifth-system screening summary: independent re-run of the leading candidates.

Re-measures, with the project's own tools, the numbers that decide the ranking in
``docs/studies/fifth-system-screening.md``:

1. wrapper vs ``model.rhs`` at random points;
2. ``build_system`` (121/33 like the screeners; 241/129 production for the top choice):
   range, chaotic fraction, windows, P(u) span and largest step, prominence on the table;
3. an independent multi-initial-condition check at 9 knob positions u = 0…1 (+ u_default):
   8 random ICs each, 2000 P_ref records → bounded?, spread of the spectral-centroid period
   between ICs, agreement with the catalog P(u), prominence;
4. engine check through the real ``Dynamical`` block at A3 (system registered in-process only):
   pitch error in cents at u_default (4 seeds) and at u = 0, 0.25, 0.5, 0.75, 1 (2 seeds), and
   resets / peak level under a slow full-range LFO (A3, T = 4 s, 24 s) and a fast one
   (A1, T = 0.25 s, 8 s).

Run from ``lab/`` (about 2 min with 7 processes)::

    NUMBA_CACHE_DIR=<scratch> caffeinate -is uv run python \
        scripts/studies/screening/fifth_system_verify.py [run [job ...]|plot|catalog]

Writes ``outputs/studies/screening/fifth_system/{verify.json, build_<job>.png, overview.png}``.
Nothing under ``src/`` or ``catalog/`` is touched.
"""

from __future__ import annotations

import inspect
import json
import math
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numba
import numpy as np

LAB = Path(__file__).resolve().parents[3]
OUT = LAB / "outputs" / "studies" / "screening" / "fifth_system"
sys.path.insert(0, str(LAB / "scripts"))

from chaotic_sound.analysis.catalog_builder import BuildSettings, build_system  # noqa: E402
from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak  # noqa: E402
from chaotic_sound.integrate import trajectory  # noqa: E402
from chaotic_sound.systems.base import SystemDef  # noqa: E402

# job -> (dysts class, modulated parameter, candidate range, phase index, drive param, build pts)
JOBS: dict[str, tuple[str, str, tuple[float, float], int | None, str | None, tuple[int, int]]] = {
    "rikitake_a": ("RikitakeDynamo", "a", (0.02, 4.0), None, None, (121, 33)),
    "rikitake_a_prod": ("RikitakeDynamo", "a", (0.02, 4.0), None, None, (241, 129)),
    "rikitake_a_wide": ("RikitakeDynamo", "a", (0.02, 10.0), None, None, (121, 33)),
    "rucklidge_b": ("Rucklidge", "b", (3.35, 10.05), None, None, (121, 33)),
    "moorespiegel_a": ("MooreSpiegel", "a", (5.0, 25.0), None, None, (121, 33)),
    "halvorsen_a": ("Halvorsen", "a", (0.7, 2.1), None, None, (121, 33)),
    "rikitake_mu": ("RikitakeDynamo", "mu", (0.2, 3.0), None, None, (121, 33)),
    "rikitake_mu_prod": ("RikitakeDynamo", "mu", (0.2, 3.0), None, None, (241, 129)),
    # Recommended configurations, production resolution:
    "rikitake_mu_rec": ("RikitakeDynamo", "mu", (0.2, 1.8), None, None, (241, 129)),
    "rucklidge_b_rec": ("Rucklidge", "b", (4.6, 8.5), None, None, (241, 129)),
    "halvorsen_a_prod": ("Halvorsen", "a", (0.7, 2.1), None, None, (241, 129)),
    "forcedbrusselator_f": ("ForcedBrusselator", "f", (0.02, 0.15), 2, "w", (121, 33)),
}
CHECK_U = (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0)
N_IC = 8
ENGINE_U = (0.0, 0.25, 0.5, 0.75, 1.0)


# ---------------------------------------------------------------------------------------
# Wrapper
# ---------------------------------------------------------------------------------------


def make_system(
    dysts_name: str,
    modulated: str,
    candidate_range: tuple[float, float],
    phase_index: int | None = None,
    drive_param: str | None = None,
) -> SystemDef:
    """``SystemDef`` around the dysts numba kernel ``cls._rhs(x, y, z, t, *params)``.

    The parameter order is taken from the kernel signature and checked against dysts'
    ``sorted(params)`` convention.
    """
    import dysts.flows

    cls = getattr(dysts.flows, dysts_name)
    model = cls()
    names = list(inspect.signature(cls._rhs.py_func).parameters)[4:]
    assert names == sorted(model.params), (names, sorted(model.params))
    ic = np.asarray(model.ic, dtype=np.float64).copy()
    if phase_index is not None:
        ic[phase_index] = math.fmod(ic[phase_index], 2.0 * math.pi)
    args = ", ".join(
        [f"x[{i}]" for i in range(3)] + ["0.0"] + [f"p[{j}]" for j in range(len(names))]
    )
    src = f"def rhs(x, p, out):\n    r = _k({args})\n" + "".join(
        f"    out[{i}] = r[{i}]\n" for i in range(3)
    )
    ns: dict[str, Any] = {"_k": cls._rhs}
    exec(src, ns)
    return SystemDef(
        name=f"{dysts_name.lower()}_{modulated}",
        display_name=dysts_name,
        variables=("x", "y", "z"),
        param_names=tuple(names),
        default_params=tuple(float(model.params[k]) for k in names),
        initial_condition=tuple(float(v) for v in ic),
        modulated_param=modulated,
        candidate_range=candidate_range,
        rhs=numba.njit(cache=False)(ns["rhs"]),
        dysts_name=dysts_name,
        period_hint=float(model.period),
        phase_indices=() if phase_index is None else (phase_index,),
        drive_frequency_param=drive_param,
    )


def verify_wrapper(system: SystemDef, n: int = 50, seed: int = 7) -> float:
    import dysts.flows

    model = getattr(dysts.flows, system.dysts_name)()
    rng = np.random.default_rng(seed)
    p = system.params_array()
    out = np.empty(3)
    scale = np.maximum(np.abs(system.initial_state()), 1.0)
    worst = 0.0
    for _ in range(n):
        x = system.initial_state() + scale * rng.normal(size=3)
        system.rhs(x, p, out)
        ref = np.asarray(model.rhs(x, 0.0), dtype=float)
        worst = max(worst, float(np.max(np.abs(out - ref)) / (np.max(np.abs(ref)) + 1e-12)))
    return worst


# ---------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------


def multi_ic_check(system: SystemDef, build: Any, seed: int = 11) -> list[dict[str, Any]]:
    """Random ICs at fixed u: boundedness, IC-to-IC period spread, agreement with P(u)."""
    e, ref = build.entry, build.reference
    obs = e.period_observable
    i_obs = system.variable_index(obs)
    audio = [system.variable_index(v) for v in system.audio_variables]
    rng = np.random.default_rng(seed)
    p_ref = ref.period
    dt = p_ref / 32
    n_tr, n_rec = (300 * 32), (2000 * 32)
    nperseg = 128 * 32
    lo, hi = ref.mean - 50 * ref.std, ref.mean + 50 * ref.std
    rows = []
    us = sorted(set(CHECK_U) | {round(float(e.u_default), 6)})
    for u in us:
        value = float(e.param_value(np.array([u]))[0])
        params = system.params_array(**{system.modulated_param: value})
        periods, proms, means, bounded = [], [], [], []
        for _ in range(N_IC):
            x0 = system.initial_state().copy()
            x0[audio] = ref.mean[audio] + 1.5 * ref.std[audio] * rng.standard_normal(len(audio))
            for k in system.phase_indices:
                x0[k] = rng.uniform(0, 2 * math.pi)
            _, x = trajectory(system, params, x0, dt=dt, n_samples=n_tr, h_max=e.h_max)
            rec, _ = trajectory(system, params, x, dt=dt, n_samples=n_rec, h_max=e.h_max)
            sub = rec[:, audio]
            ok = bool(
                np.all(np.isfinite(sub)) and np.all(sub >= lo[audio]) and np.all(sub <= hi[audio])
            )
            bounded.append(ok)
            if not ok:
                continue
            s = rec[:, i_obs]
            if e.period_method == "return_time":
                periods.append(mean_return_time(s, dt).mean)
                proms.append(spectral_peak(s, dt, nperseg=nperseg, f_min=0.25 / p_ref).prominence)
            else:
                pk = spectral_peak(s, dt, nperseg=nperseg, f_min=0.25 / p_ref)
                periods.append(pk.centroid_period)
                proms.append(pk.prominence)
            means.append(float(s.mean()))
        P_tab = float(e.period(np.array([u]))[0])
        P = np.array(periods)
        rows.append(
            {
                "u": u,
                "value": value,
                "bounded": int(sum(bounded)),
                "n": N_IC,
                "P_table": P_tab,
                "P_min": float(P.min()) if P.size else math.nan,
                "P_max": float(P.max()) if P.size else math.nan,
                "cents_vs_table": [float(1200 * math.log2(P_tab / q)) for q in P] if P.size else [],
                "prominence": proms,
                "obs_mean": means,
            }
        )
    return rows


def engine_check(system: SystemDef, build: Any) -> dict[str, Any]:
    from chaotic_sound import systems as reg
    from chaotic_sound.blocks import Dynamical
    from chaotic_sound.catalog import Catalog
    from chaotic_sound.pitch import cents_between

    reg.SYSTEMS[system.name] = system
    cat = Catalog(entries={system.name: build.entry})
    fs = 48_000
    method = build.entry.period_method

    def measure(u: float | None, seed: int, cycles: float) -> tuple[float, int]:
        b = Dynamical("osc", catalog=cat, system=system.name, note="A3", seed=seed, param=u)
        b.reset(fs)
        n = round((0.5 + cycles / b.frequency_hz) * fs)
        x = b.process(n, {"param": None, "amp": None})["out"][fs // 2 :, 0]
        if method == "return_time":
            f = 1.0 / mean_return_time(x, 1.0 / fs).mean
        else:
            f = spectral_peak(x, 1.0 / fs, nperseg=2**16, f_min=0.25 * b.frequency_hz)
            f = f.centroid_frequency
        return float(cents_between(f, b.frequency_hz)), b.resets

    t0 = time.time()
    default = [measure(None, s, 2000) for s in (1, 2, 3, 4)]
    across = {str(u): [measure(u, s, 1000) for s in (1, 2)] for u in ENGINE_U}
    t_pitch = time.time() - t0

    def lfo(note: str, period_s: float, seconds: float, seed: int) -> dict[str, Any]:
        b = Dynamical("osc", catalog=cat, system=system.name, note=note, seed=seed)
        b.reset(fs)
        t = np.arange(round(seconds * fs)) / fs
        u = 0.5 - 0.5 * np.cos(2 * np.pi * t / period_s)
        x = b.process(len(t), {"param": u, "amp": None})["out"][:, 0]
        tail = x[-fs:]
        return {
            "resets": b.resets,
            "finite": bool(np.all(np.isfinite(x))),
            "peak_over_target_rms": float(np.max(np.abs(x[fs // 2 :])) / 0.25),
            "rms": float(np.std(x[fs // 2 :])),
            "last_second_rms": float(np.std(tail)),
            "substeps_A3_default": None,
        }

    t1 = time.time()
    slow = [lfo("A3", 4.0, 24.0, s) for s in (1, 2)]
    fast = [lfo("A1", 0.25, 8.0, s) for s in (1, 2)]
    t_lfo = time.time() - t1
    b = Dynamical("osc", catalog=cat, system=system.name, note="A3")
    b.reset(fs)
    return {
        "default_cents": [c for c, _ in default],
        "default_resets": sum(r for _, r in default),
        "across_cents": {u: [c for c, _ in v] for u, v in across.items()},
        "across_resets": sum(r for v in across.values() for _, r in v),
        "lfo_slow_A3": slow,
        "lfo_fast_A1": fast,
        "substeps_A3_default": b.substeps_per_sample(),
        "substeps_A3_u0": b.substeps_per_sample(0.0),
        "substeps_A3_u1": b.substeps_per_sample(1.0),
        "seconds_pitch": t_pitch,
        "seconds_lfo": t_lfo,
    }


def run_job(job: str) -> dict[str, Any]:
    name, par, cand, phase, drive, (n_sweep, n_table) = JOBS[job]
    t0 = time.time()
    system = make_system(name, par, cand, phase, drive)
    res: dict[str, Any] = {"job": job, "system": name, "param": par, "candidate_range": cand}
    res["wrapper_max_rel_err"] = verify_wrapper(system)
    log: list[str] = []
    try:
        build = build_system(
            system, BuildSettings(sweep_points=n_sweep, table_points=n_table), progress=log.append
        )
    except Exception as exc:  # report, do not crash the pool
        res.update(error=repr(exc), log=log)
        return res
    e, i = build.entry, build.entry.info
    obs = e.period_observable
    prom = e.observables[obs].prominence
    u_def = float(e.u_default)
    lam = np.array(i["lyapunov_per_period"])
    P = e.period_table
    sweep_vals = np.array([r.value for r in build.sweep_results])
    in_range = (sweep_vals >= e.p_min) & (sweep_vals <= e.p_max)
    sweep_bounded = [r.bounded for r, k in zip(build.sweep_results, in_range, strict=True) if k]
    res.update(
        build_points=[n_sweep, n_table],
        p_default=e.p_default,
        p_min=e.p_min,
        p_max=e.p_max,
        u_default=u_def,
        rel_width=(e.p_max - e.p_min) / abs(e.p_default),
        observable=obs,
        method=e.period_method,
        P_ref=build.reference.period,
        chaotic_fraction=i["chaotic_fraction"],
        windows=i["range_selection"]["accepted_windows"],
        lo_reason=i["range_selection"]["lo_reason"],
        hi_reason=i["range_selection"]["hi_reason"],
        trims=i["range_selection"]["trims"],
        corrected=i["period_corrected_indices"],
        sweep_bounded_in_range=f"{sum(sweep_bounded)}/{len(sweep_bounded)}",
        sweep_bounded_all=f"{sum(r.bounded for r in build.sweep_results)}/{len(sweep_vals)}",
        prominence_default=float(np.interp(u_def, e.u_grid, prom)),
        prominence_table=[float(prom.min()), float(np.median(prom)), float(prom.max())],
        prominence_all_vars_default={
            v: float(np.interp(u_def, e.u_grid, e.observables[v].prominence))
            for v in system.audio_variables
        },
        lyap_per_period_default=float(np.interp(u_def, e.u_grid, lam)),
        lyap_per_period_table=[float(lam.min()), float(np.median(lam)), float(lam.max())],
        period_min=float(P.min()),
        period_max=float(P.max()),
        period_span_cents=float(1200 * math.log2(P.max() / P.min())),
        max_period_step=i["max_relative_period_step"],
        monotone=bool(np.all(np.diff(P) <= 0) or np.all(np.diff(P) >= 0)),
        u_grid=e.u_grid.tolist(),
        period_table=P.tolist(),
        prominence_curve=prom.tolist(),
        lyap_curve=lam.tolist(),
        h_max=e.h_max,
        log=log,
        seconds_build=time.time() - t0,
    )
    try:
        from build_catalog import plot_build

        plot_build(build, OUT / f"build_{job}.png")
    except Exception as exc:
        res["plot_error"] = repr(exc)
    if job in ("rikitake_a_wide",):
        return res
    t1 = time.time()
    res["multi_ic"] = multi_ic_check(system, build)
    res["seconds_multi_ic"] = time.time() - t1
    res["engine"] = engine_check(system, build)
    res["seconds_total"] = time.time() - t0
    return res


# ---------------------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------------------


def catalog_rows() -> list[dict[str, Any]]:
    """The same summary numbers for the systems already in the catalog."""
    from chaotic_sound.catalog import load_default_catalog

    cat = load_default_catalog()
    rows = []
    for name in ("lorenz", "rossler", "chua", "duffing", "thomas"):
        e = cat[name]
        obs = e.period_observable
        prom = e.observables[obs].prominence
        P = e.period_table
        lam = np.array(e.info["lyapunov_per_period"])
        rows.append(
            {
                "system": name,
                "param": e.param,
                "p_default": e.p_default,
                "p_min": e.p_min,
                "p_max": e.p_max,
                "u_default": float(e.u_default),
                "rel_width": (e.p_max - e.p_min) / abs(e.p_default),
                "observable": obs,
                "method": e.period_method,
                "chaotic_fraction": e.info["chaotic_fraction"],
                "windows": len(e.info["range_selection"]["accepted_windows"]),
                "prominence_default": float(np.interp(e.u_default, e.u_grid, prom)),
                "prominence_table": [float(prom.min()), float(np.median(prom))],
                "lyap_per_period_default": float(np.interp(e.u_default, e.u_grid, lam)),
                "period_span_cents": float(1200 * math.log2(P.max() / P.min())),
                "max_period_step": e.info["max_relative_period_step"],
                "u_grid": e.u_grid.tolist(),
                "period_table": P.tolist(),
                "prominence_curve": prom.tolist(),
            }
        )
    return rows


def plot_overview(results: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> None:
    """Two panels vs u: P(u) in cents re P(u_default), and the tuning variable's prominence."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = [  # fixed categorical order (dataviz reference palette, light mode)
        ("rikitake_mu_rec", "Rikitake (μ), recommended", "#2a78d6"),
        ("rucklidge_b_rec", "Rucklidge (b ∈ [4.6, 8.5])", "#eb6834"),
        ("halvorsen_a_prod", "Halvorsen (a)", "#1baf7a"),
        ("rikitake_a", "Rikitake (a)", "#eda100"),
        ("moorespiegel_a", "Moore–Spiegel (a)", "#e87ba4"),
        ("forcedbrusselator_f", "Forced Brusselator (f)", "#6250d6"),
    ]
    by_job = {r["job"]: r for r in results if "error" not in r}
    thomas = next(c for c in catalog if c["system"] == "thomas")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="#e4e3df", lw=0.6)
        ax.set_xlabel("knob u (linear in the parameter over the chaotic range)")
    for job, label, color in series:
        r = by_job.get(job)
        if r is None:
            continue
        u = np.array(r["u_grid"])
        P = np.array(r["period_table"])
        p_def = float(np.interp(r["u_default"], u, P))
        axes[0].plot(u, 1200 * np.log2(P / p_def), color=color, lw=2, label=label)
        axes[0].plot([r["u_default"]], [0], "o", ms=6, color=color, mec="white", mew=1.5)
        axes[1].plot(u, r["prominence_curve"], color=color, lw=2, label=label)
    u = np.array(thomas["u_grid"])
    P = np.array(thomas["period_table"])
    p_def = float(np.interp(thomas["u_default"], u, P))
    axes[0].plot(
        u, 1200 * np.log2(P / p_def), color="#8a8984", lw=1.5, ls="--", label="Thomas (catalog)"
    )
    axes[1].plot(
        u, thomas["prominence_curve"], color="#8a8984", lw=1.5, ls="--", label="Thomas (catalog)"
    )
    axes[1].axhline(0.3, color="#52514e", lw=0.8, ls=":")
    axes[1].text(1.0, 0.31, "target 0.3", ha="right", va="bottom", fontsize=8, color="#52514e")
    axes[0].set_ylabel("P(u) re P(u_default)  [cents]")
    axes[0].set_title("Characteristic period over the range (dots: dysts default)", fontsize=10)
    axes[1].set_ylabel("spectral prominence of the tuning variable")
    axes[1].set_title("Pitch clarity over the range", fontsize=10)
    axes[1].set_ylim(0, 1)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="outside lower center", ncol=4)
    fig.savefig(OUT / "overview.png", dpi=130)


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "run"
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if stage == "run":
        # Optional job names after "run": re-run only those and merge into verify.json.
        jobs = sys.argv[2:] or list(JOBS)
        with get_context("spawn").Pool(len(jobs)) as pool:
            results = pool.map(run_job, jobs)
        path = OUT / "verify.json"
        if sys.argv[2:] and path.exists():
            old = {r["job"]: r for r in json.loads(path.read_text())}
            old.update({r["job"]: r for r in results})
            results = [old[j] for j in JOBS if j in old]
        path.write_text(json.dumps(results, indent=1, default=float))
        stage = "catalog"
    if stage == "catalog":
        (OUT / "catalog_rows.json").write_text(json.dumps(catalog_rows(), indent=1, default=float))
        stage = "plot"
    if stage == "plot":
        results = json.loads((OUT / "verify.json").read_text())
        catalog = json.loads((OUT / "catalog_rows.json").read_text())
        plot_overview(results, catalog)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
