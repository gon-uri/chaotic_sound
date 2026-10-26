# Architecture

- Status: 2026-10-26.
- Built: the Python lab (reference engine, analysis, catalog), the TypeScript engine
  (Phase 2), and the editor MVP `apps/web` (Phase 3, in progress).
- Principles: hexagonal architecture (ADR 0011); one engine runs the whole patch (ADR 0004);
  all sound in the browser (ADR 0001).

## Components and data flow

```mermaid
flowchart LR
  subgraph offline["Offline (developer machine)"]
    dysts[(dysts, pinned commit)]
    lab["lab/ (Python)<br/>reference engine + analysis"]
    dysts --> lab
  end
  catalog[(catalog/systems.json<br/>ranges, P(u), μ σ π(u), …)]
  golden[(examples/golden/<br/>reference vectors)]
  patches[(examples/patches/*.json)]
  lab -- build_catalog.py --> catalog
  lab -- export_golden.py --> golden
  lab -- render_demos.py --> patches
  subgraph browser["Browser"]
    ui["apps/web<br/>patch editor, Learn-more pages"]
    worklet["AudioWorklet adapter"]
    worker["Web Worker adapter<br/>(WAV export)"]
    core["packages/engine core<br/>(TypeScript, pure)"]
    ui -- messages --> worklet --> core
    ui --> worker --> core
  end
  catalog --> core
  golden -. cross-engine tests .- core
  patches -. fixtures .- core
```

## Hexagonal structure (ADR 0011)

| Ring | TypeScript (`packages/engine/src/`) | Python (`lab/src/chaotic_sound/`) |
|---|---|---|
| **Core: DSP kernel** (C-style, allocation-free) | `core/dsp/`: `rk4.ts`, `systems.ts`, `filters.ts`, `pitch.ts`, `rng.ts` | `integrate.py`, `systems/`, `dsp.py`, `pitch.py`, `rng.py` |
| **Core: model** | `core/catalog.ts` (types, interpolation), `core/patch.ts` (document, validation) | `catalog.py` (model part), `patch.py` (graph part) |
| **Core: engine** | `core/blocks/*.ts`, `core/graph.ts`, `core/engine.ts` (implements `EnginePort`) | `blocks/`, `patch.py` (render) |
| **Ports** | `ports.ts`: `EnginePort` (driving). No driven ports: the catalog arrives as data in `load()`, and adapters poll `diagnostics()`. | `blocks.BlockContext` (supplies the catalog) |
| **Driving adapters** | `adapters/worklet/processor.ts`, `adapters/worker/render-worker.ts`, `adapters/offline.ts`, `adapters/node/cli.ts`, the apps | `scripts/`, notebooks, tests |
| **Other adapters** | `adapters/node/catalog-file.ts` (reads the catalog and patches from disk), `adapters/wav.ts` | `Catalog.load/save`, `load_default_catalog`, `wav.py` |
| **Analysis** (lab only) | none | `analysis/`: spectra, Lyapunov, sweeps, catalog builder |

Dependency rule: rings depend only inward. The core never imports an adapter, a platform API
(DOM, Web Audio, Node, `fetch`) or anything asynchronous. The TypeScript test
`test/architecture.test.ts` checks this rule; in Python it is a convention backed by review.

**C++ seam.** `EnginePort` is narrow and data-oriented (patch JSON and catalog JSON in, flat
float buffers out). A C++ core compiled to WebAssembly can implement it behind the same
adapters, verified by the same golden tests. The DSP kernel is written so it ports to C++
function by function.

## Contracts (language-neutral)

1. `docs/spec-v1.md`: behavior, with exact formulas.
2. Patch JSON (spec §5): `examples/patches/` are the canonical fixtures.
3. Catalog JSON (`catalog/systems.json`, format version 2).
4. Golden vectors (`examples/golden/`), exported by the Python reference (ADR 0016):
   - the demo patches plus eight golden-only fixtures (`examples/golden/patches/`);
   - each one's first 2048 samples (1e-9 for any engine, ≤ 1e-12 and a recorded ratchet for
     TypeScript);
   - 8 s statistics (level, level per segment, octave bands, per voice) with the spread of a
     13-seed ensemble (an engine must be within 10 spreads);
   - modulator windows around cycle edges and once ends, and each dynamical block's exact
     initial state.
5. Document rules (`examples/documents.json`): 146 edge-case patch documents with the
   expected outcome.

## Processing in the AudioWorklet

- The browser calls `process()` with 128 frames at a time. The adapter calls
  `EnginePort.process(128, left, right)`.
- Patch edits arrive as messages and are applied between quanta.
- All buffers, per-block input arrays and kernel arguments are preallocated when a patch is
  loaded or edited, so `process()` allocates (almost) nothing: the allocation probe in
  `live.test.ts` allows 32 bytes per quantum, and measures a few. Loading a patch (parsing the catalog,
  building blocks) runs between quanta on the audio thread; it takes about 2 ms.
- Knob changes arrive as `setParams` edits and update the running block (ADR 0014).
- Cost (M1, Node 24): the engine uses one hand-written RK4 kernel per system
  (`dsp/kernels.ts`). A whole voice is 1.4–2.8× faster than with the generic kernel, so at
  A7 and the worst knob one core runs about 22–46 voices in real time (about 10 before). The
  tonality step (ADR 0015) adds about 0.9% of a core per voice at any note. Details:
  `docs/studies/cost.md` and `packages/engine/bench/kernels.ts`.

## Python lab package map

| Module | Role |
|---|---|
| `systems/` | `SystemDef`, one module per system, registry |
| `integrate.py` | numba RK4 kernels: sampled trajectories, tuned audio-rate rendering, Lyapunov |
| `dsp.py`, `pitch.py`, `rng.py` | smoothers, DC blocker, soft clip; note ↔ Hz; portable seeding |
| `catalog.py` | catalog model, interpolation, `check_against`, JSON IO |
| `blocks/` | `Modulator`, `Dynamical`, `Sum`, `ControlSum`, `Output`, `BlockContext` |
| `patch.py` | `Patch`: build, validate, order, render, JSON |
| `wav.py` | WAV IO |
| `analysis/` | `spectrum.py` (period estimators, `measure_pitch`), `sweep.py` (continuation, hysteresis, range selection), `catalog_builder.py` |
