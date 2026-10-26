// Tests that kill mutations which survived the first rule tests (written by an independent
// mutation-testing pass, 2026-10-26). Probes that read the raw signal use tonality 0.
import { describe, expect, test } from "vitest";
import { AMP_EXPONENT } from "../src/core/blocks/dynamical.ts";
import { Catalog, CatalogError, type EntryJson } from "../src/core/catalog.ts";
import { noteToHz } from "../src/core/dsp/pitch.ts";
import { getSystem } from "../src/core/dsp/systems.ts";
import { Engine } from "../src/core/engine.ts";
import type { BlockJson, PatchDocument } from "../src/core/patch.ts";
import { catalog, single } from "./helpers.ts";
import { editedCatalog, firstDifference, patch, render, voice } from "./rules-helpers.ts";

const LEVEL = editedCatalog("rossler", (e) => {
  const x = e.observables.x!;
  x.mean = e.u_grid.map((u) => 1e6 * (1 + u));
  x.std = x.std.map(() => 2.5e5);
  x.peak = x.peak.map(() => 8e5);
});
function undoDcBlocker(out: Float64Array, fs: number): Float64Array {
  const r = Math.exp((-2 * Math.PI * 5) / fs);
  const y = new Float64Array(out.length);
  let prevOut = 0;
  let prevY = 0;
  for (let n = 0; n < out.length; n++) {
    prevY = out[n]! - r * prevOut + prevY;
    prevOut = out[n]!;
    y[n] = prevY;
  }
  return y;
}

// N01: the 5 ms floor of the knob slew (a high note, where 2 periods < 5 ms).
test("N01 knob slew at A6 is 5 ms", () => {
  const fs = 48_000;
  const probe = voice({
    system: "rossler",
    observable: "x",
    amp_curve: "linear",
    param: 0,
    note: "A6",
    tonality: 0,
  });
  const n0 = Math.round(0.1 * fs);
  const n = Math.round(0.05 * fs);
  const e = new Engine({ maxFrames: 4096 });
  e.load(probe, LEVEL, fs);
  const [l, r] = [new Float64Array(n0 + n), new Float64Array(n0 + n)];
  e.process(n0, l, r);
  e.setParam("osc", "param", 0.5);
  e.process(n, l.subarray(n0), r.subarray(n0));
  const y = undoDcBlocker(
    l.map((v) => v / 0.5 ** AMP_EXPONENT), // the Output's perceptual volume 0.5 (spec §4.4)
    fs,
  );
  const expected = Math.max(0.005, 2 / noteToHz("A6"));
  let checked = 0;
  for (let k = 0; k < n; k++) {
    const done = (-y[n0 + k]! - 1) / 0.5;
    if (done < 0.05 || done > 0.95) continue;
    const tau = (k + 1) / (-fs * Math.log(1 - done));
    expect(tau / expected, `k = ${k}`).toBeCloseTo(1, 2);
    checked++;
  }
  expect(checked).toBeGreaterThan(50);
});

// N02: with a pitch cable the slew uses f[n] (pitch cable at A1 ≡ note A1, knob moved live).
test("N02 knob slew with a pitch cable uses the cable's frequency", () => {
  const fs = 48_000;
  const run = (doc: PatchDocument) => {
    const e = new Engine({ maxFrames: 512 });
    e.load(doc, catalog, fs);
    const [l, r] = [new Float64Array(9600), new Float64Array(9600)];
    e.process(4800, l, r);
    e.setParam("osc", "param", 0.9);
    e.process(4800, l.subarray(4800), r.subarray(4800));
    return l;
  };
  const blocks: BlockJson[] = [
    { id: "cs", type: "control_sum" },
    { id: "osc", type: "dynamical", params: { param: 0.2 } },
    { id: "out", type: "output", params: { volume: 0.5 } },
  ];
  const cabled = patch(blocks, [
    ["cs.out", "osc.pitch"],
    ["osc.out", "out.in"],
  ]); // q = 0 → A1
  expect(firstDifference(run(cabled), run(voice({ note: "A1", param: 0.2 })))).toBe(-1);
});

// N06: a stereo box through a Sum keeps both channels.
test("N06 stereo through a Sum", () => {
  const osc: BlockJson = {
    id: "osc",
    type: "dynamical",
    params: { system: "rossler", observable: "x", observable_right: "y" },
  };
  const direct = render(
    patch([osc, { id: "out", type: "output", params: { volume: 0.5 } }], [["osc.out", "out.in"]]),
    4800,
  );
  const mixed = render(
    patch(
      [osc, { id: "mix", type: "sum" }, { id: "out", type: "output", params: { volume: 0.5 } }],
      [
        ["osc.out", "mix.in"],
        ["mix.out", "out.in"],
      ],
    ),
    4800,
  );
  expect(firstDifference(mixed.left, direct.left)).toBe(-1);
  expect(firstDifference(mixed.right, direct.right)).toBe(-1);
});

