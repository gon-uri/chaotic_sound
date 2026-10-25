"""Screening set "Halvorsen": short WAVs of the leading candidates for listening.

Each file: 3 s at the default parameter, then 6 s of a slow sweep u: 0 → 1 → 0, at A3 with
pitch lock (engine ``Dynamical`` block; systems registered in-process only).

Run from lab/:  uv run python scripts/studies/screening/halvorsen_set_listen.py
Writes lab/outputs/studies/screening/halvorsen_set/listen_<name>.wav
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from halvorsen_set_adapter import make_system, register, use_uncached_kernels
from halvorsen_set_robustness import LEADERS, render
from halvorsen_set_screen import CONFIGS, OUT

from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import Catalog
from chaotic_sound.wav import write_wav

FS = 48_000


def main() -> None:
    use_uncached_kernels()
    catalog = Catalog.load(OUT / "catalog_screening.json")
    cfg = {c[0]: c for c in CONFIGS}
    for name in LEADERS:
        _, dysts_name, param, cand, custom = cfg[name]
        register(make_system(dysts_name, param, cand, name=name, custom=custom))
        ud = catalog[name].u_default
        t = np.arange(6 * FS) / FS
        u = np.concatenate([np.full(3 * FS, ud), 0.5 - 0.5 * np.cos(2 * np.pi * t / 6.0)])
        u[3 * FS :] = np.clip(u[3 * FS :], 0, 1)
        block = Dynamical("osc", catalog=catalog, system=name, note="A3", seed=0)
        x = render(block, u)
        write_wav(OUT / f"listen_{name}.wav", np.column_stack([x, x]), FS)
        print(name, f"rms={np.std(x):.3f} resets={block.resets}")


if __name__ == "__main__":
    main()
