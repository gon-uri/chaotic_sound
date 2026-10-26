/**
 * Sample-rate scaling (TS engine review, finding 27: every other test runs at 48 kHz). The
 * browser runs at the device rate, so times and frequencies must scale with fs: modulator
 * periods, the 5 ms declick, the 5 Hz DC blocker and the tuning.
 */

import { describe, expect, test } from "vitest";
import type { Shape } from "../src/core/blocks/modulator.ts";
import { centsBetween, noteToHz } from "../src/core/dsp/pitch.ts";
import { Engine } from "../src/core/engine.ts";
import type { PatchDocument } from "../src/core/patch.ts";
import { loadPatch } from "./helpers.ts";
import {
  editedCatalog,
  firstDifference,
  measurePitch,
  render,
  renderModulator,
  voice,
} from "./rules-helpers.ts";

const RATES = [22_050, 44_100, 96_000];
const DECLICK_S = 0.005; // spec §4.2 step 2 and §6
const DC_HZ = 5; // spec §4.2 step 7

/**
 * A catalog in which Rössler's x is heard as an almost constant level that shows the box's
 * smoothers directly: μ(u) = 10⁶·(1 + u), and σ, π chosen so that
 * s = min(0.25/σ, 0.8/π) = 10⁻⁶, hence y = g·(x − μ(u_s))·10⁻⁶ ≈ −g·(1 + u_s), with a
 * ripple of about 10⁻⁵ (|x| ≲ 12).
 */
const LEVEL = editedCatalog("rossler", (e) => {
  const x = e.observables.x!;
  x.mean = e.u_grid.map((u) => 1e6 * (1 + u));
  x.std = x.std.map(() => 2.5e5);
  x.peak = x.peak.map(() => 8e5);
});
/** The level probe (knob at 0, so y ≈ −g), at the Output's volume 0.5 (no soft clip). */
const PROBE: PatchDocument = voice({
  system: "rossler",
  observable: "x",
  amp_curve: "linear",
  param: 0,
});

