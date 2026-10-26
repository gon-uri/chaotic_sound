"""Compute cost of one dynamical box, and what it implies for the browser engine (engine v0.3).

Study report: ``docs/studies/cost.md``. Usage (from ``lab/``; about 10 minutes with Chrome)::

    caffeinate -is uv run python scripts/studies/cost.py [--quick] [--no-js] [--chrome]

What it measures (all at fs = 48 kHz, compile time excluded by warm-up calls):

1. Pure RK4 step cost of the numba engine kernel per system (``integrate_sampled`` with 1000
   steps per recorded sample, so per-sample overhead is negligible), and of hand-written
   numba kernels with scalar locals (the native ceiling), checked bit for bit against it.
2. For every system x note (A1, A3, A5, A7) x {static knob at the default, full-range 4 s sine
   LFO on ``param``}: wall time of ``Dynamical.process`` in 128-sample chunks (an AudioWorklet
   render quantum) and 512-sample chunks (``Patch.render`` default), the time of
   ``render_tuned`` alone on the same per-sample inputs, the RK4 sub-steps per sample, and a
   per-stage breakdown of ``process`` (an instrumented copy, checked to give identical output).
3. Fixed per-call overhead of ``process`` (fit of time per call vs chunk length).
4. A whole ``Patch.render`` (LFO -> Lorenz -> Output).
5. The JavaScript benchmark ``rk4_bench.js``, run 3 times in separate processes with Apple's
   JavaScriptCore shell (ships with macOS) and node if installed, and once in headless Google
   Chrome (V8) with ``--chrome``. It is fed the catalog tables and Python reference outputs, so
   the JS box is checked to compute the same signal as the Python block. Its last section
   times fresh copies of the box code from their first call (JIT warm-up), with a
   ``Float64Array`` or a ``null`` control input and a switch between the two.

Outputs go to ``outputs/studies/cost/``: ``results.json``, ``summary.md``, ``js_<engine>.json``,
``bench_config.{js,json}``, ``cost_vs_substeps.png`` and ``breakdown.png``. JS result files
added there by hand (for example saved from ``rk4_bench.html`` in a browser) are included in
the summary.
"""

from __future__ import annotations

import argparse
import gc
import html
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import tempfile
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

import chaotic_sound  # noqa: E402
from chaotic_sound.blocks import BlockContext, Dynamical  # noqa: E402
from chaotic_sound.blocks.dynamical import (  # noqa: E402
    AMP_EXPONENT,
    DECLICK_TIME_S,
    PARAM_SLEW_PERIODS,
)
from chaotic_sound.catalog import default_catalog_path, load_default_catalog  # noqa: E402
from chaotic_sound.dsp import dc_block, one_pole, one_pole_varying  # noqa: E402
from chaotic_sound.integrate import integrate_sampled, render_tuned  # noqa: E402
from chaotic_sound.patch import Patch  # noqa: E402
from chaotic_sound.pitch import note_to_hz, note_to_midi  # noqa: E402
from chaotic_sound.systems import get_system  # noqa: E402

FS = 48_000.0
QUANTUM = 128  # AudioWorklet render quantum
PATCH_BLOCK = 512  # Patch.render default block size
NOTES = ("A1", "A3", "A5", "A7")
LFO_PERIOD_S = 4.0
BUDGET_US = QUANTUM / FS * 1e6  # 2666.7 µs per render quantum
HALF_BUDGET_US = 0.5 * BUDGET_US
PITCH_Q = 0.8  # pitch-input value used by the JS 'pitch' mode (midi_min = note − 12, span 15)
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
BENCH_JS = Path(__file__).resolve().parent / "rk4_bench.js"
TWO_PI = 2.0 * math.pi

CAT = load_default_catalog()
CTX = BlockContext(catalog=CAT)
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


def make_block(system: str, note: str, **params: Any) -> Dynamical:
    b = Dynamical("osc", context=CTX, system=system, note=note, **params)
    b.reset(FS)
    return b


def u_worst(system: str) -> float:
    """Knob position where P(u), and with it the number of RK4 sub-steps, is largest."""
    e = CAT[system]
    return float(e.u_grid[int(np.argmax(e.period_table))])


