---
name: add-dynamical-system
description: Add a new chaotic system (usually from dysts) to chaotic_sound — system definition, dysts cross-check tests, catalog entry with chaotic range and tuning tables, docs page. Use when the user asks to add, include, port or try a new attractor/system/oscillator as a dynamical box.
argument-hint: [dysts class name, e.g. Halvorsen]
---

# Add a dynamical system: $ARGUMENTS

Read first: `docs/math/tuning.md` (how tuning and ranges work) and ADR 0010. Work in `lab/`.

1. **Inspect dysts.** `uv run python -c "import dysts.flows as f, inspect; m=f.$ARGUMENTS(); print(m.params, m.ic, m.period, m.maximum_lyapunov_estimated); print(inspect.getsource(type(m)._rhs))"`. Note the equations, parameter names, initial condition, `period`, and whether it is non-autonomous (needs a phase variable like `systems/duffing.py`).
2. **Choose the modulated parameter.** It should have a literature story (bifurcations, route to chaos) and stay bounded around the default. Pick a wide `candidate_range` around the default; use literature landmarks to exclude regimes with coexisting stable fixed points (see the Lorenz ρ ≥ 24.8 example in ADR 0010).
3. **Write `src/chaotic_sound/systems/<name>.py`** following `rossler.py`: an `@njit(cache=True)` `rhs(x, p, out)` with no allocation, and a `SystemDef` with values copied from dysts (commit pinned in `pyproject.toml`), `period_hint` = dysts `period`, `equations_latex`, and `phase_indices`/`drive_frequency_param` for forced systems. Register it in `systems/__init__.py` (`_ALL`).
4. **Tests.** `tests/test_systems.py` is parametrized over `list_systems()`, so it checks defaults, IC, period hint and RHS against dysts automatically. Run `uv run pytest -q tests/test_systems.py`.
5. **Catalog.** `caffeinate -is uv run python scripts/build_catalog.py --systems <name>` builds that entry and merges it into the existing catalog. Read the printed range and its reasons and open `outputs/catalog/<name>.png`. Check:
   - the range is not tiny;
   - P(u) is smooth;
   - the chaotic fraction is ≥ ~75 %;
   - the tuning observable's prominence is ≥ 0.25 (otherwise it falls back to return times).

   If the default sits on a small island, report it rather than silently moving the default.
6. **Tuning tests.** `uv run pytest -q -m slow -k tuned`. If the new system needs a tolerance, add it to `TOLERANCE_CENTS` in `tests/test_dynamical.py`, justified by measuring the estimator spread (see `docs/math/tuning.md` §2).
7. **Docs.** Add `docs/systems/<name>.md` (same structure as the other pages, including "In chaotic_sound" with the measured facts). Add the system to the tables in `docs/spec-v1.md` §7 and `docs/math/tuning.md` §4, and add a line to `docs/REVIEW.md`.
8. **Demo.** Add a `voice()` demo in `scripts/render_demos.py`, render it and listen.
9. Commit with a message summarizing the range, the method and the accuracy.

## TypeScript engine (since ADR 0016)

- Add the system's RHS to `packages/engine/src/core/dsp/systems.ts` exactly as in the Python
  definition (same arithmetic order).
- Add its hand-written kernel to `packages/engine/src/core/dsp/kernels.ts`, following the
  template of the others. `test/kernels.test.ts` requires every system to have one and checks
  it bitwise against the generic `renderTuned`.
- Re-export the golden vectors, then re-record the TS prefix errors
  (`GOLDEN_RECORD=1 npx vitest run packages/engine/test/golden.test.ts`).

