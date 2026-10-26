/**
 * ADR 0011: the core is pure. No file in src/core (or src/ports.ts, src/index.ts) may import
 * an adapter, a package, a Node module, a JSON file or anything else outside the core, nor
 * use platform globals, timers, randomness, or asynchronous code.
 *
 * The check tokenizes each file (strings, template literals, regular expressions, comments)
 * so that words inside strings and comments do not count, and so that every kind of import
 * is seen: `import … from "x"`, side-effect `import "x"`, `export … from "x"` and dynamic
 * `import()`. The fixtures at the end make sure the checker itself catches known bypasses.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, test } from "vitest";

const SRC = resolve(import.meta.dirname, "../src");
const CORE = join(SRC, "core");
const PORTS = join(SRC, "ports.ts");

/** Identifiers the core must never mention (outside strings and comments). */
const BANNED_IDENTIFIERS = [
  // global objects, also through aliases (`const g = globalThis`)
  "globalThis",
  "self",
  "window",
  "document",
  "navigator",
  "localStorage",
  "sessionStorage",
  "indexedDB",
  "performance",
  "Buffer",
  "crypto",
  "console",
  // code from strings
  "eval",
  "Function",
  // asynchronous code and timers
  "Promise",
  "queueMicrotask",
  "setTimeout",
  "setInterval",
  "setImmediate",
  "requestAnimationFrame",
  "WeakRef",
  "FinalizationRegistry",
  // I/O and platform classes
  "fetch",
  "require",
  "XMLHttpRequest",
  "WebSocket",
  "Worker",
  "AudioContext",
  "AudioWorkletProcessor",
  "AudioWorkletNode",
  "registerProcessor",
  "TextEncoder",
  "TextDecoder",
  // non-determinism (spec §6: same patch → bit-identical output)
  "Date",
];

