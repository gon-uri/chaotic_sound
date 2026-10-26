/**
 * The patch document (spec §5): JSON types, parameter specs, validation and edits.
 * Mirrors the JSON rules of `lab/src/chaotic_sound/patch.py` and the blocks' parameter
 * dataclasses.
 */

export const PATCH_FORMAT = "chaotic-sound-patch";
export const PATCH_VERSION = 0;

export type BlockType = "modulator" | "dynamical" | "sum" | "control_sum" | "output";
export type SignalType = "audio" | "control";
export type ParamValue = number | string | boolean;

/** JSON shape of one block. */
export interface BlockJson {
  id: string;
  type: BlockType;
  params?: Record<string, ParamValue | null>;
  ui?: unknown;
}

/** JSON shape of one cable: `"block.port"` references. */
export interface CableJson {
  from: string;
  to: string;
}

/** JSON shape of a whole patch. */
export interface PatchDocument {
  format: typeof PATCH_FORMAT;
  version: typeof PATCH_VERSION;
  blocks: BlockJson[];
  cables: CableJson[];
  ui?: unknown;
}

export class PatchError extends Error {
  override name = "PatchError";
}

/** A port of a block type. `multi` inputs accept several cables (spec §3). */
export interface PortSpec {
  readonly name: string;
  readonly type: SignalType;
  readonly multi: boolean;
}

/** How a parameter is validated. `undefined` default = "documented default" (e.g. catalog). */
export type ParamSpec =
  | {
      readonly kind: "number";
      readonly min: number;
      readonly max: number;
      readonly default?: number;
    }
  | {
      readonly kind: "integer";
      readonly min: number;
      readonly max: number;
      readonly default?: number;
    }
  | { readonly kind: "boolean"; readonly default: boolean }
  | { readonly kind: "enum"; readonly values: readonly string[]; readonly default?: string }
  | { readonly kind: "string"; readonly default?: string };

export interface BlockSpec {
  readonly inputs: readonly PortSpec[];
  readonly outputs: readonly PortSpec[];
  readonly params: Readonly<Record<string, ParamSpec>>;
  /** The Output block: no output ports; its result is the patch audio. */
  readonly sink?: boolean;
}

const unit = (d?: number): ParamSpec =>
  d === undefined
    ? { kind: "number", min: 0, max: 1 }
    : { kind: "number", min: 0, max: 1, default: d };

/** Ports and parameters of every block type (spec §4). */
export const BLOCK_SPECS: Readonly<Record<BlockType, BlockSpec>> = {
  modulator: {
    inputs: [],
    outputs: [{ name: "out", type: "control", multi: false }],
    params: {
      shape: {
        kind: "enum",
        values: ["sine", "triangle", "square", "ramp_up", "ramp_down"],
        default: "sine",
      },
      period_s: { kind: "number", min: 0.001, max: Number.POSITIVE_INFINITY, default: 4 },
      mode: { kind: "enum", values: ["loop", "once"], default: "loop" },
    },
  },
  dynamical: {
    inputs: [
      { name: "param", type: "control", multi: false },
      { name: "amp", type: "control", multi: false },
      { name: "pitch", type: "control", multi: false },
      { name: "tonality", type: "control", multi: false },
    ],
    outputs: [{ name: "out", type: "audio", multi: false }],
    params: {
      system: { kind: "string", default: "rossler" },
      note: { kind: "string", default: "A3" },
      cents: { kind: "number", min: -100, max: 100, default: 0 },
      pitch_min: { kind: "string", default: "A1" },
      pitch_max: { kind: "string", default: "A5" },
      observable: { kind: "string" },
      observable_right: { kind: "string" },
      pitch_lock: { kind: "boolean", default: true },
      amp_curve: { kind: "enum", values: ["perceptual", "linear"], default: "perceptual" },
      seed: { kind: "integer", min: 0, max: 2 ** 31 - 1 },
      param: unit(),
      amp: unit(1),
      tonality: unit(0.3), // the owner's default: mostly the raw attractor, more pitched
    },
  },
  sum: {
    inputs: [{ name: "in", type: "audio", multi: true }],
    outputs: [{ name: "out", type: "audio", multi: false }],
    params: { gain: unit(1) },
  },
  control_sum: {
    inputs: [{ name: "in", type: "control", multi: true }],
    outputs: [{ name: "out", type: "control", multi: false }],
    params: { gain: unit(1) },
  },
  output: {
    inputs: [{ name: "in", type: "audio", multi: false }],
    outputs: [],
    params: { volume: unit(0.8) },
    sink: true,
  },
};

