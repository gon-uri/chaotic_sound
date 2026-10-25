"""Screening batch B, step 3: wider scans of the most promising parameters (QUICK settings)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from dysts_adapter_b import make_system  # noqa: E402

from chaotic_sound.analysis.catalog_builder import choose_tuning_observable  # noqa: E402
from chaotic_sound.analysis.sweep import (  # noqa: E402
    DEFAULT_SETTINGS,
    QUICK_SETTINGS,
    SWEEP_SETTINGS,
    analyze_point,
    reference_scale,
    sweep,
)

JOBS = [
    ("ChenLee", "c", (-5.0, -0.1), None, None, None),
    ("ChenLee", "c", (-5.0, -0.1), None, None, {"c": -3.8}),
    ("ForcedBrusselator", "f", (0.02, 0.25), 2, "w", None),
]


def main() -> None:
    for name, par, rng, phase, drive, over in JOBS:
        s = make_system(name, par, rng, phase_index=phase, drive_param=drive, overrides=over)
        ref = reference_scale(s, SWEEP_SETTINGS)
        dp = analyze_point(s, s.default_value, ref, DEFAULT_SETTINGS)
        obs = choose_tuning_observable(dp)
        print(f"== {name}.{par} default {s.default_value} P_ref={ref.period:.4g} obs {obs} "
              f"lamP={dp.lyapunov * ref.period:.3f} "
              + " ".join(f"{v}:prom={st.prominence:.2f},P={st.centroid_period:.4g}"
                         for v, st in dp.variables.items()))
        vals = np.linspace(rng[0], rng[1], 47)
        res = sweep(s, vals, ref, QUICK_SETTINGS)
        for r in res:
            if not r.bounded:
                print(f"  {r.value:8.4g} UNBOUNDED")
                continue
            st = r.variables[obs]
            lam = r.lyapunov * ref.period
            extra = ""
            if s.drive_period() is not None:
                extra = f" P/T={st.centroid_period / s.drive_period(s.params_array(**{par: r.value})):.3f}"
            print(f"  {r.value:8.4g} lamP={lam:6.3f} prom={st.prominence:.2f} "
                  f"Pc={st.centroid_period:.4g} ret={st.return_time:.4g}{extra} {'C' if lam > 0.05 else '.'}")


if __name__ == "__main__":
    main()
