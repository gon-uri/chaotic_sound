/**
 * Fixed-step RK4 integration kernels (spec §4.2 steps 6 and 8), mirroring
 * `lab/src/chaotic_sound/integrate.py`. Times are in system time τ.
 */

import type { Rhs } from "./systems.ts";

export const TWO_PI = 2 * Math.PI;
/** Upper bound on RK4 sub-steps per sample (a cost guard; at most 42 are needed, at C8). */
export const MAX_SUBSTEPS = 4096;

/** Scratch arrays for one RK4 step (allocate once per box). */
export interface Rk4Scratch {
  readonly k1: Float64Array;
  readonly k2: Float64Array;
  readonly k3: Float64Array;
  readonly k4: Float64Array;
  readonly tmp: Float64Array;
}

export function makeRk4Scratch(dim: number): Rk4Scratch {
  return {
    k1: new Float64Array(dim),
    k2: new Float64Array(dim),
    k3: new Float64Array(dim),
    k4: new Float64Array(dim),
    tmp: new Float64Array(dim),
  };
}

/** Advance `x` in place by one classical RK4 step of size `h`. */
export function rk4Step(
  rhs: Rhs,
  x: Float64Array,
  p: Float64Array,
  h: number,
  s: Rk4Scratch,
): void {
  const n = x.length;
  const { k1, k2, k3, k4, tmp } = s;
  rhs(x, p, k1);
  for (let i = 0; i < n; i++) tmp[i] = x[i]! + 0.5 * h * k1[i]!;
  rhs(tmp, p, k2);
  for (let i = 0; i < n; i++) tmp[i] = x[i]! + 0.5 * h * k2[i]!;
  rhs(tmp, p, k3);
  for (let i = 0; i < n; i++) tmp[i] = x[i]! + h * k3[i]!;
  rhs(tmp, p, k4);
  for (let i = 0; i < n; i++) {
    x[i]! += (h / 6) * (k1[i]! + 2 * k2[i]! + 2 * k3[i]! + k4[i]!);
  }
}

/** Wrap phase variables to [0, 2π) with the floating-point remainder (Python's `%`). */
export function wrapPhases(x: Float64Array, phaseIndices: readonly number[]): void {
  for (const i of phaseIndices) {
    const r = x[i]! % TWO_PI;
    x[i] = r < 0 ? r + TWO_PI : r + 0; // + 0 turns −0 into +0, as Python's % does
  }
}

/** Arguments of {@link renderTuned}; all arrays are caller-owned and preallocated. */
export interface TunedRenderArgs {
  readonly rhs: Rhs;
  /** ODE state, updated in place (persists across chunks). */
  readonly x: Float64Array;
  /** Parameter vector; entry `modIndex` is overwritten every sample. */
  readonly p: Float64Array;
  readonly modIndex: number;
  /** Modulated parameter value per sample. */
  readonly pValues: Float64Array;
  /** System time to advance per sample, k/fs. */
  readonly dtau: Float64Array;
  readonly hMax: number;
  readonly phaseIndices: readonly number[];
  readonly lo: Float64Array;
  readonly hi: Float64Array;
  readonly xReset: Float64Array;
  /** State after each sample, row-major (n × dim). */
  readonly out: Float64Array;
  readonly scratch: Rk4Scratch;
}

/**
 * Audio-rate integration with a per-sample parameter and time step. For each sample:
 * set the parameter, take clamp(⌈Δτ/h_max⌉, 1, MAX_SUBSTEPS) RK4 steps, wrap phases, run
 * the safety check, record the state. Returns the number of safety resets.
 */
export function renderTuned(a: TunedRenderArgs, n: number): number {
  const { rhs, x, p, modIndex, pValues, dtau, hMax, phaseIndices, lo, hi, xReset, out, scratch } =
    a;
  const dim = x.length;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    p[modIndex] = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      let nSub = 1;
      const q = d / hMax;
      if (q > 1) nSub = q >= MAX_SUBSTEPS ? MAX_SUBSTEPS : Math.ceil(q);
      const h = d / nSub;
      for (let k = 0; k < nSub; k++) rk4Step(rhs, x, p, h, scratch);
      wrapPhases(x, phaseIndices);
    }
    for (let j = 0; j < dim; j++) {
      const v = x[j]!;
      if (!Number.isFinite(v) || v < lo[j]! || v > hi[j]!) ok = false;
    }
    if (!ok) {
      x.set(xReset);
      resets++;
    }
    out.set(x, i * dim);
  }
  return resets;
}