/**
 * The documented default of a parameter (spec §4), or `undefined` when the default depends
 * on context: `param` (the catalog's default knob position), `observable` (the catalog's
 * default variable), `observable_right` (mono) and `seed` (derived from the block id).
 */
export function defaultParam(type: BlockType, name: string): ParamValue | undefined {
  return BLOCK_SPECS[type].params[name]?.default;
}

/** `params` with every documented default filled in (BLOCK_SPECS is the single source). */
export function withDefaults(
  type: BlockType,
  params: Readonly<Record<string, ParamValue>>,
): Record<string, ParamValue> {
  const out: Record<string, ParamValue> = { ...params };
  for (const [name, spec] of Object.entries(BLOCK_SPECS[type].params)) {
    if (out[name] === undefined && spec.default !== undefined) out[name] = spec.default;
  }
  return out;
}

export function isBlockType(t: unknown): t is BlockType {
  return typeof t === "string" && Object.hasOwn(BLOCK_SPECS, t);
}

function checkValue(where: string, name: string, spec: ParamSpec, value: unknown): void {
  const bad = (expected: string): never => {
    throw new PatchError(
      `${where}: parameter ${JSON.stringify(name)} has the wrong type or value: ` +
        `${JSON.stringify(value)} (expected ${expected})`,
    );
  };
  switch (spec.kind) {
    case "number":
      if (typeof value !== "number" || !Number.isFinite(value)) bad("a number");
      if ((value as number) < spec.min || (value as number) > spec.max) {
        bad(`a number in [${spec.min}, ${spec.max}]`);
      }
      return;
    case "integer":
      if (typeof value !== "number" || !Number.isInteger(value)) bad("an integer");
      if ((value as number) < spec.min || (value as number) > spec.max) {
        bad(`an integer in [${spec.min}, ${spec.max}]`);
      }
      return;
    case "boolean":
      if (typeof value !== "boolean") bad("true or false");
      return;
    case "enum":
      if (typeof value !== "string" || !spec.values.includes(value))
        bad(`one of ${spec.values.join(", ")}`);
      return;
    case "string":
      if (typeof value !== "string") bad("a string");
      return;
  }
}

/**
 * Validate a block's params against its spec: unknown names and wrong types are errors.
 * `null` means "default" (spec §5) and is dropped. Returns the cleaned params.
 */
export function validateParams(
  blockId: string,
  type: BlockType,
  params: Record<string, unknown> | undefined,
): Record<string, ParamValue> {
  const where = `${type} '${blockId}'`;
  if (params === undefined) return {};
  if (params === null || typeof params !== "object" || Array.isArray(params)) {
    throw new PatchError(`${where}: 'params' must be an object`);
  }
  const specs = BLOCK_SPECS[type].params;
  const clean: Record<string, ParamValue> = {};
  for (const [name, value] of Object.entries(params)) {
    const spec = specs[name];
    if (spec === undefined) {
      throw new PatchError(
        `${where}: unknown parameter ${JSON.stringify(name)}; allowed: ${Object.keys(specs).sort().join(", ")}`,
      );
    }
    if (value === null) continue;
    checkValue(where, name, spec, value);
    clean[name] = value as ParamValue;
  }
  return clean;
}

/** Split a `"block.port"` reference at the first `.` (spec §3). */
export function splitRef(ref: unknown): [string, string] {
  if (typeof ref !== "string")
    throw new PatchError(`port reference must be a string, got ${JSON.stringify(ref)}`);
  const i = ref.indexOf(".");
  if (i <= 0 || i === ref.length - 1) {
    throw new PatchError(`port reference must look like 'block.port', got ${JSON.stringify(ref)}`);
  }
  return [ref.slice(0, i), ref.slice(i + 1)];
}

