"""Screen dysts flows as a possible 5th voice (replacement for Thomas).

Candidates of this screener: MooreSpiegel, RikitakeDynamo (Rikitake), Colpitts, Chen,
LuChen (the Lü system), Arneodo, GenesioTesi, Rucklidge.

Stages (run from ``lab/``; total a few minutes with 8 processes)::

    NUMBA_CACHE_DIR=<scratch> caffeinate -is uv run python \
        scripts/studies/screening/screen_moorespiegel_group.py [verify|default|coarse|build|all]

- ``verify``: our numba wrapper vs ``model.rhs`` at random points.
- ``default``: reference scale + one accurate analysis at the dysts default: boundedness,
  λ·P_ref and per-variable spectral prominence.
- ``coarse``: for every *genuine* parameter (scale-only / offset-only ones are excluded, see
  ``EXCLUDED``), a 41-point continuation sweep over ×0.5…×1.5 of the default with
  ``QUICK_SETTINGS``, then ``select_chaotic_range`` with the catalog builder's thresholds.
- ``build``: the full ``build_system`` with ``BuildSettings(sweep_points=121,
  table_points=33)`` for the best parameter of each system (candidate range chosen from the
  coarse stage), plus the catalog diagnostic figure.

Outputs go to ``outputs/studies/screening/moorespiegel_group/``.
"""

from __future__ import annotations

import inspect
import json
import math
import sys
import time
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np
from numba import njit

LAB = Path(__file__).resolve().parents[3]
OUT = LAB / "outputs" / "studies" / "screening" / "moorespiegel_group"
sys.path.insert(0, str(LAB / "scripts"))

from chaotic_sound.analysis.catalog_builder import (  # noqa: E402
    BuildSettings,
    build_system,
    choose_period_method,
    choose_tuning_observable,
    point_period,
)
from chaotic_sound.analysis.sweep import (  # noqa: E402
    DEFAULT_SETTINGS,
    QUICK_SETTINGS,
    SWEEP_SETTINGS,
    analyze_point,
    reference_scale,
    select_chaotic_range,
    sweep,
)
from chaotic_sound.systems.base import SystemDef  # noqa: E402

CANDIDATES = [
    "MooreSpiegel",
    "RikitakeDynamo",
    "Colpitts",
    "Chen",
    "LuChen",
    "Arneodo",
    "GenesioTesi",
    "Rucklidge",
]

EXCLUDED = {
    # Arneodo: x''' + c x'' + b x' + a x − d x³ = 0; x → x/√|d| removes d (amplitude only).
    "Arneodo": {"d": "scale-only (x → x/√|d|)"},
    # Colpitts: x' does not depend on x, so c only shifts x by a constant (DC offset).
    # After shifting z by e − 1 (and x, y by constants) the only trace of e is a constant
    # K = d(e − 1) in x'; F is piecewise linear and homogeneous, so K is an amplitude scale.
    "Colpitts": {"c": "offset-only (x → x − c)", "e": "scale-only (bias K = d(e−1))"},
}


# ---------------------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------------------


@njit(cache=True)
def colpitts_rhs(x, p, out):  # type: ignore[no-untyped-def]
    """dysts Colpitts (its ``rhs`` is pure Python with ``np.heaviside``). p = (a,b,c,d,e)."""
    a, b, c, d, e = p[0], p[1], p[2], p[3], p[4]
    u = x[2] - (e - 1.0)
    fz = -u if u <= 0.0 else 0.0  # −u·(1 − H(u)), H(0) = 0
    out[0] = x[1] - a * fz
    out[1] = c - x[0] - b * x[1] - x[2]
    out[2] = x[1] - d * x[2]


_WRAPPERS: dict[str, Any] = {}


def dysts_param_names(cls: Any) -> list[str]:
    """Parameter names in the order of ``cls._rhs(x, y, z, t, *params)``."""
    if cls.__name__ == "Colpitts":
        return ["a", "b", "c", "d", "e"]
    names = list(inspect.signature(cls._rhs.py_func).parameters)
    return names[4:]


