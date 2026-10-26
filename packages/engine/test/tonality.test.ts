/** Tonality (spec §4.2 step 7, ADR 0015): the TS-only behavior around the shared kernel. */

import { describe, expect, test } from "vitest";
import { TonalChannel, tonal } from "../src/core/dsp/tonal.ts";
import { Engine } from "../src/core/engine.ts";
import type { PatchDocument } from "../src/core/patch.ts";
import { catalog } from "./helpers.ts";

const FS = 48_000;

function voice(
  params: Record<string, number | string>,
  cables: PatchDocument["cables"] = [],
): PatchDocument {
  return {
    format: "chaotic-sound-patch",
    version: 0,
    blocks: [
      { id: "lfo", type: "modulator", params: { period_s: 0.5 } },
      { id: "osc", type: "dynamical", params: { system: "lorenz", ...params } },
      { id: "out", type: "output", params: {} },
    ],
    cables: [{ from: "osc.out", to: "out.in" }, ...cables],
  };
}

function render(engine: Engine, frames: number): Float64Array {
  const left = new Float64Array(frames);
  engine.process(frames, left, new Float64Array(frames));
  return left;
}

describe("tonality", () => {
  test("the default is 0.3 and it changes the sound", () => {
    const a = new Engine();
    a.load(voice({}), catalog, FS);
    const b = new Engine();
    b.load(voice({ tonality: 0.3 }), catalog, FS);
    const c = new Engine();
    c.load(voice({ tonality: 0 }), catalog, FS);
    const [ya, yb, yc] = [render(a, 4096), render(b, 4096), render(c, 4096)];
    expect(ya).toEqual(yb);
    expect(ya).not.toEqual(yc);
  });

  test("tonality 0 returns the raw signal exactly", () => {
    const n = 2048;
    const r = Float64Array.from({ length: n }, (_, i) => Math.sin(i * 0.37) * 0.2);
    const out = new Float64Array(n);
    tonal(r, new Float64Array(n).fill(220), new Float64Array(n), FS, new TonalChannel(), out, n);
    expect(out).toEqual(r);
  });

  test("a cable overrides the knob, and the knob changes live without a restart", () => {
    const cabled = new Engine();
    cabled.load(voice({ tonality: 0 }, [{ from: "lfo.out", to: "osc.tonality" }]), catalog, FS);
    const knob = new Engine();
    knob.load(voice({ tonality: 0 }), catalog, FS);
    expect(render(cabled, 8192)).not.toEqual(render(knob, 8192));

    const before = knob.block("osc");
    knob.setParam("osc", "tonality", 0.9);
    expect(knob.block("osc")).toBe(before); // live: same block, ODE state kept
    render(knob, 1024);
    expect(knob.patch!.blocks[1]!.params!.tonality).toBe(0.9);
  });
});

describe("tonality live (verification findings, ADR 0015)", () => {
  const steady = (y: Float64Array, from: number, to: number): number => {
    let m = 0;
    for (let i = from; i < to; i++) m = Math.max(m, Math.abs(y[i]!));
    return m;
  };
  const maxStep = (y: Float64Array, from: number, to: number): number => {
    let m = 0;
    for (let i = Math.max(1, from); i < to; i++) m = Math.max(m, Math.abs(y[i]! - y[i - 1]!));
    return m;
  };

  test("a live note drop C8 → A1 does not overshoot (modulation-safe band filter)", () => {
    for (const system of ["lorenz", "rikitake"]) {
      const e = new Engine({ maxFrames: 128 });
      e.load(voice({ system, note: "C8" }), catalog, FS);
      const before = render(e, FS);
      e.setParam("osc", "note", "A1");
      const after = render(e, FS / 2);
      // Before the fix the box peaked 10× its steady level and the Output clipped.
      expect(steady(after, 0, after.length)).toBeLessThan(1.5 * steady(before, FS / 2, FS));
    }
  });

  test("turning tonality to 0 live glides out without a click", () => {
    const e = new Engine({ maxFrames: 128 });
    e.load(voice({ system: "chua", note: "A2", tonality: 0.7 }), catalog, FS);
    const a = render(e, FS);
    const normal = maxStep(a, FS / 2, FS);
    e.setParam("osc", "tonality", 0);
    const b = render(e, FS);
    expect(maxStep(b, 0, 2048)).toBeLessThan(2 * normal);
  });

  test("switching tonality off and on again restarts the tonal state", () => {
    const e = new Engine({ maxFrames: 128 });
    e.load(voice({ tonality: 0.5 }), catalog, FS);
    render(e, FS / 2);
    e.setParam("osc", "tonality", 0);
    render(e, FS); // τ_s reaches exactly 0 and the step is skipped
    e.setParam("osc", "tonality", 0.5);
    render(e, 1280);
    const block = e.block("osc") as unknown as { tonalLeft: { scalars: Float64Array } };
    expect(block.tonalLeft.scalars[1]).toBe(1280); // counted from 0 since it came back on
  });

  test("a non-finite band state is reset and counted", () => {
    const e = new Engine({ maxFrames: 128 });
    e.load(voice({}), catalog, FS);
    render(e, 512);
    const block = e.block("osc") as unknown as { tonalLeft: { bands: Float64Array } };
    block.tonalLeft.bands[0] = Number.NaN;
    render(e, 512);
    expect(e.diagnostics().osc!.safety_resets).toBeGreaterThanOrEqual(1);
    const y = render(e, 512);
    expect(y.every((v) => Number.isFinite(v))).toBe(true);
  });
});
