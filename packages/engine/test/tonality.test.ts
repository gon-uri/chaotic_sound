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
