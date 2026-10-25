# 0003. The Python lab generates a JSON catalog that engines consume

- Status: Accepted (owner, 2026-10-26)
- Date: 2026-10-25

## Context

Each dynamical box needs numbers that are expensive or delicate to compute: the parameter's
chaotic range, the characteristic period P(u) across that range (for pitch lock), the mean and
standard deviation of each variable across the range (for loudness normalization), a safe
bounding box, and an integration resolution. The scientific Python stack (numpy, scipy, numba,
dysts) is the natural place to compute them. The browser should not repeat the computation.

## Decision

- `lab/` is a Python package (`chaotic_sound`) with three roles:
  1. the **reference engine** (blocks, patch graph, offline WAV render);
  2. **analysis** (spectra, return times, Lyapunov exponents, parameter sweeps);
  3. the **catalog generator** (`scripts/build_catalog.py`).
- The generated `catalog/systems.json` is committed. It is the **contract** between the lab
  and every engine: engines read the system data from it and never hard-code those numbers.
- The catalog records its provenance: the dysts commit, the generator version, the analysis
  settings and the date.

## Consequences

- Adding a system means adding its definition in the lab and rerunning the generator. The
  engines then pick it up from the catalog; only the RHS function must also exist in each
  engine.
- The catalog format needs versioning (`catalog_version`), and engines must check it.
- The analysis code is held to the same standard as the engine (tests, docs), because errors
  there become wrong pitches and loudness.