const TOP_KEYS = new Set(["format", "version", "blocks", "cables", "ui"]);
const BLOCK_KEYS = new Set(["id", "type", "params", "ui"]);

/**
 * Check the document's shape (spec §5) and return a normalized copy (nulls dropped).
 * Graph rules (cables, cycles, one output) are checked by the graph compiler.
 */
export function normalizePatch(doc: unknown): PatchDocument {
  if (doc === null || typeof doc !== "object" || Array.isArray(doc)) {
    throw new PatchError("not a chaotic_sound patch");
  }
  const d = doc as Record<string, unknown>;
  if (d.format !== PATCH_FORMAT)
    throw new PatchError("not a chaotic_sound patch (missing 'format')");
  if (d.version !== PATCH_VERSION)
    throw new PatchError(`unsupported patch version ${JSON.stringify(d.version)}`);
  const unknownTop = Object.keys(d).filter((k) => !TOP_KEYS.has(k));
  if (unknownTop.length > 0)
    throw new PatchError(`unknown top-level key(s) ${unknownTop.sort().join(", ")}`);
  const blocksIn = d.blocks ?? [];
  const cablesIn = d.cables ?? [];
  if (!Array.isArray(blocksIn) || !Array.isArray(cablesIn)) {
    throw new PatchError("'blocks' and 'cables' must be arrays");
  }
  const blocks: BlockJson[] = blocksIn.map((b: unknown) => {
    if (b === null || typeof b !== "object" || Array.isArray(b))
      throw new PatchError("bad block entry");
    const bj = b as Record<string, unknown>;
    const extra = Object.keys(bj).filter((k) => !BLOCK_KEYS.has(k));
    if (extra.length > 0 || !("id" in bj) || !("type" in bj)) {
      throw new PatchError(
        `bad block entry ${JSON.stringify(b)} (needs 'id' and 'type'; allowed keys: id, params, type, ui)`,
      );
    }
    const id = bj.id;
    if (typeof id !== "string" || id === "" || id.includes(".")) {
      throw new PatchError(
        `invalid block id ${JSON.stringify(id)} (a non-empty string without '.')`,
      );
    }
    if (!isBlockType(bj.type)) {
      throw new PatchError(
        `unknown block type ${JSON.stringify(bj.type)}; known: ${Object.keys(BLOCK_SPECS).join(", ")}`,
      );
    }
    const params = validateParams(id, bj.type, bj.params as Record<string, unknown> | undefined);
    const out: BlockJson = { id, type: bj.type, params };
    if ("ui" in bj) out.ui = bj.ui;
    return out;
  });
  const cables: CableJson[] = cablesIn.map((c: unknown) => {
    if (c === null || typeof c !== "object" || Array.isArray(c))
      throw new PatchError("bad cable entry");
    const keys = Object.keys(c).sort().join(",");
    if (keys !== "from,to") {
      throw new PatchError(
        `bad cable entry ${JSON.stringify(c)} (it needs exactly 'from' and 'to')`,
      );
    }
    const cj = c as { from: unknown; to: unknown };
    splitRef(cj.from);
    splitRef(cj.to);
    return { from: cj.from as string, to: cj.to as string };
  });
  const out: PatchDocument = { format: PATCH_FORMAT, version: PATCH_VERSION, blocks, cables };
  if ("ui" in d) out.ui = d.ui;
  return out;
}

/** Structural edits for live patching (applied to a document, then re-compiled). */
export type PatchEdit =
  | { op: "addBlock"; block: BlockJson }
  | { op: "removeBlock"; id: string }
  | { op: "connect"; from: string; to: string }
  | { op: "disconnect"; from: string; to: string }
  | { op: "setParams"; id: string; params: Record<string, ParamValue | null> };

