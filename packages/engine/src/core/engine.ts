/**
 * The engine: implements the driving port `EnginePort` (ADR 0011). Pure TypeScript — it
 * receives the patch and catalog as data and writes audio into caller-provided buffers.
 */

import type { Diagnostics, EnginePort } from "../ports.ts";
import { type BlockRuntime, createBlock } from "./blocks/index.ts";
import { Catalog, type CatalogDocument } from "./catalog.ts";
import { type CompiledGraph, compileGraph, prepareInput } from "./graph.ts";
import {
  applyEdit,
  type BlockJson,
  normalizePatch,
  type ParamValue,
  type PatchDocument,
  type PatchEdit,
  PatchError,
  validateParams,
} from "./patch.ts";

export interface EngineOptions {
  /** Largest chunk processed at once (buffer size). 128 matches the AudioWorklet quantum. */
  readonly maxFrames?: number;
}

export class Engine implements EnginePort {
  readonly maxFrames: number;
  private doc: PatchDocument | null = null;
  private catalog: Catalog | null = null;
  private sampleRate = 48_000;
  private blocks = new Map<string, BlockRuntime>();
  private graph: CompiledGraph | null = null;
  private blockKeys = new Map<string, string>();

  constructor(options: EngineOptions = {}) {
    this.maxFrames = options.maxFrames ?? 1024;
    if (!(this.maxFrames >= 1)) throw new RangeError("maxFrames must be ≥ 1");
  }

  /** The current (normalized) patch document. */
  get patch(): PatchDocument | null {
    return this.doc;
  }

  /**
   * Replace the patch. Atomic: if the patch, the catalog or the sample rate is invalid, it
   * throws and the engine keeps playing the previous patch unchanged.
   */
  load(patch: PatchDocument, catalog: CatalogDocument | Catalog, sampleRate: number): void {
    if (!(Number.isFinite(sampleRate) && sampleRate > 0)) {
      throw new RangeError(`sampleRate must be a positive number, got ${sampleRate}`);
    }
    const cat = catalog instanceof Catalog ? catalog : new Catalog(catalog);
    this.install(normalizePatch(patch), cat, sampleRate, false);
  }

  /**
   * Apply a structural edit. Blocks that the edit does not touch keep their state. A
   * `setParams` edit that only changes live settings (knobs, pitch settings) is applied
   * inside the running block, exactly like {@link setParam}. Atomic, like {@link load}.
   */
  edit(e: PatchEdit): void {
    if (this.doc === null || this.catalog === null) throw new PatchError("no patch loaded");
    if (e.op === "setParams" && this.setLive(e.id, e.params)) return;
    this.install(applyEdit(this.doc, e), this.catalog, this.sampleRate, true);
  }

  /**
   * Change one parameter (spec §6). Knobs (param, amp, gain, volume) and pitch settings are
   * applied live inside the running block, which keeps its state; any other setting
   * recreates the block. `null` restores the default.
   */
  setParam(blockId: string, name: string, value: ParamValue | null): void {
    this.edit({ op: "setParams", id: blockId, params: { [name]: value } });
  }

  /**
   * Try to apply `params` inside the running block. Returns false (changing nothing) when a
   * setting needs a new block. Throws PatchError on an invalid value, changing nothing.
   */
  private setLive(blockId: string, params: Readonly<Record<string, ParamValue | null>>): boolean {
    const doc = this.doc!;
    const index = doc.blocks.findIndex((b) => b.id === blockId);
    const entry = doc.blocks[index];
    const block = this.blocks.get(blockId);
    if (entry === undefined || block === undefined || block.setParam === undefined) return false;
    const old = (entry.params ?? {}) as Record<string, ParamValue>;
    const clean = validateParams(blockId, entry.type, { ...old, ...params }); // throws if invalid
    const names = Object.keys(params).filter((k) => clean[k] !== old[k]);
    const applied: string[] = [];
    try {
      for (const name of names) {
        if (!block.setParam(name, clean[name])) {
          rollback(block, applied, old);
          return false; // e.g. `system` or `seed`: the caller recreates the block
        }
        applied.push(name);
      }
    } catch {
      // A value was rejected against the block's partly updated settings (e.g. pitch_min
      // above the old pitch_max, or a note above Nyquist). Undo, then let the caller rebuild
      // the block from the final settings: that accepts a valid final document whatever the
      // key order, and rejects an invalid one with the block's own error, changing nothing.
      rollback(block, applied, old);
      return false;
    }
    const updated: BlockJson = { ...entry, params: clean };
    const blocks = doc.blocks.slice();
    blocks[index] = updated;
    this.doc = { ...doc, blocks };
    this.blockKeys.set(blockId, blockKey(updated));
    return true;
  }

