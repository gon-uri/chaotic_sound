"""Probe realization dependence (coexisting attractors) for candidates of this screener.

For a system and parameter value, integrate from several perturbed initial conditions (as
the Dynamical block does: IC + 1e-3·σ·N(0,1)) and also from the continuation end state, then
report per run: mean of each variable, z spectral centroid period and prominence, return
time and λ·P_ref. Run from ``lab/``.
"""

from __future__ import annotations

import sys

import numpy as np

from chaotic_sound.analysis.spectrum import mean_return_time, spectral_peak
from chaotic_sound.integrate import max_lyapunov, trajectory

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from screen_moorespiegel_group import make_system  # noqa: E402


def probe(name: str, param: str, value: float, obs: str, p_ref: float, seeds=range(8)) -> None:
    system = make_system(name, modulated=param)
    p = system.params_array(**{param: value})
    i = system.variable_index(obs)
    h = p_ref / 256
    dt = p_ref / 32
    print(f"--- {name} {param}={value:.5g} (obs {obs})")
    x_ic = system.initial_state()
    for s in seeds:
        rng = np.random.default_rng(s)
        scale = np.abs(x_ic) + 1.0
        x0 = x_ic + (1e-3 * scale * rng.standard_normal(3) if s else 0.0)
        _, x = trajectory(system, p, x0, dt=dt, n_samples=50 * 32, h_max=h)
        rec, xe = trajectory(system, p, x, dt=dt, n_samples=2000 * 32, h_max=h)
        if not np.all(np.isfinite(rec)):
            print(f"  seed {s}: diverged")
            continue
        pk = spectral_peak(rec[:, i], dt, nperseg=128 * 32, f_min=0.25 / p_ref)
        rt = mean_return_time(rec[:, i], dt).mean
        lam = max_lyapunov(system, p, xe, h=h, t_transient=0, t_measure=300 * p_ref,
                           t_renorm=0.25 * p_ref)
        means = np.round(rec.mean(axis=0), 3)
        print(f"  seed {s}: means {means} P_centroid {pk.centroid_period:.4f} "
              f"P_peak {pk.period:.4f} prom {pk.prominence:.3f} P_ret {rt:.4f} "
              f"λP {lam * p_ref:.3f}")


if __name__ == "__main__":
    probe("Rucklidge", "b", 4.319, "z", 3.4591)
    probe("Rucklidge", "b", 4.6, "z", 3.4591, seeds=range(4))
    probe("Arneodo", "c", 1.0, "z", 2.6605)
    probe("Arneodo", "c", 0.954, "z", 2.6605, seeds=range(4))
    probe("RikitakeDynamo", "a", 1.0, "z", 4.9125, seeds=range(4))
    probe("RikitakeDynamo", "a", 3.0, "z", 4.9125, seeds=range(4))
    probe("LuChen", "c", 18.0, "z", 0.58642, seeds=range(4))