/** Undo the DC blocker y_out[n] = y[n] − y[n−1] + R·y_out[n−1] (zero initial state). */
function undoDcBlocker(out: Float64Array, fs: number): Float64Array {
  const r = Math.exp((-2 * Math.PI * DC_HZ) / fs);
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

describe.each(RATES)("at %i Hz", (fs) => {
  test("a modulator's period is period_s seconds", () => {
    const T = 1; // T·fs and T·fs/2 are whole numbers of samples at all three rates
    const perCycle = T * fs;
    for (const shape of ["ramp_up", "square", "sine"] as Shape[]) {
      const out = renderModulator({ shape, period_s: T, mode: "loop" }, fs, 3 * perCycle + 1, 128);
      expect(out[perCycle], shape).toBe(out[0]);
      expect(out[2 * perCycle], shape).toBe(out[0]);
    }
    const ramp = renderModulator(
      { shape: "ramp_up", period_s: T, mode: "loop" },
      fs,
      perCycle + 1,
      128,
    );
    expect(ramp[perCycle / 2]).toBe(0.5);
    expect(ramp[perCycle - 1]).toBeCloseTo(1 - 1 / perCycle, 12);
    expect(ramp[perCycle]).toBe(0);
    const once = renderModulator(
      { shape: "ramp_up", period_s: T, mode: "once" },
      fs,
      2 * perCycle,
      128,
    );
    expect(once[perCycle - 1]).toBeLessThan(1);
    expect(once[perCycle]).toBe(1);
  });

  test("the amp fade-in reaches 1 − 1/e after 5 ms (the declick time)", () => {
    const r = render(PROBE, Math.round(0.02 * fs), { fs, cat: LEVEL });
    // Pre-DC audio y ≈ −a_s (linear curve, amp 1): the smoothed amp itself.
    const amp = undoDcBlocker(
      r.left.map((v) => v / 0.5),
      fs,
    ).map((v) => -v);
    const n63 = amp.findIndex((a) => a >= 1 - Math.exp(-1));
    // a_s[n] = 1 − (1 − α)^(n+1) with α = 1 − exp(−1/(τ·fs)): 1 − 1/e at n + 1 = τ·fs.
    expect(Math.abs(n63 + 1 - DECLICK_S * fs)).toBeLessThan(1.5);
    expect(amp[0]).toBeLessThan(0.01); // every box fades in from 0
  });

  test("the DC blocker's time constant is 1/(2π·5 Hz)", () => {
    const r = render(PROBE, Math.round(0.2 * fs), { fs, cat: LEVEL });
    // After the fade-in the box outputs a (nearly) constant level, which the DC blocker
    // removes with y_out[n + N] = R^N·y_out[n], R = exp(−2π·5/fs): e^(−π) over 0.1 s.
    const n1 = Math.round(0.05 * fs);
    const ratio = r.left[n1 + Math.round(0.1 * fs)]! / r.left[n1]!;
    expect(ratio / Math.exp(-Math.PI)).toBeCloseTo(1, 2);
  });

  test("a knob change slews with τ = max(5 ms, 2 periods) (ADR 0013)", () => {
    const n0 = Math.round(0.1 * fs); // the fade-in is over (a_s = 1 − e^−20)
    const n = Math.round(0.05 * fs);
    const e = new Engine({ maxFrames: 4096 });
    e.load(PROBE, LEVEL, fs);
    const [l, r] = [new Float64Array(n0 + n), new Float64Array(n0 + n)];
    e.process(n0, l, r);
    e.setParam("osc", "param", 0.5);
    e.process(n, l.subarray(n0), r.subarray(n0));
    // −y − 1 ≈ u_s, which goes 0 → 0.5 as 1 − (1 − α)^(k+1): estimate τ from each k.
    const y = undoDcBlocker(
      l.map((v) => v / 0.5),
      fs,
    );
    const expected = Math.max(DECLICK_S, 2 / noteToHz("A3"));
    let checked = 0;
    for (let k = 0; k < n; k++) {
      const done = (-y[n0 + k]! - 1) / 0.5;
      if (done < 0.05 || done > 0.95) continue;
      const tau = (k + 1) / (-fs * Math.log(1 - done));
      expect(tau / expected, `k = ${k}`).toBeCloseTo(1, 2);
      checked++;
    }
    expect(checked).toBeGreaterThan(expected * fs);
  });

  test("a live volume change glides with the 5 ms declick time constant", () => {
    const n0 = Math.round(0.02 * fs);
    const n = Math.round(0.02 * fs);
    const steady = new Engine({ maxFrames: 4096 });
    const moved = new Engine({ maxFrames: 4096 });
    const [l, r] = [new Float64Array(n0 + n), new Float64Array(n0 + n)];
    const [lm, rm] = [new Float64Array(n0 + n), new Float64Array(n0 + n)];
    for (const e of [steady, moved]) e.load(PROBE, LEVEL, fs);
    steady.process(n0, l, r);
    moved.process(n0, lm, rm);
    moved.setParam("out", "volume", 0.25);
    steady.process(n, l.subarray(n0), r.subarray(n0));
    moved.process(n, lm.subarray(n0), rm.subarray(n0));
    // v[k] = 0.5·moved/steady goes 0.5 → 0.25 as 1 − (1 − α)^(k+1): estimate τ from each k.
    let checked = 0;
    for (let k = 0; k < n; k++) {
      const v = (0.5 * lm[n0 + k]!) / l[n0 + k]!;
      const done = (0.5 - v) / 0.25;
      if (done < 0.05 || done > 0.95) continue;
      const tau = (k + 1) / (-fs * Math.log(1 - done));
      expect(tau / DECLICK_S, `k = ${k}`).toBeCloseTo(1, 6);
      checked++;
    }
    expect(checked).toBeGreaterThan(DECLICK_S * fs);
  });

  // The lab's tolerance for a single render of ≥ 2000 cycles (lab/tests/test_dynamical.py,
  // SINGLE_CENTS, measured at 44.1, 48 and 96 kHz; docs/math/tuning.md §6).
  test.each([
    ["duffing", "drive", 2],
    ["rossler", "peak_centroid", 2],
  ] as const)(
    "%s is tuned to the note (measured by %s, within %i cents)",
    (system, method, tol) => {
      const f = noteToHz("A3");
      const seconds = 0.5 + 2000 / f;
      const r = render(voice({ system }), Math.round(seconds * fs), { fs, blockSize: 4096 });
      const measured = measurePitch(r.left.subarray(Math.round(fs / 2)), fs, method, f);
      expect(Math.abs(centsBetween(measured, f))).toBeLessThan(tol);
    },
  );
});

test.each(["02_owner_example.json", "09_pitch_glide.json", "11_amp_envelope.json"])(
  "at 44.1 kHz, %s does not depend on the chunk size",
  (name) => {
    const doc = loadPatch(name);
    const fs = 44_100;
    const a = render(doc, 30_000, { fs, blockSize: 128 });
    const b = render(doc, 30_000, { fs, blockSize: 4096 });
    const c = render(doc, 3_000, { fs, blockSize: 1 });
    expect(firstDifference(b.left, a.left)).toBe(-1);
    expect(firstDifference(b.right, a.right)).toBe(-1);
    expect(firstDifference(c.left, a.left.subarray(0, 3_000))).toBe(-1);
    expect(b.diagnostics).toEqual(a.diagnostics);
  },
);