  /**
   * Build blocks for `doc` (reusing unchanged ones when `reuse`, which keep their state),
   * compile the graph and reset the new blocks. Nothing is committed unless all succeed.
   */
  private install(doc: PatchDocument, catalog: Catalog, sampleRate: number, reuse: boolean): void {
    const ctx = { catalog, maxFrames: this.maxFrames };
    const next = new Map<string, BlockRuntime>();
    const keys = new Map<string, string>();
    const fresh: BlockRuntime[] = [];
    for (const b of doc.blocks) {
      const key = blockKey(b);
      const old = this.blocks.get(b.id);
      if (reuse && old !== undefined && this.blockKeys.get(b.id) === key) {
        next.set(b.id, old);
      } else {
        const block = createBlock(b, ctx);
        next.set(b.id, block);
        fresh.push(block);
      }
      keys.set(b.id, key);
    }
    const graph = compileGraph(doc, next, this.maxFrames);
    for (const block of fresh) block.reset(sampleRate); // new objects: safe if one throws
    this.catalog = catalog;
    this.sampleRate = sampleRate;
    this.doc = doc;
    this.blocks = next;
    this.blockKeys = keys;
    this.graph = graph;
  }

  process(
    frames: number,
    left: Float32Array | Float64Array,
    right: Float32Array | Float64Array,
  ): void {
    const graph = this.graph;
    if (graph === null) {
      left.fill(0, 0, frames);
      right.fill(0, 0, frames);
      return;
    }
    // Indexed loops over preallocated arrays: nothing here allocates (real-time safety).
    const steps = graph.steps;
    const main = graph.sink.main!;
    const mainL = main[0]!;
    const mainR = main[1]!;
    let pos = 0;
    while (pos < frames) {
      const n = Math.min(this.maxFrames, frames - pos);
      for (let s = 0; s < steps.length; s++) {
        const step = steps[s]!;
        const wiring = step.wiring;
        const ins = step.inputs;
        for (let j = 0; j < wiring.length; j++) ins[j] = prepareInput(wiring[j]!, n);
        step.block.process(n, ins);
      }
      for (let i = 0; i < n; i++) {
        left[pos + i] = mainL[i]!;
        right[pos + i] = mainR[i]!;
      }
      pos += n;
    }
  }

  reset(): void {
    for (const block of this.blocks.values()) block.reset(this.sampleRate);
  }

  diagnostics(): Diagnostics {
    const out: Diagnostics = {};
    for (const [id, block] of this.blocks) {
      const d = block.diagnostics();
      if (Object.keys(d).length > 0) out[id] = d;
    }
    return out;
  }

  /** Runtime block by id (for adapters and tests). */
  block(id: string): BlockRuntime | undefined {
    return this.blocks.get(id);
  }
}

/**
 * Undo live changes already applied to `block`, newest first, so every intermediate state
 * is one the block has already been in (each was valid).
 */
function rollback(block: BlockRuntime, names: readonly string[], old: Record<string, ParamValue>) {
  for (let i = names.length - 1; i >= 0; i--) block.setParam?.(names[i]!, old[names[i]!]);
}

/** Identity of a block's settings: a block is reused only while this stays the same. */
function blockKey(b: BlockJson): string {
  const params = b.params ?? {};
  const sorted = Object.keys(params)
    .sort()
    .map((k) => [k, params[k]]);
  return JSON.stringify([b.type, sorted]);
}
