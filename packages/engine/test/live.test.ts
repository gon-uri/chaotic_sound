/**
 * Live parameter changes and engine state (spec §6, ADR 0014).
 *
 * Every check compares the engine with a reference instead of a threshold: a twin engine
 * that received the same change at the same sample, a control cable that delivers the same
 * step, a fresh render of the edited patch, or the closed form of the 5 ms glide. Each test
 * was checked to fail on a matching mutation of the engine source.
 */

import { Session } from "node:inspector/promises";
import { describe, expect, test } from "vitest";
import { AMP_EXPONENT, type Dynamical } from "../src/core/blocks/dynamical.ts";
import { Catalog } from "../src/core/catalog.ts";
import { Engine } from "../src/core/engine.ts";
import type {
  BlockJson,
  BlockType,
  ParamValue,
  PatchDocument,
  PatchEdit,
} from "../src/core/patch.ts";
import { catalog, loadPatch, single } from "./helpers.ts";

const FS = 48_000;
const QUANTUM = 128; // the AudioWorklet quantum
/** Live changes happen here: 0.1 s in, between two process() calls. */
const N = 4800;
/** α of the 5 ms one-pole at FS (spec §4.2 step 2): the declick smoother and the glides. */
const ALPHA = 1 - Math.exp(-1 / (0.005 * FS));
/** Perceptual amp law g = a^(1/(2·log10 2)): halving the knob is −10 dB (spec §4.2 step 3). */
const perceptual = (a: number): number => a ** (1 / (2 * Math.log10(2)));
/** The catalog's default knob position for Lorenz (the documented default of `param`). */
const U_DEFAULT_LORENZ = new Catalog(catalog).get("lorenz").uDefault;

// ---------------------------------------------------------------------------------------
// Helpers

interface Audio {
  left: Float64Array;
  right: Float64Array;
}

function block(id: string, type: BlockType, params: Record<string, ParamValue> = {}): BlockJson {
  return { id, type, params };
}

function patch(blocks: BlockJson[], cables: [string, string][]): PatchDocument {
  return {
    format: "chaotic-sound-patch",
    version: 0,
    blocks,
    cables: cables.map(([from, to]) => ({ from, to })),
  };
}

/** A running engine with the AudioWorklet's chunk size. */
function start(doc: PatchDocument, fs = FS): Engine {
  const e = new Engine({ maxFrames: QUANTUM });
  e.load(doc, catalog, fs);
  return e;
}

/** The next `frames` samples of the engine's output. */
function play(e: Engine, frames: number): Audio {
  const out = { left: new Float64Array(frames), right: new Float64Array(frames) };
  e.process(frames, out.left, out.right);
  return out;
}

/** `x` followed by `y`. */
function concat(x: Float64Array, y: Float64Array): Float64Array {
  const z = new Float64Array(x.length + y.length);
  z.set(x);
  z.set(y, x.length);
  return z;
}

function join(a: Audio, b: Audio): Audio {
  return { left: concat(a.left, b.left), right: concat(a.right, b.right) };
}

/** Index of the first sample where `a` and `b` differ, or −1 if they are bit-identical. */
function firstDiff(a: Float64Array, b: Float64Array): number {
  if (a.length !== b.length) return Math.min(a.length, b.length);
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i] && !(Number.isNaN(a[i]) && Number.isNaN(b[i]))) return i;
  }
  return -1;
}

function expectSame(a: Audio, b: Audio): void {
  expect(firstDiff(a.left, b.left), "left channel: first differing sample").toBe(-1);
  expect(firstDiff(a.right, b.right), "right channel: first differing sample").toBe(-1);
}

function maxAbs(x: Float64Array): number {
  let m = 0;
  for (const v of x) m = Math.max(m, Math.abs(v));
  return m;
}

function maxAbsDiff(a: Float64Array, b: Float64Array): number {
  let m = 0;
  for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i]! - b[i]!));
  return m;
}

/** max |a − ratio·b| relative to max |b|. */
function scaledError(a: Float64Array, b: Float64Array, ratio: number): number {
  let m = 0;
  for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i]! - ratio * b[i]!));
  return m / maxAbs(b);
}

/** `x` times `ratio`, sample by sample (the "plain multiplication"). */
function times(x: Float64Array, ratio: number): Float64Array {
  return x.map((v) => ratio * v);
}

/**
 * Play `frames` samples one quantum at a time and record, for each id, the left channel of
 * that block's output (the Output block's `main`), so a block can be observed on its own.
 */
function record(e: Engine, frames: number, ids: readonly string[]): Record<string, Float64Array> {
  const rec: Record<string, Float64Array> = {};
  for (const id of ids) rec[id] = new Float64Array(frames);
  const l = new Float64Array(QUANTUM);
  const r = new Float64Array(QUANTUM);
  for (let pos = 0; pos < frames; pos += QUANTUM) {
    const n = Math.min(QUANTUM, frames - pos);
    e.process(n, l, r);
    for (const id of ids) {
      const b = e.block(id)!;
      const signal = b.main ?? b.outputs[0]!;
      rec[id]!.set(signal[0]!.subarray(0, n), pos);
    }
  }
  return rec;
}

function paramsOf(e: Engine, id: string): Record<string, unknown> | undefined {
  return e.patch?.blocks.find((b) => b.id === id)?.params;
}

/**
 * A box's signal before its 5 Hz DC blocker (spec §4.2 step 7), from its output since
 * t = 0. The blocker out[n] = y[n] − y[n−1] + R·out[n−1] is invertible:
 * y[n] = out[n] − R·out[n−1] + y[n−1], with R = exp(−2π·5/fs).
 */
function undoDcBlock(out: Float64Array, fs: number): Float64Array {
  const r = Math.exp((-2 * Math.PI * 5) / fs);
  const y = new Float64Array(out.length);
  let prevY = 0;
  let prevOut = 0;
  for (let n = 0; n < out.length; n++) {
    prevY = out[n]! - r * prevOut + prevY;
    prevOut = out[n]!;
    y[n] = prevY;
  }
  return y;
}

