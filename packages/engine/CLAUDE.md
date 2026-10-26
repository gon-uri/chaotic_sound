# packages/engine: TypeScript engine (hexagonal)

This package implements `docs/spec-v1.md` identically to the Python reference in
`lab/src/chaotic_sound/`. Its architecture follows ADR 0011.

## Layout

- `src/core/`: the pure core. No DOM, Web Audio, Node, `fetch`, timers or `async`.
  - `dsp/`: C-style kernels: `systems.ts`, `rk4.ts` (the generic RK4 renderer, the
    reference), `kernels.ts` (one hand-written, bit-identical kernel per system: a new
    system needs one, and `test/kernels.test.ts` checks them bitwise against `rk4.ts`),
    `filters.ts` (smoothers, DC blocker, soft clip, `Glide` for live knobs), `tonal.ts`
    (the tonality resynthesis), `pitch.ts`, `rng.ts`.
  - `catalog.ts` (catalog model, numpy-compatible `interp`), `patch.ts` (document rules,
    defaults, edits), `graph.ts` (cable rules, ordering, input preparation), `blocks/`,
    `engine.ts` (`Engine` implements `EnginePort`; atomic loads and edits, one live-edit
    path), `numeric.ts` (round half to even), `trajectory.ts` (attractor points for the UI).
- `src/ports.ts`: `EnginePort`, the driving port (the core needs no driven ports: the catalog
  arrives as data in `load()`).
- `src/adapters/`: `offline.ts`, `wav.ts`, `node/` (CLI, file loading), `worklet/` (the
  AudioWorklet processor and its message protocol).
- `test/`: Vitest.
  - `golden.test.ts`: the cross-engine contract (ADR 0016).
  - `architecture.test.ts`: the purity of the core.
  - `live.test.ts`: live edits, atomicity, glides, engine state, and the allocation probe
    (V8's sampling heap profiler; budget 32 bytes per quantum).
  - `rules-*.test.ts`: one spec rule each.
  - `documents.test.ts`: the shared document rules.
  - `kernels.test.ts`, `tonality.test.ts`, `diff.test.ts`, `engine.test.ts`, `dsp.test.ts`,
    `patch.test.ts`.
- `bench/kernels.ts`: integrator and box timings (`node packages/engine/bench/kernels.ts`).

## Commands (from the repository root)

- `npm test` and `npm run check` (three tsc configs plus Biome)
- `npm run render -- examples/patches/02_owner_example.json out.wav --seconds 10`
- `npm run playground` (Vite dev server on http://localhost:5173)

Node runs the `.ts` files directly: no build step, and imports carry `.ts` extensions. The
code must use only erasable TypeScript syntax: no `enum`, no `namespace`, no constructor
parameter properties.

## Rules

- **Parity first.** Every behavior mirrors the Python reference operation by operation, so
  results match to the last bits. Keep the same arithmetic order as the Python code. If you
  change behavior:
  1. update the spec;
  2. update the Python engine;
  3. run `uv run python scripts/export_golden.py` (in `lab/`);
  4. update this engine;
  5. run `npm test`.
- **The core stays pure.** It never imports from `adapters/` and uses no platform globals.
  `tsconfig.core.json` has no DOM or Node types, and `test/architecture.test.ts` checks the
  imports.
- **Real-time safety.** No allocation in `process()` paths: preallocate in constructors or
  `reset()` and reuse typed arrays. Hot loops use typed arrays and scalar locals, no closures.
  In V8 also avoid, inside sample loops, calling a function that returns a number, writing
  a number into an object field, and `fill(v)`: each can box the number. Batch per chunk
  (`interpInto`, `Glide.fill`) instead. `live.test.ts` measures this. That is also what keeps
  a C++ port mechanical.
- **Readable for a Python programmer.** Comment TypeScript idioms when they first appear:
  `x!` means "this is not undefined" (needed with `noUncheckedIndexedAccess`); `import type`
  imports only types; `readonly` makes a field immutable. The owner's primer is
  `docs/dev/typescript-for-python.md`; keep it in sync when new idioms appear.
- **Defaults live in `BLOCK_SPECS`** (`patch.ts`). Blocks read them with `withDefaults` /
  `defaultParam`; never write a default value a second time.
- **Live settings** go through `BlockRuntime.setParam`, return `false` for settings that need
  a new block, and must not click: smooth them (step 2 smoothers or `Glide`) unless they only
  change the ODE's speed. A steady value must give bit-identical output.
