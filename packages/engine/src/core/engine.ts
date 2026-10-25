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

  load(patch: PatchDocument, catalog: CatalogDocument | Catalog, sampleRate: number): void {
    if (!(Number.isFinite(sampleRate) && sampleRate > 0)) {
      throw new RangeError(`sampleRate must be a positive number, got ${sampleRate}`);
    }
    this.catalog = catalog instanceof Catalog ? catalog : new Catalog(catalog);
    this.sampleRate = sampleRate;
    this.blocks = new Map();
    this.blockKeys = new Map();
    this.install(normalizePatch(patch), true);
  }

  edit(e: PatchEdit): void {
    if (this.doc === null) throw new PatchError("no patch loaded");
    this.install(applyEdit(this.doc, e), false);
  }

  /**
   * Change one parameter. Knobs (param, amp, gain, volume) and pitch settings are applied
   * live inside the existing block, which keeps its state; anything else recreates the block.
   */
  setParam(blockId: string, name: string, value: ParamValue | null): void {
    const doc = this.doc;
    if (doc === null) throw new PatchError("no patch loaded");
    const index = doc.blocks.findIndex((b) => b.id === blockId);
    const entry = doc.blocks[index];
    const block = this.blocks.get(blockId);
    if (entry === undefined || block === undefined) {
      throw new PatchError(`no block with id ${JSON.stringify(blockId)}`);
    }
    const params: Record<string, ParamValue | null> = { ...(entry.params ?? {}), [name]: value };
    const clean = validateParams(blockId, entry.type, params); // throws on invalid values
    if (block.setParam?.(name, clean[name]) === true) {
      const updated: BlockJson = { ...entry, params: clean };
      const blocks = doc.blocks.slice();
      blocks[index] = updated;
      this.doc = { ...doc, blocks };
      this.blockKeys.set(blockId, blockKey(updated));
      return;
    }
    this.edit({ op: "setParams", id: blockId, params: { [name]: value } });
  }

  /**
   * Build blocks for `doc` (reusing unchanged ones, which keep their state) and compile.
   * Nothing is committed if validation fails.
   */
  private install(doc: PatchDocument, resetAll: boolean): void {
    const catalog = this.catalog!;
    const ctx = { catalog, maxFrames: this.maxFrames };
    const next = new Map<string, BlockRuntime>();
    const keys = new Map<string, string>();
    const fresh: BlockRuntime[] = [];
    for (const b of doc.blocks) {
      const key = blockKey(b);
      const old = this.blocks.get(b.id);
      if (!resetAll && old !== undefined && this.blockKeys.get(b.id) === key) {
        next.set(b.id, old);
      } else {
        const block = createBlock(b, ctx);
        next.set(b.id, block);
        fresh.push(block);
      }
      keys.set(b.id, key);
    }
    const graph = compileGraph(doc, next, this.maxFrames);
    for (const block of fresh) block.reset(this.sampleRate);
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
    const [mainL, mainR] = graph.sink.main!;
    let pos = 0;
    while (pos < frames) {
      const n = Math.min(this.maxFrames, frames - pos);
      for (const block of graph.order) {
        const wiring = graph.inputs.get(block.id)!;
        const ins = wiring.map((w) => prepareInput(w, n));
        block.process(n, ins);
      }
      for (let i = 0; i < n; i++) {
        left[pos + i] = mainL![i]!;
        right[pos + i] = mainR![i]!;
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

function blockKey(b: BlockJson): string {
  const params = b.params ?? {};
  const sorted = Object.keys(params)
    .sort()
    .map((k) => [k, params[k]]);
  return JSON.stringify([b.type, sorted]);
}
