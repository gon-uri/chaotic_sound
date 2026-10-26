/**
 * Cross-engine conformance (ADR 0011, spec §6): the TypeScript engine against golden vectors
 * exported by the Python reference (`lab/scripts/export_golden.py`, which documents the
 * file format). Each golden file names its patch (a demo in `examples/patches/` or a fixture
 * in `examples/golden/patches/`) and the sample rate and block size to render it with.
 *
 * Four tiers, from exact to statistical:
 * 1. initial states: bit-identical seeding (1 ulp from log/cos allowed);
 * 2. modulators: exact (sine: the last bit of cos), over the first samples and around the
 *    first cycle edges, including the end of `once` envelopes;
 * 3. the first samples of the output: within 1e-9 for any engine (spec §6). This engine
 *    mirrors the Python arithmetic, so it must do much better: within 1e-12, and on the
 *    platform where its error was recorded never worse than that (exact where it was exact);
 * 4. statistics of a longer render (level, level per segment, octave bands, safety resets):
 *    within a few times their natural spread, measured by the exporter over renders that
 *    differ only in the seeds. Round-off differences between engines (which spec §6 allows)
 *    move chaotic statistics by about that spread, so this tier must not fail on them.
 *
 * After `export_golden.py` changes a prefix, record this engine's error again with
 * `GOLDEN_RECORD=1 npx vitest run packages/engine/test/golden.test.ts` (repository root).
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { renderOffline } from "../src/adapters/offline.ts";
import type { Dynamical } from "../src/core/blocks/dynamical.ts";
import { shapeValue } from "../src/core/blocks/index.ts";
import { Engine } from "../src/core/engine.ts";
import { defaultParam, type ParamValue, type PatchDocument } from "../src/core/patch.ts";
import { catalog, EXAMPLES, f64, goldenFiles, loadPatch } from "./helpers.ts";

/** Spec §6: the first samples of any engine agree with the reference to about this. */
const SPEC_PREFIX_BOUND = 1e-9;
/** This engine keeps the reference's arithmetic order, so only libm last bits remain. */
const TS_PREFIX_BOUND = 1e-12;
/**
 * Statistics may differ by this many ensemble spreads (standard deviations). Checked by
 * perturbing this engine's initial state by k·1e-12 (k = 1 … 6) and by reordering the RK4
 * combine: the prefix tier failed in every run, and the largest statistical difference was
 * 6.1 spreads (about 550 statistics per run; unperturbed, the largest is 4.4).
 */
const SPREADS = 10;
/** Floors for statistics that hardly vary with the seed (deterministic or silent). */
const LEVEL_REL_FLOOR = 1e-3;
const LEVEL_ABS_FLOOR = 1e-6; // −120 dB re full scale: inaudible
const DB_FLOOR = 0.1;
/** Bands quieter than this (dB re total) hold window leakage and FFT round-off: skipped. */
const BAND_MIN_DB = -60;

const RECORD = process.env.GOLDEN_RECORD === "1";
const PLATFORM = `${process.platform}-${process.arch}`;

interface Window {
  start: number;
  values_f64_b64: string;
}

/** Statistics of one render: `value` from the reference, `spread` over the seed ensemble. */
interface StatsRecord {
  solo: string | null;
  value: Record<string, number[]>;
  spread: Record<string, number[]>;
}

interface Golden {
  about: string;
  patch: string;
  sample_rate: number;
  block_size: number;
  initial_states: Record<string, number[]>;
  modulators: Record<string, Window[]>;
  prefix: {
    n: number;
    left_f64_b64: string;
    right_f64_b64: string;
    ts_max_abs_error: number | null;
    ts_platform: string | null;
  };
  stats: {
    seconds: number;
    segment_s: number;
    channels: number;
    ensemble: number;
    band_centres_hz: number[];
    safety_resets: Record<string, number>;
    renders: StatsRecord[];
  };
}

function goldenPath(file: string): string {
  return resolve(EXAMPLES, "golden", file);
}

/** Write this engine's prefix error into the golden file, leaving the rest byte for byte. */
function recordPrefixError(file: string, worst: number): void {
  const text = readFileSync(goldenPath(file), "utf8")
    .replace(/"ts_max_abs_error": [^,\n]*/, `"ts_max_abs_error": ${worst}`)
    .replace(/"ts_platform": [^,\n]*/, `"ts_platform": "${PLATFORM}"`);
  writeFileSync(goldenPath(file), text);
}

/**
 * The control output of a lone modulator, rendered through the engine `chunk` samples at a
 * time (so chunk boundaries fall where they would in a real render).
 */