def wrap_dysts_rhs(cls: Any) -> Any:
    """Generate an ``@njit rhs(x, p, out)`` that calls ``cls._rhs`` (a numba dispatcher)."""
    if cls.__name__ == "Colpitts":
        return colpitts_rhs
    if cls.__name__ in _WRAPPERS:
        return _WRAPPERS[cls.__name__]
    n = len(dysts_param_names(cls))
    args = ", ".join(f"p[{i}]" for i in range(n))
    src = (
        "def rhs(x, p, out):\n"
        f"    r = _f(x[0], x[1], x[2], 0.0, {args})\n"
        "    out[0] = r[0]\n    out[1] = r[1]\n    out[2] = r[2]\n"
    )
    ns: dict[str, Any] = {"_f": cls._rhs}
    exec(src, ns)
    fn = njit(ns["rhs"])
    _WRAPPERS[cls.__name__] = fn
    return fn


def make_system(
    dysts_name: str,
    modulated: str | None = None,
    candidate_range: tuple[float, float] | None = None,
) -> SystemDef:
    """SystemDef for a dysts flow; default modulated param = first one, range ×0.5…×1.5."""
    import dysts.flows

    cls = getattr(dysts.flows, dysts_name)
    model = cls()
    names = dysts_param_names(cls)
    values = tuple(float(model.params[k]) for k in names)
    modulated = modulated or names[0]
    v = values[names.index(modulated)]
    if candidate_range is None:
        candidate_range = tuple(sorted((0.5 * v, 1.5 * v)))  # type: ignore[assignment]
    return SystemDef(
        name=dysts_name.lower(),
        display_name=dysts_name,
        variables=("x", "y", "z"),
        param_names=tuple(names),
        default_params=values,
        initial_condition=tuple(float(c) for c in model.ic),
        modulated_param=modulated,
        candidate_range=candidate_range,  # type: ignore[arg-type]
        rhs=wrap_dysts_rhs(cls),
        dysts_name=dysts_name,
        period_hint=float(model.period),
    )


def verify(dysts_name: str, n: int = 20, seed: int = 0) -> float:
    """Max relative error of our wrapper vs ``model.rhs`` at random points near the attractor."""
    import dysts.flows

    model = getattr(dysts.flows, dysts_name)()
    system = make_system(dysts_name)
    rng = np.random.default_rng(seed)
    mean = np.asarray(model.mean, dtype=float)
    std = np.asarray(model.std, dtype=float)
    p = system.params_array()
    out = np.empty(3)
    worst = 0.0
    for _ in range(n):
        x = mean + 2.0 * std * rng.standard_normal(3)
        ref = np.asarray(model.rhs(x, 0.0), dtype=float)
        system.rhs(x, p, out)
        worst = max(worst, float(np.max(np.abs(out - ref)) / (np.max(np.abs(ref)) + 1e-12)))
    return worst


# ---------------------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------------------


def stage_default(dysts_name: str) -> dict[str, Any]:
    t0 = time.time()
    system = make_system(dysts_name)
    ref = reference_scale(system, SWEEP_SETTINGS)
    point = analyze_point(system, system.default_value, ref, DEFAULT_SETTINGS)
    obs = choose_tuning_observable(point) if point.bounded else None
    res: dict[str, Any] = {
        "system": dysts_name,
        "params": dict(zip(system.param_names, system.default_params, strict=True)),
        "P_ref": ref.period,
        "period_hint": system.period_hint,
        "bounded": point.bounded,
        "stationary": point.stationary,
        "lyapunov": point.lyapunov,
        "lyapunov_per_period": point.lyapunov * ref.period,
        "best_variable": obs,
        "variables": {
            k: {
                "mean": v.mean,
                "std": v.std,
                "prominence": v.prominence,
                "centroid_period": v.centroid_period,
                "peak_period": v.peak_period,
                "return_time": v.return_time,
                "drift": v.drift,
            }
            for k, v in point.variables.items()
        },
        "seconds": time.time() - t0,
    }
    return res


