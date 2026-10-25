/** Node entry point: file-system adapters plus the offline renderer and WAV encoder. */

export { type OfflineOptions, type OfflineResult, renderOffline } from "../offline.ts";
export { encodeWav, type WavFormat } from "../wav.ts";
export { defaultCatalogPath, REPO_ROOT, readCatalog, readPatch } from "./catalog-file.ts";
