"""Rikitake dynamo (dysts RikitakeDynamo, knob a): what happens at small a?

The first verification (``fifth_system_verify.py``) found, at the low end of the range
(a ≲ 0.7), random initial conditions that land on a periodic orbit (prominence ≈ 1) instead of
the chaotic attractor, and a fast LFO sweep that collapsed the output. This probe maps that:

1. equilibria (±k, ±1/k, μk²), μk⁴ − a k² − μ = 0, and their Jacobian eigenvalues vs a;
2. 24 random ICs (N(mean, (2σ)²) of the default attractor) per a value: λ·P_ref, prominence,
   centroid period and σ_z of the attractor reached.

Note: for a = 0 the plane x = ±y is invariant and attracting (d(x²−y²)/dt = −2μ(x²−y²)), and on
it the flow x' = x(z−μ), z' = 1 − x² is conservative (H = (z−μ)²/2 + x²/2 − ln|x|), so chaos
must disappear as a → 0.

Run from ``lab/``::

    NUMBA_CACHE_DIR=<scratch> uv run python scripts/studies/screening/fifth_system_rikitake_probe.py

Writes ``outputs/studies/screening/fifth_system/rikitake_probe.json``.
"""

from __future__ import annotations

import json
import math
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fifth_system_verify import OUT, make_system

from chaotic_sound.analysis.spectrum import spectral_peak
from chaotic_sound.analysis.sweep import SWEEP_SETTINGS, reference_scale
from chaotic_sound.integrate import max_lyapunov, trajectory

A_VALUES = (
    0.15,
    0.25,
    0.35,
    0.45,
    0.55,
    0.65,
    0.75,
    0.85,
    0.95,
    1.0,
    1.1,
    1.25,
    1.5,
    2.0,
    3.0,
    4.0,
)
N_IC = 24


def equilibria(a: float, mu: float = 1.0) -> dict[str, Any]:
    k2 = (a / mu + math.sqrt((a / mu) ** 2 + 4.0)) / 2.0
    k = math.sqrt(k2)
    x, y, z = k, 1.0 / k, mu * k2
    jac = np.array([[-mu, z, y], [z - a, -mu, x], [-y, -x, 0.0]])
    ev = np.linalg.eigvals(jac)
    return {
        "a": a,
        "point": [x, y, z],
        "eigenvalues": [[float(v.real), float(v.imag)] for v in ev],
        "max_real": float(max(v.real for v in ev)),
    }


def probe_a(a: float) -> dict[str, Any]:
    system = make_system("RikitakeDynamo", "a", (0.02, 4.0))
    ref = reference_scale(system, SWEEP_SETTINGS)
    p_ref = ref.period
    h, dt = p_ref / 256, p_ref / 32
    params = system.params_array(a=a)
    rng = np.random.default_rng(int(a * 1000) + 3)
    rows = []
    for _ in range(N_IC):
        x0 = ref.mean + 2.0 * ref.std * rng.standard_normal(3)
        _, x = trajectory(system, params, x0, dt=dt, n_samples=300 * 32, h_max=h)
        rec, x_end = trajectory(system, params, x, dt=dt, n_samples=2000 * 32, h_max=h)
        if not np.all(np.isfinite(rec)):
            rows.append({"bounded": False})
            continue
        z = rec[:, 2]
        pk = spectral_peak(z, dt, nperseg=128 * 32, f_min=0.25 / p_ref)
        lam = max_lyapunov(
            system,
            params,
            x_end,
            h=h,
            t_transient=0.0,
            t_measure=300 * p_ref,
            t_renorm=0.25 * p_ref,
        )
        rows.append(
            {
                "bounded": True,
                "lyap_per_Pref": float(lam * p_ref),
                "prominence": float(pk.prominence),
                "centroid_period": float(pk.centroid_period),
                "std_z": float(z.std()),
                "mean_z": float(z.mean()),
                "x_sign_changes": int(np.sum(np.diff(np.sign(rec[:, 0])) != 0)),
            }
        )
    return {"a": a, "P_ref": p_ref, "runs": rows}


def main() -> None:
    t0 = time.time()
    eq = [equilibria(a) for a in A_VALUES]
    with get_context("spawn").Pool(8) as pool:
        probes = pool.map(probe_a, A_VALUES)
    for e, pr in zip(eq, probes, strict=True):
        runs = [r for r in pr["runs"] if r["bounded"]]
        periodic = [r for r in runs if r["lyap_per_Pref"] < 0.05]
        chaotic = [r for r in runs if r["lyap_per_Pref"] >= 0.05]
        line = f"a={e['a']:.2f} eq max Re={e['max_real']:+.4f} | {len(runs)}/{N_IC} bounded, "
        line += f"{len(chaotic)} chaotic"
        if chaotic:
            line += (
                f" (P {min(r['centroid_period'] for r in chaotic):.3f}–"
                f"{max(r['centroid_period'] for r in chaotic):.3f}, σz "
                f"{min(r['std_z'] for r in chaotic):.3f}–{max(r['std_z'] for r in chaotic):.3f})"
            )
        line += f", {len(periodic)} non-chaotic"
        if periodic:
            line += (
                f" (P {min(r['centroid_period'] for r in periodic):.3f}–"
                f"{max(r['centroid_period'] for r in periodic):.3f}, σz "
                f"{min(r['std_z'] for r in periodic):.3f}–{max(r['std_z'] for r in periodic):.3f},"
                f" prom {min(r['prominence'] for r in periodic):.2f}, λP "
                f"{max(r['lyap_per_Pref'] for r in periodic):+.3f}, sign changes "
                f"{max(r['x_sign_changes'] for r in periodic)})"
            )
        print(line)
    (OUT / "rikitake_probe.json").write_text(
        json.dumps({"equilibria": eq, "probes": probes}, indent=1, default=float)
    )
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