def _coarse_one(args: tuple[str, str]) -> dict[str, Any]:
    dysts_name, param = args
    t0 = time.time()
    system = make_system(dysts_name, modulated=param)
    ref = reference_scale(system, SWEEP_SETTINGS)
    dpoint = analyze_point(system, system.default_value, ref, QUICK_SETTINGS)
    obs = choose_tuning_observable(dpoint)
    method = choose_period_method(system, dpoint, obs, 0.25)
    lo_c, hi_c = system.candidate_range
    values = np.unique(np.append(np.linspace(lo_c, hi_c, 41), system.default_value))
    results = sweep(system, values, ref, QUICK_SETTINGS)
    lam = [r.lyapunov * ref.period if r.bounded else math.nan for r in results]
    width = hi_c - lo_c
    out: dict[str, Any] = {
        "system": dysts_name,
        "param": param,
        "default": system.default_value,
        "candidate_range": [lo_c, hi_c],
        "observable": obs,
        "method": method,
        "values": values.tolist(),
        "bounded": [r.bounded for r in results],
        "lyap_per_period": lam,
        "period": [point_period(r, obs, method, None) if r.bounded else math.nan for r in results],
        "prominence": [r.variables[obs].prominence if r.bounded else math.nan for r in results],
    }
    try:
        sel = select_chaotic_range(
            results,
            system.default_value,
            ref.period,
            lambda r: point_period(r, obs, method, None),
            lambda r: r.variables[obs].drift if r.bounded else math.inf,
            lyapunov_threshold=0.05,
            max_period_jump=0.15,
            max_window_width=0.03 * width,
            escape_margin=0.03 * width,
        )
        inside = [(lo <= v <= hi) for v, lo, hi in ((v, sel.lo, sel.hi) for v in values)]
        chaotic_in = [l > 0.05 for l, i in zip(lam, inside, strict=True) if i]
        out.update(
            lo=sel.lo,
            hi=sel.hi,
            lo_reason=sel.lo_reason,
            hi_reason=sel.hi_reason,
            windows=len(sel.windows),
            rel_width=(sel.hi - sel.lo) / abs(system.default_value),
            chaotic_fraction=float(np.mean(chaotic_in)) if chaotic_in else math.nan,
        )
    except RuntimeError as exc:
        out.update(error=str(exc), rel_width=0.0)
    out["seconds"] = time.time() - t0
    return out


def _build_one(args: tuple[str, str, tuple[float, float]]) -> dict[str, Any]:
    dysts_name, param, cand = args
    t0 = time.time()
    system = make_system(dysts_name, modulated=param, candidate_range=cand)
    settings = BuildSettings(sweep_points=121, table_points=33)
    log: list[str] = []
    try:
        build = build_system(system, settings, progress=log.append)
    except Exception as exc:  # report, do not crash the pool
        return {"system": dysts_name, "param": param, "error": repr(exc), "log": log}
    e = build.entry
    i = e.info
    prom = e.observables[e.period_observable].prominence
    res = {
        "system": dysts_name,
        "param": param,
        "candidate_range": list(cand),
        "default": e.p_default,
        "p_min": e.p_min,
        "p_max": e.p_max,
        "u_default": e.u_default,
        "rel_width": (e.p_max - e.p_min) / abs(e.p_default),
        "observable": e.period_observable,
        "method": e.period_method,
        "P_ref": build.reference.period,
        "period_min": float(e.period_table.min()),
        "period_max": float(e.period_table.max()),
        "max_period_step": i["max_relative_period_step"],
        "chaotic_fraction": i["chaotic_fraction"],
        "windows": i["range_selection"]["accepted_windows"],
        "lo_reason": i["range_selection"]["lo_reason"],
        "hi_reason": i["range_selection"]["hi_reason"],
        "trims": i["range_selection"]["trims"],
        "corrected": i["period_corrected_indices"],
        "prominence_default": build.default_point.variables[e.period_observable].prominence,
        "prominence_range": [float(prom.min()), float(np.median(prom)), float(prom.max())],
        "all_prominence_default": {
            k: v.prominence for k, v in build.default_point.variables.items()
        },
        "lyap_per_period_default": build.default_point.lyapunov * build.reference.period,
        "lyap_per_period_table": i["lyapunov_per_period"],
        "u_grid": e.u_grid.tolist(),
        "period_table": e.period_table.tolist(),
        "h_max": e.h_max,
        "log": log,
        "seconds": time.time() - t0,
    }
    try:
        from build_catalog import plot_build

        plot_build(build, OUT / f"build_{dysts_name}_{param}.png")
    except Exception as exc:
        res["plot_error"] = repr(exc)
    return res