/** Patterns checked on the code with strings and comments removed. */
const BANNED_PATTERNS: readonly [string, RegExp][] = [
  ["dynamic import()", /\bimport\s*\(/],
  ["import.meta", /\bimport\s*\.\s*meta\b/],
  ["Math.random()", /\bMath\s*\.\s*random\b/],
  // `process` is fine as a method name; the Node global is used as `process.x` / `process[x]`.
  ["the Node `process` global", /(?<![\w.$])process\s*[.[]/],
  ["async/await", /\b(async|await)\b/],
];

interface Scanned {
  /** The code with every string replaced by `"#<index>"` and comments removed. */
  readonly code: string;
  /** String literals in order (template literal text is not included). */
  readonly strings: readonly string[];
}

/** Characters after which a `/` starts a regular expression rather than a division. */
const REGEX_PREFIX = new Set(["", "(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";"]);

/** Tokenize just enough of TypeScript to separate code from strings and comments. */
function scan(src: string): Scanned {
  let code = "";
  const strings: string[] = [];
  const templateDepth: number[] = []; // brace depth at each open `${`
  let depth = 0;
  let i = 0;
  const n = src.length;
  const lastSignificant = (): string => code.trimEnd().slice(-1);

  /** Skip template text from index j; returns the index after the closing backtick or `${`. */
  const templateText = (j: number): number => {
    while (j < n) {
      const c = src[j]!;
      if (c === "\\") j += 2;
      else if (c === "`") return j + 1;
      else if (c === "$" && src[j + 1] === "{") {
        templateDepth.push(depth);
        depth++;
        code += "${";
        return j + 2;
      } else j++;
    }
    return j;
  };

  while (i < n) {
    const c = src[i]!;
    const next = src[i + 1];
    if (c === "/" && next === "/") {
      while (i < n && src[i] !== "\n") i++;
    } else if (c === "/" && next === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end < 0 ? n : end + 2;
      code += " ";
    } else if (c === '"' || c === "'") {
      let j = i + 1;
      let s = "";
      while (j < n && src[j] !== c && src[j] !== "\n") {
        if (src[j] === "\\") {
          s += src[j + 1] ?? "";
          j += 2;
        } else {
          s += src[j];
          j++;
        }
      }
      strings.push(s);
      code += `"#${strings.length - 1}"`;
      i = j + 1;
    } else if (c === "`") {
      code += "`";
      i = templateText(i + 1);
      if (src[i - 1] === "`") code += "`";
    } else if (c === "/" && REGEX_PREFIX.has(lastSignificant())) {
      let j = i + 1;
      let inClass = false;
      while (j < n && src[j] !== "\n") {
        const r = src[j]!;
        if (r === "\\") j++;
        else if (r === "[") inClass = true;
        else if (r === "]") inClass = false;
        else if (r === "/" && !inClass) break;
        j++;
      }
      j++;
      while (j < n && /[a-z]/.test(src[j]!)) j++; // flags
      code += "/regex/";
      i = j;
    } else if (c === "}" && templateDepth.length > 0 && templateDepth.at(-1) === depth - 1) {
      templateDepth.pop();
      depth--;
      code += "}";
      i = templateText(i + 1);
      if (src[i - 1] === "`") code += "`";
    } else {
      if (c === "{") depth++;
      else if (c === "}") depth--;
      code += c;
      i++;
    }
  }
  return { code, strings };
}

/** Every module specifier a file imports or re-exports, including side-effect imports. */
function specifiers({ code, strings }: Scanned): string[] {
  const out: string[] = [];
  const patterns = [
    /\b(?:import|export)\b[^;"]*?\bfrom\s*"#(\d+)"/g, // import x from "…", export { x } from "…"
    /\bimport\s*"#(\d+)"/g, // import "…" (side effect)
  ];
  for (const p of patterns) for (const m of code.matchAll(p)) out.push(strings[Number(m[1])]!);
  return out;
}

/** Problems with one core file; `path` decides where relative imports resolve. */
function violations(path: string, src: string): string[] {
  const problems: string[] = [];
  const scanned = scan(src);
  for (const spec of specifiers(scanned)) {
    if (!spec.startsWith(".")) {
      problems.push(`imports a package or platform module: ${spec}`);
      continue;
    }
    const target = resolve(path, "..", spec);
    const inside = target === PORTS || relative(CORE, target).split(/[\\/]/)[0] !== "..";
    if (!inside) problems.push(`imports a file outside the core: ${spec}`);
    else if (!target.endsWith(".ts")) problems.push(`imports a non-TypeScript file: ${spec}`);
  }
  for (const name of BANNED_IDENTIFIERS) {
    // Not part of a longer name, and not a property access such as `obj.self`.
    if (new RegExp(`(?<![\\w$.])${name}(?![\\w$])`).test(scanned.code)) {
      problems.push(`uses ${name}`);
    }
  }
  for (const [label, pattern] of BANNED_PATTERNS) {
    if (pattern.test(scanned.code)) problems.push(`uses ${label}`);
  }
  return problems;
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

const coreFiles = [...files(CORE), PORTS, join(SRC, "index.ts")];

test("the core holds only TypeScript files", () => {
  expect(files(CORE).filter((f) => !f.endsWith(".ts"))).toEqual([]);
});

test.each(coreFiles.map((f) => [relative(SRC, f), f]))("%s stays inside the core", (_, path) => {
  expect(violations(path, readFileSync(path, "utf8"))).toEqual([]);
});

describe("the purity checker", () => {
  const where = join(CORE, "catalog.ts"); // fixtures pretend to live here
  const bad: readonly [string, string][] = [
    ["side-effect import of an adapter", 'import "../adapters/wav.ts";'],
    ["import of a Node module", 'import { readFileSync } from "node:fs";'],
    ["re-export from an adapter", 'export { encodeWav } from "../adapters/wav.ts";'],
    ["dynamic import", 'const m = "node:" + "fs"; import(m);'],
    ["JSON import", 'import cat from "../../../catalog/systems.json" with { type: "json" };'],
    ["globalThis alias", "const g = globalThis as unknown as Record<string, unknown>;"],
    ["Function constructor", 'new Function("return this")();'],
    ["promise-based async", "Promise.resolve().then(f);"],
    ["timer", "setTimeout(f, 0);"],
    ["Node process global", "const env = process.env;"],
    ["randomness", "const r = Math.random();"],
    ["clock", "const t = Date.now();"],
    ["fetch after a URL string", 'const u = "https://example.org"; fetch(u);'],
    // biome-ignore lint/suspicious/noTemplateCurlyInString: this string is fixture source code
    ["fetch inside a template substitution", "const s = `${fetch(u)}`;"],
    ["async function", "async function f() {}"],
  ];
  test.each(bad)("flags %s", (_, src) => {
    expect(violations(where, src)).not.toEqual([]);
  });

  const good: readonly [string, string][] = [
    ["a method named process", "class A { process(n: number): void {} }\nblock.process(n, ins);"],
    // biome-ignore lint/suspicious/noTemplateCurlyInString: this string is fixture source code
    ["words inside strings", 'const s = "call fetch() on globalThis"; const t = `self ${x} Date`;'],
    ["words inside comments", "// fetch(url)\n/* globalThis.process */ const a = 1;"],
    ["a regular expression", 'const RE = /^([A-G])("?)$/u; const q = "ok";'],
    [
      "a core import",
      'import { interp } from "./catalog.ts";\nimport type { X } from "../ports.ts";',
    ],
    ["property names", "const o = { date: 1 }; o.self = 2; x.Function;"],
  ];
  test.each(good)("allows %s", (_, src) => {
    expect(violations(where, src)).toEqual([]);
  });
});
