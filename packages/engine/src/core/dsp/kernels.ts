/**
 * Specialized RK4 kernels, one per system (docs/studies/cost.md, recommendation 1).
 *
 * Each kernel does exactly what `renderTuned` (rk4.ts) does with that system's `rhs`, but with
 * the right-hand side written out and the state in scalar local variables instead of
 * `Float64Array`s. V8 can keep scalar locals in CPU registers, while every array access is a
 * memory load or store with a bounds check. The cost study measured this structure ("variant
 * A") 1.5–2.7× faster per step than the literal port ("variant B", `renderTuned`);
 * `bench/kernels.ts` measures it in this engine. It matters at high notes, where one sample
 * takes up to about 36 RK4 sub-steps.
 *
 * Results are bit-identical to `renderTuned`, hence to the Python reference. Every RHS
 * expression is the one in `systems.ts` with the array elements renamed (x[0] → x, …), and
 * the RK4 lines follow `rk4Step`. JavaScript never fuses a multiply and an add, and it
 * evaluates `a * b * c` as `(a * b) * c`, so the order of operations is all that matters.
 * The one rewrite is exact: `0.5 * h * k` is `(0.5 * h) * k`, so `h2 = 0.5 * h` is computed
 * once per sample, and likewise `h6 = h / 6`.
 *
 * The kernels are written by hand from one template; `renderLorenz` is the commented one.
 * `test/kernels.test.ts` runs each kernel and `renderTuned` side by side on random states,
 * parameters and time steps and requires exact equality, so a kernel that drifts from its
 * `SystemDef` fails the tests. A system without a kernel uses `renderTuned` (see
 * `tunedRenderer`). To add a kernel: copy one of the same dimension, write the new RHS into
 * its four stages, and add it to `KERNELS`. Hand-made common subexpressions are not worth it:
 * sharing the cosine of Duffing's k2 and k3 stages (same point) measured no faster, because
 * V8 can merge repeated pure calls itself.
 *
 * The argument arrays must not overlap (they do not in Dynamical): the state is read into
 * locals at the start and written back at the end.
 */

import { MAX_SUBSTEPS, renderTuned, type TunedRenderArgs, TWO_PI } from "./rk4.ts";
import type { SystemDef } from "./systems.ts";

/** `renderTuned` or a specialized kernel: same arguments, same result, same side effects. */
export type TunedRenderer = (args: TunedRenderArgs, n: number) => number;

/** Sub-steps for one sample: clamp(⌈q⌉, 1, MAX_SUBSTEPS) with q = Δτ/h_max, as in renderTuned. */
function subSteps(q: number): number {
  if (q > 1) return q >= MAX_SUBSTEPS ? MAX_SUBSTEPS : Math.ceil(q);
  return 1;
}

/** The safety check of one variable (spec §4.2 step 8), as in renderTuned. */
function outside(v: number, lo: number, hi: number): boolean {
  return !Number.isFinite(v) || v < lo || v > hi;
}

/** A phase variable wrapped to [0, 2π), as in wrapPhases. */
function wrapPhase(v: number): number {
  const r = v % TWO_PI;
  return r < 0 ? r + TWO_PI : r;
}