/** Number of sign changes: twice the frequency of a regular oscillation, per window. */
function crossings(x: Float64Array): number {
  let c = 0;
  for (let i = 1; i < x.length; i++) if (x[i - 1]! < 0 !== x[i]! < 0) c++;
  return c;
}

/**
 * Every live setting in one patch: `osc` (Lorenz) has only knobs; `pitched` (Rössler) takes
 * its pitch from a cable at q = 0.5 and its amp from a Control Sum; a Sum mixes them into
 * the Output. `hold` is a square in its first half period, so it outputs 1 for 500 s.
 */
function testPatch(): PatchDocument {
  return patch(
    [
      block("hold", "modulator", { shape: "square", period_s: 1000 }),
      block("cs", "control_sum"),
      block("q", "control_sum", { gain: 0.5 }),
      block("osc", "dynamical", { system: "lorenz", param: 0.9, amp: 0.5 }),
      block("pitched", "dynamical", { system: "rossler" }),
      block("mix", "sum"),
      block("out", "output"),
    ],
    [
      ["hold.out", "cs.in"],
      ["hold.out", "q.in"],
      ["cs.out", "pitched.amp"],
      ["q.out", "pitched.pitch"],
      ["osc.out", "mix.in"],
      ["pitched.out", "mix.in"],
      ["mix.out", "out.in"],
    ],
  );
}

/** One live change per setting: [block, setting, a value different from the patch's]. */
const LIVE_CHANGES: [string, string, ParamValue][] = [
  ["osc", "param", 0.1],
  ["osc", "amp", 0.3],
  ["osc", "note", "E3"],
  ["osc", "cents", 40],
  ["osc", "pitch_lock", false],
  ["osc", "amp_curve", "linear"],
  ["pitched", "pitch_min", "A2"],
  ["pitched", "pitch_max", "A4"],
  ["cs", "gain", 0.3],
  ["mix", "gain", 0.3],
  ["out", "volume", 0.3],
];

/** The documented default of each live setting (spec §4), restored by `null`. */
const DOCUMENTED_DEFAULT: Record<string, ParamValue> = {
  "osc.param": U_DEFAULT_LORENZ,
  "osc.amp": 1,
  "osc.note": "A3",
  "osc.cents": 0,
  "osc.pitch_lock": true,
  "osc.amp_curve": "perceptual",
  "pitched.pitch_min": "A1",
  "pitched.pitch_max": "A5",
  "cs.gain": 1,
  "mix.gain": 1,
  "out.volume": 0.8,
};

// ---------------------------------------------------------------------------------------
// (1) A live knob change continues the running block.

describe("a live knob change continues the running block", () => {
  /**
   * The same knob step delivered by a control cable at sample N: a Control Sum (gain 0.45)
   * of a square held at 1 and a square that drops to 0 at 0.1 s, so the cable carries
   * 0.45·2 = 0.9, then 0.45 (both exact in float64).
   */
  function cableStep(port: "param" | "amp"): PatchDocument {
    return patch(
      [
        block("hold", "modulator", { shape: "square", period_s: 1000 }),
        block("drop", "modulator", { shape: "square", period_s: 0.2 }),
        block("cs", "control_sum", { gain: 0.45 }),
        block("osc", "dynamical", { system: "lorenz" }),
        block("out", "output", { volume: 0.5 }),
      ],
      [
        ["hold.out", "cs.in"],
        ["drop.out", "cs.in"],
        ["cs.out", `osc.${port}`],
        ["osc.out", "out.in"],
      ],
    );
  }

  for (const name of ["param", "amp"] as const) {
    test(`${name}: the same block goes on exactly like a cable stepping at that sample`, () => {
      const doc = single({ system: "lorenz", [name]: 0.9 });
      const live = start(doc);
      const twin = start(doc);
      const before = play(live, N);
      play(twin, N);
      const osc = live.block("osc");
      live.setParam("osc", name, 0.45);
      twin.setParam("osc", name, 0.45);
      const after = play(live, N);
      expect(live.block("osc")).toBe(osc); // the same object: the block was not recreated
      expectSame(after, play(twin, N)); // the same change at the same sample: same output
      // Reference: the oscillator heard the same control values, from a cable.
      expectSame(join(before, after), play(start(cableStep(name)), 2 * N));
      // A restart would replay the edited patch from t = 0 (fading in from silence).
      const restart = play(start(live.patch!), N);
      expect(maxAbsDiff(after.left, restart.left)).toBeGreaterThan(0.05);
    });
  }

  test("the patch document follows the live change", () => {
    const e = start(single({ system: "lorenz", param: 0.4 }));
    play(e, N);
    e.setParam("osc", "param", 0.9);
    e.setParam("osc", "note", "E3");
    e.setParam("out", "volume", 0.2);
    expect(paramsOf(e, "osc")).toEqual({ system: "lorenz", param: 0.9, note: "E3" });
    expect(paramsOf(e, "out")).toEqual({ volume: 0.2 });
    expect(e.diagnostics()).toEqual({ osc: { safety_resets: 0 } });
  });
});

// ---------------------------------------------------------------------------------------
// (2) Each live setting takes effect.

