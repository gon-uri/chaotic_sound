"""Compute cost of one dynamical box, and what it implies for the browser engine.

Study report: ``docs/studies/cost.md``. Usage (from ``lab/``; about 2 minutes)::

    uv run python scripts/studies/cost.py [--quick] [--no-js]

What it measures (all at fs = 48 kHz, compile time excluded by warm-up calls):

1. Pure RK4 step cost of the numba kernel per system (``integrate_sampled`` with 1000 steps
   per recorded sample, so per-sample overhead is negligible).
2. For every system x note (A1, A3, A5, A7) x {static knob, full-range 4 s sine LFO on
   ``param``}: wall time of ``Dynamical.process`` in 128-sample chunks (an AudioWorklet render
   quantum) and 512-sample chunks (``Patch.render`` default), the time of ``render_tuned``
   alone on the same per-sample inputs, the RK4 sub-steps per sample, and a per-stage
   breakdown of ``process`` (an instrumented copy, checked to give identical output).
3. Fixed per-call overhead of ``process`` (fit of time per call vs chunk length).
4. A whole ``Patch.render`` (LFO -> Lorenz -> Output) for comparison with the "10x real
   time" rule of thumb.
5. The JavaScript benchmark ``rk4_bench.js`` run with every JS engine found on the machine
   (node, or Apple's JavaScriptCore shell, which ships with macOS), fed with the catalog
   tables and Python reference values so the JS box is checked to compute the same signal.

Outputs go to ``outputs/studies/cost/``: ``results.json``, ``summary.md``, ``js_<engine>.json``,
``bench_config.{js,json}``, ``cost_vs_substeps.png`` and ``breakdown.png``. JS result files
added there by hand (for example from a browser console run) are included in the summary.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

LAB = Path(__file__).resolve().parents[2]
OUT = LAB / "outputs" / "studies" / "cost"
OUT.mkdir(parents=True, exist_ok=True)
# Keep numba's on-disk cache out of src/ (the study must not write there).
os.environ.setdefault("NUMBA_CACHE_DIR", str(OUT / "numba_cache"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numba  # noqa: E402
import numpy as np  # noqa: E402

from chaotic_sound.blocks import Dynamical  # noqa: E402
from chaotic_sound.catalog import load_default_catalog  # noqa: E402
from chaotic_sound.dsp import dc_block, one_pole  # noqa: E402
from chaotic_sound.integrate import integrate_sampled, render_tuned  # noqa: E402
from chaotic_sound.patch import Patch  # noqa: E402
from chaotic_sound.pitch import note_to_hz  # noqa: E402
from chaotic_sound.systems import get_system  # noqa: E402

FS = 48_000.0
QUANTUM = 128  # AudioWorklet render quantum
PATCH_BLOCK = 512  # Patch.render default block size
NOTES = ("A1", "A3", "A5", "A7")
LFO_PERIOD_S = 4.0
BUDGET_US = QUANTUM / FS * 1e6  # 2666.7 µs per render quantum
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
BENCH_JS = Path(__file__).resolve().parent / "rk4_bench.js"

CAT = load_default_catalog()
SYSTEMS = list(CAT.entries)


# ------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------


def best_time(fn: Callable[[], Any], repeats: int) -> float:
    """Minimum CPU time (s) of ``fn()`` over ``repeats`` runs, with the GC disabled.

    Thread CPU time rather than wall time, so that time slices lost to other processes on a
    busy machine are not counted (on an idle core the two agree).
    """
    best = math.inf
    gc.disable()
    try:
        for _ in range(repeats):
            t0 = time.thread_time()
            fn()
            best = min(best, time.thread_time() - t0)
    finally:
        gc.enable()
    return best


def lfo(n: int) -> np.ndarray:
    """Return the Modulator's sine shape (spec §4.1), period LFO_PERIOD_S, from t = 0."""
    t = np.arange(n, dtype=np.float64) / FS
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * np.mod(t / LFO_PERIOD_S, 1.0)))


def make_block(system: str, note: str) -> Dynamical:
    b = Dynamical("osc", catalog=CAT, system=system, note=note)
    b.reset(FS)
    return b


def run_process(system: str, note: str, u: np.ndarray | None, n_total: int, chunk: int) -> float:
    """Wall time (s) of rendering ``n_total`` samples with ``Dynamical.process``."""
    b = make_block(system, note)
    t0 = time.perf_counter()
    for pos in range(0, n_total, chunk):
        n = min(chunk, n_total - pos)
        b.process(n, {"param": None if u is None else u[pos : pos + n], "amp": None})
    return time.perf_counter() - t0


STAGES = ("controls", "param_period", "kernel", "normalize", "dc_block")


