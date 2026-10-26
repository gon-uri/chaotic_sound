/**
 * The patch store: the patch JSON (spec §5) is the single source of truth. Every action
 * goes through the engine's own validation (`applyEdit` + a trial `Engine.load`), so the UI
 * can never hold a patch the engine would reject. Each accepted change is also emitted as
 * a message for the audio worklet (see audio/engineBridge.ts).
 */

import {
  applyEdit,
  type BlockJson,
  type BlockType,
  checkAndOrder,
  diffPatch,
  Engine,
  normalizePatch,
  type ParamValue,
  type PatchDocument,
  type PatchEdit,
} from "@chaotic-sound/engine";
import type { ToWorklet } from "@chaotic-sound/engine/worklet/protocol";
import { create } from "zustand";
import { catalog, catalogDocument } from "./catalog.ts";

const STORAGE_KEY = "chaotic-sound:patch";
const HISTORY_LIMIT = 100;

export interface Position {
  x: number;
  y: number;
}

type Listener = (msg: ToWorklet) => void;
const listeners = new Set<Listener>();

/** Subscribe to engine messages (the audio bridge does). Returns an unsubscribe function. */
export function onEngineMessage(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(msg: ToWorklet): void {
  for (const fn of listeners) fn(msg);
}

/** Full validation, exactly as the engine does it (throws PatchError). */
export function validatePatch(doc: PatchDocument): PatchDocument {
  const normalized = normalizePatch(doc);
  new Engine({ maxFrames: 1 }).load(normalized, catalog, 48_000);
  return normalized;
}

/**
 * Tell the engine to go from `from` to `to` (undo, redo). If every intermediate patch is
 * valid, send the few edits that differ, so unchanged boxes keep playing; otherwise reload.
 */
function emitTransition(from: PatchDocument, to: PatchDocument): void {
  const edits = diffPatch(from, to);
  try {
    let doc = from;
    for (const e of edits) {
      doc = applyEdit(doc, e);
      checkAndOrder(doc);
    }
  } catch {
    emit({ type: "load", patch: to, catalog: catalogDocument });
    return;
  }
  for (const edit of edits) emit({ type: "edit", edit });
}

export function defaultPatch(): PatchDocument {
  return {
    format: "chaotic-sound-patch",
    version: 0,
    blocks: [
      { id: "osc1", type: "dynamical", params: { system: "rossler" }, ui: { x: 80, y: 120 } },
      { id: "out", type: "output", params: {}, ui: { x: 460, y: 140 } },
    ],
    cables: [{ from: "osc1.out", to: "out.in" }],
  };
}

const ID_PREFIX: Record<BlockType, string> = {
  modulator: "mod",
  dynamical: "osc",
  sum: "mix",
  control_sum: "csum",
  output: "out",
};

function freshId(doc: PatchDocument, type: BlockType): string {
  const prefix = ID_PREFIX[type];
  for (let i = 1; ; i++) {
    const id = `${prefix}${i}`;
    if (!doc.blocks.some((b) => b.id === id)) return id;
  }
}

function loadSaved(): PatchDocument {
  try {
    const text = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (text) return validatePatch(JSON.parse(text) as PatchDocument);
  } catch {
    // ignore a missing, private or corrupt store: start from the default patch
  }
  return validatePatch(defaultPatch());
}

function save(doc: PatchDocument): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(doc));
  } catch {
    // storage can be unavailable (private mode); saving is a convenience only
  }
}

export interface PatchState {
  doc: PatchDocument;
  /** Incremented when a whole patch is loaded (the canvas re-fits the view). */
  loads: number;
  past: PatchDocument[];
  future: PatchDocument[];
  error: string | null;
  /** Load a whole patch (validated); clears the undo history. */
  load: (doc: PatchDocument) => void;
  /** Apply a structural edit (validated). Returns false and sets `error` if rejected. */
  edit: (edit: PatchEdit) => boolean;
  /** Change one parameter (knob or setting). */
  setParam: (blockId: string, name: string, value: ParamValue | null) => void;
  /** Add a block of `type` at `pos`; returns its id. */
  addBlock: (type: BlockType, pos: Position) => string | null;
  /** Move a block in the editor (UI only; not sent to the engine). */
  moveBlock: (blockId: string, pos: Position) => void;
  undo: () => void;
  redo: () => void;
  clearError: () => void;
}

