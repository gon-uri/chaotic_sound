"""Coarse exploration for screening set "Halvorsen": which parameter to modulate.

For every candidate system: check our RHS against dysts, measure P_ref and the default point
(prominence of every variable, λ·P_ref), then run a coarse continuation sweep (QUICK settings)
of each plausible parameter over ×0.5…×1.5 of its default, and report the chaotic run around
the default. The best parameter of each system then gets the full catalog pipeline in
``halvorsen_set_screen.py``.

Run from lab/:  uv run python scripts/studies/screening/halvorsen_set_explore.py
Writes lab/outputs/studies/screening/halvorsen_set/explore.json
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from halvorsen_set_adapter import make_system, use_uncached_kernels, verify_rhs

from chaotic_sound.analysis.sweep import (
    QUICK_SETTINGS,
    analyze_point,
    reference_scale,
    sweep,
)

OUT = Path(__file__).parents[3] / "outputs" / "studies" / "screening" / "halvorsen_set"
N_POINTS = 41
LYAP_THRESHOLD = 0.05

# (dysts class, parameter, custom kernel key or None)
OPTIONS: list[tuple[str, str, str | None]] = [
    ("Halvorsen", "a", None),
    ("Halvorsen", "b", None),
    ("Aizawa", "a", None),
    ("Aizawa", "b", None),
    ("Aizawa", "d", None),
    ("Aizawa", "e", None),
    ("Dadras", "p", None),
    ("Dadras", "r", None),
    ("Dadras", "e", None),
    ("Dadras", "o", None),
    ("SprottB", "b", "sprottb_b"),
    ("SprottB", "c", "sprottb_c"),
    ("SprottD", "a", "sprottd"),
    ("ShimizuMorioka", "a", None),
    ("ShimizuMorioka", "b", None),
    ("Lorenz84", "f", None),
    ("Lorenz84", "g", None),
    ("Lorenz84", "a", None),
    ("BurkeShaw", "e", None),
    ("BurkeShaw", "n", None),
]


def default_of(dysts_name: str, param: str, custom: str | None) -> float:
    import dysts.flows

    if custom is not None:
        return {"sprottb_b": 1.0, "sprottb_c": 1.0, "sprottd": 3.0}[custom]
    return float(getattr(dysts.flows, dysts_name)().params[param])


def chaotic_run(vals: np.ndarray, ok: list[bool], i0: int) -> tuple[float, float]:
    """Contiguous run of chaotic points around index i0 (no window tolerance)."""
    if not ok[i0]:
        return math.nan, math.nan
    lo = hi = i0
    while lo - 1 >= 0 and ok[lo - 1]:
        lo -= 1
    while hi + 1 < len(vals) and ok[hi + 1]:
        hi += 1
    return float(vals[lo]), float(vals[hi])


def main() -> None:
    use_uncached_kernels()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    defaults_done: set[str] = set()
    for dysts_name, param, custom in OPTIONS:
        t0 = time.time()
        d = default_of(dysts_name, param, custom)
        system = make_system(dysts_name, param, (0.5 * d, 1.5 * d), custom=custom)
        err = verify_rhs(system)
        settings = QUICK_SETTINGS
        try:
            ref = reference_scale(system, settings)
        except RuntimeError as exc:
            print(f"{dysts_name}.{param}: {exc}")
            rows.append({"system": dysts_name, "param": param, "error": str(exc)})
            continue
        default_point = analyze_point(system, d, ref, settings)
        vals = np.unique(np.append(np.linspace(0.5 * d, 1.5 * d, N_POINTS), d))
        res = sweep(system, vals, ref, settings)
        ok = [r.is_chaotic(ref.period, LYAP_THRESHOLD) for r in res]
        i0 = int(np.argmin(np.abs(vals - d)))
        lo, hi = chaotic_run(vals, ok, i0)
        n_unb = sum(not r.bounded for r in res)
        unb_vals = [float(r.value) for r in res if not r.bounded]
        prom = {v: round(s.prominence, 3) for v, s in default_point.variables.items()}
        row = {
            "system": dysts_name,
            "param": param,
            "custom": custom,
            "default": d,
            "rhs_err": err,
            "P_ref": ref.period,
            "lyap_P_default": default_point.lyapunov * ref.period,
            "prominence_default": prom,
            "peak_period_default": {
                v: round(s.centroid_period, 4) for v, s in default_point.variables.items()
            },
            "return_time_default": {
                v: round(s.return_time, 4) for v, s in default_point.variables.items()
            },
            "chaotic_fraction_sweep": float(np.mean(ok)),
            "run_lo": lo,
            "run_hi": hi,
            "run_rel_width": (hi - lo) / d if math.isfinite(lo) else 0.0,
            "n_unbounded": n_unb,
            "unbounded_min_max": [min(unb_vals), max(unb_vals)] if unb_vals else None,
            "lyapP": [round(r.lyapunov * ref.period, 3) if r.bounded else None for r in res],
            "values": [float(v) for v in vals],
            "seconds": time.time() - t0,
        }
        rows.append(row)
        defaults_done.add(dysts_name)
        print(
            f"{dysts_name:15s} {param:2s} d={d:<7g} err={err:.1e} Pref={ref.period:.4g} "
            f"λP={row['lyap_P_default']:.3f} prom={prom} "
            f"chaotic={row['chaotic_fraction_sweep']:.2f} "
            f"run=[{lo:.4g},{hi:.4g}] rel={row['run_rel_width']:.2f} unb={n_unb} "
            f"{row['unbounded_min_max']} ({row['seconds']:.1f}s)",
            flush=True,
        )
    (OUT / "explore.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