describe("each live setting takes effect", () => {
  /** Long enough for the 5 ms smoothers and the 5 Hz DC blocker to forget (e^−18). */
  const SETTLE = 0.6 * FS;

  /**
   * Change `id.name` live at N and, once settled, compare with the unchanged patch:
   * returns max |live − ratio·unchanged| / max |unchanged| over N samples.
   */
  function errorAfterSettling(
    doc: PatchDocument,
    id: string,
    name: string,
    value: ParamValue,
    ratio: number,
  ): number {
    const live = start(doc);
    const ref = start(doc);
    expectSame(play(live, N), play(ref, N));
    live.setParam(id, name, value);
    play(live, SETTLE);
    play(ref, SETTLE);
    return scaledError(play(live, N).left, play(ref, N).left, ratio);
  }

  test("amp: the level follows the perceptual law, a^(1/(2·log10 2))", () => {
    const doc = single({ system: "rossler", amp: 1 });
    const ratio = perceptual(0.5) / perceptual(1);
    expect(errorAfterSettling(doc, "osc", "amp", 0.5, ratio)).toBeLessThan(1e-6);
    expect(errorAfterSettling(doc, "osc", "amp", 0.5, 0.5)).toBeGreaterThan(0.1); // not linear
  });

  test("amp with amp_curve linear: the level follows a", () => {
    const doc = single({ system: "rossler", amp: 1, amp_curve: "linear" });
    expect(errorAfterSettling(doc, "osc", "amp", 0.5, 0.5)).toBeLessThan(1e-6);
  });

  test("Control Sum gain: a Control Sum driving amp scales it like the knob", () => {
    const doc = patch(
      [
        block("hold", "modulator", { shape: "square", period_s: 1000 }),
        block("cs", "control_sum", { gain: 0.8 }),
        block("osc", "dynamical", { system: "rossler" }),
        block("out", "output", { volume: 0.5 }),
      ],
      [
        ["hold.out", "cs.in"],
        ["cs.out", "osc.amp"],
        ["osc.out", "out.in"],
      ],
    );
    const ratio = perceptual(0.4) / perceptual(0.8);
    expect(errorAfterSettling(doc, "cs", "gain", 0.4, ratio)).toBeLessThan(1e-6);
  });

  test("Output volume and Sum gain: exactly the new factor once the glide ends", () => {
    const viaSum = patch(
      [
        block("osc", "dynamical", { system: "rossler" }),
        block("mix", "sum"),
        block("out", "output", { volume: 0.5 }),
      ],
      [
        ["osc.out", "mix.in"],
        ["mix.out", "out.in"],
      ],
    );
    for (const [id, name] of [
      ["out", "volume"],
      ["mix", "gain"],
    ] as const) {
      const live = start(viaSum);
      const ref = start(viaSum);
      play(live, N);
      play(ref, N);
      const from = id === "out" ? 0.5 : 1;
      live.setParam(id, name, from / 2); // halving is exact in float64
      play(live, 0.2 * FS); // the glide snaps to its target within 1e-9 by then
      play(ref, 0.2 * FS);
      const a = play(live, N).left;
      const b = play(ref, N).left;
      if (id === "mix") {
        expect(firstDiff(a, times(b, 0.5)), `${id}.${name}`).toBe(-1);
      } else {
        // The Output's curve: halving the knob multiplies by 0.5^1.661 (spec §4.4), which is
        // not exact in float64 (two pow calls), so compare to the last bits.
        const f = 0.5 ** AMP_EXPONENT;
        const err = a.reduce((m, v, i) => Math.max(m, Math.abs(v - f * b[i]!)), 0);
        expect(err, `${id}.${name}`).toBeLessThan(1e-15);
      }
    }
  });

  test("amp_curve: once the glide ends, the box sounds like a linear one", () => {
    const doc = single({ system: "rossler", amp: 0.25 });
    const live = start(doc);
    const unchanged = start(doc);
    const linear = start(single({ system: "rossler", amp: 0.25, amp_curve: "linear" }));
    expectSame(play(live, N), play(unchanged, N));
    play(linear, N);
    live.setParam("osc", "amp_curve", "linear");
    play(live, SETTLE);
    play(linear, SETTLE);
    play(unchanged, SETTLE);
    const a = play(live, N).left;
    expect(scaledError(a, play(linear, N).left, 1)).toBeLessThan(1e-6);
    expect(scaledError(a, play(unchanged, N).left, 1)).toBeGreaterThan(0.1);
  });

  test("note: the pitch moves to the new note", () => {
    const W = 0.25 * FS;
    const live = start(single({ note: "A3" }));
    const unchanged = start(single({ note: "A3" }));
    const fresh = start(single({ note: "A4" }));
    play(live, N);
    play(unchanged, N);
    play(fresh, N); // past the fade-in
    live.setParam("osc", "note", "A4");
    const c = crossings(play(live, W).left);
    const cA4 = crossings(play(fresh, W).left);
    const cA3 = crossings(play(unchanged, W).left);
    expect(c / cA4).toBeGreaterThan(0.97);
    expect(c / cA4).toBeLessThan(1.03);
    expect(cA3 / cA4).toBeLessThan(0.55); // an octave apart: the estimate tells them apart
  });

  test("note and cents: A3 → A♯3 equals +100 cents, both live", () => {
    const byNote = start(single({ note: "A3" }));
    const byCents = start(single({ note: "A3" }));
    const unchanged = start(single({ note: "A3" }));
    play(byNote, N);
    play(byCents, N);
    play(unchanged, N);
    byNote.setParam("osc", "note", "A#3");
    byCents.setParam("osc", "cents", 100);
    const a = play(byNote, N);
    expectSame(a, play(byCents, N));
    expect(maxAbsDiff(a.left, play(unchanged, N).left)).toBeGreaterThan(0.01);
  });

  test("pitch_min and pitch_max: a pitch cable at q = 0 plays pitch_min, at q = 1 pitch_max", () => {
    // q = 0 comes from a Control Sum with nothing connected; q = 1 from a square.
    const cases = [
      ["pitch_min", "A1", "E2", block("src", "control_sum")],
      ["pitch_max", "A5", "E5", block("src", "modulator", { shape: "square", period_s: 1000 })],
    ] as const;
    for (const [name, from, to, src] of cases) {
      const withCable = start(
        patch(
          [src, block("osc", "dynamical"), block("out", "output", { volume: 0.5 })],
          [
            ["src.out", "osc.pitch"],
            ["osc.out", "out.in"],
          ],
        ),
      );
      const withNote = start(single({ note: from }));
      const unchanged = start(single({ note: from }));
      expectSame(play(withCable, N), play(withNote, N)); // the same formula as a note
      play(unchanged, N);
      withCable.setParam("osc", name, to);
      withNote.setParam("osc", "note", to);
      const a = play(withCable, N);
      expectSame(a, play(withNote, N));
      expect(maxAbsDiff(a.left, play(unchanged, N).left), name).toBeGreaterThan(0.01);
    }
  });

  test("pitch_lock: switching it off changes only the lock of the running block", () => {
    const doc = single({ system: "lorenz", param: 0.9 }); // P(0.9) ≠ P(u_default)
    const live = start(doc);
    const ref = start(doc);
    const unchanged = start(doc);
    play(live, N);
    play(ref, N);
    play(unchanged, N);
    live.setParam("osc", "pitch_lock", false);
    (ref.block("osc") as Dynamical).pitchLock = false; // reference: flip only the flag
    const a = play(live, N);
    expectSame(a, play(ref, N));
    expect(maxAbsDiff(a.left, play(unchanged, N).left)).toBeGreaterThan(0.01);
    // At the default knob position, P(u) = P(u_default): the lock makes no difference.
    const atDefault = start(single({ system: "lorenz" }));
    const lockedRef = start(single({ system: "lorenz" }));
    play(atDefault, N);
    play(lockedRef, N);
    atDefault.setParam("osc", "pitch_lock", false);
    expectSame(play(atDefault, N), play(lockedRef, N));
  });

  for (const [id, name, other] of LIVE_CHANGES) {
    const documented = DOCUMENTED_DEFAULT[`${id}.${name}`]!;
    test(`${id}.${name} = null restores the documented default (${documented})`, () => {
      const byNull = start(testPatch());
      const byValue = start(testPatch());
      for (const e of [byNull, byValue]) {
        play(e, N);
        e.setParam(id, name, other);
        play(e, N);
      }
      const b = byNull.block(id);
      byNull.setParam(id, name, null);
      byValue.setParam(id, name, documented);
      expect(byNull.block(id)).toBe(b);
      expectSame(play(byNull, N), play(byValue, N));
      expect(paramsOf(byNull, id)).not.toHaveProperty(name);
      expect(paramsOf(byValue, id)).toHaveProperty(name, documented);
    });
  }
});