def _save(name: str, data: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=1, default=float))


def run_verify() -> None:
    errs = {n: verify(n) for n in CANDIDATES}
    for n, e in errs.items():
        print(f"{n:16s} max rel err {e:.2e}")
    _save("verify.json", errs)


def run_default(pool: Any) -> None:
    res = pool.map(stage_default, CANDIDATES)
    for r in res:
        prom = {k: round(v["prominence"], 3) for k, v in r["variables"].items()}
        print(
            f"{r['system']:16s} bounded={r['bounded']} P_ref={r['P_ref']:.4g} "
            f"λP={r['lyapunov_per_period']:.3f} prom={prom} ({r['seconds']:.1f}s)"
        )
    _save("default.json", res)


def coarse_jobs() -> list[tuple[str, str]]:
    import dysts.flows

    jobs = []
    for n in CANDIDATES:
        for p in dysts_param_names(getattr(dysts.flows, n)):
            if p not in EXCLUDED.get(n, {}):
                jobs.append((n, p))
    return jobs


def run_coarse(pool: Any) -> None:
    res = pool.map(_coarse_one, coarse_jobs())
    for r in res:
        if "error" in r:
            print(f"{r['system']:16s} {r['param']:4s} ERROR {r['error']}")
            continue
        print(
            f"{r['system']:16s} {r['param']:4s} [{r['lo']:.4g}, {r['hi']:.4g}] "
            f"rel={r['rel_width']:.2f} chaotic={r['chaotic_fraction']:.2f} "
            f"obs={r['observable']} {r['method']} | {r['lo_reason']} | {r['hi_reason']} "
            f"({r['seconds']:.1f}s)"
        )
    _save("coarse.json", res)


def build_jobs() -> list[tuple[str, str, tuple[float, float]]]:
    """Every genuine parameter of the coarse stage; widen the range where it hit an end."""
    coarse = json.loads((OUT / "coarse.json").read_text())
    jobs = []
    for best in coarse:
        n = best["system"]
        if "error" in best or best["param"] in EXCLUDED.get(n, {}):
            continue
        lo_c, hi_c = best["candidate_range"]
        v = best["default"]
        lo, hi = lo_c, hi_c
        # If the chaotic range reached an end of the ×0.5…×1.5 window, widen that side.
        if "end of candidate range" in best["lo_reason"]:
            lo = v - 1.5 * (v - lo_c) if v > 0 else lo_c - 0.5 * abs(v)
        if "end of candidate range" in best["hi_reason"]:
            hi = v + 1.5 * (hi_c - v) if v > 0 else hi_c + 0.5 * abs(v)
        if v > 0:
            lo = max(lo, 0.05 * v)
        jobs.append((n, best["param"], (float(lo), float(hi))))
    return jobs