def substeps(system: str, u: float, f0: float, fs: float = FS) -> int:
    """Return the sub-steps per sample n = ⌈P(u)·f₀/fs / h_max⌉ (spec §4.2 step 6)."""
    e = CAT[system]
    return max(1, math.ceil(float(e.period(u)) * f0 / fs / e.h_max))


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
    """Copy of ``Dynamical.process`` (v0.3, no pitch cable) with a timer around each stage.

    Returns the output and the per-sample ``p_values`` and ``dtau`` given to the kernel.
    """
    pc = time.perf_counter
    t0 = pc()
    freq = b._frequency(n, None)
    u_raw = np.full(n, b.knob_param) if u_in is None else u_in
    a_raw = np.full(n, b.params.amp)
    if b._u_state is None:
        b._u_state = np.array([u_raw[0]])
    tau = np.maximum(DECLICK_TIME_S, PARAM_SLEW_PERIODS / freq)
    alpha_u = 1.0 - np.exp(-1.0 / (tau * b.sample_rate))
    u = np.empty(n)
    a = np.empty(n)
    one_pole_varying(u_raw, b._u_state, alpha_u, u)
    one_pole(a_raw, b._a_state, b._alpha, a)
    gain = a**AMP_EXPONENT if b.params.amp_curve == "perceptual" else a
    t1 = pc()
    entry = b.entry
    p_values = entry.param_value(u)
    period = entry.period(u) if b.params.pitch_lock else np.full(n, b._period_unlocked)
    dtau = period * freq / b.sample_rate
    traj = np.empty((n, b.system.dim))
    t2 = pc()
    b.resets += int(
        render_tuned(
            b.system.rhs, b._x, b._p, b.system.modulated_index, p_values, dtau,
            entry.h_max, b._wrap, entry.bounds_lo, entry.bounds_hi, b._x_reset, traj,
        )
    )  # fmt: skip
    t3 = pc()
    left = b._audio(traj, b.observable, u, gain)
    right = left if b.observable_right is None else b._audio(traj, b.observable_right, u, gain)
    t4 = pc()
    out = np.empty((n, 2))
    dc_block(left, b._dc_state[0], b._dc_r, out[:, 0])
    dc_block(right, b._dc_state[1], b._dc_r, out[:, 1])
    t5 = pc()
    for key, dt in zip(STAGES, (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4), strict=True):
        acc[key] += dt
    return out, p_values, dtau


# ------------------------------------------------------------------------------------
# measurements: numba
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


# Scalar-local right-hand sides, same operation order as chaotic_sound.systems.
@numba.njit(cache=False)
def _f_lorenz(x0, x1, x2, p):  # type: ignore[no-untyped-def]
    return p[0] * (x1 - x0), x0 * (p[1] - x2) - x1, x0 * x1 - p[2] * x2


@numba.njit(cache=False)
def _f_rossler(x0, x1, x2, p):  # type: ignore[no-untyped-def]
    return -x1 - x2, x0 + p[0] * x1, p[1] + x2 * (x0 - p[2])


@numba.njit(cache=False)
def _f_chua(x0, x1, x2, p):  # type: ignore[no-untyped-def]
    hh = p[3] * x0 + 0.5 * (p[2] - p[3]) * (abs(x0 + 1.0) - abs(x0 - 1.0))
    return p[0] * (x1 - x0 - hh), x0 - x1 + x2, -p[1] * x1


@numba.njit(cache=False)
def _f_rikitake(x0, x1, x2, p):  # type: ignore[no-untyped-def]
    return -p[1] * x0 + x1 * x2, -p[1] * x1 - p[0] * x0 + x0 * x2, 1.0 - x0 * x1


@numba.njit(cache=False)
def _f_duffing(x0, x1, x2, p):  # type: ignore[no-untyped-def]
    return x1, -p[2] * x1 - p[1] * x0 - p[0] * x0**3 + p[3] * np.cos(x2), p[4]


SCALAR_RHS = {
    "lorenz": _f_lorenz,
    "rossler": _f_rossler,
    "chua": _f_chua,
    "rikitake": _f_rikitake,
    "duffing": _f_duffing,
}


def _scalar_kernel(f: Any, wrap_z: bool) -> Any:
    """Native RK4 loop with scalar locals for a 3-variable RHS ``f`` (wraps z if a phase)."""

    @numba.njit(cache=False)
    def kern(st, p, h, n_samples, sps):  # type: ignore[no-untyped-def]
        x0, x1, x2 = st[0], st[1], st[2]
        h2, h6 = 0.5 * h, h / 6.0
        for _ in range(n_samples):
            for _ in range(sps):
                a0, a1, a2 = f(x0, x1, x2, p)
                u0, u1, u2 = x0 + h2 * a0, x1 + h2 * a1, x2 + h2 * a2
                b0, b1, b2 = f(u0, u1, u2, p)
                v0, v1, v2 = x0 + h2 * b0, x1 + h2 * b1, x2 + h2 * b2
                c0, c1, c2 = f(v0, v1, v2, p)
                w0, w1, w2 = x0 + h * c0, x1 + h * c1, x2 + h * c2
                e0, e1, e2 = f(w0, w1, w2, p)
                x0 += h6 * (a0 + 2.0 * b0 + 2.0 * c0 + e0)
                x1 += h6 * (a1 + 2.0 * b1 + 2.0 * c1 + e1)
                x2 += h6 * (a2 + 2.0 * b2 + 2.0 * c2 + e2)
            if wrap_z:
                x2 = x2 % TWO_PI
        st[0], st[1], st[2] = x0, x1, x2

    return kern


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


