/**
 * Cross-engine conformance (ADR 0011, spec §6): the TypeScript engine against golden vectors
 * exported by the Python reference (`lab/scripts/export_golden.py`).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { renderOffline } from "../src/adapters/offline.ts";
import type { Dynamical } from "../src/core/blocks/dynamical.ts";
import { Modulator, shapeValue } from "../src/core/blocks/index.ts";
import { Engine } from "../src/core/engine.ts";
import { catalog, EXAMPLES, examplePatches, f64, loadPatch } from "./helpers.ts";

interface Golden {
  sample_rate: number;
  block_size: number;
  initial_states: Record<string, number[]>;
  modulators: { n: number; values_f64_b64: Record<string, string> };
  prefix: { n: number; left_f64_b64: string; right_f64_b64: string };
  stats: {
    seconds: number;
    rms: number[];
    peak: number[];
    octave_bands_db: number[];
    band_centres_hz: number[];
    safety_resets: Record<string, number>;
    pitch_hz?: number;
    pitch_method?: string;
    nominal_hz?: number;
  };
}

function golden(name: string): Golden {
  return JSON.parse(readFileSync(resolve(EXAMPLES, "golden", name), "utf8")) as Golden;
}

/** Octave-band levels (dB re total) from one FFT, same bands as the exporter. */
function octaveBandsDb(x: Float64Array, fs: number, centres: number[]): number[] {
  // Power spectrum via a simple real FFT of the Hann-windowed signal (radix-2 on a padded copy).
  let n = 1;
  while (n < x.length) n <<= 1;
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  for (let i = 0; i < x.length; i++) {
    re[i] = x[i]! * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (x.length - 1)));
  }
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j]!, re[i]!];
      [im[i], im[j]] = [im[j]!, im[i]!];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < len / 2; k++) {
        const wr = Math.cos(ang * k);
        const wi = Math.sin(ang * k);
        const a = i + k;
        const b = a + len / 2;
        const tr = re[b]! * wr - im[b]! * wi;
        const ti = re[b]! * wi + im[b]! * wr;
        re[b] = re[a]! - tr;
        im[b] = im[a]! - ti;
        re[a] = re[a]! + tr;
        im[a] = im[a]! + ti;
      }
    }
  }
  const df = fs / n;
  let total = 0;
  const power = new Float64Array(n / 2 + 1);
  for (let k = 1; k <= n / 2; k++) {
    power[k] = re[k]! ** 2 + im[k]! ** 2;
    total += power[k]!;
  }
  return centres.map((fc) => {
    let e = 0;
    for (let k = 1; k <= n / 2; k++) {
      const f = k * df;
      if (f >= fc / Math.SQRT2 && f < fc * Math.SQRT2) e += power[k]!;
    }
    return 10 * Math.log10(Math.max(e / total, 1e-30));
  });
}

describe.each(examplePatches())("%s", (name) => {
  const g = golden(name);
  const patch = loadPatch(name);

  test("initial states are bit-identical (portable seeding)", () => {
    const engine = new Engine({ maxFrames: g.block_size });
    engine.load(patch, catalog, g.sample_rate);
    for (const [id, expected] of Object.entries(g.initial_states)) {
      const block = engine.block(id) as Dynamical;
      const mine = block.initialState();
      expected.forEach((v, j) => {
        // CRC-32 and mulberry32 are exact; log/cos may differ by 1 ulp (~1e-22 here).
        expect(Math.abs(mine[j]! - v)).toBeLessThanOrEqual(1e-15 * Math.max(1, Math.abs(v)));
      });
    }
  });

  test("modulators match exactly", () => {
    for (const [id, b64] of Object.entries(g.modulators.values_f64_b64)) {
      const spec = patch.blocks.find((b) => b.id === id)!;
      const m = new Modulator(id, (spec.params ?? {}) as Record<string, never>, {
        catalog: undefined as never,
        maxFrames: g.modulators.n,
      });
      m.reset(g.sample_rate);
      m.process(g.modulators.n);
      const expected = f64(b64);
      const shape = (spec.params?.shape ?? "sine") as string;
      for (let i = 0; i < expected.length; i++) {
        const got = m.outputs[0]![0]![i]!;
        if (shape === "sine") expect(Math.abs(got - expected[i]!)).toBeLessThanOrEqual(1e-15);
        else expect(got).toBe(expected[i]);
      }
    }
    expect(shapeValue("square", 0.5)).toBe(0);
  });

  test("the first samples agree with the reference", () => {
    const r = renderOffline(patch, catalog, {
      frames: g.prefix.n,
      sampleRate: g.sample_rate,
      blockSize: g.block_size,
    });
    const left = f64(g.prefix.left_f64_b64);
    const right = f64(g.prefix.right_f64_b64);
    let worst = 0;
    for (let i = 0; i < left.length; i++) {
      worst = Math.max(worst, Math.abs(r.left[i]! - left[i]!), Math.abs(r.right[i]! - right[i]!));
    }
    // Only libm last-bit differences, amplified by chaos over ~10 cycles (spec §6).
    expect(worst).toBeLessThan(1e-9);
  });

  test("long-run statistics agree with the reference", () => {
    const r = renderOffline(patch, catalog, {
      seconds: g.stats.seconds,
      sampleRate: g.sample_rate,
      blockSize: g.block_size,
    });
    const s = g.stats;
    // Chaotic statistics over 4 s: RMS within 6 %, bands within 2 dB where they matter.
    const rmsL = Math.sqrt(r.left.reduce((a, v) => a + v * v, 0) / r.left.length);
    const meanL = r.left.reduce((a, v) => a + v, 0) / r.left.length;
    const stdL = Math.sqrt(rmsL ** 2 - meanL ** 2);
    expect(stdL / s.rms[0]!).toBeGreaterThan(0.94);
    expect(stdL / s.rms[0]!).toBeLessThan(1.06);
    const bands = octaveBandsDb(r.left, g.sample_rate, s.band_centres_hz);
    bands.forEach((db, k) => {
      if (s.octave_bands_db[k]! > -40) expect(Math.abs(db - s.octave_bands_db[k]!)).toBeLessThan(2);
    });
    const resets = Object.fromEntries(
      Object.entries(r.diagnostics).map(([id, d]) => [id, d.safety_resets ?? 0]),
    );
    expect(resets).toEqual(s.safety_resets);
  });
});