// ---------------------------------------------------------------------------------------
// (3) edit({op: "setParams"}) and setParam are one path.

describe("setParams edits", () => {
  for (const [id, name, value] of LIVE_CHANGES) {
    test(`setParams of a live setting (${id}.${name}) is exactly setParam`, () => {
      const bySet = start(testPatch());
      const byEdit = start(testPatch());
      expectSame(play(bySet, N), play(byEdit, N));
      const b = byEdit.block(id);
      bySet.setParam(id, name, value);
      byEdit.edit({ op: "setParams", id, params: { [name]: value } });
      expect(byEdit.block(id)).toBe(b); // live: the same block keeps running
      expectSame(play(bySet, N), play(byEdit, N));
      expect(byEdit.patch).toEqual(bySet.patch);
    });
  }

  test("a setParams of several live settings equals one setParam per setting", () => {
    const bySet = start(testPatch());
    const byEdit = start(testPatch());
    play(bySet, N);
    play(byEdit, N);
    const params = { param: 0.1, amp: 0.3, note: "E3", amp_curve: "linear" };
    const b = byEdit.block("osc");
    for (const [name, value] of Object.entries(params)) bySet.setParam("osc", name, value);
    byEdit.edit({ op: "setParams", id: "osc", params });
    expect(byEdit.block("osc")).toBe(b);
    expectSame(play(bySet, N), play(byEdit, N));
  });

  const RECREATE: [string, Record<string, ParamValue>][] = [
    ["osc", { system: "chua" }],
    ["osc", { seed: 7 }],
    ["osc", { observable: "x" }],
    ["osc", { observable_right: "y" }],
    ["osc", { amp: 0.3, seed: 7 }], // live and non-live together: recreated
    ["hold", { shape: "triangle" }],
    ["hold", { period_s: 3 }],
    ["hold", { mode: "once" }],
  ];
  for (const [id, params] of RECREATE) {
    test(`a non-live setting (${id} ${JSON.stringify(params)}) restarts the block from t = 0`, () => {
      const e = start(testPatch());
      play(e, N);
      const b = e.block(id);
      const others = ["pitched", "mix", "out"].map((x) => e.block(x));
      e.edit({ op: "setParams", id, params });
      expect(e.block(id)).not.toBe(b);
      expect(["pitched", "mix", "out"].map((x) => e.block(x))).toEqual(others);
      // The new block sounds exactly like the same block in a fresh render of the patch.
      const fresh = start(e.patch!);
      expect(firstDiff(record(e, N, [id])[id]!, record(fresh, N, [id])[id]!)).toBe(-1);
    });
  }

  test("an invalid value throws and changes nothing, even after other params applied", () => {
    // Each edit's first params are valid and live, so they are applied before the bad one
    // is found; they must be rolled back.
    const LOW_FS = 8000; // C8 (4186 Hz) is above this Nyquist frequency
    const bad: [string, Record<string, ParamValue>, RegExp][] = [
      ["osc", { param: 0.1, amp: 2 }, /wrong type or value/],
      ["osc", { param: 0.1, nope: 1 }, /unknown parameter/],
      ["osc", { param: 0.1, amp: 0.2, note: "C8" }, /Nyquist/],
      ["osc", { cents: 50, note: "C9" }, /C0 and C8/],
      ["pitched", { pitch_min: "C5", pitch_max: "C4" }, /lower than pitch_max/],
      ["mix", { gain: 0.2, volume: 1 }, /unknown parameter/],
      ["osc", { seed: 3, note: "C8" }, /not below/], // non-live: the new block fails reset
      ["nope", { amp: 1 }, /no block/],
    ];
    const e = start(testPatch(), LOW_FS);
    const twin = start(testPatch(), LOW_FS);
    play(e, N);
    play(twin, N);
    const before = e.patch;
    const blocks = e.patch!.blocks.map((b) => e.block(b.id));
    for (const [id, params, message] of bad) {
      expect(() => e.edit({ op: "setParams", id, params }), JSON.stringify(params)).toThrow(
        message,
      );
    }
    // setParam goes through the same checks.
    expect(() => e.setParam("osc", "param", 2)).toThrow(/wrong type or value/);
    expect(() => e.setParam("osc", "note", "C8")).toThrow(/Nyquist/);
    expect(e.patch).toBe(before);
    expect(e.patch!.blocks.map((b) => e.block(b.id))).toEqual(blocks);
    expectSame(play(e, N), play(twin, N));
  });

  // BUG (engine): rollback() in engine.ts undoes the applied settings in the order they were
  // applied, so it can pass through an invalid pair and throw. Here pitch_max goes back to
  // A5 while pitch_min is still B5: the rollback throws "pitch_min must be lower than
  // pitch_max", the block keeps the new range B5–A6 and the caller gets the wrong error.
  // Undoing in reverse order passes only through states that were valid.
  test.fails("a rejected setParams rolls back settings that depend on each other", () => {
    const e = start(testPatch());
    const twin = start(testPatch());
    play(e, N);
    play(twin, N);
    const params = { pitch_max: "A6", pitch_min: "B5", note: "C9" };
    expect(() => e.edit({ op: "setParams", id: "pitched", params })).toThrow(/C0 and C8/);
    expectSame(play(e, N), play(twin, N));
  });
});

