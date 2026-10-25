# chaotic_sound

A browser-based modular synthesizer whose sound comes from chaotic ODEs (from the
[dysts](https://github.com/GilpinLab/dysts) catalog) tuned to musical notes by rescaling time.
It is educational first: the main goal is to get people interested in dynamical systems and
their history. The audiences are math/physics/engineering people curious about music, and
musicians curious about math.

## Status

- Phase 1 is done: the Python reference engine, analysis and catalog v2 in `lab/` (engine
  v0.3).
- Phase 2 is done for the engine: the TypeScript engine in `packages/engine/`, verified
  against the golden vectors and run live in the browser through `apps/playground/`.
- Phase 3 has started: the editor MVP in `apps/web/` (React + React Flow + Zustand), and
  the Learn-more pages (Three.js, KaTeX). Design: `docs/design/web-app.md`.
- `docs/REVIEW.md` lists the decisions the owner has not reviewed yet. Keep it up to date.

## Repo map

- `lab/`: Python package `chaotic_sound`, which holds the reference engine, the analysis tools
  and the catalog generator. Read `lab/CLAUDE.md` before working there.
- `packages/engine/`: the TypeScript engine (core + ports + adapters). Read
  `packages/engine/CLAUDE.md` before working there.
- `apps/web/`: the app (a driving adapter of the engine). `apps/playground/` is a developer
  page.
- `catalog/`: generated JSON (systems, ranges, tuning tables). It is the contract between the
  lab and the engines. Never edit it by hand; regenerate it.
- `examples/patches/`: demo patches (patch JSON). They double as cross-engine fixtures.
- `examples/golden/`: reference vectors exported by the Python lab for cross-engine tests.
  Generated; never hand-edited.
- `docs/`: vision, v1 spec, architecture, decision records (ADRs), math notes, studies, system
  pages.

## Commands

Python (run from `lab/`):
- `uv run pytest -q` (add `-m "not slow"` for a fast loop)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy`
- `caffeinate -is uv run python scripts/build_catalog.py` (about 2 minutes)
- `uv run python scripts/render_demos.py`
- `uv run python scripts/export_golden.py`

TypeScript (run from the repo root; Node 24 is in `~/.local/node`, see `docs/REVIEW.md`):
- `npm test`
- `npm run check` (types and lint)
- `npm run render -- <patch.json> <out.wav>`
- `npm run web`: the editor on http://localhost:5174 (launch config `web`)
- `npm run playground`: developer page on http://localhost:5173 (launch config `playground`)
- The `.claude/launch.json` configs call Node by absolute path, because `~/.local/bin` may not
  be on the app's PATH.

## Docs to read before changing related code

- `docs/spec-v1.md`: the behavior of every box, with exact formulas. It is the source of
  truth for all engines.
- `docs/architecture.md` and ADR 0011: the hexagonal architecture and the dependency rules.
- `docs/math/tuning.md`: tuning, pitch lock, range selection, loudness and accuracy.
- `docs/decisions/`: one ADR per decision. Add a new ADR instead of silently changing an
  accepted one.
- `docs/roadmap.md`.

## Conventions

- Terms: a **block** in code is a **box** in the UI; boxes are joined by **cables** between
  **ports** to form a **patch**.
- Knobs are in [0, 1], except pitch (note names, cents) and durations (seconds). Control
  signals are in [0, 1]; audio is nominally in [-1, 1].
- Control inputs take one cable. Combining controllers needs a `control_sum` box (ADR 0013).
- Every engine must pass the golden tests. A behavior change means: update the spec, then the
  Python reference, then regenerate the golden vectors, then the TypeScript engine.
- When you make a non-trivial decision, record it as an ADR and add a line to `docs/REVIEW.md`.
- The owner is fluent in Python and new to TypeScript and web development. Explain TS and web
  concepts when they come up, and keep the TS code readable for a Python programmer.
- Wrap long jobs in `caffeinate -is`. It does not prevent sleep when the laptop lid is closed.

## Git

- Remote: private repo `gon-uri/chaotic_sound`, default branch `main`.
- Write small, descriptive commits. Never commit `lab/outputs/` or `node_modules/`. Commit
  `uv.lock` and `package-lock.json`.