/** Lorenz: σ = p[0], ρ = p[1] (modulated), β = p[2]. */
export function renderLorenz(args: TunedRenderArgs, n: number): number {
  const { p, pValues, dtau, hMax, lo, hi, xReset, out } = args;
  const state = args.x;
  // Parameters that are not modulated stay fixed for the whole call.
  const sigma = p[0]!;
  const beta = p[2]!;
  const xLo = lo[0]!;
  const xHi = hi[0]!;
  const yLo = lo[1]!;
  const yHi = hi[1]!;
  const zLo = lo[2]!;
  const zHi = hi[2]!;
  // The ODE state lives in locals during the call.
  let x = state[0]!;
  let y = state[1]!;
  let z = state[2]!;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    const rho = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      const nSub = subSteps(d / hMax);
      const h = d / nSub;
      const h2 = 0.5 * h;
      const h6 = h / 6;
      for (let s = 0; s < nSub; s++) {
        // k1 = F(x)
        const k1x = sigma * (y - x);
        const k1y = x * (rho - z) - y;
        const k1z = x * y - beta * z;
        // k2 = F(x + h/2·k1); (tx, ty, tz) plays the role of rk4Step's `tmp`
        let tx = x + h2 * k1x;
        let ty = y + h2 * k1y;
        let tz = z + h2 * k1z;
        const k2x = sigma * (ty - tx);
        const k2y = tx * (rho - tz) - ty;
        const k2z = tx * ty - beta * tz;
        // k3 = F(x + h/2·k2)
        tx = x + h2 * k2x;
        ty = y + h2 * k2y;
        tz = z + h2 * k2z;
        const k3x = sigma * (ty - tx);
        const k3y = tx * (rho - tz) - ty;
        const k3z = tx * ty - beta * tz;
        // k4 = F(x + h·k3)
        tx = x + h * k3x;
        ty = y + h * k3y;
        tz = z + h * k3z;
        const k4x = sigma * (ty - tx);
        const k4y = tx * (rho - tz) - ty;
        const k4z = tx * ty - beta * tz;
        x += h6 * (k1x + 2 * k2x + 2 * k3x + k4x);
        y += h6 * (k1y + 2 * k2y + 2 * k3y + k4y);
        z += h6 * (k1z + 2 * k2z + 2 * k3z + k4z);
      }
    }
    if (outside(x, xLo, xHi) || outside(y, yLo, yHi) || outside(z, zLo, zHi)) ok = false;
    if (!ok) {
      x = xReset[0]!;
      y = xReset[1]!;
      z = xReset[2]!;
      resets++;
    }
    const o = 3 * i;
    out[o] = x;
    out[o + 1] = y;
    out[o + 2] = z;
  }
  // Leave the arrays as renderTuned does: the state, and the last modulated value in p.
  state[0] = x;
  state[1] = y;
  state[2] = z;
  if (n > 0) p[1] = pValues[n - 1]!;
  return resets;
}

/** Rössler: a = p[0], b = p[1], c = p[2] (modulated). */
export function renderRossler(args: TunedRenderArgs, n: number): number {
  const { p, pValues, dtau, hMax, lo, hi, xReset, out } = args;
  const state = args.x;
  const a = p[0]!;
  const b = p[1]!;
  const xLo = lo[0]!;
  const xHi = hi[0]!;
  const yLo = lo[1]!;
  const yHi = hi[1]!;
  const zLo = lo[2]!;
  const zHi = hi[2]!;
  let x = state[0]!;
  let y = state[1]!;
  let z = state[2]!;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    const c = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      const nSub = subSteps(d / hMax);
      const h = d / nSub;
      const h2 = 0.5 * h;
      const h6 = h / 6;
      for (let s = 0; s < nSub; s++) {
        const k1x = -y - z;
        const k1y = x + a * y;
        const k1z = b + z * (x - c);
        let tx = x + h2 * k1x;
        let ty = y + h2 * k1y;
        let tz = z + h2 * k1z;
        const k2x = -ty - tz;
        const k2y = tx + a * ty;
        const k2z = b + tz * (tx - c);
        tx = x + h2 * k2x;
        ty = y + h2 * k2y;
        tz = z + h2 * k2z;
        const k3x = -ty - tz;
        const k3y = tx + a * ty;
        const k3z = b + tz * (tx - c);
        tx = x + h * k3x;
        ty = y + h * k3y;
        tz = z + h * k3z;
        const k4x = -ty - tz;
        const k4y = tx + a * ty;
        const k4z = b + tz * (tx - c);
        x += h6 * (k1x + 2 * k2x + 2 * k3x + k4x);
        y += h6 * (k1y + 2 * k2y + 2 * k3y + k4y);
        z += h6 * (k1z + 2 * k2z + 2 * k3z + k4z);
      }
    }
    if (outside(x, xLo, xHi) || outside(y, yLo, yHi) || outside(z, zLo, zHi)) ok = false;
    if (!ok) {
      x = xReset[0]!;
      y = xReset[1]!;
      z = xReset[2]!;
      resets++;
    }
    const o = 3 * i;
    out[o] = x;
    out[o + 1] = y;
    out[o + 2] = z;
  }
  state[0] = x;
  state[1] = y;
  state[2] = z;
  if (n > 0) p[2] = pValues[n - 1]!;
  return resets;
}

/**
 * Chua: α = p[0] (modulated), β = p[1], m0 = p[2], m1 = p[3]. `r1` … `r4` are the
 * piecewise-linear resistor h(x) of each stage (called `h` in systems.ts).
 */
