/**
 * Shared helpers of the `rules-*.test.ts` files: patch builders, rendering at any sample
 * rate, catalog copies and a pitch estimator ported from the Python lab
 * (`lab/src/chaotic_sound/analysis/spectrum.py`).
 */

import { type OfflineResult, renderOffline } from "../src/adapters/offline.ts";
import { Modulator } from "../src/core/blocks/index.ts";
import type { Shape } from "../src/core/blocks/modulator.ts";
import type { CatalogDocument, EntryJson } from "../src/core/catalog.ts";
import type { BlockJson, CableJson, PatchDocument } from "../src/core/patch.ts";
import { catalog } from "./helpers.ts";

/** A patch from blocks and `[from, to]` cable pairs. */
export function patch(blocks: BlockJson[], cables: [string, string][] = []): PatchDocument {
  const cableJson: CableJson[] = cables.map(([from, to]) => ({ from, to }));
  return { format: "chaotic-sound-patch", version: 0, blocks, cables: cableJson };
}

/** One dynamical box `id` (with `params`) into an Output at `volume`. */
export function voice(
  params: Record<string, unknown>,
  { id = "osc", volume = 0.5 }: { id?: string; volume?: number } = {},
): PatchDocument {
  return patch(
    [
      { id, type: "dynamical", params: params as Record<string, never> },
      { id: "out", type: "output", params: { volume } },
    ],
    [[`${id}.out`, "out.in"]],
  );
}

export interface RenderOptions {
  readonly fs?: number;
  readonly blockSize?: number;
  readonly cat?: CatalogDocument;
}

/** Render `frames` samples of `doc` (48 kHz and 512-sample chunks unless given). */
export function render(doc: PatchDocument, frames: number, o: RenderOptions = {}): OfflineResult {
  return renderOffline(doc, o.cat ?? catalog, {
    frames,
    sampleRate: o.fs ?? 48_000,
    blockSize: o.blockSize ?? 512,
  });
}

/** Render a modulator block on its own, `blockSize` samples at a time. */
export function renderModulator(
  params: { shape: Shape; period_s: number; mode: "loop" | "once" },
  fs: number,
  frames: number,
  blockSize: number,
): Float64Array {
  // A modulator needs no catalog; `undefined as never` satisfies the type checker.
  const m = new Modulator("m", params, { catalog: undefined as never, maxFrames: blockSize });
  m.reset(fs);
  const out = new Float64Array(frames);
  for (let pos = 0; pos < frames; pos += blockSize) {
    const n = Math.min(blockSize, frames - pos);
    m.process(n);
    out.set(m.outputs[0]![0]!.subarray(0, n), pos);
  }
  return out;
}

/** A deep copy of the real catalog with one system entry changed by `edit`. */
export function editedCatalog(system: string, edit: (e: EntryJson) => void): CatalogDocument {
  const doc = structuredClone(catalog);
  edit(doc.systems[system]!);
  return doc;
}

/** Index of the first sample where `a` and `b` differ (`Object.is`), or -1. */
export function firstDifference(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length) return Math.min(a.length, b.length);
  for (let i = 0; i < a.length; i++) if (!Object.is(a[i], b[i])) return i;
  return -1;
}

/** Pearson correlation of two equally long signals. */
export function correlation(a: ArrayLike<number>, b: ArrayLike<number>): number {
  const n = a.length;
  let ma = 0;
  let mb = 0;
  for (let i = 0; i < n; i++) {
    ma += a[i]!;
    mb += b[i]!;
  }
  ma /= n;
  mb /= n;
  let sab = 0;
  let saa = 0;
  let sbb = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i]! - ma;
    const db = b[i]! - mb;
    sab += da * db;
    saa += da * da;
    sbb += db * db;
  }
  return sab / Math.sqrt(saa * sbb);
}

/** In-place radix-2 complex FFT (`re.length` must be a power of two). */
function fft(re: Float64Array, im: Float64Array): void {
  const n = re.length;
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
    const half = len >> 1;
    for (let k = 0; k < half; k++) {
      const wr = Math.cos(ang * k);
      const wi = Math.sin(ang * k);
      for (let i = k; i < n; i += len) {
        const b = i + half;
        const tr = re[b]! * wr - im[b]! * wi;
        const ti = re[b]! * wi + im[b]! * wr;
        re[b] = re[i]! - tr;
        im[b] = im[i]! - ti;
        re[i] = re[i]! + tr;
        im[i] = im[i]! + ti;
      }
    }
  }
}

/**
 * Welch power spectral density like `scipy.signal.welch(x, fs, nperseg, noverlap=nperseg/2,
 * window="hann", detrend="constant")`, up to a constant factor (which no estimator here
 * depends on). Returns the PSD on bins k·fs/nperseg, k = 0 … nperseg/2.
 */
function welchPsd(x: ArrayLike<number>, nperseg: number): Float64Array {
  const step = nperseg >> 1;
  const psd = new Float64Array(step + 1);
  const window = Float64Array.from(
    { length: nperseg },
    (_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / nperseg), // periodic Hann (scipy)
  );
  const re = new Float64Array(nperseg);
  const im = new Float64Array(nperseg);
  for (let start = 0; start + nperseg <= x.length; start += step) {
    let mean = 0;
    for (let i = 0; i < nperseg; i++) mean += x[start + i]!;
    mean /= nperseg;
    for (let i = 0; i < nperseg; i++) {
      re[i] = (x[start + i]! - mean) * window[i]!;
      im[i] = 0;
    }
    fft(re, im);
    for (let k = 0; k <= step; k++) {
      const p = re[k]! ** 2 + im[k]! ** 2;
      psd[k] = psd[k]! + (k === 0 || k === step ? p : 2 * p);
    }
  }
  return psd;
}

/**
 * Frequency (Hz) of rendered audio, measured the way the catalog defines P: a port of the
 * lab's `measure_pitch` for the methods `drive` (interpolated spectral maximum) and
 * `peak_centroid` (power-weighted mean within ±10 % of the maximum).
 */
export function measurePitch(
  x: ArrayLike<number>,
  fs: number,
  method: "drive" | "peak_centroid",
  nominalHz: number,
): number {
  const nperseg = Math.min(2 ** 17, 2 ** Math.floor(Math.log2(Math.max(x.length >> 2, 256))));
  const psd = welchPsd(x, nperseg);
  const df = fs / nperseg;
  const fMin = 0.25 * nominalHz;
  let k = -1;
  for (let i = 0; i < psd.length; i++) {
    if (i * df > fMin && (k < 0 || psd[i]! > psd[k]!)) k = i;
  }
  if (method === "drive") {
    let f = k * df;
    const [a, b, c] = [psd[k - 1]!, psd[k]!, psd[k + 1]!];
    if ((k - 1) * df > fMin && b >= a && b >= c && a > 0 && c > 0) {
      const [la, lb, lc] = [Math.log(a), Math.log(b), Math.log(c)];
      const denom = la - 2 * lb + lc;
      if (denom < 0) f += Math.max(-0.5, Math.min(0.5, (0.5 * (la - lc)) / denom)) * df;
    }
    return f;
  }
  let num = 0;
  let den = 0;
  for (let i = 0; i < psd.length; i++) {
    const f = i * df;
    if (f > fMin && Math.abs(f - k * df) <= 0.1 * k * df) {
      num += f * psd[i]!;
      den += psd[i]!;
    }
  }
  return num / den;
}