def process_instrumented(
    b: Dynamical, n: int, u_in: np.ndarray | None, acc: dict[str, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Copy of ``Dynamical.process`` with a timer around each stage (spec §4.2 steps 1–9).

    Returns the output and the per-sample ``p_values`` and ``dtau`` given to the kernel.
    """
    pc = time.perf_counter
    t0 = pc()
    u_raw = np.full(n, b.knob_param) if u_in is None else np.asarray(u_in, dtype=np.float64)
    a_raw = np.full(n, b.params.amp)
    if b._u_state is None:
        b._u_state = np.array([u_raw[0]])
    u = np.empty(n)
    a = np.empty(n)
    one_pole(u_raw, b._u_state, b._alpha, u)
    one_pole(a_raw, b._a_state, b._alpha, a)
    t1 = pc()
    entry = b.entry
    p_values = entry.param_value(u)
    period = entry.period(u) if b.params.pitch_lock else np.full(n, b._period_unlocked)
    dtau = period * (b.frequency_hz / b.sample_rate)
    traj = np.empty((n, b.system.dim))
    t2 = pc()
    b.resets += int(
        render_tuned(
            b.system.rhs,
            b._x,
            b._p,
            b.system.modulated_index,
            p_values,
            dtau,
            entry.h_max,
            b._wrap,
            entry.bounds_lo,
            entry.bounds_hi,
            b._x_reset,
            traj,
        )
    )
    t3 = pc()
    left = b._audio(traj, b.observable, u, a)
    right = left if b.observable_right is None else b._audio(traj, b.observable_right, u, a)
    t4 = pc()
    out = np.empty((n, 2))
    dc_block(left, b._dc_state[0], b._dc_r, out[:, 0])
    dc_block(right, b._dc_state[1], b._dc_r, out[:, 1])
    t5 = pc()
    for key, dt in zip(STAGES, (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4), strict=True):
        acc[key] += dt
    return out, p_values, dtau


# ------------------------------------------------------------------------------------
# measurements
# ------------------------------------------------------------------------------------


def pure_step_cost(repeats: int, n_samples: int = 2000, sps: int = 1000) -> dict[str, float]:
    """Measure ns per RK4 step of the numba kernel (integrate_sampled, ``sps`` steps per sample)."""
    res = {}
    for name in SYSTEMS:
        sysdef, entry = get_system(name), CAT[name]
        p = sysdef.params_array()
        out = np.empty((n_samples, sysdef.dim))
        wrap = sysdef.wrap_mask()
        x = entry.initial_condition.copy()
        integrate_sampled(sysdef.rhs, x, p, entry.h_max, 2, out[:4], wrap)  # compile

        def run(sysdef: Any = sysdef, entry: Any = entry, p: Any = p, out: Any = out) -> None:
            x = entry.initial_condition.copy()
            integrate_sampled(sysdef.rhs, x, p, entry.h_max, sps, out, sysdef.wrap_mask())

        res[name] = best_time(run, repeats) / (n_samples * sps) * 1e9
    return res


@numba.njit(cache=False)
def _lorenz_scalar(st, p, h, nsteps):  # type: ignore[no-untyped-def]
    """Lorenz RK4 with scalar locals (the native ceiling); same op order as rk4_step."""
    s, r, b = p[0], p[1], p[2]
    x0, x1, x2 = st[0], st[1], st[2]
    h2, h6 = 0.5 * h, h / 6.0
    for _ in range(nsteps):
        a0, a1, a2 = s * (x1 - x0), x0 * (r - x2) - x1, x0 * x1 - b * x2
        u0, u1, u2 = x0 + h2 * a0, x1 + h2 * a1, x2 + h2 * a2
        b0, b1, b2 = s * (u1 - u0), u0 * (r - u2) - u1, u0 * u1 - b * u2
        v0, v1, v2 = x0 + h2 * b0, x1 + h2 * b1, x2 + h2 * b2
        c0, c1, c2 = s * (v1 - v0), v0 * (r - v2) - v1, v0 * v1 - b * v2
        w0, w1, w2 = x0 + h * c0, x1 + h * c1, x2 + h * c2
        e0, e1, e2 = s * (w1 - w0), w0 * (r - w2) - w1, w0 * w1 - b * w2
        x0 += h6 * (a0 + 2.0 * b0 + 2.0 * c0 + e0)
        x1 += h6 * (a1 + 2.0 * b1 + 2.0 * c1 + e1)
        x2 += h6 * (a2 + 2.0 * b2 + 2.0 * c2 + e2)
    st[0], st[1], st[2] = x0, x1, x2


@numba.njit(cache=False)
def _lorenz_scalar_pair(st, p, h, nsteps):  # type: ignore[no-untyped-def]
    """Two independent Lorenz states stepped in one loop (latency-bound test)."""
    s, r, b = p[0], p[1], p[2]
    x0, x1, x2, y0, y1, y2 = st[0], st[1], st[2], st[3], st[4], st[5]
    h2, h6 = 0.5 * h, h / 6.0
    for _ in range(nsteps):
        a0, a1, a2 = s * (x1 - x0), x0 * (r - x2) - x1, x0 * x1 - b * x2
        f0, f1, f2 = s * (y1 - y0), y0 * (r - y2) - y1, y0 * y1 - b * y2
        u0, u1, u2 = x0 + h2 * a0, x1 + h2 * a1, x2 + h2 * a2
        q0, q1, q2 = y0 + h2 * f0, y1 + h2 * f1, y2 + h2 * f2
        b0, b1, b2 = s * (u1 - u0), u0 * (r - u2) - u1, u0 * u1 - b * u2
        g0, g1, g2 = s * (q1 - q0), q0 * (r - q2) - q1, q0 * q1 - b * q2
        v0, v1, v2 = x0 + h2 * b0, x1 + h2 * b1, x2 + h2 * b2
        m0, m1, m2 = y0 + h2 * g0, y1 + h2 * g1, y2 + h2 * g2
        c0, c1, c2 = s * (v1 - v0), v0 * (r - v2) - v1, v0 * v1 - b * v2
        k0, k1, k2 = s * (m1 - m0), m0 * (r - m2) - m1, m0 * m1 - b * m2
        w0, w1, w2 = x0 + h * c0, x1 + h * c1, x2 + h * c2
        n0, n1, n2 = y0 + h * k0, y1 + h * k1, y2 + h * k2
        e0, e1, e2 = s * (w1 - w0), w0 * (r - w2) - w1, w0 * w1 - b * w2
        z0, z1, z2 = s * (n1 - n0), n0 * (r - n2) - n1, n0 * n1 - b * n2
        x0 += h6 * (a0 + 2.0 * b0 + 2.0 * c0 + e0)
        x1 += h6 * (a1 + 2.0 * b1 + 2.0 * c1 + e1)
        x2 += h6 * (a2 + 2.0 * b2 + 2.0 * c2 + e2)
        y0 += h6 * (f0 + 2.0 * g0 + 2.0 * k0 + z0)
        y1 += h6 * (f1 + 2.0 * g1 + 2.0 * k1 + z1)
        y2 += h6 * (f2 + 2.0 * g2 + 2.0 * k2 + z2)
    st[0], st[1], st[2], st[3], st[4], st[5] = x0, x1, x2, y0, y1, y2


@numba.njit(cache=False)
def _rossler_scalar(st, p, h, nsteps):  # type: ignore[no-untyped-def]
    """Rössler RK4 with scalar locals; same op order as rk4_step."""
    a, b, c = p[0], p[1], p[2]
    x0, x1, x2 = st[0], st[1], st[2]
    h2, h6 = 0.5 * h, h / 6.0
    for _ in range(nsteps):
        a0, a1, a2 = -x1 - x2, x0 + a * x1, b + x2 * (x0 - c)
        u0, u1, u2 = x0 + h2 * a0, x1 + h2 * a1, x2 + h2 * a2
        b0, b1, b2 = -u1 - u2, u0 + a * u1, b + u2 * (u0 - c)
        v0, v1, v2 = x0 + h2 * b0, x1 + h2 * b1, x2 + h2 * b2
        c0, c1, c2 = -v1 - v2, v0 + a * v1, b + v2 * (v0 - c)
        w0, w1, w2 = x0 + h * c0, x1 + h * c1, x2 + h * c2
        e0, e1, e2 = -w1 - w2, w0 + a * w1, b + w2 * (w0 - c)
        x0 += h6 * (a0 + 2.0 * b0 + 2.0 * c0 + e0)
        x1 += h6 * (a1 + 2.0 * b1 + 2.0 * c1 + e1)
        x2 += h6 * (a2 + 2.0 * b2 + 2.0 * c2 + e2)
    st[0], st[1], st[2] = x0, x1, x2


def native_scalar_cost(repeats: int, nsteps: int = 2_000_000) -> dict[str, Any]:
    """Measure ns per state-step of hand-specialized numba kernels with scalar locals.

    This is what LLVM makes of the loop without the generic array structure: a proxy for
    the best native/WASM code. The results are checked bit-for-bit against the engine.
    """
    res: dict[str, Any] = {}
    for name, fn, count in (
        ("lorenz", _lorenz_scalar, 1),
        ("lorenz", _lorenz_scalar_pair, 2),
        ("rossler", _rossler_scalar, 1),
    ):
        sysdef, entry = get_system(name), CAT[name]
        p, h = sysdef.params_array(), entry.h_max
        ic = np.tile(entry.initial_condition, count)
        # bit-for-bit check against the engine's generic kernel over 1000 steps
        st = ic.copy()
        fn(st, p, h, 1000)
        x = entry.initial_condition.copy()
        integrate_sampled(sysdef.rhs, x, p, h, 1, np.empty((1000, 3)), sysdef.wrap_mask())
        same = bool(np.array_equal(st[:3], x))
        t = best_time(lambda fn=fn, ic=ic, p=p, h=h: fn(ic.copy(), p, h, nsteps), repeats)
        res[f"{name}_x{count}"] = {"ns_per_state_step": t / (nsteps * count) * 1e9, "bitwise": same}
    return res


def reference_states(n_periods: float) -> dict[str, tuple[int, list[float]]]:
    """State after ~``n_periods`` default periods of fixed RK4 steps h_max from the catalog IC.

    Used to check the JS kernels. A short run keeps the chaotic amplification of any
    last-bit difference (e.g. a different libm sin) far below the comparison tolerance.
    """
    ref = {}
    for name in SYSTEMS:
        sysdef, entry = get_system(name), CAT[name]
        n_steps = round(n_periods * float(entry.period(entry.u_default)) / entry.h_max)
        x = entry.initial_condition.copy()
        out = np.empty((n_steps, sysdef.dim))
        integrate_sampled(
            sysdef.rhs, x, sysdef.params_array(), entry.h_max, 1, out, sysdef.wrap_mask()
        )
        ref[name] = (n_steps, x.tolist())
    return ref


def measure_config(
    system: str, note: str, modulated: bool, seconds: float, repeats: int
) -> dict[str, Any]:
    """All Python timings for one (system, note, modulation) configuration."""
    n_total = round(seconds * FS)
    u = lfo(n_total) if modulated else None
    entry, sysdef = CAT[system], get_system(system)

    # Instrumented pass: per-stage times, per-sample kernel inputs, and an output check.
    acc = dict.fromkeys(STAGES, 0.0)
    b = make_block(system, note)
    x_init = b._x.copy()
    outs, pvs, dts = [], [], []
    gc.disable()
    for pos in range(0, n_total, QUANTUM):
        n = min(QUANTUM, n_total - pos)
        o, pv, dt = process_instrumented(b, n, None if u is None else u[pos : pos + n], acc)
        outs.append(o)
        pvs.append(pv)
        dts.append(dt)
    gc.enable()
    out_instr = np.concatenate(outs)
    p_values, dtau = np.concatenate(pvs), np.concatenate(dts)
    ref = make_block(system, note)
    out_ref = np.concatenate(
        [
            ref.process(
                min(QUANTUM, n_total - pos),
                {"param": None if u is None else u[pos : pos + QUANTUM], "amp": None},
            )["out"]
            for pos in range(0, n_total, QUANTUM)
        ]
    )
    identical = bool(np.array_equal(out_instr, out_ref))

    n_sub = np.maximum(1, np.ceil(dtau / entry.h_max))
    steps = float(n_sub.sum())

    t128 = best_time(lambda: run_process(system, note, u, n_total, QUANTUM), repeats)
    t512 = best_time(lambda: run_process(system, note, u, n_total, PATCH_BLOCK), repeats)

    def kernel(chunk: int) -> None:
        x = x_init.copy()
        p = sysdef.params_array()
        traj = np.empty((n_total, sysdef.dim))
        for pos in range(0, n_total, chunk):
            sl = slice(pos, pos + chunk)
            render_tuned(
                sysdef.rhs,
                x,
                p,
                sysdef.modulated_index,
                p_values[sl],
                dtau[sl],
                entry.h_max,
                sysdef.wrap_mask(),
                entry.bounds_lo,
                entry.bounds_hi,
                x_init,
                traj[sl],
            )

    tk_whole = best_time(lambda: kernel(n_total), repeats)
    tk_128 = best_time(lambda: kernel(QUANTUM), repeats)
    total_instr = sum(acc.values())
    return {
        "system": system,
        "note": note,
        "f0": note_to_hz(note),
        "modulated": modulated,
        "seconds": seconds,
        "substeps_mean": float(n_sub.mean()),
        "substeps_min": int(n_sub.min()),
        "substeps_max": int(n_sub.max()),
        "rk4_steps": steps,
        "t_process_128": t128,
        "t_process_512": t512,
        "t_kernel_whole": tk_whole,
        "t_kernel_128": tk_128,
        "ns_per_step_in_kernel": tk_whole / steps * 1e9,
        "rtf_process_128": seconds / t128,
        "rtf_process_512": seconds / t512,
        "rtf_kernel": seconds / tk_whole,
        "breakdown_128": {k: v / total_instr for k, v in acc.items()},
        "t_instrumented_128": total_instr,
        "instrumented_output_identical": identical,
        "resets": int(b.resets),
    }


def call_overhead(repeats: int) -> dict[str, Any]:
    """Time per ``process`` call vs chunk length (Lorenz A3, static); linear fit a + b·n."""
    n_total = round(1.0 * FS)
    sizes = [16, 32, 64, 128, 256, 512, 1024, 4096, 16384]
    per_call = []
    for c in sizes:
        t = best_time(lambda c=c: run_process("lorenz", "A3", None, n_total, c), repeats)
        per_call.append(t / math.ceil(n_total / c))
    pc = np.array(per_call)
    b, a = np.polyfit(np.array(sizes, dtype=float), pc, 1, w=1.0 / pc)
    return {
        "chunk_sizes": sizes,
        "us_per_call": (pc * 1e6).tolist(),
        "fit_us_per_call_fixed": a * 1e6,
        "fit_ns_per_sample": b * 1e9,
    }


def patch_render(seconds: float, repeats: int) -> dict[str, float]:
    """Whole-patch render time (LFO -> Lorenz A3 with pitch lock -> Output)."""

    def build() -> Patch:
        p = Patch(catalog=CAT)
        p.add_block("dynamical", "osc", system="lorenz", note="A3", pitch_lock=True)
        p.add_block("modulator", "lfo", shape="sine", period_s=LFO_PERIOD_S, mode="loop")
        p.add_block("output", "out", volume=1.0)
        p.connect("lfo.out", "osc.param")
        p.connect("osc.out", "out.in")
        return p

    res = {}
    for bs in (QUANTUM, PATCH_BLOCK):
        p = build()
        t = best_time(lambda p=p, bs=bs: p.render(seconds, sample_rate=FS, block_size=bs), repeats)
        res[f"rtf_block_{bs}"] = seconds / t
    return res


# ------------------------------------------------------------------------------------
# JavaScript
# ------------------------------------------------------------------------------------


def bench_config(quick: bool) -> dict[str, Any]:
    """Catalog tables and Python reference values for rk4_bench.js."""
    refs = reference_states(10.0)
    systems = []
    for name in SYSTEMS:
        s, e = get_system(name), CAT[name]
        obs = e.default_observable
        systems.append(
            {
                "name": name,
                "dim": s.dim,
                "params": list(s.default_params),
                "mod": s.modulated_index,
                "wrap": list(s.phase_indices),
                "ic": e.initial_condition.tolist(),
                "lo": e.bounds_lo.tolist(),
                "hi": e.bounds_hi.tolist(),
                "h_max": e.h_max,
                "p_min": e.p_min,
                "p_max": e.p_max,
                "u_default": e.u_default,
                "u_grid": e.u_grid.tolist(),
                "period": e.period_table.tolist(),
                "mean": e.observables[obs].mean.tolist(),
                "std": e.observables[obs].std.tolist(),
                "obs": s.variable_index(obs),
                "ref_steps": refs[name][0],
                "ref_x": refs[name][1],
            }
        )
    # Box-level check: the first 0.1 s of the Python block, every 10th sample (left channel).
    validation = []
    n_val, stride = 4800, 10
    for system, note, modulated in (
        ("lorenz", "A3", False),
        ("lorenz", "A3", True),
        ("rossler", "A5", True),
        ("duffing", "A3", True),
    ):
        b = make_block(system, note)
        x_init = b._x.tolist()
        u = lfo(n_val) if modulated else None
        out = b.process(n_val, {"param": u, "amp": None})["out"][:, 0]
        validation.append(
            {
                "system": system,
                "note": note,
                "f0": note_to_hz(note),
                "modulated": modulated,
                "x_init": x_init,
                "n_samples": n_val,
                "stride": stride,
                "expected": out[::stride].tolist(),
            }
        )
    b = make_block("lorenz", "A3")
    return {
        "quick": quick,
        "fs": FS,
        "seconds": 1.0 if quick else 4.0,
        "lfo_period_s": LFO_PERIOD_S,
        "alpha": b._alpha,
        "dc_r": b._dc_r,
        "notes": [{"name": n, "f0": note_to_hz(n)} for n in NOTES],
        "multibox": multibox_scenarios(),
        "multibox_seconds": 0.5 if quick else 1.0,
        "systems": systems,
        "box_validation": validation,
    }


def multibox_scenarios() -> list[dict[str, Any]]:
    """Patches of many boxes for the JS multi-box test (all boxes LFO-modulated)."""
    a3 = [[name, note_to_hz("A3")] for name in SYSTEMS]
    grid = [[name, note_to_hz(n)] for n in NOTES for name in SYSTEMS]
    return [
        {"label": "5 boxes: each system at A3", "boxes": a3},
        {"label": "40 boxes: 8 of each system at A3", "boxes": a3 * 8},
        {"label": "20 boxes: every system x {A1,A3,A5,A7}", "boxes": grid},
        {"label": "40 boxes: 2 x every system x {A1,A3,A5,A7}", "boxes": grid * 2},
        {
            "label": "10 boxes: Thomas at A7 (most expensive)",
            "boxes": [["thomas", note_to_hz("A7")]] * 10,
        },
    ]


def attach_js_metadata(res: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Add f0 to each JS box row and the box list to each multi-box row (for the summary)."""
    f0 = {n["name"]: n["f0"] for n in cfg["notes"]}
    for b in res["box"]:
        b["f0"] = f0[b["note"]]
    for m, scen in zip(res["multibox"], cfg["multibox"], strict=True):
        m["box_list"] = scen["boxes"]


LOWER_IS_BETTER = ("us_per_quantum", "ns_per_sample", "ns_per_step", "ns_per_state_step")


def merge_min(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine repeated JS runs: keep the fastest value of every timing (min over runs)."""
    out = json.loads(json.dumps(runs[0]))
    for key in ("step", "box", "multibox", "deopt"):
        for i, row in enumerate(out.get(key, [])):
            for k, v in row.items():
                if isinstance(v, float) and k.startswith(LOWER_IS_BETTER):
                    row[k] = min(r[key][i][k] for r in runs)
                elif k == "realtime_factor":
                    row[k] = max(r[key][i][k] for r in runs)
    out["runs_merged"] = len(runs)
    return out


def run_js(cfg: dict[str, Any], n_runs: int) -> list[dict[str, Any]]:
    """Run rk4_bench.js ``n_runs`` times with every JS engine available (fastest values kept)."""
    cfg_json = OUT / "bench_config.json"
    cfg_js = OUT / "bench_config.js"
    runners = []
    node = shutil.which("node")
    if node:
        runners.append(("node", [node, str(BENCH_JS), str(cfg_json)]))
    if JSC.exists():
        runners.append(("jsc", [str(JSC), str(cfg_js), str(BENCH_JS)]))
    results = []
    for engine, cmd in runners:
        cfg_e = dict(cfg, engine=engine)
        cfg_json.write_text(json.dumps(cfg_e))
        cfg_js.write_text("var BENCH_CONFIG = " + json.dumps(cfg_e) + ";\n")
        t0 = time.perf_counter()
        runs = []
        for _ in range(n_runs):
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
            lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT_JSON ")]
            if proc.returncode != 0 or not lines:
                print(f"[js] {engine} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
                break
            runs.append(json.loads(lines[-1][len("RESULT_JSON ") :]))
        if not runs:
            continue
        res = merge_min(runs)
        attach_js_metadata(res, cfg)
        res["wall_s"] = time.perf_counter() - t0
        (OUT / f"js_{engine}.json").write_text(json.dumps(res, indent=1))
        print(f"[js] {engine}: done in {res['wall_s']:.1f} s")
        results.append(res)
    if not runners:
        print("[js] no JavaScript engine found (node, jsc); JS numbers must be estimated")
    return results


# ------------------------------------------------------------------------------------
# report helpers
# ------------------------------------------------------------------------------------


def md_table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def summarize(res: dict[str, Any], js: list[dict[str, Any]]) -> str:
    parts = []
    env = res["env"]
    parts.append(
        f"Machine: {env['cpu']}, {env['python']}, numba {env['numba']}, numpy {env['numpy']}. "
        f"Load average before/after: {env['load_before']} / {env['load_after']}."
    )
    parts.append("\n### Pure RK4 step (ns), numba vs JS\n")
    hdr = ["system", "numba (engine)"]
    for r in js:
        hdr += [
            f"{r['engine']} A spec.",
            f"{r['engine']} B mono",
            f"{r['engine']} B mega",
            f"{r['engine']} 1 state",
            f"{r['engine']} 2 interleaved (per state)",
        ]
    rows = []
    for name in SYSTEMS:
        row = [name, f"{res['pure_step_ns'][name]:.1f}"]
        for r in js:
            s = next(x for x in r["step"] if x["system"] == name)
            row += [
                f"{s['ns_per_step_A_specialized']:.1f}",
                f"{s['ns_per_step_B_generic_mono']:.1f}",
                f"{s['ns_per_step_B_generic_mega']:.1f}",
                f"{s.get('ns_per_state_step_interleaved_1', float('nan')):.1f}",
                f"{s.get('ns_per_state_step_interleaved_2', float('nan')):.1f}",
            ]
        rows.append(row)
    parts.append(md_table(hdr, rows))
    parts.append("\nNative ceiling (numba, scalar locals): " + json.dumps(res["native_scalar"]))

    parts.append("\n### Python engine per configuration (4 s of audio)\n")
    rows = []
    for c in res["configs"]:
        rows.append(
            [
                c["system"],
                c["note"],
                "LFO" if c["modulated"] else "-",
                f"{c['substeps_mean']:.2f} ({c['substeps_min']}–{c['substeps_max']})",
                f"{c['ns_per_step_in_kernel']:.1f}",
                f"{c['rtf_kernel']:.0f}",
                f"{c['rtf_process_512']:.0f}",
                f"{c['rtf_process_128']:.0f}",
                f"{100 * c['breakdown_128']['kernel']:.0f}",
            ]
        )
    parts.append(
        md_table(
            [
                "system",
                "note",
                "mod",
                "substeps mean (min–max)",
                "ns/step in kernel",
                "RTF kernel",
                "RTF process@512",
                "RTF process@128",
                "kernel % @128",
            ],
            rows,
        )
    )
    co = res["call_overhead"]
    parts.append(
        f"\nprocess() per-call fixed cost ≈ {co['fit_us_per_call_fixed']:.1f} µs, "
        f"plus {co['fit_ns_per_sample']:.0f} ns/sample (Lorenz A3, static). "
        f"Patch render RTF (LFO→Lorenz A3→Out): {res['patch']}"
    )
    for r in js:
        parts.append(
            f"\n### JS full box, {r['engine']} (µs per 128-sample quantum; budget "
            f"{BUDGET_US:.0f} µs)\n"
        )
        rows = []
        for b in r["box"]:
            rows.append(
                [
                    b["system"],
                    b["note"],
                    "LFO" if b["modulated"] else "-",
                    f"{b['us_per_quantum']:.1f}",
                    f"{b['ns_per_sample']:.0f}",
                    f"{b['realtime_factor']:.0f}",
                    f"{0.5 * BUDGET_US / b['us_per_quantum']:.0f}",
                ]
            )
        parts.append(
            md_table(
                ["system", "note", "mod", "µs/quantum", "ns/sample", "RTF", "boxes @50 % core"],
                rows,
            )
        )
        parts.append("\nMulti-box (LFO on all boxes; 'sum of singles' adds the table above):\n")
        lut = {(b["system"], round(b["f0"], 6)): b for b in r["box"] if b["modulated"]}
        rows = []
        for m in r["multibox"]:
            pred = sum(lut[(n, round(f0, 6))]["us_per_quantum"] for n, f0 in m["box_list"])
            rows.append(
                [
                    m["label"],
                    f"{m['us_per_quantum']:.0f}",
                    f"{pred:.0f}",
                    f"{m['us_per_quantum'] / m['boxes']:.1f}",
                    f"{100 * m['us_per_quantum'] / BUDGET_US:.0f}",
                ]
            )
        parts.append(
            md_table(["patch", "µs/quantum", "sum of singles", "µs/box", "% of budget"], rows)
        )
        if r.get("deopt"):
            parts.append("\nJIT type pollution (Rössler A1, static): " + json.dumps(r["deopt"]))
        parts.append("\nValidation: " + json.dumps(r["validation"]))
    return "\n".join(parts) + "\n"


def plot(res: dict[str, Any], js: list[dict[str, Any]]) -> None:
    configs = res["configs"]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ss = np.array([c["substeps_mean"] for c in configs])
    markers = {"t_process_128": "o", "t_process_512": "s", "t_kernel_whole": "^"}
    labels = {
        "t_process_128": "Python process(), 128-sample chunks",
        "t_process_512": "Python process(), 512-sample chunks",
        "t_kernel_whole": "numba render_tuned alone",
    }
    for key, m in markers.items():
        frac = np.array([c[key] / c["seconds"] for c in configs])
        ax.scatter(ss, 100 * frac, marker=m, label=labels[key], alpha=0.8)
    for r in js:
        lut = {(b["system"], b["note"], b["modulated"]): b for b in r["box"]}
        xs, ys = [], []
        for c in configs:
            b = lut.get((c["system"], c["note"], c["modulated"]))
            if b:
                xs.append(c["substeps_mean"])
                ys.append(100 / b["realtime_factor"])
        ax.scatter(xs, ys, marker="x", label=f"JS full box ({r['engine']}), 128-sample quanta")
    ax.axhline(100, color="k", lw=0.8)
    ax.axhline(50, color="k", lw=0.8, ls="--")
    ax.text(1.02, 52, "50 % of one core", fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("RK4 sub-steps per sample (mean over the render)")
    ax.set_ylabel("CPU time per second of audio (% of one core), one box")
    ax.set_title("Cost of one dynamical box at 48 kHz (A1, A3, A5, A7; static and LFO)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "cost_vs_substeps.png", dpi=130)
    plt.close(fig)

    # Breakdown of Python process() at 128-sample chunks: % per stage, static knob.
    sel = [c for c in configs if not c["modulated"]]
    fig, ax = plt.subplots(figsize=(10, 4))
    xlab = [f"{c['system']}\n{c['note']}" for c in sel]
    bottom = np.zeros(len(sel))
    for st in STAGES:
        v = np.array([100 * c["breakdown_128"][st] for c in sel])
        ax.bar(range(len(sel)), v, bottom=bottom, label=st)
        bottom += v
    for i, c in enumerate(sel):
        us = 1e6 * c["t_instrumented_128"] / (c["seconds"] * FS / QUANTUM)
        ax.text(i, 101, f"{us:.0f}", ha="center", fontsize=7)
    ax.set_xticks(range(len(sel)), xlab, fontsize=7)
    ax.set_ylim(0, 108)
    ax.set_ylabel("% of process() time")
    ax.set_title(
        "Python Dynamical.process(), 128-sample chunks, static knob (top: µs per chunk)",
        fontsize=10,
    )
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(OUT / "breakdown.png", dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------------------------


def js_only(n_runs: int) -> None:
    """Rerun only the JS benchmark and merge it into the previous results (see --js-only)."""
    res = json.loads((OUT / "results.json").read_text())
    cfg = bench_config(quick=False)
    old = {r["engine"]: r for r in res["js"]}
    new = run_js(cfg, n_runs)
    for r in new:
        if r["engine"] in old:
            merged = merge_min([old[r["engine"]], r])
            merged["runs_merged"] = old[r["engine"]].get("runs_merged", 1) + r["runs_merged"]
            attach_js_metadata(merged, cfg)
            (OUT / f"js_{r['engine']}.json").write_text(json.dumps(merged, indent=1))
            old[r["engine"]] = merged
        else:
            old[r["engine"]] = r
    res["js"] = list(old.values())
    res["env"]["load_js_only"] = [round(x, 2) for x in os.getloadavg()]
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    summary = summarize(res, res["js"])
    (OUT / "summary.md").write_text(summary)
    plot(res, res["js"])
    print(summary)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="1 s renders, fewer repeats")
    ap.add_argument("--no-js", action="store_true", help="skip the JavaScript benchmark")
    ap.add_argument(
        "--js-only",
        type=int,
        metavar="N",
        help="reuse results.json, run the JS benchmark N more times and merge (min) with the "
        "existing js_<engine>.json, then rewrite summary and figures",
    )
    args = ap.parse_args()
    if args.js_only:
        js_only(args.js_only)
        return
    seconds = 1.0 if args.quick else 4.0
    repeats = 2 if args.quick else 3
    t_start = time.perf_counter()
    cpu = (
        subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or platform.processor()
    )
    env = {
        "cpu": cpu,
        "python": platform.python_version(),
        "numba": numba.__version__,
        "numpy": np.__version__,
        "load_before": [round(x, 2) for x in os.getloadavg()],
    }

    # Warm-up: compile every kernel specialization once (excluded from all timings).
    for name in SYSTEMS:
        run_process(name, "A3", lfo(1024), 1024, QUANTUM)

    res: dict[str, Any] = {"env": env}
    res["pure_step_ns"] = pure_step_cost(repeats=5)
    print("pure step ns:", {k: round(v, 1) for k, v in res["pure_step_ns"].items()})
    res["native_scalar"] = native_scalar_cost(repeats=5)
    print("native scalar:", res["native_scalar"])
    res["configs"] = []
    for name in SYSTEMS:
        for note in NOTES:
            for modulated in (False, True):
                c = measure_config(name, note, modulated, seconds, repeats)
                res["configs"].append(c)
                print(
                    f"{name:8s} {note} {'LFO' if modulated else '   '} "
                    f"sub={c['substeps_mean']:6.2f} ns/step={c['ns_per_step_in_kernel']:5.1f} "
                    f"RTF kernel={c['rtf_kernel']:6.0f} p512={c['rtf_process_512']:6.0f} "
                    f"p128={c['rtf_process_128']:6.0f} same={c['instrumented_output_identical']}"
                )
    res["call_overhead"] = call_overhead(repeats)
    res["patch"] = {k: round(v, 1) for k, v in patch_render(seconds, repeats).items()}
    print("call overhead:", res["call_overhead"], "patch:", res["patch"])
    env["load_after"] = [round(x, 2) for x in os.getloadavg()]

    cfg = bench_config(args.quick)
    js = [] if args.no_js else run_js(cfg, n_runs=1 if args.quick else 3)
    for f in sorted(OUT.glob("js_*.json")):  # include hand-added runs (e.g. a browser)
        if f.stem[3:] not in {r["engine"] for r in js}:
            extra = json.loads(f.read_text())
            if "box_list" not in extra["multibox"][0]:
                attach_js_metadata(extra, cfg)
            js.append(extra)
    res["js"] = js
    res["wall_s"] = time.perf_counter() - t_start
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    summary = summarize(res, js)
    (OUT / "summary.md").write_text(summary)
    plot(res, js)
    print(summary)
    print(f"total wall time {res['wall_s']:.0f} s; outputs in {OUT}")


if __name__ == "__main__":
    main()
