# Architecture

- Status: Phase 1. Only the Python lab exists. This document describes the target design; the
  "Planned" parts are not built yet.

## Components and data flow

```mermaid
flowchart LR
  subgraph offline["Offline (developer machine)"]
    dysts[(dysts snapshot<br/>params, ICs, metadata)]
    lab["lab/ (Python)<br/>reference engine + analysis"]
    dysts --> lab
  end
  catalog[(catalog/systems.json<br/>ranges, P(u), μ(u), σ(u), …)]
  lab -- build_catalog.py --> catalog
  subgraph browser["Browser (Planned)"]
    ui["apps/web<br/>patch editor (React + React Flow)<br/>Learn-more pages (Three.js, KaTeX)"]
    engine["packages/engine<br/>real-time engine (TypeScript)"]
    worklet["AudioWorklet<br/>(live audio thread)"]
    worker["Web Worker<br/>(offline WAV render)"]
    ui -- patch edits (messages) --> worklet
    engine --- worklet
    engine --- worker
  end
  catalog --> engine
  catalog --> ui
  lab -. cross-engine tests: same patch JSON .- engine
```

## Layers inside an engine (Python today, TypeScript later)

Each layer depends only on the layers above it in this list.

1. **Systems**: pure RHS functions `F(x, p) → dx/dτ`, parameter vectors and metadata. No audio
   concepts.
2. **Integrators**: fixed-step RK4 with per-sample time scale and parameter (the "kernel"). No
   graph concepts.
3. **Tuning and signals**: pitch ↔ frequency, catalog tables and interpolation, smoothers, DC
   blocker, soft clip.
4. **Blocks**: Modulator, Dynamical, Sum, Output. Each has typed ports and a
   `process(n_samples)` step, and keeps its own state.
5. **Patch / graph**: validation, topological order, fan-in summing, block-wise rendering, JSON
   (de)serialization.
6. **Render / IO**: offline render to arrays, WAV writing.

Analysis (sweeps, spectra, Lyapunov exponents) sits beside layers 1–2 and is used only by the
lab and the catalog builder.

## Python package map (`lab/src/chaotic_sound/`)

| Module | Layer | Contents |
|---|---|---|
| `systems/` | 1 | `SystemDef`, one module per system, registry |
| `integrate.py` | 2 | numba RK4 kernels: plain trajectories and tuned audio-rate rendering |
| `pitch.py` | 3 | note names ↔ MIDI ↔ Hz |
| `catalog.py` | 3 | catalog data classes, load/save, table interpolation |
| `dsp.py` | 3 | one-pole smoother, DC blocker, soft clip |
| `blocks/` | 4 | `modulator.py`, `dynamical.py`, `sum.py`, `output.py`, `base.py` |
| `patch.py` | 5 | `Patch`: add/connect/validate/order/render, JSON format |
| `render.py`, `wav.py` | 6 | offline rendering helpers, WAV IO |
| `analysis/` | | `spectrum.py`, `lyapunov.py`, `sweep.py` |

## Web app (Planned, Phase 3)

- Vite + React + TypeScript, with React Flow (xyflow) for the node editor.
- Zustand for UI state. The patch JSON (spec §5) is the single source of truth, sent to the
  engine as messages.
- Three.js (likely through react-three-fiber) for 3D attractors, KaTeX for equations, and
  Markdown content from `docs/systems/` for the Learn-more pages.
- Deployment: a static build on any static host (ADR 0001).
