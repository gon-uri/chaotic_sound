/**
 * Differential test of the specialized RK4 kernels (src/core/dsp/kernels.ts): each kernel and
 * the generic `renderTuned` run side by side on the same random inputs, and everything they
 * leave behind must be bit-identical: the recorded trajectory, the final state, the parameter
 * vector and the number of safety resets.
 *
 * Bit identity (not a tolerance) is the requirement: the kernels only restructure the code, so
 * any difference is a changed operation order. The trajectories are chaotic, so a one-ulp
 * difference anywhere grows until it shows up in the comparison.
 */

import { describe, expect, test } from "vitest";
import { Catalog, type CatalogEntry } from "../src/core/catalog.ts";
import { tunedRenderer } from "../src/core/dsp/kernels.ts";
import {
  MAX_SUBSTEPS,
  makeRk4Scratch,
  renderTuned,
  type TunedRenderArgs,
  TWO_PI,
} from "../src/core/dsp/rk4.ts";
import { Mulberry32 } from "../src/core/dsp/rng.ts";
import { SYSTEMS, type SystemDef } from "../src/core/dsp/systems.ts";
import { catalog } from "./helpers.ts";

const CAT = new Catalog(catalog);
const CHUNK = 128; // one render quantum
const CHUNKS = 4; // the state carries over between calls, as in Dynamical

/** Index of the first element whose bits differ, or -1 if the arrays are bit-identical. */
function firstDiff(a: Float64Array, b: Float64Array): number {
  if (a.length !== b.length) return Math.min(a.length, b.length);
  const ua = new BigUint64Array(a.buffer, a.byteOffset, a.length);
  const ub = new BigUint64Array(b.buffer, b.byteOffset, b.length);
  for (let i = 0; i < ua.length; i++) if (ua[i] !== ub[i]) return i;
  return -1;
}

/** Inputs of one side-by-side run (shared, read-only for both integrators). */
interface Case {
  readonly x: Float64Array;
  readonly p: Float64Array;
  readonly hMax: number;
  readonly lo: Float64Array;
  readonly hi: Float64Array;
  readonly xReset: Float64Array;
  /** Fills the per-sample inputs of one chunk. */
  readonly fill: (pValues: Float64Array, dtau: Float64Array) => void;
}

/** Arguments for one integrator, with its own copies of everything it writes. */
function argsFor(sys: SystemDef, c: Case, pValues: Float64Array, dtau: Float64Array) {
  const dim = sys.variables.length;
  const args: TunedRenderArgs = {
    rhs: sys.rhs,
    x: c.x.slice(),
    p: c.p.slice(),
    modIndex: sys.paramNames.indexOf(sys.modulatedParam),
    pValues,
    dtau,
    hMax: c.hMax,
    phaseIndices: sys.phaseIndices,
    lo: c.lo,
    hi: c.hi,
    xReset: c.xReset,
    out: new Float64Array(CHUNK * dim),
    scratch: makeRk4Scratch(dim),
  };
  return args;
}

/** Runs both integrators chunk by chunk and asserts identity; returns the total resets. */
function compare(sys: SystemDef, c: Case, label: string): number {
  const pValues = new Float64Array(CHUNK);
  const dtau = new Float64Array(CHUNK);
  const generic = argsFor(sys, c, pValues, dtau);
  const kernel = argsFor(sys, c, pValues, dtau);
  const render = tunedRenderer(sys);
  let total = 0;
  for (let k = 0; k < CHUNKS; k++) {
    c.fill(pValues, dtau);
    const n = k === CHUNKS - 1 ? CHUNK - 37 : CHUNK; // a short last chunk, like a partial quantum
    const rg = renderTuned(generic, n);
    const rk = render(kernel, n);
    const where = `${sys.name} ${label} chunk ${k}`;
    expect(rk, `${where}: resets`).toBe(rg);
    expect(firstDiff(kernel.out, generic.out), `${where}: trajectory`).toBe(-1);
    expect(firstDiff(kernel.x, generic.x), `${where}: state`).toBe(-1);
    expect(firstDiff(kernel.p, generic.p), `${where}: parameters`).toBe(-1);
    total += rg;
  }
  return total;
}

function uniform(rng: Mulberry32, lo: number, hi: number): number {
  return lo + (hi - lo) * rng.uniform();
}

/** A state near the catalog's attractor, the defaults, and per-sample parameter jitter. */
function attractorCase(sys: SystemDef, e: CatalogEntry, rng: Mulberry32): Case {
  const dim = sys.variables.length;
  const x = e.initialCondition.slice();
  for (let j = 0; j < dim; j++) x[j] = x[j]! + uniform(rng, -0.1, 0.1);
  const range = e.pMax - e.pMin;
  let pv = uniform(rng, e.pMin, e.pMax);
  return {
    x,
    p: Float64Array.from(sys.defaultParams),
    hMax: e.hMax,
    lo: e.boundsLo,
    hi: e.boundsHi,
    xReset: e.initialCondition,
    fill: (pValues, dtau) => {
      for (let i = 0; i < pValues.length; i++) {
        // A random walk inside the knob range; Δτ from 0 to 40 sub-steps (beyond C8).
        pv = Math.min(e.pMax, Math.max(e.pMin, pv + 0.01 * range * uniform(rng, -1, 1)));
        pValues[i] = pv;
        dtau[i] = rng.uniform() < 0.05 ? 0 : uniform(rng, 0, 40 * e.hMax);
      }
    },
  };
}

