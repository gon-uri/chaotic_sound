/**
 * ADR 0011: the core is pure. No file in src/core (or src/ports.ts) may import an adapter,
 * a Node module or anything outside the core, nor use platform globals.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { expect, test } from "vitest";

const SRC = resolve(import.meta.dirname, "../src");
/** Platform globals, matched by how they are used (so a method named `process` is fine). */
const BANNED: readonly [string, RegExp][] = [
  ["fetch()", /(?<![\w.$])fetch\s*\(/],
  ["require()", /(?<![\w.$])require\s*\(/],
  ["timers", /(?<![\w.$])(setTimeout|setInterval|requestAnimationFrame)\s*\(/],
  ["registerProcessor()", /(?<![\w.$])registerProcessor\s*\(/],
  [
    "platform objects",
    /(?<![\w.$])(window|document|process|globalThis|localStorage|performance|Buffer|navigator)\s*\./,
  ],
  [
    "platform classes",
    /\b(new|extends)\s+(AudioContext|AudioWorkletProcessor|AudioWorkletNode|TextEncoder|TextDecoder|XMLHttpRequest|WebSocket|Worker)\b/,
  ],
];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : p.endsWith(".ts") ? [p] : [];
  });
}

function code(path: string): string {
  // Strip comments and string literals so that docs mentioning `fetch` do not count.
  return readFileSync(path, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "")
    .replace(/`(?:\\.|[^`\\])*`/g, "``")
    .replace(/"(?:\\.|[^"\\])*"/g, '""');
}

const coreFiles = [...files(join(SRC, "core")), join(SRC, "ports.ts"), join(SRC, "index.ts")];

test.each(coreFiles.map((f) => [relative(SRC, f), f]))("%s stays inside the core", (_, path) => {
  const text = readFileSync(path, "utf8");
  for (const m of text.matchAll(/^\s*(?:import|export)[^;]*?from\s+"([^"]+)"/gm)) {
    const target = m[1]!;
    expect(target.startsWith(".")).toBe(true); // no packages, no node: modules
    const resolved = resolve(path, "..", target);
    const rel = relative(SRC, resolved);
    expect(rel.startsWith("adapters")).toBe(false);
  }
  const body = code(path);
  for (const [label, pattern] of BANNED) {
    expect(pattern.test(body), `${label} in ${relative(SRC, path)}`).toBe(false);
  }
  expect(/\basync\b|\bawait\b/.test(body)).toBe(false);
});