function renderModulator(
  params: Record<string, ParamValue | null>,
  fs: number,
  n: number,
  chunk = 512,
): Float64Array {
  const doc: PatchDocument = {
    format: "chaotic-sound-patch",
    version: 0,
    blocks: [
      { id: "m", type: "modulator", params },
      { id: "out", type: "output" },
    ],
    cables: [],
  };
  const engine = new Engine({ maxFrames: chunk });
  engine.load(doc, catalog, fs);
  const out = engine.block("m")!.outputs[0]![0]!; // the buffer the engine fills per chunk
  const left = new Float64Array(chunk);
  const right = new Float64Array(chunk);
  const y = new Float64Array(n);
  for (let pos = 0; pos < n; pos += chunk) {
    const m = Math.min(chunk, n - pos);
    engine.process(m, left, right);
    y.set(out.subarray(0, m), pos);
  }
  return y;
}

/** `doc` with every dynamical box except `voice` removed, with their cables (as the exporter). */
function solo(doc: PatchDocument, voice: string): PatchDocument {
  const others = new Set(
    doc.blocks.filter((b) => b.type === "dynamical" && b.id !== voice).map((b) => b.id),
  );
  const owner = (end: string) => end.split(".")[0]!;
  return {
    ...doc,
    blocks: doc.blocks.filter((b) => !others.has(b.id)),
    cables: doc.cables.filter((c) => !others.has(owner(c.from)) && !others.has(owner(c.to))),
  };
}

/** Population standard deviation of x[from, to) (numpy's `np.std`). */
function std(x: Float64Array, from = 0, to = x.length): number {
  let mean = 0;
  for (let i = from; i < to; i++) mean += x[i]!;
  mean /= to - from;
  let s = 0;
  for (let i = from; i < to; i++) s += (x[i]! - mean) ** 2;
  return Math.sqrt(s / (to - from));
}

/**
 * Octave-band levels (dB re total) from one Hann-windowed FFT, zero-padded to a power of two
 * as in the exporter (an iterative radix-2 FFT: bit-reversal permutation, then butterflies).
 */
function octaveBandsDb(x: Float64Array, fs: number, centres: readonly number[]): number[] {
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
      const t = re[i]!;
      re[i] = re[j]!;
      re[j] = t; // the imaginary parts are still all zero
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const half = len / 2;
    const wr = new Float64Array(half);
    const wi = new Float64Array(half);
    for (let k = 0; k < half; k++) {
      wr[k] = Math.cos((-2 * Math.PI * k) / len);
      wi[k] = Math.sin((-2 * Math.PI * k) / len);
    }
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < half; k++) {
        const a = i + k;
        const b = a + half;
        const tr = re[b]! * wr[k]! - im[b]! * wi[k]!;
        const ti = re[b]! * wi[k]! + im[b]! * wr[k]!;
        re[b] = re[a]! - tr;
        im[b] = im[a]! - ti;
        re[a] = re[a]! + tr;
        im[a] = im[a]! + ti;
      }
    }
  }
  const df = fs / n;
  const power = new Float64Array(n / 2 + 1);
  let total = 0;
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

/** The exporter's statistics, channel after channel. */
function statistics(
  audio: readonly Float64Array[],
  fs: number,
  s: Golden["stats"],
): Record<string, number[]> {
  const seg = Math.round(s.segment_s * fs);
  const out: Record<string, number[]> = { std: [], segment_std: [], bands_db: [] };
  for (const x of audio.slice(0, s.channels)) {
    out.std!.push(std(x));
    for (let i = 0; i < x.length; i += seg) {
      out.segment_std!.push(std(x, i, Math.min(i + seg, x.length)));
    }
    out.bands_db!.push(...octaveBandsDb(x, fs, s.band_centres_hz));
  }
  return out;
}

/** The allowed difference for one statistic, or null if it is not compared. */
function tolerance(name: string, value: number, spread: number): number | null {
  if (name === "bands_db") {
    return value < BAND_MIN_DB ? null : Math.max(SPREADS * spread, DB_FLOOR);
  }
  return Math.max(SPREADS * spread, LEVEL_REL_FLOOR * Math.abs(value), LEVEL_ABS_FLOOR);
}

