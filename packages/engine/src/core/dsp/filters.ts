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
/** A gliding setting snaps to its target once it is this close (−180 dB for a gain of 1). */
export const GLIDE_SNAP = 1e-9;

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

/**
 * A setting that glides to a new value after a live change (spec §6): a one-pole with the
 * declick time constant, so moving a knob does not click. While the setting is steady its
 * value is returned exactly, so renders without live changes are bit-identical to using the
 * plain value (and to the reference engine, which has no live changes).
 */
export class Glide {
  /** [current, target]: kept in a typed array so updating them never boxes a number. */
  private readonly state = new Float64Array(2);
  private alpha = 1;

  constructor(value: number) {
    this.state[0] = value;
    this.state[1] = value;
  }

  /** The value used for the current sample. */
  get current(): number {
    return this.state[0]!;
  }

  /** The value the setting is moving to (set it to change the setting live). */
  get target(): number {
    return this.state[1]!;
  }

  set target(value: number) {
    this.state[1] = value;
  }

  /** Start a new render at `sampleRate` with no glide in progress. */
  reset(timeConstantS: number, sampleRate: number): void {
    this.alpha = onePoleCoefficient(timeConstantS, sampleRate);
    this.state[0] = this.state[1]!;
  }

  /** True while no glide is in progress. */
  get steady(): boolean {
    return this.state[0] === this.state[1];
  }

  /**
   * Write the next `n` values into `out` (same arithmetic as `next()`). Use this in audio
   * loops: the state stays in locals, so nothing is boxed per sample.
   */
  fill(out: Float64Array, n: number): void {
    const state = this.state;
    let current = state[0]!;
    const target = state[1]!;
    const alpha = this.alpha;
    for (let i = 0; i < n; i++) {
      if (current !== target) {
        current += alpha * (target - current);
        if (Math.abs(target - current) < GLIDE_SNAP) current = target;
      }
      out[i] = current;
    }
    state[0] = current;
  }

  /** Advance one sample and return the value for it. */
  next(): number {
    const state = this.state;
    let current = state[0]!;
    const target = state[1]!;
    if (current !== target) {
      current += this.alpha * (target - current);
      if (Math.abs(target - current) < GLIDE_SNAP) current = target;
      state[0] = current;
    }
    return current;
  }
}
