/**
 * Ports of the engine core (hexagonal architecture, ADR 0011).
 *
 * - `EnginePort` is the *driving* port: what adapters (AudioWorklet, offline renderer, CLI,
 *   tests) call. Everything crossing it is plain data or a flat float buffer, so a future
 *   C++/WebAssembly core can implement the same interface.
 * - `DiagnosticsSink` is a *driven* port: where the core may report counters. Adapters
 *   implement it (post to the UI, log, collect in tests).
 */

import type { CatalogDocument } from "./core/catalog.ts";
import type { ParamValue, PatchDocument, PatchEdit } from "./core/patch.ts";

/** Per-block diagnostics, e.g. `{ lorenz: { safety_resets: 0 } }`. */
export type Diagnostics = Record<string, Record<string, number>>;

export interface EnginePort {
  /** Validate and compile a patch; resets every block to t = 0. Throws PatchError. */
  load(patch: PatchDocument, catalog: CatalogDocument, sampleRate: number): void;
  /** Apply a structural edit; unchanged blocks keep their state. Throws PatchError. */
  edit(e: PatchEdit): void;
  /** Change one parameter of one block (recreates that block if needed). */
  setParam(blockId: string, name: string, value: ParamValue | null): void;
  /** Render the next `frames` samples into `left` and `right` (any length ≥ frames). */
  process(
    frames: number,
    left: Float32Array | Float64Array,
    right: Float32Array | Float64Array,
  ): void;
  /** Restart every block at t = 0. */
  reset(): void;
  /** Counters per block (safety resets, …). */
  diagnostics(): Diagnostics;
}

export interface DiagnosticsSink {
  report(d: Diagnostics): void;
}
