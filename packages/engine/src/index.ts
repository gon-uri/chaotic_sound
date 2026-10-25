/**
 * @chaotic-sound/engine — the pure core and its ports (ADR 0011).
 * Platform adapters live under `adapters/` and are imported from their own entry points.
 */

export { Dynamical, Modulator, shapeValue } from "./core/blocks/index.ts";
export {
  Catalog,
  type CatalogDocument,
  CatalogEntry,
  CatalogError,
  interp,
} from "./core/catalog.ts";
export { centsBetween, midiToHz, noteToHz, noteToMidi } from "./core/dsp/pitch.ts";
export { crc32, Mulberry32, stableSeed } from "./core/dsp/rng.ts";
export { audioVariables, getSystem, SYSTEMS, type SystemDef } from "./core/dsp/systems.ts";
export { Engine, type EngineOptions } from "./core/engine.ts";
export {
  applyEdit,
  BLOCK_SPECS,
  type BlockJson,
  type CableJson,
  normalizePatch,
  type ParamValue,
  type PatchDocument,
  type PatchEdit,
  PatchError,
} from "./core/patch.ts";
export type { Diagnostics, DiagnosticsSink, EnginePort } from "./ports.ts";
