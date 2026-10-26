/**
 * Ports of the engine core (hexagonal architecture, ADR 0011).
 *
 * `EnginePort` is the *driving* port: what adapters (AudioWorklet, offline renderer, CLI,
 * tests) call. Everything crossing it is plain data or a flat float buffer, so a future
 * C++/WebAssembly core can implement the same interface.
 *
 * The core needs nothing from outside except data passed to `load()` (the catalog arrives as
 * a parsed document; reading the file is an adapter's job), so there are no driven ports.
 * Adapters poll `diagnostics()` (the worklet does it every 250 ms).
 */

import type { CatalogDocument } from "./core/catalog.ts";
import type { ParamValue, PatchDocument, PatchEdit } from "./core/patch.ts";

/** Per-block diagnostics, e.g. `{ lorenz: { safety_resets: 0 } }`. */
export type Diagnostics = Record<string, Record<string, number>>;

export interface EnginePort {
  /**
   * Validate and compile a patch; resets every block to t = 0. Atomic: on an error
   * (PatchError, CatalogError, RangeError) the previous patch keeps playing unchanged.
   */
  load(patch: PatchDocument, catalog: CatalogDocument, sampleRate: number): void;
  /**
   * Apply an edit; blocks it does not touch keep their state. A `setParams` edit of live
   * settings (knobs, pitch settings; spec §6) updates the running block. Atomic, like load.
   */
  edit(e: PatchEdit): void;
  /** Same as `edit({ op: "setParams", id: blockId, params: { [name]: value } })`. */
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