def native_scalar_cost(repeats: int, n_samples: int = 2000, sps: int = 1000) -> dict[str, Any]:
    """Measure ns per step of hand-specialized numba kernels with scalar locals (all systems).

    This is what LLVM makes of the loop without the generic array structure: a proxy for
    the best native/WASM scalar code. Each kernel is checked bit for bit against the engine
    kernel over 2000 steps (``integrate_sampled`` with one step per sample).
    """
    res: dict[str, Any] = {}
    for name in SYSTEMS:
        sysdef, entry = get_system(name), CAT[name]
        p, h = sysdef.params_array(), entry.h_max
        kern = _scalar_kernel(SCALAR_RHS[name], bool(sysdef.wrap_mask()[2]))
        st = entry.initial_condition.copy()
        kern(st, p, h, 2000, 1)
        x = entry.initial_condition.copy()
        integrate_sampled(sysdef.rhs, x, p, h, 1, np.empty((2000, 3)), sysdef.wrap_mask())
        same = bool(np.array_equal(st, x))
        t = best_time(
            lambda kern=kern, entry=entry, p=p, h=h: kern(
                entry.initial_condition.copy(), p, h, n_samples, sps
            ),
            repeats,
        )
        res[name] = {"ns_per_step": t / (n_samples * sps) * 1e9, "bitwise": same}
    sysdef, entry = get_system("lorenz"), CAT["lorenz"]
    p, h, nsteps = sysdef.params_array(), entry.h_max, n_samples * sps
    ic = np.tile(entry.initial_condition, 2)
    _lorenz_scalar_pair(ic.copy(), p, h, 10)
    t = best_time(lambda: _lorenz_scalar_pair(ic.copy(), p, h, nsteps), repeats)
    res["lorenz_x2"] = {"ns_per_state_step": t / (2 * nsteps) * 1e9}
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
                sysdef.rhs, x, p, sysdef.modulated_index, p_values[sl], dtau[sl], entry.h_max,
                sysdef.wrap_mask(), entry.bounds_lo, entry.bounds_hi, x_init, traj[sl],
            )  # fmt: skip

    tk_whole = best_time(lambda: kernel(n_total), repeats)
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
                "u_worst": u_worst(name),
                "u_grid": e.u_grid.tolist(),
                "period": e.period_table.tolist(),
                "mean": e.observables[obs].mean.tolist(),
                "std": e.observables[obs].std.tolist(),
                "peak": e.observables[obs].peak.tolist(),
                "obs": s.variable_index(obs),
                "ref_steps": refs[name][0],
                "ref_x": refs[name][1],
            }
        )
    # Box-level check: the first 0.1 s of the Python block, every 10th sample (left channel).
    validation = []
    n_val, stride, n_short = 4800, 10, 480
    t = np.arange(n_val) / FS
    pitch_wobble = 0.5 + 0.4 * np.sin(2 * np.pi * 20.0 * t)  # 20 Hz pitch wobble, A2..C4
    for system, note, modulated, pitch, linear in (
        ("lorenz", "A3", False, False, False),
        ("lorenz", "A3", True, False, False),
        ("lorenz", "A3", True, True, False),
        ("lorenz", "A3", True, False, True),
        ("rossler", "A5", True, False, False),
        ("chua", "A5", True, False, False),
        ("rikitake", "A5", True, False, False),
        ("duffing", "A3", True, False, False),
    ):
        kw: dict[str, Any] = {"pitch_min": "A2", "pitch_max": "C4"} if pitch else {}
        if linear:
            kw["amp_curve"] = "linear"
        b = make_block(system, note, **kw)
        x_init = b._x.tolist()
        u = lfo(n_val) if modulated else None
        q = pitch_wobble if pitch else None
        out = b.process(n_val, {"param": u, "amp": None, "pitch": q})["out"][:, 0]
        row = {
            "system": system,
            "note": note,
            "f0": note_to_hz(note),
            "modulated": modulated,
            "x_init": x_init,
            "n_samples": n_val,
            "short_samples": n_short,
            "stride": stride,
            "expected": out[::stride].tolist(),
            "linear": linear,
        }
        if pitch:
            row |= {
                "pitch_signal": pitch_wobble.tolist(),
                "midi_min": b.midi_min,
                "midi_max": b.midi_max,
            }
        validation.append(row)
    b = make_block("lorenz", "A3")
    return {
        "quick": quick,
        "fs": FS,
        "seconds": 1.0 if quick else 4.0,
        "lfo_period_s": LFO_PERIOD_S,
        "alpha": b._alpha,
        "dc_r": b._dc_r,
        "amp_exponent": AMP_EXPONENT,
        "pitch_q": PITCH_Q,
        "notes": [{"name": n, "f0": note_to_hz(n), "midi": note_to_midi(n)} for n in NOTES],
        "multibox": multibox_scenarios(),
        "multibox_seconds": 1.0 if quick else LFO_PERIOD_S,
        "systems": systems,
        "box_validation": validation,
    }


