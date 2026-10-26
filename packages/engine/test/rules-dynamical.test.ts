/**
 * Settings of the dynamical box that no golden patch exercises with a non-default value
 * (TS engine review, findings 26 and 29): amp_curve, cents, an explicit seed, a custom
 * pitch range with a pitch cable, pitch_lock = false, stereo and an explicit observable.
 */

import { describe, expect, test } from "vitest";
import type { Dynamical } from "../src/core/blocks/dynamical.ts";
import { Catalog } from "../src/core/catalog.ts";
import { centsBetween, noteToHz } from "../src/core/dsp/pitch.ts";
import { stableSeed } from "../src/core/dsp/rng.ts";
import { Engine } from "../src/core/engine.ts";
import type { BlockJson, PatchDocument } from "../src/core/patch.ts";
import { catalog } from "./helpers.ts";
import {
  correlation,
  firstDifference,
  measurePitch,
  patch,
  render,
  voice,
} from "./rules-helpers.ts";

const FS = 48_000;
const N = 9_600; // 0.2 s

/** Left channel of a one-voice render. */
const left = (params: Record<string, unknown>, frames = N, volume = 0.5) =>
  render(voice(params, { volume }), frames).left;

describe("amp_curve (spec §4.2 step 3)", () => {
  test("linear: halving the knob halves the output exactly", () => {
    const full = left({ amp: 1, amp_curve: "linear" });
    const half = left({ amp: 0.5, amp_curve: "linear" });
    // Every step scales exactly by 1/2 (a power of two), the fade-in and the DC blocker too.
    const halved = full.map((v) => v / 2);
    expect(firstDifference(half, halved)).toBe(-1);
  });

  test("perceptual: halving the knob is −10 dB, and the two laws differ", () => {
    const full = left({ amp: 1 });
    const half = left({ amp: 0.5 });
    // −10 dB is the amplitude ratio 10^(−10/20), which the spec's exponent 1/(2·log₁₀2)
    // gives exactly: 0.5^(1/(2·log₁₀2)) = 10^(−1/2).
    const minus10dB = 10 ** (-10 / 20);
    for (let i = 0; i < N; i += 37) expect(half[i]).toBeCloseTo(minus10dB * full[i]!, 12);
    // At amp = 1 the laws differ only during the fade-in (a_s < 1), which the DC blocker
    // remembers; at amp = 0.5 they differ at every sample.
    const linFull = left({ amp: 1, amp_curve: "linear" });
    expect(Math.abs(linFull[50]! - full[50]!)).toBeGreaterThan(1e-6);
    const linHalf = left({ amp: 0.5, amp_curve: "linear" });
    expect(linHalf[N - 1]! / half[N - 1]!).toBeCloseTo(0.5 / minus10dB, 2);
  });
});

describe("cents (spec §4.2 step 1)", () => {
  test("f = 440·2^((m + cents/100 − 69)/12)", () => {
    const e = new Engine();
    e.load(voice({ note: "A3", cents: -37 }), catalog, FS);
    expect((e.block("osc") as Dynamical).frequencyHz).toBe(440 * 2 ** ((57 + -37 / 100 - 69) / 12));
  });

  test("A3 + 100 cents plays exactly A#3, and other detunes change the sound", () => {
    expect(firstDifference(left({ note: "A3", cents: 100 }), left({ note: "A#3" }))).toBe(-1);
    expect(firstDifference(left({ note: "A3", cents: -100 }), left({ note: "Ab3" }))).toBe(-1);
    expect(firstDifference(left({ note: "A3", cents: 13 }), left({ note: "A3" }))).not.toBe(-1);
  });
});

describe("seed (spec §4.2 step 9)", () => {
  test("an explicit seed replaces the hash of the block id", () => {
    // Box "osc" seeded like a box called "voice" sounds exactly like it.
    const seeded = render(voice({ seed: stableSeed("voice") }, { id: "osc" }), N).left;
    const named = render(voice({}, { id: "voice" }), N).left;
    expect(firstDifference(seeded, named)).toBe(-1);
    const own = render(voice({}, { id: "osc" }), N).left;
    expect(firstDifference(seeded, own)).not.toBe(-1);
    expect(firstDifference(left({ seed: stableSeed("osc") }), own)).toBe(-1);
  });
});

