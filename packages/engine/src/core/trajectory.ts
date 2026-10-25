/**
 * Attractor points for visualization (e.g. the 3D view on the Learn-more pages). Uses the
 * same RK4 kernel and catalog data as the audio path, so what you see is what you hear.
 */

import type { Catalog } from "./catalog.ts";
import { makeRk4Scratch, renderTuned } from "./dsp/rk4.ts";
import { getSystem } from "./dsp/systems.ts";

export interface AttractorPoints {
  /** Interleaved x, y, z, … (state variables in system order), `count` points. */
  readonly points: Float64Array;
  readonly count: number;
  readonly dim: number;
  readonly variables: readonly string[];
}

/**
 * Integrate `system` at knob position `u` from the catalog's initial condition and sample
 * `count` points, `samplesPerPeriod` per characteristic period, after `transientPeriods`.
 */
export function attractorPoints(
  catalog: Catalog,
  systemName: string,
  u: number,
  count = 20_000,
  samplesPerPeriod = 48,
  transientPeriods = 20,
): AttractorPoints {
  const system = getSystem(systemName);
  const entry = catalog.get(systemName);
  const dim = system.variables.length;
  const p = Float64Array.from(system.defaultParams);
  const modIndex = system.paramNames.indexOf(system.modulatedParam);
  const dt = entry.period(u) / samplesPerPeriod;
  const x = Float64Array.from(entry.initialCondition);
  const scratch = makeRk4Scratch(dim);
  const run = (n: number, out: Float64Array): void => {
    renderTuned(
      {
        rhs: system.rhs,
        x,
        p,
        modIndex,
        pValues: new Float64Array(n).fill(entry.paramValue(u)),
        dtau: new Float64Array(n).fill(dt),
        hMax: entry.hMax,
        phaseIndices: system.phaseIndices,
        lo: entry.boundsLo,
        hi: entry.boundsHi,
        xReset: Float64Array.from(entry.initialCondition),
        out,
        scratch,
      },
      n,
    );
  };
  const transient = Math.round(transientPeriods * samplesPerPeriod);
  run(transient, new Float64Array(transient * dim));
  const points = new Float64Array(count * dim);
  run(count, points);
  return { points, count, dim, variables: system.variables };
}
