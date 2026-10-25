/** Read catalog and patch JSON files from disk (Node driven adapter). */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { CatalogDocument } from "../../core/catalog.ts";
import type { PatchDocument } from "../../core/patch.ts";

/** Repository root (this file is packages/engine/src/adapters/node/). */
export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../..");

/** `$CHAOTIC_SOUND_CATALOG` or `<repo>/catalog/systems.json`. */
export function defaultCatalogPath(): string {
  return process.env.CHAOTIC_SOUND_CATALOG ?? resolve(REPO_ROOT, "catalog/systems.json");
}

export function readCatalog(path: string = defaultCatalogPath()): CatalogDocument {
  return JSON.parse(readFileSync(path, "utf8")) as CatalogDocument;
}

export function readPatch(path: string): PatchDocument {
  return JSON.parse(readFileSync(path, "utf8")) as PatchDocument;
}
