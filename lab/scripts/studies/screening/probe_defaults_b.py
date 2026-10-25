"""Screening batch B, step 1: verify wrappers and measure each candidate at its dysts default."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dysts_adapter_b import make_system, verify_against_dysts  # noqa: E402

from chaotic_sound.analysis.sweep import DEFAULT_SETTINGS, SWEEP_SETTINGS, analyze_point, reference_scale  # noqa: E402

# (dysts name, modulated param placeholder, candidate range placeholder, phase idx, drive param)
CANDIDATES = [
    ("HindmarshRose", "c", None, None),
    ("HastingsPowell", "b1", None, None),
    ("ForcedVanDerPol", "a", 2, "w"),
    ("ForcedBrusselator", "f", 2, "w"),
    ("RabinovichFabrikant", "g", None, None),
    ("Hadley", "f", None, None),
    ("ChenLee", "c", None, None),
    ("Bouali", "b", None, None),
    ("Bouali2", "b", None, None),
]


def main() -> None:
    for name, par, phase, drive in CANDIDATES:
        import dysts.flows

        d = float(getattr(dysts.flows, name)().params[par])
        rng = (d - abs(d) * 0.5 - 1e-3, d + abs(d) * 0.5 + 1e-3)
        s = make_system(name, par, rng, phase_index=phase, drive_param=drive)
        t0 = time.time()
        err = verify_against_dysts(s)
        try:
            ref = reference_scale(s, SWEEP_SETTINGS)
            pt = analyze_point(s, s.default_value, ref, DEFAULT_SETTINGS)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: verify={err:.1e} FAILED {e}")
            continue
        dt = time.time() - t0
        lam = pt.lyapunov * ref.period
        print(
            f"{name}: verify={err:.1e} params={dict(zip(s.param_names, s.default_params))} "
            f"P_ref={ref.period:.4g} (hint {s.period_hint:.4g}) bounded={pt.bounded} "
            f"stationary={pt.stationary} lamP={lam:.3f}  [{dt:.1f}s]"
        )
        if s.drive_period():
            print(f"    drive period 2pi/w = {s.drive_period():.4g}")
        for v, st in pt.variables.items():
            print(
                f"    {v}: mean={st.mean:.4g} std={st.std:.4g} peakP={st.peak_period:.4g} "
                f"centroidP={st.centroid_period:.4g} prom={st.prominence:.3f} "
                f"ret={st.return_time:.4g} drift={st.drift:.3f} [{st.minimum:.3g},{st.maximum:.3g}]"
            )


if __name__ == "__main__":
    main()
