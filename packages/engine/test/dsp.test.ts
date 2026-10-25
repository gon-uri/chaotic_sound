import { describe, expect, test } from "vitest";
import { interp } from "../src/core/catalog.ts";
import {
  dcBlock,
  dcBlockCoefficient,
  onePole,
  onePoleCoefficient,
  onePoleVarying,
  softClip,
} from "../src/core/dsp/filters.ts";
import { centsBetween, midiToHz, noteToHz, noteToMidi } from "../src/core/dsp/pitch.ts";
import { makeRk4Scratch, renderTuned, rk4Step } from "../src/core/dsp/rk4.ts";
import { crc32, Mulberry32, stableSeed, utf8Bytes } from "../src/core/dsp/rng.ts";
import { getSystem } from "../src/core/dsp/systems.ts";

describe("pitch", () => {
  test.each([
    ["A4", 69],
    ["a4", 69],
    ["C4", 60],
    ["C#4", 61],
    ["Db4", 61],
    ["C♯4", 61],
    ["B♭3", 58],
    ["Bb2", 46],
    ["C-1", 0],
    ["G9", 127],
    ["E#4", 65],
  ])("%s → %i", (note, midi) => {
    expect(noteToMidi(note)).toBe(midi);
  });
  test.each(["H4", "A", "4", "A#b#4", "", "A4.5", "Cbb4", " A4", "A10", "A-2", "A 4"])(
    "rejects %j",
    (bad) => {
      expect(() => noteToMidi(bad)).toThrow(RangeError);
    },
  );
  test("frequencies", () => {
    expect(noteToHz("A4")).toBe(440);
    expect(noteToHz("A3")).toBeCloseTo(220, 12);
    expect(noteToHz("C4")).toBeCloseTo(261.6255653, 6);
    expect(noteToHz("A4", 100)).toBeCloseTo(midiToHz(70), 12);
    expect(centsBetween(880, 440)).toBeCloseTo(1200, 12);
  });
});

describe("portable randomness (bit-exact with Python)", () => {
  test("mulberry32 reference values", () => {
    const r = new Mulberry32(1);
    expect([r.uniform(), r.uniform(), r.uniform()]).toEqual([
      0.6270739405881613, 0.002735721180215478, 0.5274470399599522,
    ]);
    expect(new Mulberry32(1).nextUint32()).toBe(2693262067);
  });
  test("CRC-32 seed hash", () => {
    expect(crc32(utf8Bytes("123456789"))).toBe(0xcbf43926); // the standard check value
    expect(stableSeed("osc")).toBe(1818447832);
    expect(stableSeed("lorenz")).toBe(286405065);
    expect(utf8Bytes("Rö")).toEqual([0x52, 0xc3, 0xb6]);
  });
  test("normal deviates look normal", () => {
    const r = new Mulberry32(12345);
    const z = Array.from({ length: 20_000 }, () => r.normal());
    const mean = z.reduce((a, v) => a + v, 0) / z.length;
    const sd = Math.sqrt(z.reduce((a, v) => a + (v - mean) ** 2, 0) / z.length);
    expect(Math.abs(mean)).toBeLessThan(0.03);
    expect(Math.abs(sd - 1)).toBeLessThan(0.03);
  });
});

describe("filters", () => {
  test("one-pole time constant and flush-to-zero", () => {
    const fs = 48_000;
    const alpha = onePoleCoefficient(0.005, fs);
    const step = new Float64Array(2400).fill(1);
    const out = new Float64Array(2400);
    onePole(step, new Float64Array(1), alpha, out, 2400);
    expect(out[239]).toBeCloseTo(1 - Math.exp(-1), 3);
    const decay = new Float64Array(5000);
    onePole(new Float64Array(5000), Float64Array.of(1), 0.1, decay, 5000);
    expect(decay[4999]).toBe(0);
  });
  test("varying α equals constant α", () => {
    const x = Float64Array.from({ length: 500 }, (_, i) => Math.sin(i));
    const a = new Float64Array(500);
    const b = new Float64Array(500);
    onePole(x, Float64Array.of(0.3), 0.05, a, 500);
    onePoleVarying(x, Float64Array.of(0.3), new Float64Array(500).fill(0.05), b, 500);
    expect(Array.from(b)).toEqual(Array.from(a));
  });
  test("DC blocker removes an offset", () => {
    const fs = 48_000;
    const x = Float64Array.from(
      { length: fs },
      (_, i) => 0.5 + Math.sin((2 * Math.PI * 220 * i) / fs),
    );
    const out = new Float64Array(fs);
    dcBlock(x, new Float64Array(2), dcBlockCoefficient(5, fs), out, fs);
    const tail = out.slice(fs / 2);
    expect(Math.abs(tail.reduce((a, v) => a + v, 0) / tail.length)).toBeLessThan(1e-3);
  });
  test("soft clip", () => {
    expect(softClip(0.5)).toBe(0.5);
    expect(softClip(-0.9)).toBe(-0.9);
    expect(softClip(1.5)).toBeCloseTo(0.9 + 0.1 * Math.tanh(0.6 / 0.1), 14);
    expect(Math.abs(softClip(50))).toBeLessThanOrEqual(1);
  });
});

describe("interp mirrors numpy.interp", () => {
  const xp = Float64Array.of(0, 0.25, 0.5, 1);
  const fp = Float64Array.of(1, 2, 4, 8);
  test.each([
    [-1, 1],
    [0, 1],
    [0.25, 2],
    [0.375, 3],
    [0.75, 6],
    [1, 8],
    [2, 8],
  ])("interp(%d) = %d", (x, y) => {
    expect(interp(x, xp, fp)).toBe(y);
  });
});

describe("RK4", () => {
  const harmonic = (x: Float64Array, _p: Float64Array, out: Float64Array) => {
    out[0] = x[1]!;
    out[1] = -x[0]!;
  };
  const err = (h: number) => {
    const steps = Math.round((2 * Math.PI) / h);
    const x = Float64Array.of(1, 0);
    const s = makeRk4Scratch(2);
    for (let i = 0; i < steps; i++)
      rk4Step(harmonic, x, new Float64Array(0), (2 * Math.PI) / steps, s);
    return Math.max(Math.abs(x[0]! - 1), Math.abs(x[1]!));
  };
  test("fourth order", () => {
    const order = Math.log2(err(0.1) / err(0.05));
    expect(order).toBeGreaterThan(3.8);
    expect(order).toBeLessThan(4.2);
  });
  test("tuned render resets on bad time steps and caps sub-steps", () => {
    const sys = getSystem("rossler");
    const n = 5;
    const x = Float64Array.of(1, 1, 1);
    const out = new Float64Array(n * 3);
    const resets = renderTuned(
      {
        rhs: sys.rhs,
        x,
        p: Float64Array.from(sys.defaultParams),
        modIndex: 2,
        pValues: new Float64Array(n).fill(5.7),
        dtau: Float64Array.of(0.02, Number.NaN, Number.POSITIVE_INFINITY, -1, 0.02),
        hMax: 0.01,
        phaseIndices: [],
        lo: new Float64Array(3).fill(-1e6),
        hi: new Float64Array(3).fill(1e6),
        xReset: Float64Array.of(1, 1, 1),
        out,
        scratch: makeRk4Scratch(3),
      },
      n,
    );
    expect(resets).toBe(3);
    expect(Array.from(out.slice(3, 6))).toEqual([1, 1, 1]);
  });
});