export const usePatchStore = create<PatchState>((set, get) => {
  const commit = (next: PatchDocument, msg: ToWorklet | null, coalesceKey?: string): void => {
    const { doc, past } = get();
    const coalesce = coalesceKey !== undefined && coalesceKey === lastKey;
    lastKey = coalesceKey;
    set({
      doc: next,
      past: coalesce ? past : [...past, doc].slice(-HISTORY_LIMIT),
      future: [],
      error: null,
    });
    save(next);
    if (msg) emit(msg);
  };
  let lastKey: string | undefined;

  return {
    doc: loadSaved(),
    loads: 0,
    past: [],
    future: [],
    error: null,

    load: (doc) => {
      try {
        const next = validatePatch(doc);
        lastKey = undefined;
        set((st) => ({ doc: next, past: [], future: [], error: null, loads: st.loads + 1 }));
        save(next);
        emit({ type: "load", patch: next, catalog: catalogDocument });
      } catch (e) {
        set({ error: (e as Error).message });
      }
    },

    edit: (e) => {
      try {
        const next = validatePatch(applyEdit(get().doc, e));
        commit(next, { type: "edit", edit: e });
        return true;
      } catch (err) {
        set({ error: (err as Error).message });
        return false;
      }
    },

    setParam: (blockId, name, value) => {
      const { doc } = get();
      if (!doc.blocks.some((b) => b.id === blockId)) return;
      try {
        const next = validatePatch(
          applyEdit(doc, { op: "setParams", id: blockId, params: { [name]: value } }),
        );
        commit(next, { type: "setParam", blockId, name, value }, `${blockId}.${name}`);
      } catch (err) {
        set({ error: (err as Error).message });
      }
    },

    addBlock: (type, pos) => {
      const { doc } = get();
      if (type === "output" && doc.blocks.some((b) => b.type === "output")) {
        set({ error: "A patch has exactly one Output box." });
        return null;
      }
      const id = freshId(doc, type);
      const block: BlockJson = { id, type, params: {}, ui: { x: pos.x, y: pos.y } };
      return get().edit({ op: "addBlock", block }) ? id : null;
    },

    moveBlock: (blockId, pos) => {
      const { doc } = get();
      const blocks = doc.blocks.map((b) =>
        b.id === blockId ? { ...b, ui: { x: pos.x, y: pos.y } } : b,
      );
      const next = { ...doc, blocks };
      set({ doc: next });
      save(next);
    },

    undo: () => {
      const { past, doc, future } = get();
      const prev = past[past.length - 1];
      if (prev === undefined) return;
      lastKey = undefined;
      set({ doc: prev, past: past.slice(0, -1), future: [doc, ...future], error: null });
      save(prev);
      emitTransition(doc, prev);
    },

    redo: () => {
      const { past, doc, future } = get();
      const next = future[0];
      if (next === undefined) return;
      lastKey = undefined;
      set({ doc: next, past: [...past, doc], future: future.slice(1), error: null });
      save(next);
      emitTransition(doc, next);
    },

    clearError: () => set({ error: null }),
  };
});

/**
 * Positions for every block: its saved `ui` position, or an automatic left-to-right layout
 * by signal flow (column = longest path from a source block), for patches without positions.
 */
export function layout(doc: PatchDocument): Map<string, Position> {
  const depth = new Map<string, number>();
  const parents = new Map<string, string[]>(doc.blocks.map((b) => [b.id, []]));
  for (const c of doc.cables) {
    const src = c.from.slice(0, c.from.indexOf("."));
    const dst = c.to.slice(0, c.to.indexOf("."));
    parents.get(dst)?.push(src);
  }
  const visit = (id: string, seen: Set<string>): number => {
    const known = depth.get(id);
    if (known !== undefined) return known;
    if (seen.has(id)) return 0; // cycles are rejected elsewhere; be safe
    seen.add(id);
    const d = Math.max(-1, ...(parents.get(id) ?? []).map((p) => visit(p, seen))) + 1;
    depth.set(id, d);
    return d;
  };
  const rows = new Map<number, number>();
  const out = new Map<string, Position>();
  for (const b of doc.blocks) {
    const ui = b.ui as Partial<Position> | undefined;
    if (ui && typeof ui.x === "number" && typeof ui.y === "number") {
      out.set(b.id, { x: ui.x, y: ui.y });
      continue;
    }
    const col = visit(b.id, new Set());
    const row = rows.get(col) ?? 0;
    rows.set(col, row + 1);
    out.set(b.id, { x: 40 + 300 * col, y: 40 + 290 * row });
  }
  return out;
}
