"""Screening batch B, step 5: follow-up checks (QUICK settings, no continuation).

1. ForcedVanDerPol: chaotic fraction of the (a, w) plane at mu = 8.53 (dysts default periodic?).
2. ForcedBrusselator: do wide random initial conditions reach the same attractor (basin check)?
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from dysts_adapter_b import make_system  # noqa: E402

from chaotic_sound.analysis.sweep import QUICK_SETTINGS, SWEEP_SETTINGS, analyze_point, reference_scale  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "outputs" / "studies" / "screening" / "batch_b"


def vdp_plane() -> None:
    s = make_system("ForcedVanDerPol", "a", (0.1, 6.0), phase_index=2, drive_param="w")
    ref = reference_scale(s, SWEEP_SETTINGS)
    a_vals = np.linspace(0.25, 5.0, 20)
    w_vals = np.linspace(0.3, 1.6, 27)
    lam = np.full((w_vals.size, a_vals.size), np.nan)
    for i, w in enumerate(w_vals):
        for j, a in enumerate(a_vals):
            s2 = make_system("ForcedVanDerPol", "a", (0.1, 6.0), phase_index=2, drive_param="w",
                             overrides={"w": float(w)}) if j == 0 else s2
            r = analyze_point(s2, float(a), ref, QUICK_SETTINGS)
            # λ per drive period of this w
            lam[i, j] = r.lyapunov * (2 * np.pi / w) if r.bounded else np.nan
    chaotic = np.nan_to_num(lam, nan=-1) > 0.05
    print(f"ForcedVanDerPol mu=8.53: chaotic in {chaotic.sum()} of {chaotic.size} (a, w) points "
          f"({100 * chaotic.mean():.1f} %); max λ·T = {np.nanmax(lam):.3f}")
    for i, j in zip(*np.nonzero(chaotic)):
        print(f"   chaotic at a={a_vals[j]:.3f}, w={w_vals[i]:.3f}: λ·T={lam[i, j]:.3f}")
    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.pcolormesh(a_vals, w_vals, lam, shading="nearest", cmap="RdBu_r", vmin=-0.5, vmax=0.5)
    ax.plot(1.2, 0.63, "k*", ms=12, label="dysts default")
    ax.set_xlabel("forcing amplitude a")
    ax.set_ylabel("drive frequency w")
    ax.set_title("Forced van der Pol (μ = 8.53): λ_max per drive period")
    fig.colorbar(im, label="λ·T_drive")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "forcedvanderpol_a_w_plane.png", dpi=110)
    plt.close(fig)


def brusselator_basin() -> None:
    s = make_system("ForcedBrusselator", "f", (0.02, 0.15), phase_index=2, drive_param="w")
    ref = reference_scale(s, SWEEP_SETTINGS)
    rng = np.random.default_rng(7)
    for f in (0.05, 0.07, 0.09):
        rows = []
        for _ in range(8):
            x0 = np.array([rng.uniform(0.0, 3.0), rng.uniform(0.0, 5.0), rng.uniform(0, 2 * np.pi)])
            r = analyze_point(s, f, ref, QUICK_SETTINGS, x0=x0)
            if not r.bounded:
                rows.append("UNB")
                continue
            st = r.variables["y"]
            rows.append(f"λT={r.lyapunov * ref.period:.2f}/P={st.centroid_period:.3f}/prom={st.prominence:.2f}")
        print(f"ForcedBrusselator f={f}: " + "; ".join(rows))


if __name__ == "__main__":
    brusselator_basin()
    vdp_plane()
