# chaotic_sound

A browser-based modular synthesizer whose sound comes from chaotic ODEs (from the
[dysts](https://github.com/GilpinLab/dysts) catalog) tuned to musical notes by rescaling time.
It is educational first: the main goal is to get people interested in dynamical systems and
their history. The two audiences are (a) math/physics/engineering people who are curious about
music and (b) musicians who are curious about math.

## Status

- Phase 1 (current): Python reference engine and analysis in `lab/`.
- The browser engine and web app have not started. The engine language is proposed as
  TypeScript but still awaits the owner's review (`docs/decisions/0002-engine-language.md`).
- `docs/REVIEW.md` lists every decision the owner has not reviewed yet. Keep it up to date.

## Repo map

- `lab/`: Python package `chaotic_sound`, which holds the reference engine, the analysis tools
  and the catalog generator. Read `lab/CLAUDE.md` before working there.
- `catalog/`: generated JSON with the systems, parameter ranges and tuning tables. It is the
  contract between the lab and any engine. Never edit it by hand; regenerate it instead.
- `docs/`: vision, v1 spec, architecture, decision records (ADRs), math notes and system pages.
- Planned for later phases: `packages/engine/` (real-time engine) and `apps/web/` (UI).

## Commands (run from `lab/`)

- Install/update the environment: `uv sync`
- Tests: `uv run pytest -q`. For a fast loop, add `-m "not slow"`.
- Lint and format check: `uv run ruff check . && uv run ruff format --check .`
- Type check: `uv run mypy`
- Regenerate the catalog: `uv run python scripts/build_catalog.py`. This takes minutes, so wrap
  it in `caffeinate -is`.
- Render the demo patches to `lab/outputs/demos/`: `uv run python scripts/render_demos.py`

A hook in `.claude/settings.json` runs `ruff format` automatically on every Python file you edit
under `lab/`.

## Docs to read before changing related code

- `docs/spec-v1.md`: blocks, ports, signal conventions, the patch format and the glossary.
  This is the source of truth for behavior.
- `docs/math/tuning.md`: how a chaotic system is tuned to a note (time rescaling, period
  estimation, pitch lock, normalization, aliasing).
- `docs/architecture.md`: the components and the data flow between lab, catalog, engine and UI.
- `docs/decisions/`: one ADR per non-trivial decision. Add a new ADR rather than silently
  changing an accepted decision.
- `docs/roadmap.md`: the phases, plus the future ideas the owner asked to keep on record.

## Conventions

- Use the terms from the spec glossary: a **block** in code is shown as a **box** in the UI, and
  boxes are joined by **cables** between **ports** to form a **patch**.
- Every user-facing knob is normalized to [0, 1]. The exceptions are pitch (note, octave, cents)
  and durations (seconds). Control signals are in [0, 1]; audio is nominally in [-1, 1].
- Modulator boxes and dynamical boxes are separate entities in v1. Dynamical boxes cannot act
  as modulators.
- When you make a non-trivial decision, record it as an ADR and add a line to `docs/REVIEW.md`.
- The owner is fluent in Python and new to TypeScript and web development. Explain web and
  TypeScript concepts when they come up.
- Wrap long jobs (sweeps, catalog builds) in `caffeinate -is`. Note that this does not prevent
  sleep when the laptop lid is closed.

## Git

- Remote: private repo `gon-uri/chaotic_sound`, default branch `main`.
- Write small, descriptive commits. Never commit `lab/outputs/`. Commit `uv.lock`.