def run_build(pool: Any, jobs: list[tuple[str, str, tuple[float, float]]] | None = None) -> None:
    jobs = jobs or build_jobs()
    for j in jobs:
        print("build job:", j)
    res = pool.map(_build_one, jobs)
    for r in res:
        if "error" in r:
            print(f"{r['system']:16s} {r['param']:4s} ERROR {r['error']}")
            print("   ", "\n    ".join(r["log"]))
            continue
        print(
            f"{r['system']:16s} {r['param']:4s} [{r['p_min']:.4g}, {r['p_max']:.4g}] "
            f"rel={r['rel_width']:.2f} chaotic={r['chaotic_fraction']:.2f} "
            f"obs={r['observable']} {r['method']} prom(def)={r['prominence_default']:.2f} "
            f"P∈[{r['period_min']:.4g},{r['period_max']:.4g}] step={r['max_period_step']:.3f} "
            f"win={len(r['windows'])} ({r['seconds']:.0f}s)"
        )
        for line in r["log"]:
            print("    ", line)
    name = "build.json" if not (OUT / "build.json").exists() else "build_extra.json"
    _save(name, res)


EXTRA_JOBS: list[tuple[str, str, tuple[float, float]]] = [
    # Rikitake reached both ends of the widened window: explore further.
    ("RikitakeDynamo", "a", (0.02, 4.0)),
    ("RikitakeDynamo", "mu", (0.2, 3.0)),
    # Lü c: the first build hit catalog_builder's duplicate-u_default bug (the default fell
    # on a u-grid node up to rounding); a slightly different window avoids it.
    ("LuChen", "c", (9.03, 26.97)),
    ("MooreSpiegel", "a", (5.0, 25.0)),
]


TUNE_JOBS: list[tuple[str, str, tuple[float, float]]] = [
    ("MooreSpiegel", "a", (5.0, 25.0)),
    ("RikitakeDynamo", "a", (0.02, 4.0)),
    ("Colpitts", "d", (0.02, 0.12)),
    ("Chen", "b", (1.5, 4.5)),
    ("LuChen", "c", (9.03, 26.97)),
    ("Arneodo", "c", (0.5, 1.5)),
    ("GenesioTesi", "a", (0.22, 0.66)),
    ("Rucklidge", "b", (3.35, 10.05)),
]
TUNE_U = (0.05, 0.25, 0.5, 0.75, 0.95)
TUNE_SEEDS = (1, 2, 3, 4, 5, 6)


