"""Screening set "Halvorsen": escape and pitch robustness of the leading candidates.

Uses the entries written by ``halvorsen_set_screen.py`` (catalog_screening.json) and renders
the engine's ``Dynamical`` block (systems registered in-process only) under stress:

- held at the range ends u = 0 and u = 1, 20 s at A3;
- slow sweep u(t) = ½ − ½·cos(2πt/T), T = 4 s, 20 s at A3;
- fast sweep T = 0.25 s at A1 (only ≈ 14 oscillation cycles per sweep: far from adiabatic).

8 seeds each. Counts safety resets (state left the catalog's bounds box), "collapses" (last
second RMS < 0.1, i.e. the trajectory fell onto a fixed point or a small cycle) and the
largest normalized excursion |audio|/RMS_TARGET.

Run from lab/:  uv run python scripts/studies/screening/halvorsen_set_robustness.py
Writes lab/outputs/studies/screening/halvorsen_set/robustness.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from halvorsen_set_adapter import make_system, register, use_uncached_kernels
from halvorsen_set_screen import CONFIGS, OUT

from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import Catalog

FS = 48_000
SEEDS = range(8)
LEADERS = ["halvorsen_a", "halvorsen_b", "sprottd_a", "shimizu_a", "shimizu_b", "aizawa_e"]


def render(block: Dynamical, u: np.ndarray, chunk: int = 4096) -> np.ndarray:
    block.reset(FS)
    out = np.empty(u.size)
    for pos in range(0, u.size, chunk):
        m = min(chunk, u.size - pos)
        out[pos : pos + m] = block.process(m, {"param": u[pos : pos + m]})["out"][:, 0]
    return out


def scenario(catalog: Catalog, name: str, note: str, u: np.ndarray) -> dict:
    resets, collapses, excursion = 0, 0, 0.0
    for seed in SEEDS:
        block = Dynamical("osc", catalog=catalog, system=name, note=note, seed=seed)
        x = render(block, u)
        resets += block.resets
        collapses += int(np.std(x[-FS:]) < 0.1)
        excursion = max(excursion, float(np.max(np.abs(x[FS // 10 :]))) / 0.25)
    return {"resets": resets, "collapses": collapses, "max_excursion_sigma": excursion}


def main() -> None:
    use_uncached_kernels()
    catalog = Catalog.load(OUT / "catalog_screening.json")
    cfg = {c[0]: c for c in CONFIGS}
    n = 20 * FS
    t = np.arange(n) / FS
    cases = {
        "hold_u0_A3": ("A3", np.zeros(n)),
        "hold_u1_A3": ("A3", np.ones(n)),
        "sweep_T4s_A3": ("A3", 0.5 - 0.5 * np.cos(2 * np.pi * t / 4.0)),
        "sweep_T0.25s_A1": ("A1", 0.5 - 0.5 * np.cos(2 * np.pi * t / 0.25)),
    }
    results = {}
    for name in LEADERS:
        _, dysts_name, param, cand, custom = cfg[name]
        register(make_system(dysts_name, param, cand, name=name, custom=custom))
        results[name] = {k: scenario(catalog, name, note, u) for k, (note, u) in cases.items()}
        print(name, json.dumps(results[name]), flush=True)
    (OUT / "robustness.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
