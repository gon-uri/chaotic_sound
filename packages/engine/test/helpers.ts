import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { REPO_ROOT, readCatalog } from "../src/adapters/node/catalog-file.ts";
import type { CatalogDocument } from "../src/core/catalog.ts";
import type { PatchDocument } from "../src/core/patch.ts";

export const EXAMPLES = resolve(REPO_ROOT, "examples");
export const catalog: CatalogDocument = readCatalog();

/** Golden files (`examples/golden/*.json`), one per demo patch or golden fixture. */
export function goldenFiles(): string[] {
  return readdirSync(resolve(EXAMPLES, "golden"))
    .filter((f) => f.endsWith(".json"))
    .sort();
}

/** A patch from `examples/patches/` by file name, or any path relative to `examples/`. */
export function loadPatch(name: string): PatchDocument {
  const path = name.includes("/") ? resolve(EXAMPLES, name) : resolve(EXAMPLES, "patches", name);
  return JSON.parse(readFileSync(path, "utf8")) as PatchDocument;
}

export function f64(b64: string): Float64Array {
  const bytes = Buffer.from(b64, "base64");
  return new Float64Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 8);
}

/** A one-voice patch, like the Python tests' `single()`. */
export function single(params: Record<string, unknown> = {}, volume = 0.5): PatchDocument {
  return {
    format: "chaotic-sound-patch",
    version: 0,
    blocks: [
      { id: "osc", type: "dynamical", params: params as Record<string, never> },
      { id: "out", type: "output", params: { volume } },
    ],
    cables: [{ from: "osc.out", to: "out.in" }],
  };
}

export function rms(x: Float64Array, from = 0): number {
  let s = 0;
  let m = 0;
  const n = x.length - from;
  for (let i = from; i < x.length; i++) m += x[i]!;
  m /= n;
  for (let i = from; i < x.length; i++) s += (x[i]! - m) ** 2;
  return Math.sqrt(s / n);
}