def _tune_one(job: tuple[str, str, tuple[float, float]]) -> dict[str, Any]:
    """Render the candidate through the real Dynamical block and measure its pitch at A3.

    The system is registered in the in-memory registry only (``SYSTEMS``), and the catalog is
    a one-entry :class:`Catalog` built here; nothing on disk changes.
    """
    from chaotic_sound import systems as reg
    from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
    from chaotic_sound.blocks import Dynamical
    from chaotic_sound.catalog import Catalog
    from chaotic_sound.pitch import cents_between

    dysts_name, param, cand = job
    t0 = time.time()
    system = make_system(dysts_name, modulated=param, candidate_range=cand)
    build = build_system(system, BuildSettings(sweep_points=121, table_points=33))
    reg.SYSTEMS[system.name] = system
    cat = Catalog(entries={system.name: build.entry})
    fs = 48_000

    def measure(u: float | None, seed: int, cycles: float) -> tuple[float, int, int]:
        block = Dynamical("osc", catalog=cat, system=system.name, note="A3", seed=seed, param=u)
        block.reset(fs)
        n = round((0.5 + cycles / block.frequency_hz) * fs)
        x = block.process(n, {"param": None, "amp": None})["out"][fs // 2 :, 0]
        if build.entry.period_method == "return_time":
            f = 1.0 / mean_return_time(x, 1.0 / fs).mean
        else:
            f = spectral_peak(x, 1.0 / fs, nperseg=2**16, f_min=0.25 * block.frequency_hz)
            f = f.centroid_frequency
        return cents_between(f, block.frequency_hz), block.resets, block.substeps_per_sample()

    default = [measure(None, s, 2000) for s in TUNE_SEEDS]
    across = {u: [measure(u, s, 1000) for s in TUNE_SEEDS[:3]] for u in TUNE_U}
    return {
        "system": dysts_name,
        "param": param,
        "range": [build.entry.p_min, build.entry.p_max],
        "u_default": build.entry.u_default,
        "method": build.entry.period_method,
        "observable": build.entry.period_observable,
        "default_cents": [c for c, _, _ in default],
        "default_resets": sum(r for _, r, _ in default),
        "substeps_A3": default[0][2],
        "across_cents": {str(u): [c for c, _, _ in v] for u, v in across.items()},
        "across_resets": sum(r for v in across.values() for _, r, _ in v),
        "seconds": time.time() - t0,
    }


def _modulate_one(job: tuple[str, str, tuple[float, float]]) -> dict[str, Any]:
    """Sweep u over [0, 1] with a 4 s sine LFO for 24 s at A3; count resets and clipping."""
    from chaotic_sound import systems as reg
    from chaotic_sound.blocks import Dynamical
    from chaotic_sound.catalog import Catalog

    dysts_name, param, cand = job
    system = make_system(dysts_name, modulated=param, candidate_range=cand)
    build = build_system(system, BuildSettings(sweep_points=121, table_points=33))
    reg.SYSTEMS[system.name] = system
    cat = Catalog(entries={system.name: build.entry})
    fs = 48_000
    t = np.arange(24 * fs) / fs
    u = 0.5 - 0.5 * np.cos(2 * np.pi * t / 4.0)
    out = []
    for seed in (1, 2):
        block = Dynamical("osc", catalog=cat, system=system.name, note="A3", seed=seed)
        block.reset(fs)
        x = block.process(len(t), {"param": u, "amp": None})["out"][:, 0]
        rms = [float(np.std(x[k : k + fs // 4])) for k in range(fs, len(x), fs // 4)]
        out.append(
            {
                "resets": block.resets,
                "finite": bool(np.all(np.isfinite(x))),
                "peak": float(np.max(np.abs(x))),
                "rms_min": min(rms),
                "rms_max": max(rms),
            }
        )
    return {"system": dysts_name, "param": param, "runs": out}


def run_modulate(pool: Any) -> None:
    res = pool.map(_modulate_one, TUNE_JOBS)
    for r in res:
        print(f"{r['system']:16s} {r['param']:4s}", r["runs"])
    _save("modulate.json", res)


def run_tune(pool: Any) -> None:
    res = pool.map(_tune_one, TUNE_JOBS)
    for r in res:
        d = np.array(r["default_cents"])
        acr = {u: np.round(np.mean(v), 1) for u, v in r["across_cents"].items()}
        print(
            f"{r['system']:16s} {r['param']:4s} default: mean {d.mean():+.1f} c, "
            f"range [{d.min():+.1f}, {d.max():+.1f}] resets={r['default_resets']} "
            f"substeps@A3={r['substeps_A3']} | across u: {acr} resets={r['across_resets']} "
            f"({r['seconds']:.0f}s)"
        )
    _save("tune.json", res)


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if stage in ("verify", "all"):
        run_verify()
    if stage in ("default", "coarse", "build", "extra", "tune", "modulate", "all"):
        with get_context("spawn").Pool(8) as pool:
            if stage in ("default", "all"):
                run_default(pool)
            if stage in ("coarse", "all"):
                run_coarse(pool)
            if stage in ("build", "all"):
                run_build(pool)
            if stage == "extra":
                run_build(pool, EXTRA_JOBS)
            if stage == "tune":
                run_tune(pool)
            if stage == "modulate":
                run_modulate(pool)
    print(f"stage {stage} done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