// ---------------------------------------------------------------------------------------
// (4) Editing one block never resets another (spec §6).

test("edits of other blocks never reset a block changed live", () => {
  const e = start(testPatch());
  const twin = start(testPatch()); // gets the live change only, none of the other edits
  play(e, N);
  play(twin, N);
  // A live change: the engine must remember the block's new settings…
  e.setParam("osc", "param", 0.1);
  twin.setParam("osc", "param", 0.1);
  const osc = e.block("osc");
  const hold = e.block("hold");
  // …so that rebuilding the graph for edits elsewhere keeps it running.
  const edits: PatchEdit[] = [
    { op: "setParams", id: "pitched", params: { seed: 5 } }, // recreates `pitched`
    { op: "addBlock", block: block("lfo", "modulator", { period_s: 0.5 }) },
    { op: "connect", from: "lfo.out", to: "pitched.param" },
    { op: "setParams", id: "mix", params: { gain: 0.7 } },
    { op: "disconnect", from: "lfo.out", to: "pitched.param" },
    { op: "removeBlock", id: "lfo" },
    { op: "setParams", id: "pitched", params: { system: "chua" } },
  ];
  for (const edit of edits) {
    e.edit(edit);
    expect(e.block("osc"), `osc after ${edit.op}`).toBe(osc);
    expect(e.block("hold"), `hold after ${edit.op}`).toBe(hold);
    const a = record(e, QUANTUM, ["osc", "hold"]);
    const b = record(twin, QUANTUM, ["osc", "hold"]);
    expect(firstDiff(a.osc!, b.osc!), `osc after ${edit.op}`).toBe(-1);
    expect(firstDiff(a.hold!, b.hold!), `hold after ${edit.op}`).toBe(-1);
  }
});

// ---------------------------------------------------------------------------------------
// (5) load() and edit() are atomic.

test("a rejected load or edit leaves the running patch exactly as it was", () => {
  const LOW_FS = 8000; // C8 (4186 Hz) is above this Nyquist frequency
  const good = testPatch();
  const e = start(good, LOW_FS);
  const twin = start(good, LOW_FS);
  play(e, N);
  play(twin, N);
  e.setParam("out", "volume", 0.4); // a glide in progress must survive too
  twin.setParam("out", "volume", 0.4);
  play(e, 64);
  play(twin, 64);
  const before = e.patch;
  const blocks = e.patch!.blocks.map((b) => e.block(b.id));
  const withOsc = (params: Record<string, ParamValue>): PatchDocument => ({
    ...good,
    blocks: good.blocks.map((b) => (b.id === "osc" ? { ...b, params } : b)),
  });
  const badLoads: [string, () => void][] = [
    ["unknown param", () => e.load(withOsc({ nope: 1 }), catalog, LOW_FS)],
    [
      "cable error",
      () =>
        e.load(
          { ...good, cables: [...good.cables, { from: "osc.out", to: "out.in" }] },
          catalog,
          LOW_FS,
        ),
    ],
    [
      "unknown port",
      () => e.load({ ...good, cables: [{ from: "osc.out", to: "out.nope" }] }, catalog, LOW_FS),
    ],
    ["note above Nyquist", () => e.load(withOsc({ note: "C8" }), catalog, LOW_FS)],
    ["pitch_max above Nyquist at a new rate", () => e.load(good, catalog, 1000)],
    ["bad sample rate", () => e.load(good, catalog, Number.NaN)],
    ["unknown system", () => e.load(withOsc({ system: "nope" }), catalog, LOW_FS)],
  ];
  const badEdits: PatchEdit[] = [
    { op: "setParams", id: "osc", params: { nope: 1 } },
    { op: "setParams", id: "osc", params: { amp: 0.2, note: "C8" } },
    { op: "setParams", id: "osc", params: { system: "chua", note: "C8" } },
    { op: "addBlock", block: block("x", "dynamical", { note: "C8" }) },
    { op: "addBlock", block: block("x", "dynamical", { nope: 1 }) },
    { op: "addBlock", block: block("osc", "dynamical") },
    { op: "addBlock", block: block("out2", "output") },
    { op: "connect", from: "osc.out", to: "out.nope" },
    { op: "connect", from: "osc.out", to: "out.in" },
    { op: "connect", from: "mix.out", to: "mix.in" },
    { op: "disconnect", from: "osc.out", to: "out.in" },
    { op: "removeBlock", id: "nope" },
  ];
  /** Same document, same blocks, same sound as the twin; reset() too (at the old rate). */
  const expectUnchanged = (what: string) => {
    expect(e.patch, what).toBe(before);
    expect(
      e.patch!.blocks.map((b) => e.block(b.id)),
      what,
    ).toEqual(blocks);
    expect(e.diagnostics(), what).toEqual(twin.diagnostics());
    expectSame(play(e, QUANTUM), play(twin, QUANTUM));
    e.reset();
    twin.reset();
    expectSame(play(e, QUANTUM), play(twin, QUANTUM));
  };
  for (const [what, load] of badLoads) {
    expect(load, what).toThrow();
    expectUnchanged(what);
  }
  for (const edit of badEdits) {
    const what = JSON.stringify(edit);
    expect(() => e.edit(edit), what).toThrow();
    expectUnchanged(what);
  }
  expectSame(play(e, N), play(twin, N));
  // Live changes and reset still work, at the old sample rate.
  e.setParam("osc", "note", "E3");
  twin.setParam("osc", "note", "E3");
  expectSame(play(e, N), play(twin, N));
  e.reset();
  twin.reset();
  const fresh = start(e.patch!, LOW_FS);
  const a = play(e, N);
  expectSame(a, play(twin, N));
  expectSame(a, play(fresh, N));
  expect(e.diagnostics()).toEqual(fresh.diagnostics());
});

