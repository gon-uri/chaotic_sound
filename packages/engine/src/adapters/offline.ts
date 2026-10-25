/**
 * Offline rendering (driving adapter): runs the engine for a fixed length. Pure, so it works
 * in Node and in a Web Worker (WAV export).
 */

import type { CatalogDocument } from "../core/catalog.ts";
import { Engine } from "../core/engine.ts";
import type { PatchDocument } from "../core/patch.ts";
import type { Diagnostics } from "../ports.ts";

export interface OfflineOptions {
  readonly sampleRate?: number;
  /** Render length: give `seconds` or `frames`. */
  readonly seconds?: number;
  readonly frames?: number;
  /** Chunk size; the output does not depend on it (spec §6). */
  readonly blockSize?: number;
}

export interface OfflineResult {
  readonly left: Float64Array;
  readonly right: Float64Array;
  readonly sampleRate: number;
  readonly diagnostics: Diagnostics;
}

export function renderOffline(
  patch: PatchDocument,
  catalog: CatalogDocument,
  options: OfflineOptions = {},
): OfflineResult {
  const sampleRate = options.sampleRate ?? 48_000;
  const frames = options.frames ?? Math.round((options.seconds ?? 10) * sampleRate);
  const engine = new Engine({ maxFrames: options.blockSize ?? 512 });
  engine.load(patch, catalog, sampleRate);
  const left = new Float64Array(frames);
  const right = new Float64Array(frames);
  engine.process(frames, left, right);
  return { left, right, sampleRate, diagnostics: engine.diagnostics() };
}