def multibox_scenarios() -> list[dict[str, Any]]:
    """Patches of many boxes for the JS multi-box test (all boxes LFO-modulated)."""
    a3 = [[name, note_to_hz("A3")] for name in SYSTEMS]
    a7 = [[name, note_to_hz("A7")] for name in SYSTEMS]
    grid = [[name, note_to_hz(n)] for n in NOTES for name in SYSTEMS]
    return [
        {"label": "5 boxes: each system at A3", "boxes": a3},
        {"label": "40 boxes: 8 of each system at A3", "boxes": a3 * 8},
        {"label": "20 boxes: every system x {A1,A3,A5,A7}", "boxes": grid},
        {"label": "40 boxes: 2 x every system x {A1,A3,A5,A7}", "boxes": grid * 2},
        {"label": "16 boxes at A7: 3 of each system + 1 Lorenz", "boxes": a7 * 3 + a7[:1]},
    ]


def _median(xs: list[float]) -> float:
    return float(statistics.median(xs))


def merge_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine repeated JS runs (separate processes) into one result with the spread.

    Step costs: ``key`` is the minimum over runs, ``key_max`` the maximum. Box and multi-box
    rows: ``us_per_quantum`` (min), ``us_median``, ``us_max`` over every timed repetition of
    every run; tail statistics of the per-quantum distribution are the median over runs
    (``max`` is the maximum).
    """
    out = json.loads(json.dumps(runs[0]))
    for i, row in enumerate(out["step"]):
        for k, v in list(row.items()):
            if isinstance(v, float):
                vals = [r["step"][i][k] for r in runs]
                row[k], row[k + "_max"] = min(vals), max(vals)
    for key in ("box", "multibox"):
        for i, row in enumerate(out[key]):
            reps = [x for r in runs for x in r[key][i]["us_per_quantum_reps"]]
            row["us_per_quantum"] = min(reps)
            row["us_median"] = _median(reps)
            row["us_max"] = max(reps)
            row["us_per_quantum_reps"] = reps
            dists = [r[key][i]["dist_us"] for r in runs]
            row["dist_us"] = {
                s: (max if s == "max" else _median)([d[s] for d in dists]) for s in dists[0]
            }
            if key == "box":
                row["ns_per_sample"] = row["us_median"] * 1e3 / QUANTUM
                row["realtime_factor"] = BUDGET_US / row["us_median"]
    for i, row in enumerate(out.get("deopt", [])):
        # JIT test: per block of quanta, the median, min and max over runs.
        blocks = list(zip(*(r["deopt"][i]["blocks_us"] for r in runs), strict=True))
        row["blocks_us"] = [_median(list(b)) for b in blocks]
        row["blocks_us_min"] = [min(b) for b in blocks]
        row["blocks_us_max"] = [max(b) for b in blocks]
    out["validation"] = [
        {
            **v,
            **{
                k: max(r["validation"][j][k] for r in runs)
                for k in v
                if k.startswith("max_abs_diff")
            },
        }
        for j, v in enumerate(runs[0]["validation"])
    ]
    out["timer_resolution_us"] = max(r.get("timer_resolution_us", 0.0) for r in runs)
    out["runs_merged"] = len(runs)
    return out


def attach_js_metadata(res: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Add f0 to each JS box row and the box list to each multi-box row (for the summary)."""
    f0 = {n["name"]: n["f0"] for n in cfg["notes"]}
    for b in res["box"]:
        b["f0"] = f0[b["note"]]
    for m, scen in zip(res["multibox"], cfg["multibox"], strict=True):
        m["box_list"] = scen["boxes"]


