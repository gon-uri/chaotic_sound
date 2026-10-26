/**
 * Shared document rules: the edge-case patches of `examples/documents.json`.
 *
 * The Python reference reads the same file (`lab/tests/test_documents.py`), so both engines
 * accept and reject exactly the same patch documents (spec §3, §4, §5).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { Dynamical } from "../src/core/blocks/dynamical.ts";
import { Engine } from "../src/core/engine.ts";
import { type PatchDocument, PatchError } from "../src/core/patch.ts";
import { catalog, EXAMPLES } from "./helpers.ts";

interface DocumentCase {
  name: string;
  outcome: "accept" | "reject";
  rule: string;
  /** Seed each named dynamical box must use (accepted documents only). */
  seeds?: Record<string, number>;
  /** The document under test: any JSON value, valid or not. */
  doc: unknown;
}

interface DocumentFixture {
  sample_rate: number;
  render_frames: number;
  cases: DocumentCase[];
}

// JSON.parse reads 1e400 and 400-digit integers as Infinity, and "\ud800" as an unpaired
// surrogate, exactly as the engine would receive them from a patch file.
const fixture = JSON.parse(
  readFileSync(resolve(EXAMPLES, "documents.json"), "utf8"),
) as DocumentFixture;

/**
 * Cases where this engine still disagrees with the shared rule, each waiting for a fix in
 * `src/core/patch.ts`. `test.fails` passes while the case fails, so the list must shrink
 * when the fix lands (the test then reports the case as unexpectedly passing). Empty: the
 * last ones (unpaired surrogates in ids, params named like Object.prototype members) were
 * fixed on 2026-10-26.
 */
const PENDING_TS_FIX = new Set<string>([]);

function load(doc: unknown): Engine {
  const engine = new Engine({ maxFrames: fixture.render_frames });
  engine.load(doc as PatchDocument, catalog, fixture.sample_rate);
  return engine;
}

describe("shared document rules (examples/documents.json)", () => {
  test("the fixture is well formed", () => {
    const names = fixture.cases.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
    for (const name of PENDING_TS_FIX) expect(names).toContain(name);
  });

  for (const c of fixture.cases) {
    const run = PENDING_TS_FIX.has(c.name) ? test.fails : test;
    if (c.outcome === "accept") {
      run(`accepts ${c.name} (${c.rule})`, () => {
        const engine = load(c.doc);
        const n = fixture.render_frames;
        const left = new Float64Array(n);
        const right = new Float64Array(n);
        engine.process(n, left, right);
        expect(left.every(Number.isFinite) && right.every(Number.isFinite)).toBe(true);
        for (const [id, seed] of Object.entries(c.seeds ?? {})) {
          const block = engine.block(id);
          expect(block).toBeInstanceOf(Dynamical);
          expect((block as Dynamical).seed).toBe(seed);
        }
      });
    } else {
      run(`rejects ${c.name} (${c.rule})`, () => {
        expect(() => load(c.doc)).toThrow(PatchError);
      });
    }
  }
});
