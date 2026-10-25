import { describe, expect, test } from "vitest";
import { renderOffline } from "../src/adapters/offline.ts";
import { encodeWav } from "../src/adapters/wav.ts";
import { AMP_EXPONENT } from "../src/core/blocks/dynamical.ts";
import { Engine } from "../src/core/engine.ts";
import type { PatchDocument } from "../src/core/patch.ts";
import { catalog, loadPatch, rms, single } from "./helpers.ts";

const FS = 48_000;

function render(doc: PatchDocument, frames: number, blockSize = 512) {
  return renderOffline(doc, catalog, { frames, sampleRate: FS, blockSize });
}

describe("processing model (spec §6)", () => {
  test("output does not depend on the chunk size", () => {
    const doc = loadPatch("02_owner_example.json");
    const a = render(doc, 30_000, 128);
    const b = render(doc, 30_000, 1001);
    const c = render(doc, 3_000, 1);
    expect(Array.from(b.left)).toEqual(Array.from(a.left));
    expect(Array.from(b.right)).toEqual(Array.from(a.right));
    expect(Array.from(c.left)).toEqual(Array.from(a.left.slice(0, 3_000)));
  });

  test("deterministic, and the order of blocks in the file does not matter", () => {
    const doc = loadPatch("06_chaotic_chord.json");
    const reversed = { ...doc, blocks: [...doc.blocks].reverse() };
    expect(Array.from(render(reversed, 20_000).left)).toEqual(Array.from(render(doc, 20_000).left));
  });

  test("Float32 output (the AudioWorklet case) equals rounded Float64", () => {
    const doc = single({ system: "lorenz" });
    const e64 = new Engine({ maxFrames: 128 });
    const e32 = new Engine({ maxFrames: 128 });
    e64.load(doc, catalog, FS);
    e32.load(doc, catalog, FS);
    const [l64, r64] = [new Float64Array(4096), new Float64Array(4096)];
    const [l32, r32] = [new Float32Array(4096), new Float32Array(4096)];
    e64.process(4096, l64, r64);
    e32.process(4096, l32, r32);
    expect(Array.from(l32)).toEqual(Array.from(Float32Array.from(l64)));
  });
});

describe("dynamical box", () => {
  test("loudness is normalized", () => {
    for (const system of ["lorenz", "rossler", "chua", "rikitake", "duffing"]) {
      const r = render(single({ system }, 1), FS * 2);
      expect(rms(r.left, FS / 4) / 0.25, system).toBeGreaterThan(0.85);
      expect(rms(r.left, FS / 4) / 0.25, system).toBeLessThan(1.15);
    }
  });

  test("perceptual amp curve: halving the knob is −10 dB", () => {
    const full = render(single({ amp: 1 }), FS / 2).left;
    const half = render(single({ amp: 0.5 }), FS / 2).left;
    for (let i = FS / 10; i < FS / 2; i += 97) {
      expect(half[i]).toBeCloseTo(0.5 ** AMP_EXPONENT * full[i]!, 12);
    }
    expect(20 * Math.log10(0.5 ** AMP_EXPONENT)).toBeCloseTo(-10, 12);
  });

  test("a cable overrides its knob exactly, from the first sample", () => {
    const knob = single({ system: "lorenz", param: 0.3 });
    const cable: PatchDocument = {
      format: "chaotic-sound-patch",
      version: 0,
      blocks: [
        { id: "cs", type: "control_sum", params: { gain: 0.3 } },
        { id: "m", type: "modulator", params: { shape: "ramp_up", period_s: 1000, mode: "once" } },
        { id: "osc", type: "dynamical", params: { system: "lorenz", param: 0.9 } },
        { id: "out", type: "output", params: { volume: 0.5 } },
      ],
      // ramp_up at t≈0 is ≈0, so feed a constant 1 via square instead:
      cables: [],
    };
    cable.blocks[1] = { id: "m", type: "modulator", params: { shape: "square", period_s: 1000 } };
    cable.cables = [
      { from: "m.out", to: "cs.in" },
      { from: "cs.out", to: "osc.param" },
      { from: "osc.out", to: "out.in" },
    ];
    expect(Array.from(render(cable, 8000).left)).toEqual(Array.from(render(knob, 8000).left));
  });

  test("Control Sum adds, then clips", () => {
    const doc: PatchDocument = {
      format: "chaotic-sound-patch",
      version: 0,
      blocks: [
        { id: "m1", type: "modulator", params: { shape: "square", period_s: 10 } },
        { id: "m2", type: "modulator", params: { shape: "square", period_s: 10 } },
        { id: "cs", type: "control_sum", params: { gain: 0.7 } },
        { id: "osc", type: "dynamical", params: { system: "rossler" } },
        { id: "out", type: "output", params: { volume: 0.5 } },
      ],
      cables: [
        { from: "m1.out", to: "cs.in" },
        { from: "m2.out", to: "cs.in" },
        { from: "cs.out", to: "osc.amp" },
        { from: "osc.out", to: "out.in" },
      ],
    };
    // clip(0.7 · (1 + 1)) = 1, the same as a knob amp of 1.
    expect(Array.from(render(doc, 9600).left)).toEqual(
      Array.from(render(single({ system: "rossler", amp: 1 }), 9600).left),
    );
  });

  test("live edits keep the state of unchanged blocks", () => {
    const doc = single({ system: "chua" });
    const live = new Engine({ maxFrames: 256 });
    live.load(doc, catalog, FS);
    const ref = new Engine({ maxFrames: 256 });
    ref.load(doc, catalog, FS);
    const [a, b, c, d] = [0, 0, 0, 0].map(() => new Float64Array(4800));
    live.process(4800, a!, b!);
    ref.process(4800, c!, d!);
    // Changing the output volume recreates only the output block; osc keeps going.
    live.setParam("out", "volume", 0.25);
    ref.setParam("out", "volume", 0.25);
    const [l1, r1, l2, r2] = [0, 0, 0, 0].map(() => new Float64Array(4800));
    live.process(4800, l1!, r1!);
    ref.process(4800, l2!, r2!);
    expect(Array.from(l1!)).toEqual(Array.from(l2!));
    // …and it really is a continuation, not a restart.
    const fresh = render(single({ system: "chua" }, 0.25), 4800).left;
    expect(Array.from(l1!)).not.toEqual(Array.from(fresh));
    expect(live.diagnostics()).toEqual({ osc: { safety_resets: 0 } });
  });
});

test("WAV encoding", () => {
  const bytes = encodeWav(
    Float64Array.of(0, 1, -2, 0.5 / 32767),
    Float64Array.of(0, 0, 0, 1.5 / 32767),
    48_000,
  );
  const v = new DataView(bytes.buffer);
  expect(String.fromCharCode(...bytes.slice(0, 4))).toBe("RIFF");
  expect(v.getUint32(24, true)).toBe(48_000);
  expect(v.getInt16(44 + 4 * 1, true)).toBe(32767);
  expect(v.getInt16(44 + 4 * 2, true)).toBe(-32767);
  expect(v.getInt16(44 + 4 * 3, true)).toBe(0); // 0.5 rounds half to even
  expect(v.getInt16(44 + 4 * 3 + 2, true)).toBe(2); // 1.5 rounds half to even
});
