/**
 * The modulator over many periods against the closed form of spec §4.1 (TS engine review,
 * finding 25: the golden vectors cover only the first 2048 samples, so cycle wraps and the
 * end of a `once` envelope were never checked).
 */

import { describe, expect, test } from "vitest";
import type { Shape } from "../src/core/blocks/modulator.ts";
import { firstDifference, renderModulator } from "./rules-helpers.ts";

const SHAPES: Shape[] = ["sine", "triangle", "square", "ramp_up", "ramp_down"];

/** shape(φ) of the spec §4.1 table, written from the spec. */
const SHAPE: Record<Shape, (phi: number) => number> = {
  sine: (phi) => (1 - Math.cos(2 * Math.PI * phi)) / 2,
  triangle: (phi) => 1 - Math.abs(2 * phi - 1),
  square: (phi) => (phi < 0.5 ? 1 : 0),
  ramp_up: (phi) => phi,
  ramp_down: (phi) => 1 - phi,
};
/** The table's last two columns: the value at φ = 0, and the value held after a `once`. */
const AT_ZERO: Record<Shape, number> = {
  sine: 0,
  triangle: 0,
  square: 1,
  ramp_up: 0,
  ramp_down: 1,
};
const HELD: Record<Shape, number> = { sine: 0, triangle: 0, square: 0, ramp_up: 1, ramp_down: 0 };

/** Sample i of the closed form: t = i/fs, c = t/T, φ = c − ⌊c⌋ (loop) or min(c, 1) (once). */
function closedForm(shape: Shape, mode: "loop" | "once", T: number, fs: number, i: number) {
  const t = i / fs;
  const c = t / T;
  const phi = mode === "loop" ? c - Math.floor(c) : Math.min(c, 1);
  return SHAPE[shape](phi);
}

const FS = 48_000;
// T = 0.25 s puts every cycle edge exactly on a sample (12000 samples per cycle); 0.0123 s
// does not; 0.001 s is the shortest period (48 samples, thousands of cycles).
const CASES: [number, number][] = [
  [0.25, 10.5 * 0.25 * FS],
  [0.0123, 40_000],
  [0.001, 120_000],
];

describe.each(SHAPES)("%s", (shape) => {
  describe.each(["loop", "once"] as const)("%s", (mode) => {
    test.each([1, 127, 4096])("matches the closed form in chunks of %i", (blockSize) => {
      for (const [T, frames] of CASES) {
        const got = renderModulator({ shape, period_s: T, mode }, FS, frames, blockSize);
        const want = Float64Array.from({ length: frames }, (_, i) =>
          closedForm(shape, mode, T, FS, i),
        );
        const i = firstDifference(got, want);
        expect(i, `T = ${T}: first difference at sample ${i}: ${got[i]} vs ${want[i]}`).toBe(-1);
      }
    });
  });

  test("cycle edges and the end of a once envelope", () => {
    const T = 0.25;
    const perCycle = T * FS;
    const loop = renderModulator({ shape, period_s: T, mode: "loop" }, FS, 10 * perCycle + 1, 127);
    const once = renderModulator({ shape, period_s: T, mode: "once" }, FS, 10 * perCycle + 1, 127);
    for (let k = 0; k <= 10; k++) {
      expect(loop[k * perCycle], `loop, cycle ${k}`).toBe(AT_ZERO[shape]);
    }
    expect(once[0]).toBe(AT_ZERO[shape]);
    // From t = T on, a once envelope holds shape(1).
    expect(once.subarray(perCycle).findIndex((v) => v !== HELD[shape])).toBe(-1);
    // Half a cycle in: sine and triangle peak at 1, square switches to 0.
    const half = { sine: 1, triangle: 1, square: 0, ramp_up: 0.5, ramp_down: 0.5 }[shape];
    expect(loop[perCycle / 2]).toBe(half);
    expect(loop[3 * perCycle + perCycle / 2]).toBe(half);
  });
});
