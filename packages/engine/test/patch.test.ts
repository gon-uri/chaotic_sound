import { describe, expect, test } from "vitest";
import { Engine } from "../src/core/engine.ts";
import { applyEdit, normalizePatch, type PatchDocument, PatchError } from "../src/core/patch.ts";
import { catalog, single } from "./helpers.ts";

const base: PatchDocument = { format: "chaotic-sound-patch", version: 0, blocks: [], cables: [] };

function load(doc: unknown): Engine {
  const e = new Engine({ maxFrames: 256 });
  e.load(doc as PatchDocument, catalog, 48_000);
  return e;
}

describe("document rules (spec §5)", () => {
  test("unknown keys, types and params are errors; null means default", () => {
    expect(() => normalizePatch({ ...base, extra: 1 })).toThrow(/top-level/);
    expect(() => normalizePatch({ format: "other", version: 0 })).toThrow(PatchError);
    expect(() =>
      normalizePatch({ ...base, blocks: [{ id: "s", type: "sum", parms: {} }] }),
    ).toThrow(/bad block/);
    expect(() =>
      normalizePatch({
        ...base,
        blocks: [{ id: "s", type: "sum" }],
        cables: [{ from: "s.out", to: "s.in", x: 1 }],
      }),
    ).toThrow(/bad cable/);
    expect(() => normalizePatch({ ...base, blocks: [{ id: "s", type: "reverb" }] })).toThrow(
      /unknown block type/,
    );
    expect(() =>
      normalizePatch({ ...base, blocks: [{ id: "s", type: "sum", params: { volume: 1 } }] }),
    ).toThrow(/unknown parameter/);
    for (const params of [
      { pitch_lock: "false" },
      { pitch_lock: 1 },
      { seed: -1 },
      { seed: 1.5 },
      { seed: true },
      { amp: true },
      { amp: "1" },
      { amp: 1.5 },
      { cents: 150 },
      { amp_curve: "dB" },
      { note: 440 },
    ]) {
      expect(
        () => normalizePatch({ ...base, blocks: [{ id: "o", type: "dynamical", params }] }),
        JSON.stringify(params),
      ).toThrow(PatchError);
    }
    const doc = normalizePatch({
      ...base,
      blocks: [{ id: "o", type: "dynamical", params: { param: null } }],
    });
    expect(doc.blocks[0]!.params).toEqual({});
    expect(() => normalizePatch({ ...base, blocks: [{ id: "a.b", type: "sum" }] })).toThrow(
      /invalid block id/,
    );
  });

  test("semantic checks of dynamical params", () => {
    for (const params of [
      { system: "thomas" },
      { note: "C9" },
      { note: "B-1" },
      { observable: "w" },
      { system: "duffing", observable: "z" },
      { pitch_min: "A5", pitch_max: "A1" },
    ]) {
      expect(() => load(single(params)), JSON.stringify(params)).toThrow(PatchError);
    }
    expect(() => new Engine().load(single({ note: "C8" }), catalog, 8000)).toThrow(/below/);
  });
});

describe("graph rules (spec §3)", () => {
  const blocks = [
    { id: "m1", type: "modulator" as const },
    { id: "m2", type: "modulator" as const },
    { id: "osc", type: "dynamical" as const },
    { id: "mix", type: "sum" as const },
    { id: "out", type: "output" as const },
  ];
  test("control inputs take one cable, with a hint", () => {
    const doc = {
      ...base,
      blocks,
      cables: [
        { from: "m1.out", to: "osc.amp" },
        { from: "m2.out", to: "osc.amp" },
      ],
    };
    expect(() => load(doc)).toThrow(/only one cable.*control_sum/);
  });
  test.each([
    ["m1.out", "osc.out", /has no input/],
    ["osc.out", "osc.param", /cannot connect/],
    ["m1.out", "mix.in", /cannot connect/],
    ["nope.out", "mix.in", /no block/],
    ["m1", "osc.param", /block\.port/],
  ])("bad cable %s → %s", (from, to, message) => {
    expect(() => load({ ...base, blocks, cables: [{ from, to }] })).toThrow(message);
  });
  test("duplicates, cycles and output count", () => {
    expect(() =>
      load({
        ...base,
        blocks,
        cables: [
          { from: "osc.out", to: "mix.in" },
          { from: "osc.out", to: "mix.in" },
        ],
      }),
    ).toThrow(/already exists/);
    const two = [
      { id: "s1", type: "sum" },
      { id: "s2", type: "sum" },
      { id: "out", type: "output" },
    ];
    expect(() =>
      load({
        ...base,
        blocks: two,
        cables: [
          { from: "s1.out", to: "s2.in" },
          { from: "s2.out", to: "s1.in" },
        ],
      }),
    ).toThrow(/cycle/);
    expect(() => load({ ...base, blocks: [{ id: "a", type: "sum" }] })).toThrow(
      /exactly one output/,
    );
    expect(() =>
      load({
        ...base,
        blocks: [
          { id: "o1", type: "output" },
          { id: "o2", type: "output" },
        ],
      }),
    ).toThrow(/exactly one output/);
    // An unconnected output is valid and silent.
    const e = load({ ...base, blocks: [{ id: "out", type: "output" }] });
    const l = new Float64Array(64).fill(1);
    const r = new Float64Array(64).fill(1);
    e.process(64, l, r);
    expect(Math.max(...l, ...r)).toBe(0);
  });
});

describe("edits", () => {
  test("applyEdit is pure and validates", () => {
    const doc = normalizePatch(single());
    const next = applyEdit(doc, { op: "setParams", id: "osc", params: { note: "C4" } });
    expect(doc.blocks[0]!.params).toEqual({});
    expect(next.blocks[0]!.params).toEqual({ note: "C4" });
    expect(() => applyEdit(doc, { op: "removeBlock", id: "nope" })).toThrow(/no block/);
    const removed = applyEdit(doc, { op: "removeBlock", id: "osc" });
    expect(removed.cables).toEqual([]);
  });
});