// ---------------------------------------------------------------------------------------
// (6) Glides: a 5 ms one-pole after a live change, the exact value while steady.

describe("gliding settings", () => {
  /**
   * The glide from `v0` to `v1` started at sample 0 (output after the update, then the snap
   * within 1e-9), with the one-pole coefficient `alpha`.
   */
  function glide(v0: number, v1: number, k: number, alpha = ALPHA): number {
    const v = v1 + (v0 - v1) * (1 - alpha) ** (k + 1);
    return Math.abs(v - v1) < 1e-9 ? v1 : v;
  }

  /**
   * The setting implied by a block's output: v[n] = out[n] / in[n] (samples with a tiny
   * input are skipped). Before the change at `n0` it is exactly `v0`; after it, it follows
   * the closed-form glide, never moves by more than the one-pole's first step α·|v1 − v0|
   * per sample, and is exactly `v1` once the glide has snapped (0.2 s later).
   */
  /** `curve` maps the knob to the block's gain (the Output's volume is perceptual). */
  function checkGlide(
    out: Float64Array,
    inp: Float64Array,
    v0: number,
    v1: number,
    n0: number,
    fs = FS,
    curve: "linear" | "perceptual" = "linear",
  ) {
    const alpha = 1 - Math.exp(-1 / (0.005 * fs));
    let shape = 0;
    let step = 0;
    let prev = Number.NaN;
    const gain = (v: number): number => (curve === "perceptual" ? v ** AMP_EXPONENT : v);
    const [g0, g1] = [gain(v0), gain(v1)];
    for (let n = 0; n < out.length; n++) {
      if (n < n0) {
        expect(out[n], `sample ${n} before the change`).toBe(g0 * inp[n]!);
        continue;
      }
      if (n >= n0 + 0.2 * fs) {
        expect(out[n], `sample ${n} after the glide`).toBe(g1 * inp[n]!);
        continue;
      }
      if (Math.abs(inp[n]!) < 1e-2) {
        prev = Number.NaN;
        continue;
      }
      const g = out[n]! / inp[n]!;
      const v = curve === "perceptual" ? g ** (1 / AMP_EXPONENT) : g; // back to the knob
      shape = Math.max(shape, Math.abs(v - glide(v0, v1, n - n0, alpha)));
      const last = n === n0 ? v0 : prev;
      if (!Number.isNaN(last)) step = Math.max(step, Math.abs(v - last));
      prev = v;
    }
    expect(shape, "distance from the closed-form glide").toBeLessThan(1e-9);
    expect(step, "largest per-sample move").toBeLessThanOrEqual(alpha * Math.abs(v1 - v0) + 1e-9);
  }

  const chain = patch(
    [
      block("hold", "modulator", { shape: "square", period_s: 1000 }),
      block("cs", "control_sum", { gain: 0.9 }),
      block("osc", "dynamical", { system: "rossler" }),
      block("mix", "sum", { gain: 0.8 }),
      block("out", "output", { volume: 0.5 }),
    ],
    [
      ["hold.out", "cs.in"],
      ["cs.out", "osc.amp"],
      ["osc.out", "mix.in"],
      ["mix.out", "out.in"],
    ],
  );

  /** Record every block of the chain, with a live change of `id.name` to v1 at sample N. */
  function chainWithChange(id: string, name: string, v1: number, fs = FS) {
    const e = start(chain, fs);
    const ids = ["hold", "cs", "osc", "mix", "out"];
    const a = record(e, N, ids);
    e.setParam(id, name, v1);
    const b = record(e, 0.3 * fs, ids);
    const rec: Record<string, Float64Array> = {};
    for (const x of ids) rec[x] = concat(a[x]!, b[x]!);
    return rec;
  }

  test("Output volume glides from 0.5 to 0.1", () => {
    const r = chainWithChange("out", "volume", 0.1);
    checkGlide(r.out!, r.mix!, 0.5, 0.1, N, FS, "perceptual");
  });

  test("the glide lasts 5 ms at any sample rate (44.1 kHz)", () => {
    const r = chainWithChange("out", "volume", 0.1, 44_100);
    checkGlide(r.out!, r.mix!, 0.5, 0.1, N, 44_100, "perceptual");
  });

  test("Sum gain glides from 0.8 to 0.2", () => {
    const r = chainWithChange("mix", "gain", 0.2);
    checkGlide(r.mix!, r.osc!, 0.8, 0.2, N);
  });

  test("Control Sum gain glides from 0.9 to 0.3", () => {
    const r = chainWithChange("cs", "gain", 0.3);
    checkGlide(r.cs!, r.hold!, 0.9, 0.3, N);
  });

  test("amp moves through the 5 ms amp smoother (at 44.1 kHz)", () => {
    // With the linear curve, the box's signal before the DC blocker is a_s·s·(x − μ), so
    // the ratio of two boxes on the same trajectory is the ratio of their smoothed amps.
    const fs = 44_100;
    const alpha = 1 - Math.exp(-1 / (0.005 * fs));
    const doc = single({ system: "rossler", amp_curve: "linear" }); // amp 1
    const raw = (e: Engine, change: boolean) => {
      const a = record(e, N, ["osc"]).osc!;
      if (change) e.setParam("osc", "amp", 0.25);
      return undoDcBlock(concat(a, record(e, 0.1 * fs, ["osc"]).osc!), fs);
    };
    const live = raw(start(doc, fs), true);
    const ref = raw(start(doc, fs), false);
    // Both fade in from 0: a_s[n] = 1 − (1 − α)^(n+1); after N the live one heads to 0.25.
    const fadeIn = (n: number) => 1 - (1 - alpha) ** (n + 1);
    const atChange = fadeIn(N - 1);
    const big = 1e-2 * maxAbs(ref);
    let worst = 0;
    for (let n = 0; n < live.length; n++) {
      if (n < N) {
        expect(live[n], `sample ${n} before the change`).toBe(ref[n]);
        continue;
      }
      if (Math.abs(ref[n]!) < big) continue;
      const expected = (0.25 + (atChange - 0.25) * (1 - alpha) ** (n - N + 1)) / fadeIn(n);
      worst = Math.max(worst, Math.abs(live[n]! / ref[n]! - expected));
    }
    expect(worst, "distance from the closed-form smoother").toBeLessThan(1e-8);
  });

  test("amp_curve blends the two laws while m glides from 1 to 0", () => {
    // The amp curve acts before the DC blocker: undo the blocker and compare raw signals.
    const doc = single({ system: "rossler", amp: 0.25 });
    const raw = (e: Engine, change: boolean) => {
      const a = record(e, N, ["osc"]).osc!;
      if (change) e.setParam("osc", "amp_curve", "linear");
      const b = record(e, 0.3 * FS, ["osc"]).osc!;
      return undoDcBlock(concat(a, b), FS);
    };
    const live = raw(start(doc), true);
    const yP = raw(start(doc), false); // perceptual throughout
    const yL = raw(start(single({ system: "rossler", amp: 0.25, amp_curve: "linear" })), false);
    // The same trajectory in all three: y = g(a)·s·(x − μ), so live = m·yP + (1 − m)·yL.
    const big = 1e-2 * maxAbsDiff(yP, yL);
    let shape = 0;
    let step = 0;
    let prev = Number.NaN;
    for (let n = 0; n < live.length; n++) {
      if (n < N) {
        expect(live[n], `sample ${n} before the change`).toBe(yP[n]);
        continue;
      }
      if (Math.abs(yP[n]! - yL[n]!) < big) {
        prev = Number.NaN;
        continue;
      }
      const m = (live[n]! - yL[n]!) / (yP[n]! - yL[n]!);
      shape = Math.max(shape, Math.abs(m - glide(1, 0, n - N)));
      const last = n === N ? 1 : prev;
      if (!Number.isNaN(last)) step = Math.max(step, Math.abs(m - last));
      prev = m;
    }
    expect(shape, "distance from the closed-form glide of m").toBeLessThan(1e-6);
    expect(step, "largest per-sample move of m").toBeLessThanOrEqual(ALPHA + 1e-6);
  });

  test("without live changes, every gain is the plain multiplication", () => {
    const e = start(chain);
    const r = record(e, 0.5 * FS, ["hold", "cs", "osc", "mix", "out"]);
    expect(firstDiff(r.cs!, times(r.hold!, 0.9))).toBe(-1);
    expect(firstDiff(r.mix!, times(r.osc!, 0.8))).toBe(-1);
    expect(firstDiff(r.out!, times(r.mix!, 0.5 ** AMP_EXPONENT))).toBe(-1); // perceptual volume
  });
});

