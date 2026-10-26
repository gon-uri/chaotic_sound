/**
 * Safety paths of the dynamical box (spec §4.2 steps 6 and 8; TS engine review, finding
 * 28): the sub-step cap, resets when the state leaves the bounding box or stops being finite,
 * and the DC-blocker guard. None of the golden patches ever reaches them.
 */

import { describe, expect, test } from "vitest";
import {
  MAX_SUBSTEPS,
  makeRk4Scratch,
  renderTuned,
  type TunedRenderArgs,
} from "../src/core/dsp/rk4.ts";
import { getSystem, type Rhs } from "../src/core/dsp/systems.ts";
import { Engine } from "../src/core/engine.ts";
import { editedCatalog, firstDifference, render, voice } from "./rules-helpers.ts";

/** renderTuned arguments for `dtau.length` samples with a constant parameter vector `p`. */
function args(
  rhs: Rhs,
  x0: readonly number[],
  dtau: readonly number[],
  hMax: number,
  { lo = -1e300, hi = 1e300, p = [] as readonly number[], modIndex = 0 } = {},
): TunedRenderArgs {
  const dim = x0.length;
  return {
    rhs,
    x: Float64Array.from(x0),
    p: Float64Array.from(p),
    modIndex,
    pValues: new Float64Array(dtau.length).fill(p[modIndex] ?? 0),
    dtau: Float64Array.from(dtau),
    hMax,
    phaseIndices: [],
    lo: new Float64Array(dim).fill(lo),
    hi: new Float64Array(dim).fill(hi),
    xReset: Float64Array.from(x0),
    out: new Float64Array(dtau.length * dim),
    scratch: makeRk4Scratch(dim),
  };
}

/** Rows of a row-major (n × dim) trajectory. */
const rows = (out: Float64Array, dim: number): number[][] =>
  Array.from({ length: out.length / dim }, (_, i) =>
    Array.from(out.subarray(i * dim, i * dim + dim)),
  );

describe("sub-steps (spec §4.2 step 6)", () => {
  test("n_sub = clamp(⌈Δτ/h_max⌉, 1, 4096), and a huge finite Δτ really hits the cap", () => {
    expect(MAX_SUBSTEPS).toBe(4096);
    let calls = 0;
    // A harmonic oscillator that counts its evaluations (4 per RK4 step) and stops a
    // runaway loop: without the cap, Δτ = 1e9 with h_max = 1e-6 would take 1e15 steps.
    const rhs: Rhs = (x, _p, out) => {
      if (++calls > 4 * MAX_SUBSTEPS + 4) throw new Error("the sub-step cap was not applied");
      out[0] = x[1]!;
      out[1] = -x[0]!;
    };
    const steps = (dtau: number): number => {
      calls = 0;
      renderTuned(args(rhs, [1, 0], [dtau], 1e-6), 1);
      return calls / 4;
    };
    expect(steps(1e9)).toBe(MAX_SUBSTEPS);
    expect(steps(4500e-6)).toBe(MAX_SUBSTEPS);
    expect(steps(4095.5e-6)).toBe(4096);
    expect(steps(3.2e-6)).toBe(4); // ceil, not round
    expect(steps(1e-6)).toBe(1);
    expect(steps(0.4e-6)).toBe(1);
    expect(steps(0)).toBe(1); // at least one step
  });
});

