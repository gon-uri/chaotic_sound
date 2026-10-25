# packages/engine: TypeScript engine (hexagonal)

This package implements `docs/spec-v1.md` identically to the Python reference in
`lab/src/chaotic_sound/`. Its architecture follows ADR 0011.

## Layout

- `src/core/`: the pure core. No DOM, Web Audio, Node, `fetch`, timers or `async`.
  - `dsp/`: C-style kernels: `systems.ts`, `rk4.ts`, `filters.ts`, `pitch.ts`, `rng.ts`.
  - `catalog.ts` (catalog model, numpy-compatible `interp`), `patch.ts` (document rules,
    edits), `graph.ts` (cable rules, ordering, input preparation), `blocks/`, `engine.ts`
    (`Engine` implements `EnginePort`).
- `src/ports.ts`: `EnginePort` (driving) and `DiagnosticsSink` (driven).
- `src/adapters/`: `offline.ts`, `wav.ts`, `node/` (CLI, file loading), `worklet/` (the
  AudioWorklet processor and its message protocol).
- `test/`: Vitest. `golden.test.ts` holds the cross-engine tests;
  `architecture.test.ts` enforces the purity of the core.

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
  That is also what keeps a C++ port mechanical.
- **Readable for a Python programmer.** Comment TypeScript idioms when they first appear:
  `x!` means "this is not undefined" (needed with `noUncheckedIndexedAccess`); `import type`
  imports only types; `readonly` makes a field immutable.