export function renderChua(args: TunedRenderArgs, n: number): number {
  const { p, pValues, dtau, hMax, lo, hi, xReset, out } = args;
  const state = args.x;
  const beta = p[1]!;
  const m0 = p[2]!;
  const m1 = p[3]!;
  const xLo = lo[0]!;
  const xHi = hi[0]!;
  const yLo = lo[1]!;
  const yHi = hi[1]!;
  const zLo = lo[2]!;
  const zHi = hi[2]!;
  let x = state[0]!;
  let y = state[1]!;
  let z = state[2]!;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    const alpha = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      const nSub = subSteps(d / hMax);
      const h = d / nSub;
      const h2 = 0.5 * h;
      const h6 = h / 6;
      for (let s = 0; s < nSub; s++) {
        const r1 = m1 * x + 0.5 * (m0 - m1) * (Math.abs(x + 1) - Math.abs(x - 1));
        const k1x = alpha * (y - x - r1);
        const k1y = x - y + z;
        const k1z = -beta * y;
        let tx = x + h2 * k1x;
        let ty = y + h2 * k1y;
        let tz = z + h2 * k1z;
        const r2 = m1 * tx + 0.5 * (m0 - m1) * (Math.abs(tx + 1) - Math.abs(tx - 1));
        const k2x = alpha * (ty - tx - r2);
        const k2y = tx - ty + tz;
        const k2z = -beta * ty;
        tx = x + h2 * k2x;
        ty = y + h2 * k2y;
        tz = z + h2 * k2z;
        const r3 = m1 * tx + 0.5 * (m0 - m1) * (Math.abs(tx + 1) - Math.abs(tx - 1));
        const k3x = alpha * (ty - tx - r3);
        const k3y = tx - ty + tz;
        const k3z = -beta * ty;
        tx = x + h * k3x;
        ty = y + h * k3y;
        tz = z + h * k3z;
        const r4 = m1 * tx + 0.5 * (m0 - m1) * (Math.abs(tx + 1) - Math.abs(tx - 1));
        const k4x = alpha * (ty - tx - r4);
        const k4y = tx - ty + tz;
        const k4z = -beta * ty;
        x += h6 * (k1x + 2 * k2x + 2 * k3x + k4x);
        y += h6 * (k1y + 2 * k2y + 2 * k3y + k4y);
        z += h6 * (k1z + 2 * k2z + 2 * k3z + k4z);
      }
    }
    if (outside(x, xLo, xHi) || outside(y, yLo, yHi) || outside(z, zLo, zHi)) ok = false;
    if (!ok) {
      x = xReset[0]!;
      y = xReset[1]!;
      z = xReset[2]!;
      resets++;
    }
    const o = 3 * i;
    out[o] = x;
    out[o + 1] = y;
    out[o + 2] = z;
  }
  state[0] = x;
  state[1] = y;
  state[2] = z;
  if (n > 0) p[0] = pValues[n - 1]!;
  return resets;
}

/** Rikitake dynamo: a = p[0], μ = p[1] (modulated). */
export function renderRikitake(args: TunedRenderArgs, n: number): number {
  const { p, pValues, dtau, hMax, lo, hi, xReset, out } = args;
  const state = args.x;
  const a = p[0]!;
  const xLo = lo[0]!;
  const xHi = hi[0]!;
  const yLo = lo[1]!;
  const yHi = hi[1]!;
  const zLo = lo[2]!;
  const zHi = hi[2]!;
  let x = state[0]!;
  let y = state[1]!;
  let z = state[2]!;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    const mu = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      const nSub = subSteps(d / hMax);
      const h = d / nSub;
      const h2 = 0.5 * h;
      const h6 = h / 6;
      for (let s = 0; s < nSub; s++) {
        const k1x = -mu * x + y * z;
        const k1y = -mu * y - a * x + x * z;
        const k1z = 1 - x * y;
        let tx = x + h2 * k1x;
        let ty = y + h2 * k1y;
        let tz = z + h2 * k1z;
        const k2x = -mu * tx + ty * tz;
        const k2y = -mu * ty - a * tx + tx * tz;
        const k2z = 1 - tx * ty;
        tx = x + h2 * k2x;
        ty = y + h2 * k2y;
        tz = z + h2 * k2z;
        const k3x = -mu * tx + ty * tz;
        const k3y = -mu * ty - a * tx + tx * tz;
        const k3z = 1 - tx * ty;
        tx = x + h * k3x;
        ty = y + h * k3y;
        tz = z + h * k3z;
        const k4x = -mu * tx + ty * tz;
        const k4y = -mu * ty - a * tx + tx * tz;
        const k4z = 1 - tx * ty;
        x += h6 * (k1x + 2 * k2x + 2 * k3x + k4x);
        y += h6 * (k1y + 2 * k2y + 2 * k3y + k4y);
        z += h6 * (k1z + 2 * k2z + 2 * k3z + k4z);
      }
    }
    if (outside(x, xLo, xHi) || outside(y, yLo, yHi) || outside(z, zLo, zHi)) ok = false;
    if (!ok) {
      x = xReset[0]!;
      y = xReset[1]!;
      z = xReset[2]!;
      resets++;
    }
    const o = 3 * i;
    out[o] = x;
    out[o + 1] = y;
    out[o + 2] = z;
  }
  state[0] = x;
  state[1] = y;
  state[2] = z;
  if (n > 0) p[1] = pValues[n - 1]!;
  return resets;
}