/** Time steps that renderTuned must reject (reset) or treat specially. */
const ODD_DTAU = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1, -0, 0];

/**
 * Anything goes: a state anywhere in the bounds box, every parameter scaled at random,
 * parameter values outside the knob range, odd and huge time steps (the MAX_SUBSTEPS cap),
 * and bounds shrunk so that trajectories leave them (the safety reset).
 */
function wildCase(sys: SystemDef, e: CatalogEntry, rng: Mulberry32): Case {
  const dim = sys.variables.length;
  const lo = new Float64Array(dim);
  const hi = new Float64Array(dim);
  const x = new Float64Array(dim);
  const xReset = new Float64Array(dim);
  const shrink = uniform(rng, 0.2, 1);
  for (let j = 0; j < dim; j++) {
    const mid = 0.5 * (e.boundsLo[j]! + e.boundsHi[j]!);
    const half = 0.5 * (e.boundsHi[j]! - e.boundsLo[j]!);
    lo[j] = mid - shrink * half;
    hi[j] = mid + shrink * half;
    x[j] = uniform(rng, lo[j]!, hi[j]!);
    xReset[j] = uniform(rng, lo[j]!, hi[j]!);
  }
  const p = Float64Array.from(sys.defaultParams, (v) => v * uniform(rng, 0.5, 1.5));
  const hMax = e.hMax * uniform(rng, 0.5, 2);
  const range = e.pMax - e.pMin;
  return {
    x,
    p,
    hMax,
    lo,
    hi,
    xReset,
    fill: (pValues, dtau) => {
      for (let i = 0; i < pValues.length; i++) {
        pValues[i] = uniform(rng, e.pMin - 0.5 * range, e.pMax + 0.5 * range);
        const r = rng.uniform();
        if (r < 0.06) dtau[i] = ODD_DTAU[Math.floor(rng.uniform() * ODD_DTAU.length)]!;
        else if (r < 0.07)
          dtau[i] = hMax * MAX_SUBSTEPS * uniform(rng, 1, 1e6); // capped
        else if (r < 0.3)
          dtau[i] = uniform(rng, 0, hMax); // one sub-step
        else dtau[i] = uniform(rng, 0, 20 * hMax);
      }
    },
  };
}

describe("specialized RK4 kernels", () => {
  test.each(SYSTEMS.map((s) => [s.name, s] as const))("%s has a kernel", (_, sys) => {
    expect(tunedRenderer(sys)).not.toBe(renderTuned);
  });

  test("a system without a kernel falls back to renderTuned", () => {
    expect(tunedRenderer({ ...SYSTEMS[0]!, name: "no-such-system" })).toBe(renderTuned);
  });

  test.each(SYSTEMS.map((s, i) => [s.name, s, i] as const))(
    "%s matches renderTuned bit for bit near the attractor",
    (_, sys, index) => {
      const e = CAT.get(sys.name);
      const rng = new Mulberry32(1000 + index);
      for (let k = 0; k < 40; k++) compare(sys, attractorCase(sys, e, rng), `attractor case ${k}`);
    },
  );

  test.each(SYSTEMS.map((s, i) => [s.name, s, i] as const))(
    "%s matches renderTuned bit for bit on wild inputs, resets included",
    (_, sys, index) => {
      const e = CAT.get(sys.name);
      const rng = new Mulberry32(2000 + index);
      let resets = 0;
      for (let k = 0; k < 40; k++) resets += compare(sys, wildCase(sys, e, rng), `wild case ${k}`);
      expect(resets, "the safety reset path must be exercised").toBeGreaterThan(100);
    },
  );

  test.each(SYSTEMS.filter((s) => s.phaseIndices.length > 0).map((s) => [s.name, s] as const))(
    "%s wraps its phase exactly like renderTuned",
    (_, sys) => {
      const e = CAT.get(sys.name);
      const dim = sys.variables.length;
      // Negative, exactly-2π and very large phases, held (Δτ = 0) or advanced.
      const phases = [-3.7, -0, -TWO_PI, -1e3, 0, TWO_PI, 4 * TWO_PI + 0.1, 1e3, 1e15];
      const steps = [0, 1e-3 * e.hMax, 0.5 * e.hMax, 7.3 * e.hMax, 50 * e.hMax];
      const lo = new Float64Array(dim).fill(-1e300);
      const hi = new Float64Array(dim).fill(1e300);
      for (const phase of phases) {
        for (const step of steps) {
          const x = e.initialCondition.slice();
          for (const j of sys.phaseIndices) x[j] = phase;
          const c: Case = {
            x,
            p: Float64Array.from(sys.defaultParams),
            hMax: e.hMax,
            lo,
            hi,
            xReset: e.initialCondition,
            fill: (pValues, dtau) => {
              pValues.fill(e.pDefault);
              dtau.fill(step);
            },
          };
          compare(sys, c, `phase ${phase}, dtau ${step}`);
        }
      }
    },
  );
});
