# lab/: Python reference engine and analysis

This package (`chaotic_sound`, `src/` layout) is the reference implementation of
`docs/spec-v1.md`, the analysis toolkit and the catalog generator. Package map:
`docs/architecture.md`.

## Commands (run from `lab/`)

- `uv run pytest -q -m "not slow"` (fast loop) and `uv run pytest -q` (everything)
- `uv run ruff check . && uv run ruff format --check .` and `uv run mypy`
- `caffeinate -is uv run python scripts/build_catalog.py`: writes `../catalog/systems.json`
  and plots to `outputs/catalog/` (about 2 minutes). Copy updated figures to
  `../docs/figures/` when they change the conclusions.
- `uv run python scripts/render_demos.py`: writes WAVs, spectrograms and `report.md` to
  `outputs/demos/`, and the demo patches to `../examples/patches/` (committed).
- `uv run python scripts/export_golden.py`: writes the cross-engine vectors to
  `../examples/golden/`. `tests/test_golden.py` fails when they are stale.
- After any change to tuning, catalog or blocks: rebuild the catalog, re-render the demos,
  re-export the golden vectors, then run the full test suite (`uv run pytest -q`; the slow
  tests check tuning accuracy per note) and the TypeScript tests (`npm test` at the repo root).

## Code rules

- **The spec is the source of truth.** If code and spec disagree, fix one of them explicitly;
  never let them drift. Reference spec sections in docstrings (for example "spec §4.2 step 5").
- **Layering** (architecture.md): `systems` and `integrate` know nothing about audio blocks;
  `blocks` know nothing about the patch graph; `analysis` is never imported by `blocks` or
  `patch`.
- **Hot loops live in numba `@njit` functions** in `integrate.py` or `dsp.py`. No Python
  per-sample loops elsewhere. Kernels take preallocated arrays and do not allocate per sample.
- **float64 everywhere.** Arrays are C-contiguous. Audio has shape `(n, 2)`; control signals
  have shape `(n,)`.
- **Block-size independence.** A block's output must not depend on how the render is chunked.
  `tests/test_patch.py` enforces this. Keep state (phases, ODE state, filter memories) in the
  block, never recomputed from the chunk start.
- **Determinism.** Randomness only through `numpy.random.default_rng(seed)`, with the seed
  passed in explicitly.
- **Docstrings**: numpy style; state units (system time vs. seconds vs. samples) and array
  shapes. Use the math symbols from `docs/math/tuning.md` (τ, k, P, f₀, u, …).
- **Types**: annotate every function; `mypy` must pass on `src/`.
- **No plotting in `src/`.** matplotlib is only for `scripts/` and `notebooks/`.

## Tests

- Numerical tests state their tolerance and why it is that value.
- Mark tests longer than about 2 s with `@pytest.mark.slow`.
- `tests/test_systems.py` checks each RHS against dysts at random points. Every new system must
  be added there.

## Outputs

- Generated WAVs, plots and caches go in `lab/outputs/` (gitignored).
- Generated catalog data goes in `../catalog/` (committed). Never hand-edit it.
- Adding a new system: follow the project skill `/add-dynamical-system`.
