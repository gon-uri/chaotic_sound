/**
 * Graph compiler (architecture layer 5): validates the cables of a normalized patch,
 * orders the blocks topologically and wires preallocated buffers between them (spec §3, §6).
 * Mirrors `lab/src/chaotic_sound/patch.py` (connect rules, Kahn ordering, fan-in).
 */

import type { BlockRuntime, PortSignal } from "./blocks/index.ts";
import { BLOCK_SPECS, type PatchDocument, PatchError, splitRef } from "./patch.ts";

/** One input port at run time: where its signal comes from. */
export interface InputWiring {
  /** Source port signals, in cable order. */
  readonly sources: readonly PortSignal[];
  readonly control: boolean;
  /** Buffers the prepared input is written into (sanitized and/or summed). */
  readonly scratch: PortSignal;
}

/** One block in processing order, with its input wiring and a reusable inputs array. */
export interface GraphStep {
  readonly block: BlockRuntime;
  readonly wiring: readonly InputWiring[];
  /** Filled before each `process()` call (one entry per input port; no allocation). */
  readonly inputs: (PortSignal | null)[];
}

/** A compiled patch: blocks in processing order with their inputs. */
export interface CompiledGraph {
  readonly steps: readonly GraphStep[];
  readonly sink: BlockRuntime;
}

/**
 * Check the cables of `doc` against the block specs and return the processing order
 * (Kahn's algorithm, ties broken by file order — same as the reference).
 */
export function checkAndOrder(doc: PatchDocument): string[] {
  const ids = new Set<string>();
  let sinks = 0;
  for (const b of doc.blocks) {
    if (ids.has(b.id)) throw new PatchError(`duplicate block id ${JSON.stringify(b.id)}`);
    ids.add(b.id);
    if (BLOCK_SPECS[b.type].sink === true) sinks++;
  }
  if (sinks !== 1) throw new PatchError(`a patch needs exactly one output block (found ${sinks})`);
  const typeOf = new Map(doc.blocks.map((b) => [b.id, b.type]));
  const seen = new Set<string>();
  const taken = new Set<string>();
  for (const c of doc.cables) {
    const [sb, sp] = splitRef(c.from);
    const [db, dp] = splitRef(c.to);
    const st = typeOf.get(sb);
    const dt = typeOf.get(db);
    if (st === undefined) throw new PatchError(`no block with id ${JSON.stringify(sb)}`);
    if (dt === undefined) throw new PatchError(`no block with id ${JSON.stringify(db)}`);
    const out = BLOCK_SPECS[st].outputs.find((p) => p.name === sp);
    if (out === undefined) throw new PatchError(`${st} has no output ${JSON.stringify(sp)}`);
    const inp = BLOCK_SPECS[dt].inputs.find((p) => p.name === dp);
    if (inp === undefined) throw new PatchError(`${dt} has no input ${JSON.stringify(dp)}`);
    if (out.type !== inp.type) {
      throw new PatchError(`cannot connect ${c.from} (${out.type}) to ${c.to} (${inp.type})`);
    }
    const key = `${c.from}→${c.to}`;
    if (seen.has(key)) throw new PatchError(`cable ${c.from} → ${c.to} already exists`);
    seen.add(key);
    if (taken.has(c.to) && !inp.multi) {
      const helper = inp.type === "control" ? "control_sum" : "sum";
      throw new PatchError(
        `input ${c.to} accepts only one cable (combine signals with a ${helper} block)`,
      );
    }
    taken.add(c.to);
  }
  // Kahn's algorithm with a FIFO queue; children in cable order.
  const indegree = new Map(doc.blocks.map((b) => [b.id, 0]));
  const children = new Map<string, string[]>(doc.blocks.map((b) => [b.id, []]));
  for (const c of doc.cables) {
    const [sb] = splitRef(c.from);
    const [db] = splitRef(c.to);
    indegree.set(db, (indegree.get(db) ?? 0) + 1);
    children.get(sb)?.push(db);
  }
  const ready = doc.blocks.filter((b) => indegree.get(b.id) === 0).map((b) => b.id);
  const ordered: string[] = [];
  while (ready.length > 0) {
    const bid = ready.shift()!;
    ordered.push(bid);
    for (const child of children.get(bid) ?? []) {
      const d = (indegree.get(child) ?? 0) - 1;
      indegree.set(child, d);
      if (d === 0) ready.push(child);
    }
  }
  if (ordered.length !== doc.blocks.length) {
    const stuck = doc.blocks.map((b) => b.id).filter((id) => !ordered.includes(id));
    throw new PatchError(
      `cables form a cycle through ${stuck.sort().join(", ")} (feedback is not supported)`,
    );
  }
  return ordered;
}

/** Wire `blocks` (by id) according to `doc`; `maxFrames` sizes the scratch buffers. */
export function compileGraph(
  doc: PatchDocument,
  blocks: ReadonlyMap<string, BlockRuntime>,
  maxFrames: number,
): CompiledGraph {
  const order = checkAndOrder(doc).map((id) => blocks.get(id)!);
  const steps: GraphStep[] = [];
  for (const block of order) {
    const wiring = block.spec.inputs.map((port) => {
      const sources = doc.cables
        .filter((c) => c.to === `${block.id}.${port.name}`)
        .map((c) => {
          const [sb, sp] = splitRef(c.from);
          const src = blocks.get(sb)!;
          const index = src.spec.outputs.findIndex((p) => p.name === sp);
          return src.outputs[index]!;
        });
      const channels = port.type === "audio" ? 2 : 1;
      const scratch = Array.from({ length: channels }, () => new Float64Array(maxFrames));
      return { sources, control: port.type === "control", scratch };
    });
    steps.push({ block, wiring, inputs: wiring.map(() => null) });
  }
  const sink = order.find((b) => b.main !== undefined)!;
  return { steps, sink };
}

/** Sanitize a control value: NaN → 0, +∞ → 1, −∞ → 0, then clip to [0, 1] (spec §3). */
export function sanitizeControl(v: number): number {
  if (Number.isNaN(v)) return 0;
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Prepare one input for `n` samples. Single-cable audio inputs are passed through without
 * copying; control cables are sanitized one by one, then summed (spec §3).
 */
export function prepareInput(w: InputWiring, n: number): PortSignal | null {
  const { sources, scratch, control } = w;
  if (sources.length === 0) return null;
  if (!control && sources.length === 1) return sources[0]!;
  for (let ch = 0; ch < scratch.length; ch++) {
    const dst = scratch[ch]!;
    const first = sources[0]![ch]!;
    for (let i = 0; i < n; i++) dst[i] = control ? sanitizeControl(first[i]!) : first[i]!;
    for (let s = 1; s < sources.length; s++) {
      const src = sources[s]![ch]!;
      for (let i = 0; i < n; i++) dst[i] = dst[i]! + (control ? sanitizeControl(src[i]!) : src[i]!);
    }
  }
  return scratch;
}