/** Apply an edit to a document, returning a new document (the input is not modified). */
export function applyEdit(doc: PatchDocument, edit: PatchEdit): PatchDocument {
  const blocks: BlockJson[] = doc.blocks.map((b) => ({ ...b, params: { ...(b.params ?? {}) } }));
  let cables = doc.cables.map((c) => ({ ...c }));
  switch (edit.op) {
    case "addBlock":
      blocks.push(structuredCloneJson(edit.block));
      break;
    case "removeBlock": {
      const i = blocks.findIndex((b) => b.id === edit.id);
      if (i < 0) throw new PatchError(`no block with id ${JSON.stringify(edit.id)}`);
      blocks.splice(i, 1);
      cables = cables.filter(
        (c) => splitRef(c.from)[0] !== edit.id && splitRef(c.to)[0] !== edit.id,
      );
      break;
    }
    case "connect":
      cables.push({ from: edit.from, to: edit.to });
      break;
    case "disconnect": {
      const i = cables.findIndex((c) => c.from === edit.from && c.to === edit.to);
      if (i < 0) throw new PatchError(`no cable ${edit.from} → ${edit.to}`);
      cables.splice(i, 1);
      break;
    }
    case "setParams": {
      const b = blocks.find((x) => x.id === edit.id);
      if (b === undefined) throw new PatchError(`no block with id ${JSON.stringify(edit.id)}`);
      b.params = { ...b.params, ...edit.params };
      break;
    }
  }
  const next: PatchDocument = { ...doc, blocks, cables };
  return normalizePatch(next);
}

function structuredCloneJson<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

/**
 * The edits that turn `from` into `to` (block `ui` is ignored), so a running engine can
 * follow an undo or redo without restarting the blocks that did not change. Order:
 * disconnect, remove blocks (with their cables), add blocks, set params, connect. A block
 * whose type changed is removed and added again. Applying the edits to `from` gives `to`
 * up to the order of blocks and cables (which does not change the sound beyond rounding:
 * a Sum adds its cables in order).
 */
export function diffPatch(from: PatchDocument, to: PatchDocument): PatchEdit[] {
  const edits: PatchEdit[] = [];
  const cableKey = (c: CableJson): string => `${c.from}→${c.to}`;
  const fromCables = new Set(from.cables.map(cableKey));
  const toCables = new Set(to.cables.map(cableKey));
  const fromBlocks = new Map(from.blocks.map((b) => [b.id, b]));
  const toBlocks = new Map(to.blocks.map((b) => [b.id, b]));
  // Blocks that exist only in `from`, or whose type changed, are rebuilt from scratch.
  const gone = (id: string): boolean => {
    const t = toBlocks.get(id);
    const f = fromBlocks.get(id);
    return t === undefined || (f !== undefined && f.type !== t.type);
  };
  const isNew = (id: string): boolean => !fromBlocks.has(id) || gone(id);
  for (const c of from.cables) {
    const touchesGone = gone(splitRef(c.from)[0]) || gone(splitRef(c.to)[0]);
    if (!toCables.has(cableKey(c)) && !touchesGone) {
      edits.push({ op: "disconnect", from: c.from, to: c.to });
    }
  }
  for (const b of from.blocks) if (gone(b.id)) edits.push({ op: "removeBlock", id: b.id });
  for (const b of to.blocks) {
    if (isNew(b.id))
      edits.push({
        op: "addBlock",
        block: { id: b.id, type: b.type, params: { ...(b.params ?? {}) } },
      });
  }
  for (const b of to.blocks) {
    const f = fromBlocks.get(b.id);
    if (f === undefined || isNew(b.id)) continue;
    const before = f.params ?? {};
    const after = b.params ?? {};
    const params: Record<string, ParamValue | null> = {};
    for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
      const value = after[name] ?? null;
      if (value !== (before[name] ?? null)) params[name] = value; // null = back to default
    }
    if (Object.keys(params).length > 0) edits.push({ op: "setParams", id: b.id, params });
  }
  for (const c of to.cables) {
    const touchesNew = isNew(splitRef(c.from)[0]) || isNew(splitRef(c.to)[0]);
    if (!fromCables.has(cableKey(c)) || touchesNew) {
      edits.push({ op: "connect", from: c.from, to: c.to });
    }
  }
  return edits;
}