def _parse_result(stdout: str) -> dict[str, Any] | None:
    lines = [ln for ln in html.unescape(stdout).splitlines() if "RESULT_JSON " in ln]
    if not lines:
        return None
    text = lines[-1].split("RESULT_JSON ", 1)[1]
    text = text[: text.rfind("}") + 1]
    result: dict[str, Any] = json.loads(text)
    return result


def chrome_command(cfg_e: dict[str, Any], profile: Path) -> list[str]:
    """Headless Chrome running rk4_bench.js in a page (V8, with a throwaway profile)."""
    page = OUT / "bench_headless.html"
    rel = os.path.relpath(BENCH_JS, OUT)
    page.write_text(
        "<!doctype html>\n<html><head><meta charset='utf-8'><title>RK4 bench</title></head>"
        "<body>\n<script src='bench_config.js'></script>\n"
        f"<script src='{rel}'></script>\n<pre id='out'></pre>\n<script>"
        "document.getElementById('out').textContent = 'RESULT' + '_JSON ' + "
        "JSON.stringify(BENCH_RESULTS);</script>\n</body></html>\n"
    )
    return [
        str(CHROME),
        "--headless",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile}",
        "--dump-dom",
        page.as_uri(),
    ]


def run_js(cfg: dict[str, Any], n_runs: int, chrome: bool) -> list[dict[str, Any]]:
    """Run rk4_bench.js with every JS engine available (``n_runs`` processes each)."""
    cfg_json = OUT / "bench_config.json"
    cfg_js = OUT / "bench_config.js"
    runners: list[tuple[str, Callable[[Path], list[str]], int]] = []
    node = shutil.which("node")
    if node:
        runners.append(
            ("node", lambda _p: [node, "--no-warnings", str(BENCH_JS), str(cfg_json)], n_runs)
        )
    if JSC.exists():
        runners.append(("jsc", lambda _p: [str(JSC), str(cfg_js), str(BENCH_JS)], n_runs))
    if chrome and CHROME.exists():
        runners.append(("chrome", lambda p: chrome_command(dict(cfg, engine="chrome"), p), 1))
    results = []
    for engine, cmd, runs_wanted in runners:
        cfg_e = dict(cfg, engine=engine)
        cfg_json.write_text(json.dumps(cfg_e))
        cfg_js.write_text("var BENCH_CONFIG = " + json.dumps(cfg_e) + ";\n")
        t0 = time.perf_counter()
        runs = []
        for _ in range(runs_wanted):
            with tempfile.TemporaryDirectory() as profile:
                proc = subprocess.run(
                    cmd(Path(profile)), capture_output=True, text=True, timeout=900, check=False
                )
            parsed = _parse_result(proc.stdout)
            if proc.returncode != 0 or parsed is None:
                print(f"[js] {engine} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
                break
            runs.append(parsed)
        if not runs:
            continue
        res = merge_runs(runs)
        attach_js_metadata(res, cfg)
        res["wall_s"] = time.perf_counter() - t0
        (OUT / f"js_{engine}.json").write_text(json.dumps(res, indent=1))
        print(f"[js] {engine}: {len(runs)} run(s) in {res['wall_s']:.1f} s")
        results.append(res)
    if not runners:
        print("[js] no JavaScript engine found (node, jsc); JS numbers must be estimated")
    return results


# ------------------------------------------------------------------------------------
# analysis and report helpers
# ------------------------------------------------------------------------------------


def substep_table(res: dict[str, Any]) -> list[dict[str, Any]]:
    """Per system: P ratios, n at the default and worst knob per note, LFO n (measured)."""
    rows = []
    for name in SYSTEMS:
        e = CAT[name]
        pmin = float(e.period_table.min())
        row: dict[str, Any] = {
            "system": name,
            "p_def_over_p_min": float(e.period(e.u_default)) / pmin,
            "p_max_over_p_min": float(e.period_table.max()) / pmin,
            "u_default": e.u_default,
            "u_worst": u_worst(name),
        }
        for note in NOTES:
            f0 = note_to_hz(note)
            n_def = substeps(name, e.u_default, f0)
            cont = e.steps_per_period * float(e.period(e.u_default)) / pmin * f0 / FS
            lfo_c = next(
                c for c in res["configs"] if c["system"] == name and c["note"] == note
                and c["modulated"]
            )  # fmt: skip
            row[note] = {
                "n_default": n_def,
                "n_worst": substeps(name, u_worst(name), f0),
                "n_lfo_mean": lfo_c["substeps_mean"],
                "n_lfo_min": lfo_c["substeps_min"],
                "n_lfo_max": lfo_c["substeps_max"],
                "rounding_factor": n_def / cont,
                "n_default_44k1": substeps(name, e.u_default, f0, 44_100.0),
            }
        rows.append(row)
    return rows


def overhead_fit(js: dict[str, Any], table: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit ns/sample = c0 + c1·n per system on the JS 'default' and 'worst' box rows.

    c1 is the step cost inside the box, c0 the per-sample bookkeeping that is not hidden
    behind the RK4 chain. Also the extra ns/sample of a pitch cable ('pitch' − 'default') and
    of the perceptual amp curve ('default' − 'linear'), and c0 refitted on the 'linear' rows.
    """
    tab = {r["system"]: r for r in table}
    out = {}
    for name in SYSTEMS:
        ns, nn, ns_lin, nn_lin = [], [], [], []
        pitch_extra, pow_extra = {}, {}
        for b in js["box"]:
            if b["system"] != name:
                continue
            nt = tab[name][b["note"]]
            if b["mode"] in ("default", "worst"):
                nn.append(nt["n_default"] if b["mode"] == "default" else nt["n_worst"])
                ns.append(b["us_median"] * 1e3 / QUANTUM)
            if b["mode"] == "linear":
                nn_lin.append(nt["n_default"])
                ns_lin.append(b["us_median"] * 1e3 / QUANTUM)
        for note in NOTES:
            rows = {b["mode"]: b for b in js["box"] if b["system"] == name and b["note"] == note}
            us = {m: rows[m]["us_median"] for m in ("pitch", "default", "linear")}
            pitch_extra[note] = (us["pitch"] - us["default"]) * 1e3 / QUANTUM
            pow_extra[note] = (us["default"] - us["linear"]) * 1e3 / QUANTUM
        c1, c0 = np.polyfit(np.array(nn, float), np.array(ns), 1)
        c0_lin = float(np.mean(np.array(ns_lin) - c1 * np.array(nn_lin, float)))
        out[name] = {
            "c0_ns": float(c0),
            "c1_ns": float(c1),
            "c0_linear_ns": c0_lin,
            "pitch_extra_ns": pitch_extra,
            "perceptual_extra_ns": pow_extra,
        }
    return out


def md_table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def summarize(res: dict[str, Any], js: list[dict[str, Any]]) -> str:
    parts = []
    env = res["env"]
    parts.append(
        f"Engine chaotic_sound {env['engine_version']}, catalog generated "
        f"{env['catalog_generated']}. Machine: {env['cpu']}, Python {env['python']}, numba "
        f"{env['numba']}, numpy {env['numpy']}. Load average before/after: "
        f"{env['load_before']} / {env['load_after']}."
    )
    parts.append("\n### Sub-steps per sample (catalog; LFO columns measured)\n")
    rows = []
    for r in res["substeps"]:
        cells = [r["system"], f"{r['p_def_over_p_min']:.3f}", f"{r['p_max_over_p_min']:.3f}"]
        for note in NOTES:
            c = r[note]
            cells.append(
                f"{c['n_default']} / {c['n_worst']} / {c['n_lfo_mean']:.1f} "
                f"({c['n_lfo_min']}–{c['n_lfo_max']}) ×{c['rounding_factor']:.2f}"
            )
        rows.append(cells)
    parts.append(
        md_table(
            ["system", "P_def/P_min", "P_max/P_min"]
            + [f"{n}: default / worst / LFO mean (min–max) ×ceil" for n in NOTES],
            rows,
        )
    )
    parts.append("\n### Pure RK4 step (ns): numba engine, numba scalar, JS (min–max over runs)\n")
    hdr = ["system", "numba engine", "numba scalar (bitwise)"]
    for r in js:
        e = r["engine"]
        hdr += [f"{e} A spec.", f"{e} B mono", f"{e} B mega", f"{e} 1 st.", f"{e} 2 interl."]
    rows = []
    for name in SYSTEMS:
        ns = res["native_scalar"][name]
        row = [
            name,
            f"{res['pure_step_ns'][name]:.1f}",
            f"{ns['ns_per_step']:.1f} ({ns['bitwise']})",
        ]
        for r in js:
            s = next(x for x in r["step"] if x["system"] == name)

            def mm(k: str, s: dict[str, Any] = s) -> str:
                hi = s.get(k + "_max", s[k])
                return f"{s[k]:.1f}–{hi:.1f}" if hi > s[k] * 1.005 else f"{s[k]:.1f}"

            row += [
                mm("ns_per_step_A_specialized"),
                mm("ns_per_step_B_generic_mono"),
                mm("ns_per_step_B_generic_mega"),
                mm("ns_per_state_step_interleaved_1"),
                mm("ns_per_state_step_interleaved_2"),
            ]
        rows.append(row)
    parts.append(md_table(hdr, rows))
    parts.append(
        f"\nnumba scalar, 2 Lorenz states interleaved: "
        f"{res['native_scalar']['lorenz_x2']['ns_per_state_step']:.1f} ns per state-step."
    )

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
                f"{100 * c['breakdown_128']['controls']:.0f}",
                c["instrumented_output_identical"],
            ]
        )
    parts.append(
        md_table(
            [
                "system", "note", "mod", "substeps mean (min–max)", "ns/step in kernel",
                "RTF kernel", "RTF process@512", "RTF process@128", "kernel % @128",
                "controls % @128", "instr. identical",
            ],
            rows,
        )
    )  # fmt: skip
    co = res["call_overhead"]
    parts.append(
        f"\nprocess() per-call fixed cost ≈ {co['fit_us_per_call_fixed']:.1f} µs, "
        f"plus {co['fit_ns_per_sample']:.0f} ns/sample (Lorenz A3, static). "
        f"Patch render RTF (LFO→Lorenz A3→Out): {res['patch']}"
    )
    for r in js:
        parts.append(
            f"\n### JS full box, {r['engine']} ({r.get('runs_merged', 1)} run(s); timer "
            f"resolution {r.get('timer_resolution_us', float('nan')):.2f} µs). µs per "
            f"128-sample quantum; budget {BUDGET_US:.0f} µs\n"
        )
        parts.append(
            "mean = min / median / max over all timed repetitions; p99, max and peak16 (largest "
            "16-quantum moving average) from the per-quantum rep; boxes = ⌊1333 µs / median⌋ "
            "(rounded down: a fraction of a box does not fit).\n"
        )
        rows = []
        for b in r["box"]:
            d = b["dist_us"]
            rows.append(
                [
                    b["system"],
                    b["note"],
                    b["mode"],
                    f"{b['us_per_quantum']:.1f} / {b['us_median']:.1f} / {b['us_max']:.1f}",
                    f"{d['p99']:.1f}",
                    f"{d['max']:.0f}",
                    f"{d['peak16']:.1f}",
                    f"{b['ns_per_sample']:.0f}",
                    f"{math.floor(HALF_BUDGET_US / b['us_median'])}",
                    b["resets"],
                ]
            )
        parts.append(
            md_table(
                [
                    "system", "note", "mode", "mean µs (min/med/max)", "p99", "max", "peak16",
                    "ns/sample", "boxes @50 %", "resets",
                ],
                rows,
            )
        )  # fmt: skip
        if r["engine"] in res.get("overhead_fit", {}):
            parts.append("\nPer-sample model ns/sample = c0 + c1·n (default + worst rows):\n")
            fit = res["overhead_fit"][r["engine"]]
            parts.append(
                md_table(
                    ["system", "c0 (ns)", "c1 (ns/step)", "c0 linear amp (ns)"]
                    + [f"pitch cable extra {n} (ns)" for n in NOTES]
                    + [f"a^1.661 extra {n} (ns)" for n in NOTES],
                    [
                        [k, f"{v['c0_ns']:.1f}", f"{v['c1_ns']:.1f}", f"{v['c0_linear_ns']:.1f}"]
                        + [f"{v['pitch_extra_ns'][n]:.1f}" for n in NOTES]
                        + [f"{v['perceptual_extra_ns'][n]:.1f}" for n in NOTES]
                        for k, v in fit.items()
                    ],
                )
            )
        parts.append("\nMulti-box (LFO on all boxes, 4 s = one LFO cycle):\n")
        lut = {(b["system"], round(b["f0"], 6)): b for b in r["box"] if b["mode"] == "lfo"}
        rows = []
        for m in r["multibox"]:
            pred = sum(lut[(n, round(f0, 6))]["us_median"] for n, f0 in m["box_list"])
            d = m["dist_us"]
            rows.append(
                [
                    m["label"],
                    f"{m['us_per_quantum']:.0f} / {m['us_median']:.0f} / {m['us_max']:.0f}",
                    f"{pred:.0f}",
                    f"{d['peak16']:.0f}",
                    f"{d['p99']:.0f}",
                    f"{d['max']:.0f}",
                    f"{100 * m['us_median'] / BUDGET_US:.0f}",
                    f"{100 * d['peak16'] / BUDGET_US:.0f}",
                ]
            )
        parts.append(
            md_table(
                [
                    "patch", "mean µs (min/med/max)", "sum of single medians", "peak16", "p99",
                    "max", "% budget (median)", "% budget (peak16)",
                ],
                rows,
            )
        )  # fmt: skip
        jit = [d for d in r.get("deopt", []) if "blocks_us" in d]
        if jit:
            parts.append(
                f"\nJIT warm-up and control-input type (Rössler A1, static knob; fresh code "
                f"copies in this order; µs per quantum in blocks of {jit[0]['block_quanta']} "
                "quanta, median (min–max) over runs):\n"
            )
            rows = []
            for d in jit:
                nb = d["blocks_per_input"]
                for j, kind in enumerate(d["inputs"]):
                    sl = slice(j * nb, (j + 1) * nb)
                    cells = zip(
                        d["blocks_us"][sl],
                        d.get("blocks_us_min", d["blocks_us"])[sl],
                        d.get("blocks_us_max", d["blocks_us"])[sl],
                        strict=True,
                    )
                    rows.append(
                        [" → ".join(d["inputs"]), kind]
                        + [f"{m:.2f} ({lo:.2f}–{hi:.2f})" for m, lo, hi in cells]
                    )
            nb = jit[0]["blocks_per_input"]
            parts.append(
                md_table(["copy (inputs)", "input"] + [f"block {k + 1}" for k in range(nb)], rows)
            )
        elif r.get("deopt"):  # an older result file
            parts.append("\nJIT test (older format): " + json.dumps(r["deopt"]))
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
        ax.scatter(ss, 100 * frac, marker=m, label=labels[key], alpha=0.6)
    tab = {r["system"]: r for r in res["substeps"]}
    for r, mk in zip(js, ("x", "+", "1"), strict=False):
        xs, ys = [], []
        for b in r["box"]:
            if b["mode"] not in ("default", "worst"):
                continue
            nt = tab[b["system"]][b["note"]]
            xs.append(nt["n_default"] if b["mode"] == "default" else nt["n_worst"])
            ys.append(100 * b["us_median"] / BUDGET_US)
        ax.scatter(xs, ys, marker=mk, s=40, label=f"JS full box ({r['engine']}), 128-sample quanta")
    ax.axhline(100, color="k", lw=0.8)
    ax.axhline(50, color="k", lw=0.8, ls="--")
    ax.text(1.02, 52, "50 % of one core", fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("RK4 sub-steps per sample")
    ax.set_ylabel("CPU time per second of audio (% of one core), one box")
    ax.set_title("Cost of one dynamical box at 48 kHz, engine v0.3 (A1–A7)", fontsize=10)
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
        "Python Dynamical.process() (v0.3), 128-sample chunks, static knob (top: µs per chunk)",
        fontsize=10,
    )
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(OUT / "breakdown.png", dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="1 s renders, fewer repeats")
    ap.add_argument("--no-js", action="store_true", help="skip the JavaScript benchmark")
    ap.add_argument(
        "--chrome", action="store_true", help="also run the JS benchmark once in headless Chrome"
    )
    args = ap.parse_args()
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
        "engine_version": chaotic_sound.__version__,
        "catalog": str(default_catalog_path()),
        "catalog_generated": CAT.metadata.get("generated"),
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
    res["substeps"] = substep_table(res)
    env["load_after"] = [round(x, 2) for x in os.getloadavg()]

    cfg = bench_config(args.quick)
    js = [] if args.no_js else run_js(cfg, 1 if args.quick else 3, args.chrome)
    for f in sorted(OUT.glob("js_*.json")):  # include hand-added runs (e.g. a browser)
        if f.stem[3:] not in {r["engine"] for r in js} and not args.no_js:
            extra = json.loads(f.read_text())
            if "box_list" not in extra["multibox"][0]:
                attach_js_metadata(extra, cfg)
            if "us_median" in extra["box"][0]:
                js.append(extra)
    res["js"] = js
    res["overhead_fit"] = {r["engine"]: overhead_fit(r, res["substeps"]) for r in js}
    env["load_end"] = [round(x, 2) for x in os.getloadavg()]
    res["wall_s"] = time.perf_counter() - t_start
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    summary = summarize(res, js)
    (OUT / "summary.md").write_text(summary)
    plot(res, js)
    print(summary)
    print(f"total wall time {res['wall_s']:.0f} s; outputs in {OUT}")


if __name__ == "__main__":
    main()
