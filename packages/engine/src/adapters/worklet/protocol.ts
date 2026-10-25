/**
 * Messages between the UI thread and the AudioWorklet processor (shared types).
 * The UI owns the patch document and sends edits; the worklet applies them between
 * render quanta and reports diagnostics about four times per second.
 */

import type { CatalogDocument } from "../../core/catalog.ts";
import type { ParamValue, PatchDocument, PatchEdit } from "../../core/patch.ts";
import type { Diagnostics } from "../../ports.ts";

export type ToWorklet =
  | { type: "load"; patch: PatchDocument; catalog: CatalogDocument }
  | { type: "edit"; edit: PatchEdit }
  | { type: "setParam"; blockId: string; name: string; value: ParamValue | null }
  | { type: "reset" }
  | { type: "play"; playing: boolean };

export type FromWorklet =
  | { type: "loaded" }
  | { type: "error"; message: string }
  | { type: "diagnostics"; diagnostics: Diagnostics; frames: number };

/** Name the processor is registered under (`new AudioWorkletNode(ctx, PROCESSOR_NAME)`). */
export const PROCESSOR_NAME = "chaotic-sound";