describe("pitch range and the pitch cable (spec §4.2 step 1)", () => {
  /**
   * One box whose pitch input is the constant `q`: a square modulator (1 for the first half
   * of its 1000 s period) through a Control Sum with gain q, or q = 0 from an empty one.
   */
  function pitched(q: number, params: Record<string, unknown>): PatchDocument {
    const blocks: BlockJson[] = [
      { id: "m", type: "modulator", params: { shape: "square", period_s: 1000 } },
      { id: "cs", type: "control_sum", params: { gain: q } },
      { id: "osc", type: "dynamical", params: params as Record<string, never> },
      { id: "out", type: "output", params: { volume: 0.5 } },
    ];
    const cables: [string, string][] = [
      ["cs.out", "osc.pitch"],
      ["osc.out", "out.in"],
    ];
    if (q > 0) cables.push(["m.out", "cs.in"]);
    return patch(blocks, cables);
  }
  const range = { pitch_min: "C2", pitch_max: "C6" };

  test.each([
    [1, "C6"],
    [0.5, "C4"],
    [0, "C2"],
  ])("q = %d maps onto the custom range: it plays %s", (q, note) => {
    // m = m_min + q·(m_max − m_min): C2 (36) … C6 (84).
    const cable = render(pitched(q, range), N).left;
    expect(firstDifference(cable, left({ note }))).toBe(-1);
  });

  test("with a pitch cable, note and cents are ignored", () => {
    const a = render(pitched(0.5, range), N).left;
    const b = render(pitched(0.5, { ...range, note: "E5", cents: 50 }), N).left;
    expect(firstDifference(a, b)).toBe(-1);
  });

  test("the default range is A1 … A5", () => {
    expect(firstDifference(render(pitched(1, {}), N).left, left({ note: "A5" }))).toBe(-1);
    expect(firstDifference(render(pitched(0, {}), N).left, left({ note: "A1" }))).toBe(-1);
  });

  test("pitch_max must be below Nyquist even when the note is", () => {
    const e = new Engine();
    expect(() => e.load(voice({ note: "A3", pitch_max: "C8" }), catalog, 8_000)).toThrow(/below/);
    expect(() => e.load(voice({ note: "A3", pitch_max: "B7" }), catalog, 8_000)).not.toThrow();
  });
});

describe("pitch_lock (spec §4.2 step 5)", () => {
  const entry = new Catalog(catalog).get("lorenz");
  const f = noteToHz("A3");

  test("without pitch lock, k = P(u_default)·f whatever the knob", () => {
    // At the default knob both laws give the same k, bit for bit.
    const u = entry.uDefault;
    expect(
      firstDifference(
        left({ system: "lorenz", param: u, pitch_lock: false }),
        left({ system: "lorenz", param: u }),
      ),
    ).toBe(-1);
    expect(
      firstDifference(
        left({ system: "lorenz", param: 0.1, pitch_lock: false }),
        left({ system: "lorenz", param: 0.1 }),
      ),
    ).not.toBe(-1);
  });

  test("pitch lock keeps the note; without it the pitch follows P(u)", () => {
    const u = 0.1;
    /** Cents between the measured pitch of a 2 s render (from 0.5 s) and `nominal`. */
    const centsOff = (params: Record<string, unknown>, nominal: number) => {
      const x = left({ system: "lorenz", param: u, ...params }, 2 * FS).subarray(FS / 2);
      return centsBetween(measurePitch(x, FS, "peak_centroid", nominal), nominal);
    };
    // Free: the orbit's period P(u) in system time runs at k = P(u_default)·f.
    const fFree = (f * entry.period(entry.uDefault)) / entry.period(u);
    expect(Math.abs(centsBetween(fFree, f))).toBeGreaterThan(300); // a clear difference
    // About 300 cycles: the 5-cent tolerance of 2000-cycle renders widens to 25 cents.
    expect(Math.abs(centsOff({}, f))).toBeLessThan(25);
    expect(Math.abs(centsOff({ pitch_lock: false }, fFree))).toBeLessThan(25);
  });
});

describe("stereo and the heard variable (spec §4.2 step 7)", () => {
  test("stereo: left is the mono render of observable, right that of observable_right", () => {
    const stereo = render(voice({ system: "rossler", observable: "x", observable_right: "y" }), N);
    const monoX = render(voice({ system: "rossler", observable: "x" }), N);
    const monoY = render(voice({ system: "rossler", observable: "y" }), N);
    expect(firstDifference(stereo.left, monoX.left)).toBe(-1);
    expect(firstDifference(stereo.right, monoY.left)).toBe(-1);
    expect(firstDifference(stereo.left, stereo.right)).not.toBe(-1);
    // Mono puts the same variable on both channels.
    expect(firstDifference(monoX.left, monoX.right)).toBe(-1);
    expect(firstDifference(monoY.left, monoY.right)).toBe(-1);
  });

  test("an explicit non-default observable is heard: Duffing's x, whose derivative is y", () => {
    // Duffing: ẋ = y. Its default observable is y, so the box plays y unless told otherwise.
    // Per sample, x[n] − x[n−1] ≈ Δτ·(y[n] + y[n−1])/2; level scaling, the mean and the DC
    // blocker are linear and constant at a fixed knob, so they keep the relation.
    const frames = FS / 2;
    const x = left({ system: "duffing", observable: "x" }, frames);
    const y = left({ system: "duffing" }, frames);
    const from = FS / 10; // after the fade-in
    const dx = Float64Array.from(
      { length: frames - from },
      (_, i) => x[from + i]! - x[from + i - 1]!,
    );
    const yMid = Float64Array.from(
      { length: frames - from },
      (_, i) => (y[from + i]! + y[from + i - 1]!) / 2,
    );
    expect(correlation(dx, yMid)).toBeGreaterThan(0.99);
    // …while a variable is not correlated with its own derivative.
    const xMid = Float64Array.from(
      { length: frames - from },
      (_, i) => (x[from + i]! + x[from + i - 1]!) / 2,
    );
    expect(Math.abs(correlation(dx, xMid))).toBeLessThan(0.2);
    expect(firstDifference(left({ system: "duffing", observable: "y" }, frames), y)).toBe(-1);
  });
});
