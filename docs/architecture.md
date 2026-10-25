# Architecture

- Status: 2026-10-26.
- Built: the Python lab (reference engine, analysis, catalog), and the TypeScript engine
  (Phase 2, in progress).
- Not built yet: the web UI (Phase 3).
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
    ui["apps/web (Phase 3)<br/>patch editor, Learn-more pages"]
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
| **Core: DSP kernel** (C-style, allocation-free) | `core/dsp/`: `rk4.ts`, `systems/*.ts`, `filters.ts`, `pitch.ts`, `rng.ts` | `integrate.py`, `systems/`, `dsp.py`, `pitch.py`, `rng.py` |
| **Core: model** | `core/catalog.ts` (types, interpolation), `core/patch.ts` (document, validation) | `catalog.py` (model part), `patch.py` (graph part) |
| **Core: engine** | `core/blocks/*.ts`, `core/graph.ts`, `core/engine.ts` (implements `EnginePort`) | `blocks/`, `patch.py` (render) |
| **Ports** | `ports.ts`: `EnginePort` (driving), `CatalogSource`, `DiagnosticsSink` (driven) | `blocks.BlockContext` (supplies the catalog) |
| **Driving adapters** | `adapters/worklet/processor.ts`, `adapters/offline.ts`, `adapters/node/cli.ts` | `scripts/`, notebooks, tests |
| **Driven adapters** | `adapters/catalog-json.ts`, `adapters/wav.ts` | `Catalog.load/save`, `load_default_catalog`, `wav.py` |
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
4. Golden vectors (`examples/golden/`), exported by the Python reference:
   - each fixture's first samples;
   - statistics (RMS, pitch, octave-band spectrum);
   - each dynamical block's exact initial state.

## Processing in the AudioWorklet

- The browser calls `process()` with 128 frames at a time. The adapter calls
  `EnginePort.process(128, left, right)`.
- Patch edits arrive as messages and are applied between quanta.
- All buffers are preallocated when a patch is loaded, so nothing allocates in the audio
  thread.
- Cost (`docs/studies/cost.md`): one box is about 0.2–0.4% of a core at A3, so more than 100
  boxes fit in real time.

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
