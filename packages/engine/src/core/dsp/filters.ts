/**
 * Small DSP building blocks: smoothing, DC blocking, soft clipping (spec §3, §4.2, §4.4).
 *
 * Recurrences are pinned by the spec and mirror `lab/src/chaotic_sound/dsp.py`:
 * - one-pole: y[n] = y[n−1] + α(x[n] − y[n−1]), output after the update;
 * - DC blocker: y[n] = x[n] − x[n−1] + R·y[n−1], with x[−1] = y[−1] = 0;
 * - states with |s| < 1e-30 are flushed to 0.
 *
 * State lives in caller-owned Float64Arrays so chunked processing is seamless. These are
 * C-style kernels (no allocation), ready to be ported function by function (ADR 0011).
 */

export const SOFT_CLIP_KNEE = 0.9;
export const FLUSH_TO_ZERO = 1e-30;

/** α = 1 − exp(−1/(τ·fs)); τ ≤ 0 gives 1 (no smoothing). */
export function onePoleCoefficient(timeConstantS: number, sampleRate: number): number {
  if (timeConstantS <= 0) return 1;
  return 1 - Math.exp(-1 / (timeConstantS * sampleRate));
}

/** One-pole low-pass with a constant α over the first `n` samples. `state[0]` is y[n−1]. */
export function onePole(
  x: Float64Array,
  state: Float64Array,
  alpha: number,
  out: Float64Array,
  n: number,
): void {
  let y = state[0]!;
  for (let i = 0; i < n; i++) {
    y += alpha * (x[i]! - y);
    if (Math.abs(y) < FLUSH_TO_ZERO) y = 0;
    out[i] = y;
  }
  state[0] = y;
}

/** One-pole low-pass with a per-sample α. */
export function onePoleVarying(
  x: Float64Array,
  state: Float64Array,
  alpha: Float64Array,
  out: Float64Array,
  n: number,
): void {
  let y = state[0]!;
  for (let i = 0; i < n; i++) {
    y += alpha[i]! * (x[i]! - y);
    if (Math.abs(y) < FLUSH_TO_ZERO) y = 0;
    out[i] = y;
  }
  state[0] = y;
}

/** Pole radius R = exp(−2π f_c / fs) of the first-order DC blocker. */
export function dcBlockCoefficient(cutoffHz: number, sampleRate: number): number {
  return Math.exp((-2 * Math.PI * cutoffHz) / sampleRate);
}

/** First-order DC blocker. `state = [x_prev, y_prev]`. */
export function dcBlock(
  x: Float64Array,
  state: Float64Array,
  r: number,
  out: Float64Array,
  n: number,
): void {
  let xp = state[0]!;
  let yp = state[1]!;
  for (let i = 0; i < n; i++) {
    let y = x[i]! - xp + r * yp;
    if (Math.abs(y) < FLUSH_TO_ZERO) y = 0;
    xp = x[i]!;
    yp = y;
    out[i] = y;
  }
  state[0] = xp;
  state[1] = yp;
}

/** Identity for |x| ≤ knee; above it, tanh-squashed into (knee, 1). */
export function softClip(x: number, knee: number = SOFT_CLIP_KNEE): number {
  const ax = Math.abs(x);
  if (ax <= knee) return x;
  const width = 1 - knee;
  return Math.sign(x) * (knee + width * Math.tanh((ax - knee) / width));
}