// ---------------------------------------------------------------------------------------
// (7) The pitch smoother restarts from a new cable's first value.

describe("pitch cable reconnected live", () => {
  /** `pitched` plays A5 (q = 1 from `hi`); `zero` is a Control Sum with no input (q = 0). */
  const doc = patch(
    [
      block("hi", "modulator", { shape: "square", period_s: 1000 }),
      block("zero", "control_sum"),
      block("osc", "dynamical"),
      block("out", "output", { volume: 0.5 }),
    ],
    [
      ["hi.out", "osc.pitch"],
      ["osc.out", "out.in"],
    ],
  );

  /**
   * After moving the pitch cable from q = 1 to q = 0, the box must play pitch_min (A1) from
   * the first sample, with no glide down from A5: exactly like a box whose cable was removed
   * and whose note was set to A1 at that sample.
   */
  function reconnect(gap: number) {
    const e = start(doc);
    const ref = start(doc);
    for (const x of [e, ref]) {
      play(x, N);
      x.edit({ op: "disconnect", from: "hi.out", to: "osc.pitch" });
      play(x, gap);
    }
    e.edit({ op: "connect", from: "zero.out", to: "osc.pitch" });
    ref.setParam("osc", "note", "A1");
    expectSame(play(e, N), play(ref, N));
  }

  test("after a gap without a cable", () => reconnect(QUANTUM));

  // BUG (engine): Dynamical clears its "first value" flag only in a process() call without a
  // pitch cable, so a disconnect and a connect between the same two process() calls (what
  // diffPatch sends for an undo that moves a cable) glide from the old q value.
  test.fails("right after the disconnect (no process() in between)", () => reconnect(0));
});

// ---------------------------------------------------------------------------------------
// (8) Engine.reset() restarts every block from t = 0.

test("reset() restarts every block from t = 0, like a fresh load", () => {
  const e = start(testPatch());
  play(e, N);
  // Live changes with their glides and smoothers in progress at the reset.
  e.setParam("osc", "param", 0.1);
  e.setParam("osc", "amp_curve", "linear");
  e.setParam("pitched", "pitch_max", "A4");
  e.setParam("cs", "gain", 0.3);
  e.setParam("mix", "gain", 0.5);
  e.setParam("out", "volume", 0.3);
  // `hold` restarts with a 4 ms period: it drops to 0 just before the reset and is back at
  // 1 right after it, so the pitch smoother must take the cable's new first value.
  e.setParam("hold", "period_s", 0.004);
  e.edit({ op: "disconnect", from: "q.out", to: "pitched.pitch" });
  play(e, 64);
  e.edit({ op: "connect", from: "q.out", to: "pitched.pitch" });
  play(e, 64);
  const blocks = e.patch!.blocks.map((b) => e.block(b.id));
  e.reset();
  expect(e.patch!.blocks.map((b) => e.block(b.id))).toEqual(blocks); // reset, not rebuilt
  const fresh = start(e.patch!);
  const ids = e.patch!.blocks.map((b) => b.id);
  const a = record(e, 2 * N, ids);
  const b = record(fresh, 2 * N, ids);
  for (const id of ids) expect(firstDiff(a[id]!, b[id]!), id).toBe(-1);
  expect(e.diagnostics()).toEqual(fresh.diagnostics());
});

