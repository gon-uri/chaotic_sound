/**
 * Graph and document rules that had no TypeScript test (TS engine review, findings 33 and
 * 39): control sanitizing (spec §3), the Output soft clip (§4.4), duplicate block ids (§3),
 * `ui` preservation and the parameter rules of the patch document (§5).
 */

import { describe, expect, test } from "vitest";
import { Output } from "../src/core/blocks/index.ts";
import { Engine } from "../src/core/engine.ts";
import {
  checkAndOrder,
  type InputWiring,
  prepareInput,
  sanitizeControl,
} from "../src/core/graph.ts";
import {
  applyEdit,
  type BlockJson,
  normalizePatch,
  type PatchDocument,
  type PatchEdit,
} from "../src/core/patch.ts";
import { catalog, single } from "./helpers.ts";
import { firstDifference, patch, render } from "./rules-helpers.ts";

const FS = 48_000;

/** Spec §4.4: softclip(x) = x for |x| ≤ 0.9, else sign(x)·(0.9 + 0.1·tanh((|x| − 0.9)/0.1)). */
function specSoftClip(x: number): number {
  const ax = Math.abs(x);
  return ax <= 0.9 ? x : Math.sign(x) * (0.9 + 0.1 * Math.tanh((ax - 0.9) / 0.1));
}

describe("control sanitizing (spec §3)", () => {
  test("NaN → 0, +∞ → 1, −∞ → 0, then clip to [0, 1]", () => {
    const input = [Number.NaN, Infinity, -Infinity, 2, -1, -1e-300, 0.3, 0, 1];
    expect(input.map(sanitizeControl)).toEqual([0, 1, 0, 1, 0, 0, 0.3, 0, 1]);
  });

  // An InputWiring is what the graph compiler builds for one input port: the source
  // signals (one Float64Array per cable for control), and a scratch buffer to write into.
  const controlInput = (cables: number[][]): InputWiring => ({
    sources: cables.map((c) => [Float64Array.from(c)]),
    control: true,
    scratch: [new Float64Array(8)],
  });

  test("a single control cable is sanitized", () => {
    const out = prepareInput(controlInput([[Number.NaN, Infinity, -Infinity, 2, -1, 0.3]]), 6);
    expect(Array.from(out![0]!.subarray(0, 6))).toEqual([0, 1, 0, 1, 0, 0.3]);
  });

  test("each control cable is sanitized before the cables are added", () => {
    const a = [Number.NaN, -1, 0.7, Infinity, 2, 0.25];
    const b = [0.5, 0.7, -Infinity, -Infinity, 0.5, 0.25];
    const c = [0.125, Number.NaN, 0.125, 0.5, -Infinity, 0.25];
    const out = prepareInput(controlInput([a, b, c]), 6);
    // sanitize(a) + sanitize(b) + sanitize(c). Sanitizing the sum instead would give
    // [0, 0, 0, 0, 0, 0.75]. The sum itself is not clipped here: Control Sum clips after
    // its gain (spec §4.5).
    expect(Array.from(out![0]!.subarray(0, 6))).toEqual([0.625, 0.7, 0.825, 1.5, 1.5, 0.75]);
  });

  test("audio cables are added without sanitizing", () => {
    const w: InputWiring = {
      sources: [
        [Float64Array.of(0.5, -2), Float64Array.of(3, 0)],
        [Float64Array.of(1, 3), Float64Array.of(-4, 0.25)],
      ],
      control: false,
      scratch: [new Float64Array(2), new Float64Array(2)],
    };
    const out = prepareInput(w, 2)!;
    expect([Array.from(out[0]!), Array.from(out[1]!)]).toEqual([
      [1.5, 1],
      [-1, 0.25],
    ]);
  });
});