/**
 * Forced Duffing: α = p[0], β = p[1], δ = p[2], γ = p[3] (modulated), ω = p[4]. z is the
 * phase of the drive (ż = ω), wrapped to [0, 2π) after each sample's sub-steps.
 */
export function renderDuffing(args: TunedRenderArgs, n: number): number {
  const { p, pValues, dtau, hMax, lo, hi, xReset, out } = args;
  const state = args.x;
  const alpha = p[0]!;
  const beta = p[1]!;
  const delta = p[2]!;
  const omega = p[4]!;
  const xLo = lo[0]!;
  const xHi = hi[0]!;
  const yLo = lo[1]!;
  const yHi = hi[1]!;
  const zLo = lo[2]!;
  const zHi = hi[2]!;
  let x = state[0]!;
  let y = state[1]!;
  let z = state[2]!;
  let resets = 0;
  for (let i = 0; i < n; i++) {
    const gamma = pValues[i]!;
    const d = dtau[i]!;
    let ok = Number.isFinite(d) && d >= 0;
    if (ok) {
      const nSub = subSteps(d / hMax);
      const h = d / nSub;
      const h2 = 0.5 * h;
      const h6 = h / 6;
      for (let s = 0; s < nSub; s++) {
        const k1x = y;
        const k1y = -delta * y - beta * x - alpha * (x * x * x) + gamma * Math.cos(z);
        const k1z = omega;
        let tx = x + h2 * k1x;
        let ty = y + h2 * k1y;
        let tz = z + h2 * k1z;
        const k2x = ty;
        const k2y = -delta * ty - beta * tx - alpha * (tx * tx * tx) + gamma * Math.cos(tz);
        const k2z = omega;
        tx = x + h2 * k2x;
        ty = y + h2 * k2y;
        tz = z + h2 * k2z;
        const k3x = ty;
        const k3y = -delta * ty - beta * tx - alpha * (tx * tx * tx) + gamma * Math.cos(tz);
        const k3z = omega;
        tx = x + h * k3x;
        ty = y + h * k3y;
        tz = z + h * k3z;
        const k4x = ty;
        const k4y = -delta * ty - beta * tx - alpha * (tx * tx * tx) + gamma * Math.cos(tz);
        const k4z = omega;
        x += h6 * (k1x + 2 * k2x + 2 * k3x + k4x);
        y += h6 * (k1y + 2 * k2y + 2 * k3y + k4y);
        z += h6 * (k1z + 2 * k2z + 2 * k3z + k4z);
      }
      z = wrapPhase(z); // as wrapPhases, after the sub-steps of the sample
    }
    if (outside(x, xLo, xHi) || outside(y, yLo, yHi) || outside(z, zLo, zHi)) ok = false;
    if (!ok) {
      x = xReset[0]!;
      y = xReset[1]!;
      z = xReset[2]!;
      resets++;
    }
    const o = 3 * i;
    out[o] = x;
    out[o + 1] = y;
    out[o + 2] = z;
  }
  state[0] = x;
  state[1] = y;
  state[2] = z;
  if (n > 0) p[3] = pValues[n - 1]!;
  return resets;
}

/** The specialized kernels, by system name. */
const KERNELS: ReadonlyMap<string, TunedRenderer> = new Map<string, TunedRenderer>([
  ["lorenz", renderLorenz],
  ["rossler", renderRossler],
  ["chua", renderChua],
  ["rikitake", renderRikitake],
  ["duffing", renderDuffing],
]);

/** The integrator for `system`: its specialized kernel, or `renderTuned` if it has none. */
export function tunedRenderer(system: SystemDef): TunedRenderer {
  return KERNELS.get(system.name) ?? renderTuned;
}
