/**
 * The dynamical systems (right-hand sides and metadata), mirroring
 * `lab/src/chaotic_sound/systems/`. Parameter values and initial conditions come from the
 * catalog; here we only need the equations and the parameter order.
 *
 * An RHS writes F(x; p) into `out` without allocating: `rhs(x, p, out)`.
 */

export type Rhs = (x: Float64Array, p: Float64Array, out: Float64Array) => void;

export interface SystemDef {
  readonly name: string;
  readonly displayName: string;
  readonly variables: readonly string[];
  readonly paramNames: readonly string[];
  readonly defaultParams: readonly number[];
  readonly modulatedParam: string;
  /** Indices of phase variables (wrapped to [0, 2π), never heard). */
  readonly phaseIndices: readonly number[];
  readonly rhs: Rhs;
}

const lorenz: SystemDef = {
  name: "lorenz",
  displayName: "Lorenz",
  variables: ["x", "y", "z"],
  paramNames: ["sigma", "rho", "beta"],
  defaultParams: [10, 28, 2.667],
  modulatedParam: "rho",
  phaseIndices: [],
  rhs: (x, p, out) => {
    const sigma = p[0]!;
    const rho = p[1]!;
    const beta = p[2]!;
    out[0] = sigma * (x[1]! - x[0]!);
    out[1] = x[0]! * (rho - x[2]!) - x[1]!;
    out[2] = x[0]! * x[1]! - beta * x[2]!;
  },
};

const rossler: SystemDef = {
  name: "rossler",
  displayName: "Rössler",
  variables: ["x", "y", "z"],
  paramNames: ["a", "b", "c"],
  defaultParams: [0.2, 0.2, 5.7],
  modulatedParam: "c",
  phaseIndices: [],
  rhs: (x, p, out) => {
    const a = p[0]!;
    const b = p[1]!;
    const c = p[2]!;
    out[0] = -x[1]! - x[2]!;
    out[1] = x[0]! + a * x[1]!;
    out[2] = b + x[2]! * (x[0]! - c);
  },
};

const chua: SystemDef = {
  name: "chua",
  displayName: "Chua",
  variables: ["x", "y", "z"],
  paramNames: ["alpha", "beta", "m0", "m1"],
  defaultParams: [15.6, 28, -1.142857, -0.71429],
  modulatedParam: "alpha",
  phaseIndices: [],
  rhs: (x, p, out) => {
    const alpha = p[0]!;
    const beta = p[1]!;
    const m0 = p[2]!;
    const m1 = p[3]!;
    const x0 = x[0]!;
    const h = m1 * x0 + 0.5 * (m0 - m1) * (Math.abs(x0 + 1) - Math.abs(x0 - 1));
    out[0] = alpha * (x[1]! - x0 - h);
    out[1] = x0 - x[1]! + x[2]!;
    out[2] = -beta * x[1]!;
  },
};

const rikitake: SystemDef = {
  name: "rikitake",
  displayName: "Rikitake dynamo",
  variables: ["x", "y", "z"],
  paramNames: ["a", "mu"],
  defaultParams: [1, 1],
  modulatedParam: "mu",
  phaseIndices: [],
  rhs: (x, p, out) => {
    const a = p[0]!;
    const mu = p[1]!;
    out[0] = -mu * x[0]! + x[1]! * x[2]!;
    out[1] = -mu * x[1]! - a * x[0]! + x[0]! * x[2]!;
    out[2] = 1 - x[0]! * x[1]!;
  },
};

const duffing: SystemDef = {
  name: "duffing",
  displayName: "Duffing (forced)",
  variables: ["x", "y", "z"],
  paramNames: ["alpha", "beta", "delta", "gamma", "omega"],
  defaultParams: [1, -1, 0.1, 0.35, 1.4],
  modulatedParam: "gamma",
  phaseIndices: [2],
  rhs: (x, p, out) => {
    const alpha = p[0]!;
    const beta = p[1]!;
    const delta = p[2]!;
    const gamma = p[3]!;
    const omega = p[4]!;
    const x0 = x[0]!;
    out[0] = x[1]!;
    out[1] = -delta * x[1]! - beta * x0 - alpha * (x0 * x0 * x0) + gamma * Math.cos(x[2]!);
    out[2] = omega;
  },
};

/** The v1 systems, in display order (same order as the Python registry). */
export const SYSTEMS: readonly SystemDef[] = [lorenz, rossler, chua, rikitake, duffing];

const BY_NAME = new Map(SYSTEMS.map((s) => [s.name, s]));

/** The system registered under `name`; throws RangeError if unknown. */
export function getSystem(name: string): SystemDef {
  const system = BY_NAME.get(name);
  if (system === undefined) {
    throw new RangeError(
      `unknown system ${JSON.stringify(name)}; available: ${SYSTEMS.map((s) => s.name).join(", ")}`,
    );
  }
  return system;
}

/** Variables that can be heard (all except phase variables). */
export function audioVariables(system: SystemDef): string[] {
  return system.variables.filter((_, i) => !system.phaseIndices.includes(i));
}