describe("Output block (spec §4.4)", () => {
  function output(volume: number, left: number[], right: number[]) {
    const n = left.length;
    // The Output block needs no catalog; `undefined as never` satisfies the type checker.
    const o = new Output("out", { volume }, { catalog: undefined as never, maxFrames: n });
    o.reset(FS);
    o.process(n, [[Float64Array.from(left), Float64Array.from(right)]]);
    return { left: Array.from(o.main[0]!), right: Array.from(o.main[1]!) };
  }
  /** Each sample equals the spec's value to 1e-15 (`1 − 0.9` is not exactly 0.1). */
  function expectClose(got: number[], want: number[], label: string) {
    for (let i = 0; i < want.length; i++) expect(got[i], `${label} ${i}`).toBeCloseTo(want[i]!, 15);
  }

  test("soft clip above 0.9, identity below, NaN → 0", () => {
    const left = [0.5, 0.9, -0.9, 0.95, -1.2, 3, -50, Number.NaN, Infinity];
    const right = [Number.NaN, -0.95, 0.9, 1.2, -3, 50, 0.1, -0.5, -Infinity];
    const got = output(1, left, right);
    const want = (xs: number[]) => xs.map((x) => (Number.isNaN(x) ? 0 : specSoftClip(x)));
    expectClose(got.left, want(left), "left");
    expectClose(got.right, want(right), "right");
    expect(got.left.slice(0, 3)).toEqual([0.5, 0.9, -0.9]); // exact below the knee
    const peak = Math.max(...got.left.map(Math.abs), ...got.right.map(Math.abs));
    expect(peak).toBeLessThanOrEqual(1);
  });

  test("the volume multiplies before the clip", () => {
    const got = output(0.5, [1.9, -1.9, 1, 4], [0.5, 2.2, -4, 0]);
    // softclip(0.5·1.9) = softclip(0.95), not 0.5·softclip(1.9).
    expectClose(got.left, [0.95, -0.95, 0.5, 2].map(specSoftClip), "left");
    expectClose(got.right, [0.25, 1.1, -2, 0].map(specSoftClip), "right");
  });

  test("a loud patch is soft-clipped at the output", () => {
    // Four voices at full level, summed with gain 1: the sum exceeds 0.9 often.
    const ids = ["a", "b", "c", "d"];
    const doc = patch(
      [
        ...ids.map((id): BlockJson => ({ id, type: "dynamical", params: { system: "lorenz" } })),
        { id: "mix", type: "sum" },
        { id: "out", type: "output", params: { volume: 1 } },
      ],
      [...ids.map((id): [string, string] => [`${id}.out`, "mix.in"]), ["mix.out", "out.in"]],
    );
    const r = render(doc, FS);
    let above = 0;
    for (const v of r.left) {
      expect(Math.abs(v)).toBeLessThan(1);
      if (Math.abs(v) > 0.9) above++;
    }
    expect(above).toBeGreaterThan(100);
  });
});

describe("block ids (spec §3)", () => {
  test("duplicate block ids are rejected", () => {
    const doc = single();
    doc.blocks.push({ id: "osc", type: "dynamical", params: { system: "lorenz" } });
    expect(() => checkAndOrder(normalizePatch(doc))).toThrow(/duplicate block id "osc"/);
    expect(() => new Engine().load(doc, catalog, FS)).toThrow(/duplicate block id/);
    const e = new Engine();
    e.load(single(), catalog, FS);
    expect(() => e.edit({ op: "addBlock", block: { id: "out", type: "sum" } })).toThrow(
      /duplicate block id/,
    );
    expect(e.patch?.blocks.map((b) => b.id)).toEqual(["osc", "out"]); // unchanged
  });
});

