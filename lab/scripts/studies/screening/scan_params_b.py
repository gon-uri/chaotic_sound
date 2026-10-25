"""Screening batch B, step 2: coarse scan of every parameter of every candidate.

For each parameter we sweep 41 values over ``d ± 0.75·|d|`` (continuation from the default,
``QUICK_SETTINGS``) and record: chaotic fraction, the contiguous chaotic band around the default
(``select_chaotic_range`` with the catalog builder's tolerances), prominence of the tuning
observable and, for forced systems, the ratio of the observable's spectral-peak period to the
drive period.

Run from ``lab/`` (about a minute)::

    NUMBA_CACHE_DIR=<scratch> uv run python scripts/studies/screening/scan_params_b.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from dysts_adapter_b import make_system  # noqa: E402

from chaotic_sound.analysis.catalog_builder import (  # noqa: E402
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

OUT = Path(__file__).resolve().parents[3] / "outputs" / "studies" / "screening" / "batch_b"

# name -> (phase index, drive parameter)
SYSTEMS = {
    "HindmarshRose": (None, None),
    "HastingsPowell": (None, None),
    "ForcedVanDerPol": (2, "w"),
    "ForcedBrusselator": (2, "w"),
    "RabinovichFabrikant": (None, None),
    "Hadley": (None, None),
    "ChenLee": (None, None),
    "Bouali": (None, None),
    "Bouali2": (None, None),
}
N_POINTS = 41
SPAN = 0.75


def scan(name: str, par: str, phase: int | None, drive: str | None) -> dict[str, object]:
    import dysts.flows

    d = float(getattr(dysts.flows, name)().params[par])
    half = SPAN * abs(d) if d != 0 else 0.05
    rng = (d - half, d + half)
    s = make_system(name, par, rng, phase_index=phase, drive_param=drive)
    ref = reference_scale(s, SWEEP_SETTINGS)
    dp = analyze_point(s, s.default_value, ref, DEFAULT_SETTINGS)
    obs = choose_tuning_observable(dp)
    method = choose_period_method(s, dp, obs, 0.25)
    drive_p = s.drive_period()
    vals = np.unique(np.append(np.linspace(rng[0], rng[1], N_POINTS), d))
    res = sweep(s, vals, ref, QUICK_SETTINGS)
    lam = np.array([r.lyapunov * ref.period if r.bounded else np.nan for r in res])
    bounded = np.array([r.bounded for r in res])
    chaotic = np.nan_to_num(lam, nan=-1) > 0.05
    prom = np.array([r.variables[obs].prominence if r.bounded else np.nan for r in res])
    ratio = np.array(
        [
            r.variables[obs].centroid_period / s.drive_period(s.params_array(**{par: r.value}))
            if (r.bounded and drive_p is not None)
            else np.nan
            for r in res
        ]
    )
    row: dict[str, object] = {
        "system": name,
        "param": par,
        "default": d,
        "scan": list(rng),
        "observable": obs,
        "method": method,
        "default_lamP": dp.lyapunov * ref.period,
        "default_prom": dp.variables[obs].prominence,
        "bounded_frac": float(bounded.mean()),
        "chaotic_frac": float(chaotic.mean()),
        "values": vals.tolist(),
        "lamP": lam.tolist(),
        "prom": prom.tolist(),
        "ratio_to_drive": ratio.tolist(),
    }

    def period_of(r):  # type: ignore[no-untyped-def]
        if method == "drive":
            return s.drive_period(s.params_array(**{par: r.value}))
        return point_period(r, obs, method, drive_p)

    def drift_of(r):  # type: ignore[no-untyped-def]
        return r.variables[obs].drift if r.bounded else math.inf

    try:
        sel = select_chaotic_range(
            res, d, ref.period, period_of, drift_of,
            max_window_width=0.03 * (rng[1] - rng[0]),
            escape_margin=0.03 * (rng[1] - rng[0]),
        )  # fmt: skip
        row.update(
            band=[sel.lo, sel.hi],
            band_rel_width=(sel.hi - sel.lo) / abs(d) if d else (sel.hi - sel.lo),
            lo_reason=sel.lo_reason,
            hi_reason=sel.hi_reason,
            windows=len(sel.windows),
        )
    except RuntimeError as e:
        row.update(band=None, band_rel_width=0.0, lo_reason=str(e), hi_reason="", windows=0)
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.time()
    for name, (phase, drive) in SYSTEMS.items():
        import dysts.flows

        params = sorted(getattr(dysts.flows, name)().params)
        for par in params:
            if par == drive:
                pass  # drive frequency is a legitimate knob too (P = 2π/w is exact)
            try:
                row = scan(name, par, phase, drive)
            except Exception as e:  # noqa: BLE001
                print(f"{name}.{par}: FAILED {e}")
                continue
            rows.append(row)
            band = row["band"]
            bstr = f"[{band[0]:.4g}, {band[1]:.4g}]" if band else "—"
            rat = np.array(row["ratio_to_drive"], dtype=float)
            rstr = (
                f" P_obs/T_drive∈[{np.nanmin(rat):.3g},{np.nanmax(rat):.3g}]"
                if np.any(np.isfinite(rat))
                else ""
            )
            print(
                f"{name}.{par} (d={row['default']:.4g}, scan {row['scan'][0]:.4g}..{row['scan'][1]:.4g}): "
                f"bounded {100 * row['bounded_frac']:.0f}% chaotic {100 * row['chaotic_frac']:.0f}% "
                f"band {bstr} rel {row['band_rel_width']:.3f} win {row['windows']} "
                f"| {row['lo_reason']} / {row['hi_reason']} | obs {row['observable']} "
                f"prom∈[{np.nanmin(row['prom']):.2f},{np.nanmax(row['prom']):.2f}]{rstr}",
                flush=True,
            )
    (OUT / "param_scan.json").write_text(json.dumps(rows, indent=1))
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