// ---------------------------------------------------------------------------------------
// (9) process() allocates nothing in steady state.

/**
 * Bytes allocated per quantum inside Engine.process, by the source file of the allocating
 * function, measured with V8's sampling heap profiler (it counts objects a minor GC has
 * already freed, and needs no --expose-gc). Each patch is warmed up first so the JIT has
 * settled; `knobs` (if given) moves knobs between quanta so glides are in progress
 * (setParam's own allocations happen outside process() and are not counted).
 */
async function allocationsPerQuantum(
  docs: PatchDocument[],
  knobs?: (e: Engine, i: number) => void,
): Promise<Map<string, number>> {
  const engines = docs.map((d) => start(d));
  const l = new Float32Array(QUANTUM);
  const r = new Float32Array(QUANTUM);
  const run = (quanta: number) => {
    for (const e of engines) {
      for (let i = 0; i < quanta; i++) {
        knobs?.(e, i); // `f?.(x)` calls f only when it is defined
        e.process(QUANTUM, l, r);
      }
    }
  };
  run(4000); // warm-up
  const QUANTA = 1000;
  // The inspector protocol is asynchronous: `await` waits for each reply (like asyncio).
  const session = new Session();
  session.connect();
  try {
    await session.post("HeapProfiler.enable");
    await session.post("HeapProfiler.startSampling", {
      samplingInterval: 64,
      includeObjectsCollectedByMinorGC: true,
      includeObjectsCollectedByMajorGC: true,
    });
    run(QUANTA);
    const { profile } = await session.post("HeapProfiler.stopSampling");
    const bytes = new Map<string, number>();
    type ProfileNode = typeof profile.head; // the type of that value (a call-tree node)
    // Sum each node's own bytes, counting only nodes called (directly or not) by process().
    const walk = (node: ProfileNode, inProcess: boolean): void => {
      const { functionName, url } = node.callFrame;
      const here = inProcess || (functionName === "process" && url.endsWith("core/engine.ts"));
      if (here && node.selfSize > 0) {
        const where = `${url.split("/src/")[1] ?? url} (${functionName || "anonymous"})`;
        bytes.set(where, (bytes.get(where) ?? 0) + node.selfSize / (QUANTA * engines.length));
      }
      for (const child of node.children) walk(child, here);
    };
    walk(profile.head, false);
    return bytes;
  } finally {
    session.disconnect();
  }
}

const ALLOCATION_PATCHES = (): PatchDocument[] => [
  testPatch(),
  loadPatch("06_chaotic_chord.json"),
  loadPatch("09_pitch_glide.json"),
  loadPatch("10_control_sum.json"),
];

/** Sites (file (function): bytes per quantum) whose file matches `files`. */
function sites(bytes: Map<string, number>, files: RegExp): Record<string, number> {
  return Object.fromEntries([...bytes].filter(([where]) => files.test(where)));
}

describe("real-time safety: no allocation in process()", () => {
  test("the probe sees an allocation made inside process()", async () => {
    // Positive control: wrap one block's process() so it allocates a small array per quantum.
    const kept: number[][] = [];
    const bytes = await allocationsPerQuantum([testPatch()], (e, i) => {
      if (i > 0) return;
      const b = e.block("mix")!;
      const inner = b.process.bind(b);
      Object.assign(b, {
        process(n: number, inputs: Parameters<typeof inner>[1]) {
          kept.length = 0;
          kept.push([n, n, n, n, n, n, n, n]);
          inner(n, inputs);
        },
      });
    });
    const probe = sites(bytes, /test\/live\.test\.ts/);
    expect(Object.keys(probe)).toHaveLength(1);
    expect(Object.values(probe)[0]).toBeGreaterThan(16);
  });

  test("steady state: the engine loop, the graph and the mixers allocate nothing", async () => {
    const bytes = await allocationsPerQuantum(ALLOCATION_PATCHES());
    expect(sites(bytes, /core\/(engine|graph|blocks\/mixers|dsp\/filters)\.ts/)).toEqual({});
  });

  // BUG (engine): in steady state the boxes still allocate per quantum, depending on what the
  // JIT inlines: the Modulator's shapeValue() result (≈2 KB per modulator), the step h passed
  // to rk4Step() and CatalogEntry.at()/interp() results (≈2–6 KB per box), and the doubles
  // given to Float64Array.fill() in Dynamical.process (≈16 B per box).
  test.fails("steady state: the oscillators and modulators allocate nothing", async () => {
    const bytes = await allocationsPerQuantum(ALLOCATION_PATCHES());
    expect(Object.fromEntries(bytes)).toEqual({});
  });

  // BUG (engine): while a gain, volume or amp_curve glides, Glide.current is boxed on every
  // sample (≈1.5 KB per gliding knob per quantum): a slider drag allocates continuously.
  test.fails("while knobs glide, the mixers allocate nothing", async () => {
    const bytes = await allocationsPerQuantum([testPatch()], (e, i) => {
      if (i % 20 !== 0) return;
      const up = i % 40 === 0;
      e.setParam("out", "volume", up ? 0.7 : 0.3);
      e.setParam("mix", "gain", up ? 0.9 : 0.4);
      e.setParam("cs", "gain", up ? 0.9 : 0.4);
      e.setParam("osc", "amp_curve", up ? "linear" : "perceptual");
    });
    expect(sites(bytes, /core\/(engine|graph|blocks\/mixers|dsp\/filters)\.ts|gains/)).toEqual({});
  });
});