// N11: a failed load keeps the previous patch playing (sound, not just the document).
test("N11 a failed load keeps playing", () => {
  const bad = editedCatalog("lorenz", (e) => void (e.period[10] = 0));
  const a = new Engine({ maxFrames: 256 });
  const b = new Engine({ maxFrames: 256 });
  for (const e of [a, b]) e.load(single({ system: "rossler" }), catalog, 48_000);
  const [la, ra, lb, rb] = [0, 0, 0, 0].map(() => new Float64Array(512));
  a.process(256, la!, ra!);
  b.process(256, lb!, rb!);
  expect(() => a.load(single({ system: "lorenz" }), bad, 48_000)).toThrow();
  a.process(256, la!.subarray(256), ra!.subarray(256));
  b.process(256, lb!.subarray(256), rb!.subarray(256));
  expect(firstDifference(la!, lb!)).toBe(-1);
  expect(a.diagnostics()).toEqual(b.diagnostics());
});

// N12–N16: the other checkAgainst rules.
const MORE: [string, (e: EntryJson) => void][] = [
  [
    "u_grid not increasing",
    (e) => void ([e.u_grid[3], e.u_grid[4]] = [e.u_grid[4]!, e.u_grid[3]!]),
  ],
  ["u_grid not ending at 1", (e) => void (e.u_grid[e.u_grid.length - 1] = 0.999999)],
  ["p_min above p_max", (e) => void ([e.p_min, e.p_max] = [e.p_max, e.p_min])],
  ["p_default outside", (e) => void (e.p_default = e.p_max + 1)],
  ["bounds.lo short", (e) => void e.bounds.lo.pop()],
  ["initial_condition long", (e) => void e.initial_condition.push(0)],
  ["an extra observable", (e) => void (e.observables.w = structuredClone(e.observables.x!))],
  ["a missing observable", (e) => void delete e.observables.y],
  ["param name", (e) => void (e.param = "sigma")],
];
describe.each(MORE)("N12-16 catalog with %s", (_, edit) => {
  test("is rejected", () => {
    const entry = new Catalog(editedCatalog("lorenz", edit)).get("lorenz");
    expect(() => entry.checkAgainst(getSystem("lorenz"))).toThrow(CatalogError);
  });
});

// Fixes from the review of commits 27170ff..66446f0 (2026-10-26).
describe("review fixes", () => {
  test("a gain changed while nothing is connected has finished gliding when a cable arrives", () => {
    const doc = patch(
      [
        { id: "osc", type: "dynamical", params: { system: "rossler" } },
        { id: "mix", type: "sum", params: { gain: 1 } },
        { id: "out", type: "output", params: { volume: 1 } },
      ],
      [["mix.out", "out.in"]],
    );
    const e = new Engine({ maxFrames: 128 });
    e.load(doc, catalog, 48_000);
    const [l, r] = [new Float64Array(9600), new Float64Array(9600)];
    e.process(4800, l, r);
    e.setParam("mix", "gain", 0.25);
    e.process(9600, l, r); // 200 ms with no input: the glide must still run (and snap)
    const ref = new Engine({ maxFrames: 128 });
    ref.load(
      {
        ...doc,
        blocks: doc.blocks.map((b) => (b.id === "mix" ? { ...b, params: { gain: 0.25 } } : b)),
      },
      catalog,
      48_000,
    );
    ref.process(14_400, new Float64Array(14_400), new Float64Array(14_400));
    for (const x of [e, ref]) x.edit({ op: "connect", from: "osc.out", to: "mix.in" });
    const [a, b] = [new Float64Array(2048), new Float64Array(2048)];
    e.process(2048, a, new Float64Array(2048));
    ref.process(2048, b, new Float64Array(2048));
    expect(firstDifference(a, b)).toBe(-1); // no late 40 ms glide from the old gain
  });

  test("an added block with a non-finite param is rejected, not read as the default", () => {
    const e = new Engine();
    e.load(single({ system: "lorenz" }), catalog, 48_000);
    const before = e.patch;
    expect(() =>
      e.edit({ op: "addBlock", block: { id: "m", type: "sum", params: { gain: Number.NaN } } }),
    ).toThrow(/wrong type or value/);
    expect(e.patch).toBe(before);
  });

  test("phase wrapping gives +0, like Python's %", async () => {
    const { wrapPhases } = await import("../src/core/dsp/rk4.ts");
    const x = Float64Array.of(-0, -2 * Math.PI, 2 * Math.PI, -1);
    wrapPhases(x, [0, 1, 2, 3]);
    expect(Object.is(x[0], 0)).toBe(true);
    expect(Object.is(x[1], 0)).toBe(true);
    expect(Object.is(x[2], 0)).toBe(true);
    expect(x[3]).toBeCloseTo(2 * Math.PI - 1, 15);
  });
});