describe("safety resets (spec §4.2 step 8)", () => {
  const lorenz = getSystem("lorenz");
  /**
   * Lorenz at ρ = 28 from `start`, inside the box [−5, 5]³ that the orbit soon leaves. From
   * (1, 1, 1) it leaves through the top of the box; from the mirror image (−1, −1, 1)
   * (the system is symmetric under x, y → −x, −y) through the bottom.
   */
  const lorenzInBox = (n: number, start = [1, 1, 1]) =>
    args(lorenz.rhs, start, new Array(n).fill(0.01), 0.005, {
      lo: -5,
      hi: 5,
      p: lorenz.defaultParams,
      modIndex: lorenz.paramNames.indexOf(lorenz.modulatedParam),
    });

  test.each([
    [1, 1, 1],
    [-1, -1, 1],
  ])(
    "leaving the box from (%i, %i, %i) resets to the initial condition, and each reset is counted",
    (...start) => {
      // `...start` collects the row's three numbers into an array, like Python's *args.
      // Port of the reference's test_render_tuned_resets_when_leaving_bounds.
      const a = lorenzInBox(400, start);
      const resets = renderTuned(a, 400);
      expect(resets).toBeGreaterThan(0);
      const all = rows(a.out, 3);
      const resetRows = all.filter((r) => r.every((v, j) => v === start[j]));
      expect(resetRows.length).toBe(resets); // every reset row is exactly the reset state
      expect(resetRows.length).toBeLessThan(all.length / 2); // the orbit runs between resets
      for (const r of all) for (const v of r) expect(Math.abs(v)).toBeLessThanOrEqual(5);
    },
  );

  test("the reset count does not depend on the chunking", () => {
    const run = (chunks: number[]) => {
      const n = chunks.reduce((s, c) => s + c, 0);
      const a = lorenzInBox(n);
      let resets = 0;
      let pos = 0;
      const traj: number[] = [];
      for (const c of chunks) {
        const chunk: TunedRenderArgs = {
          ...a, // the same state x, carried across chunks
          pValues: a.pValues.subarray(pos, pos + c),
          dtau: a.dtau.subarray(pos, pos + c),
          out: new Float64Array(c * 3),
        };
        resets += renderTuned(chunk, c);
        traj.push(...chunk.out);
        pos += c;
      }
      return { resets, traj };
    };
    const whole = run([400]);
    const parts = run([150, 1, 249]);
    expect(whole.resets).toBeGreaterThan(0);
    expect(parts.resets).toBe(whole.resets);
    expect(firstDifference(parts.traj, whole.traj)).toBe(-1);
  });

  test("a non-finite state resets even when the bounds are infinite", () => {
    // ẋ = x² blows up in finite time; RK4 overflows to ∞ (then NaN) within a few samples.
    const rhs: Rhs = (x, _p, out) => {
      out[0] = x[0]! * x[0]!;
    };
    const n = 40;
    const a = args(rhs, [1], new Array(n).fill(0.5), 0.5, { lo: -Infinity, hi: Infinity });
    const resets = renderTuned(a, n);
    expect(resets).toBeGreaterThan(2);
    const out = Array.from(a.out);
    expect(out.every(Number.isFinite)).toBe(true);
    expect(out.filter((v) => v === 1).length).toBe(resets);
  });

  test("a box whose state leaves the catalog's box reports safety_resets and stays finite", () => {
    // A box that holds the initial condition (−12.8, −22.3, 37.0) but not the whole
    // attractor (|x| reaches about 20): the orbit leaves it often.
    const cat = editedCatalog("lorenz", (e) => {
      e.bounds = { lo: [-15, -25, 0], hi: [15, 25, 45] };
    });
    const doc = voice({ system: "lorenz" });
    const a = render(doc, 24_000, { cat, blockSize: 128 });
    const b = render(doc, 24_000, { cat, blockSize: 1 });
    const resets = a.diagnostics.osc?.safety_resets ?? 0;
    expect(resets).toBeGreaterThan(10);
    expect(b.diagnostics).toEqual(a.diagnostics);
    expect(firstDifference(a.left, b.left)).toBe(-1);
    expect(a.left.every((v) => Number.isFinite(v) && Math.abs(v) <= 1)).toBe(true);
    // The same box with the real catalog never resets.
    expect(render(doc, 24_000).diagnostics).toEqual({ osc: { safety_resets: 0 } });
  });
});

describe("DC-blocker guard (spec §4.2 step 8, defense in depth)", () => {
  // Tiny (but positive, so the catalog is accepted) std and peak of one Rössler variable at
  // the top of the knob range: there the level scale is ∞ and that variable's audio is not
  // finite. `bad` is the variable with the bad tables; the box plays x (left, and right
  // when mono) and y (right, when stereo).
  test.each([
    ["x, in both channels (mono)", "x", {}],
    ["y, in the right channel only", "y", { observable_right: "y" }],
  ] as const)("a non-finite DC-blocker state from %s is cleared and counted", (_, bad, extra) => {
    const cat = editedCatalog("rossler", (e) => {
      const t = e.observables[bad]!;
      t.std[t.std.length - 1] = 1e-320;
      t.peak[t.peak.length - 1] = 1e-320;
    });
    const e = new Engine({ maxFrames: 256 });
    e.load(voice({ system: "rossler", observable: "x", param: 1, ...extra }), cat, 48_000);
    const [l, r] = [new Float64Array(256), new Float64Array(256)];
    e.process(256, l, r);
    // The Output block keeps NaN away from the speakers.
    expect(l.every(Number.isFinite) && r.every(Number.isFinite)).toBe(true);
    expect(e.diagnostics().osc?.safety_resets).toBe(1); // one bad chunk, one reset
    // Moving the knob down leaves the bad table entry: both DC blockers must start clean.
    e.setParam("osc", "param", 0.5);
    for (let chunk = 0; chunk < 3; chunk++) {
      e.process(256, l, r);
      expect(l.every(Number.isFinite) && r.every(Number.isFinite)).toBe(true);
      expect(Math.max(...l.map(Math.abs)), `left, chunk ${chunk}`).toBeGreaterThan(1e-3);
      expect(Math.max(...r.map(Math.abs)), `right, chunk ${chunk}`).toBeGreaterThan(1e-3);
    }
    expect(e.diagnostics().osc?.safety_resets).toBe(1);
  });
});