describe("the optional ui objects (spec §5)", () => {
  const blockUi = { x: 120, y: 40, color: "teal" };
  const topUi = { zoom: 1.5, comment: "kept as is" };
  function withUi(): PatchDocument {
    const doc: PatchDocument = { ...single({ system: "lorenz" }), ui: structuredClone(topUi) };
    doc.blocks[0]!.ui = structuredClone(blockUi);
    return doc;
  }
  const uiOf = (doc: PatchDocument | null, id: string) => doc?.blocks.find((b) => b.id === id)?.ui;

  test("normalizePatch keeps block and top-level ui, and adds none", () => {
    const n = normalizePatch(withUi());
    expect(n.ui).toEqual(topUi);
    expect(uiOf(n, "osc")).toEqual(blockUi);
    expect("ui" in n.blocks[1]!).toBe(false);
    expect("ui" in normalizePatch(single())).toBe(false);
  });

  test("every applyEdit keeps them", () => {
    let doc = normalizePatch(withUi());
    const edits: PatchEdit[] = [
      { op: "setParams", id: "osc", params: { note: "C4", param: null } },
      { op: "addBlock", block: { id: "lfo", type: "modulator", ui: { x: 1 } } },
      { op: "connect", from: "lfo.out", to: "osc.param" },
      { op: "disconnect", from: "lfo.out", to: "osc.param" },
      { op: "setParams", id: "lfo", params: { shape: "square" } },
      { op: "removeBlock", id: "lfo" },
    ];
    for (const edit of edits) {
      doc = applyEdit(doc, edit);
      expect(doc.ui, edit.op).toEqual(topUi);
      expect(uiOf(doc, "osc"), edit.op).toEqual(blockUi);
      if (edit.op === "addBlock") expect(uiOf(doc, "lfo")).toEqual({ x: 1 });
    }
  });

  test("the engine keeps them through loads, live changes and structural edits", () => {
    const e = new Engine({ maxFrames: 128 });
    e.load(withUi(), catalog, FS);
    const check = (what: string) => {
      expect(e.patch?.ui, what).toEqual(topUi);
      expect(uiOf(e.patch, "osc"), what).toEqual(blockUi);
    };
    check("load");
    e.setParam("osc", "param", 0.3); // live: the block keeps running
    check("live knob");
    e.setParam("osc", "system", "chua"); // structural: the block is recreated
    check("structural setting");
    e.edit({ op: "addBlock", block: { id: "lfo", type: "modulator" } });
    check("addBlock");
  });
});

describe("parameter rules (spec §4.1, §5)", () => {
  const base: PatchDocument = { format: "chaotic-sound-patch", version: 0, blocks: [], cables: [] };
  const withParams = (type: BlockJson["type"], params: Record<string, unknown>) =>
    normalizePatch({ ...base, blocks: [{ id: "b", type, params: params as never }] });

  test("period_s must be at least 0.001 s, with no maximum", () => {
    expect(withParams("modulator", { period_s: 0.001 }).blocks[0]!.params).toEqual({
      period_s: 0.001,
    });
    expect(() => withParams("modulator", { period_s: 1e9 })).not.toThrow();
    for (const bad of [0.000999, 1e-6, 0, -1]) {
      expect(() => withParams("modulator", { period_s: bad }), String(bad)).toThrow(/period_s/);
    }
  });

  test("unknown params are errors even when null; known params set to null are dropped", () => {
    expect(() => withParams("dynamical", { foo: null })).toThrow(/unknown parameter "foo"/);
    expect(() => withParams("sum", { volume: null })).toThrow(/unknown parameter "volume"/);
    expect(
      withParams("dynamical", { note: null, amp: null, seed: null }).blocks[0]!.params,
    ).toEqual({});
    const e = new Engine({ maxFrames: 128 });
    e.load(single(), catalog, FS);
    expect(() => e.setParam("osc", "foo", null)).toThrow(/unknown parameter "foo"/);
    expect(() => e.edit({ op: "setParams", id: "out", params: { gain: null } })).toThrow(
      /unknown parameter "gain"/,
    );
    expect(e.patch?.blocks[0]?.params).toEqual({});
  });

  test("seed is an integer in [0, 2³¹) and may be written as an integral float", () => {
    const seedText = (text: string) =>
      JSON.parse(
        `{"format":"chaotic-sound-patch","version":0,"blocks":[{"id":"osc","type":"dynamical",` +
          `"params":{"seed":${text}}},{"id":"out","type":"output"}],` +
          `"cables":[{"from":"osc.out","to":"out.in"}]}`,
      ) as PatchDocument;
    // JSON has a single number type: 7.0 is the integer 7 (spec §5).
    for (const [text, value] of [
      ["7.0", 7],
      ["1e3", 1000],
      ["0.0", 0],
      ["2147483647.0", 2 ** 31 - 1],
    ] as const) {
      expect(normalizePatch(seedText(text)).blocks[0]!.params, text).toEqual({ seed: value });
    }
    for (const text of ["2147483648", "7.5", "-1.0", "1e-3", "true", '"7"']) {
      expect(() => normalizePatch(seedText(text)), text).toThrow(/seed/);
    }
    const a = render(seedText("7.0"), 2048).left;
    const b = render(single({ seed: 7 }, 0.8), 2048).left;
    expect(firstDifference(a, b)).toBe(-1);
  });
});