describe.each(goldenFiles())("%s", (file) => {
  const g = JSON.parse(readFileSync(goldenPath(file), "utf8")) as Golden;
  const patch = loadPatch(g.patch);

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

  test("modulators match exactly, across cycle edges and the end of once", () => {
    const wrong: string[] = [];
    for (const [id, windows] of Object.entries(g.modulators)) {
      const params = patch.blocks.find((b) => b.id === id)!.params ?? {};
      const sine = (params.shape ?? defaultParam("modulator", "shape")) === "sine";
      const expected = windows.map((w) => f64(w.values_f64_b64));
      const n = Math.max(...windows.map((w, k) => w.start + expected[k]!.length));
      const got = renderModulator(params, g.sample_rate, n, g.block_size);
      windows.forEach((w, k) => {
        expected[k]!.forEach((v, i) => {
          const mine = got[w.start + i]!;
          // Sine: cos may differ in its last bit (spec §6), which moves (1 − cos)/2 by < ε.
          const ok = sine ? Math.abs(mine - v) <= Number.EPSILON : mine === v;
          if (!ok) wrong.push(`${id}[${w.start + i}]: ${mine}, expected ${v}`);
        });
      });
    }
    expect(wrong.slice(0, 10)).toEqual([]);
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
    expect(worst).toBeLessThan(SPEC_PREFIX_BOUND);
    expect(worst).toBeLessThanOrEqual(TS_PREFIX_BOUND);
    if (RECORD) recordPrefixError(file, worst);
    const recorded = RECORD ? worst : g.prefix.ts_max_abs_error;
    expect(recorded, "no recorded TypeScript error: run with GOLDEN_RECORD=1").not.toBeNull();
    // On the platform of the record the output is deterministic, so any change of arithmetic
    // order shows: never worse than recorded (exact where it was exact). Other CPUs may
    // differ in libm last bits (and FMA use), so there only the 1e-12 bound applies.
    if ((RECORD ? PLATFORM : g.prefix.ts_platform) === PLATFORM) {
      expect(worst, `recorded ${recorded} on ${PLATFORM}`).toBeLessThanOrEqual(recorded!);
    }
  });

  test("long-run statistics agree within their seed-to-seed spread", () => {
    const s = g.stats;
    const wrong: string[] = [];
    for (const record of s.renders) {
      const doc = record.solo === null ? patch : solo(patch, record.solo);
      const r = renderOffline(doc, catalog, {
        seconds: s.seconds,
        sampleRate: g.sample_rate,
        blockSize: g.block_size,
      });
      if (record.solo === null) {
        const resets = Object.fromEntries(
          Object.entries(r.diagnostics).map(([id, d]) => [id, d.safety_resets ?? 0]),
        );
        expect(resets).toEqual(s.safety_resets);
      }
      const mine = statistics([r.left, r.right], g.sample_rate, s);
      for (const [name, values] of Object.entries(record.value)) {
        values.forEach((v, k) => {
          const tol = tolerance(name, v, record.spread[name]![k]!);
          const got = mine[name]![k]!;
          if (tol !== null && !(Math.abs(got - v) <= tol)) {
            wrong.push(`${record.solo ?? "patch"} ${name}[${k}]: ${got}, expected ${v} ± ${tol}`);
          }
        });
      }
    }
    expect(wrong).toEqual([]);
  });
});

describe("modulator phase (spec §4.1; ports of lab/tests/test_modulator.py)", () => {
  test("a loop is periodic and a once envelope holds its end value", () => {
    const loop = renderModulator({ shape: "ramp_up", period_s: 0.5, mode: "loop" }, 1000, 2000);
    for (let i = 0; i < 500; i++) {
      expect(Math.abs(loop[i]! - loop[i + 500]!)).toBeLessThanOrEqual(1e-12);
    }
    const once = renderModulator({ shape: "ramp_up", period_s: 0.5, mode: "once" }, 1000, 2000);
    expect(once[499]).toBeLessThan(1);
    expect(once.subarray(500).every((v) => v === 1)).toBe(true);
    const onceSine = renderModulator({ shape: "sine", period_s: 0.5, mode: "once" }, 1000, 2000);
    expect(onceSine.subarray(500).every((v) => v === 0)).toBe(true);
  });

  test("the phase formula is pinned at cycle edges", () => {
    // t = i/fs, c = t/T, φ = c − floor(c), all in float64.
    const fs = 48_000;
    const period = 0.1;
    const y = renderModulator({ shape: "square", period_s: period }, fs, 30_000);
    let wrong = 0;
    for (let i = 0; i < y.length; i++) {
      const c = i / fs / period;
      if (y[i] !== (c - Math.floor(c) < 0.5 ? 1 : 0)) wrong++;
    }
    expect(wrong).toBe(0);
    // With a binary-exact period the edges are exact: sample 500 is t = T/2 at fs = 1000.
    const z = renderModulator({ shape: "square", period_s: 1.0 }, 1000, 2001);
    expect([z[499], z[500], z[1000], z[2000]]).toEqual([1, 0, 1, 1]);
    expect(shapeValue("square", 0.5)).toBe(0);
  });
});
