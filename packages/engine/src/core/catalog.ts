/**
 * The system catalog (`catalog/systems.json`, format version 2): typed access and
 * interpolation. Mirrors `lab/src/chaotic_sound/catalog.py`.
 *
 * The catalog arrives as plain data (parsed JSON). Reading the file is an adapter's job
 * (ADR 0011); this module never touches the file system or the network.
 */

import { audioVariables, type SystemDef } from "./dsp/systems.ts";

export const CATALOG_FORMAT = "chaotic-sound-catalog";
export const CATALOG_VERSION = 2;

/** JSON shape of one observable's tables. */
export interface ObservableJson {
  mean: number[];
  std: number[];
  peak: number[];
  prominence: number[];
}

/** JSON shape of one system entry. */
export interface EntryJson {
  param: string;
  p_min: number;
  p_max: number;
  p_default: number;
  p_reference: number;
  u_default: number;
  u_grid: number[];
  period: number[];
  period_method: "peak_centroid" | "return_time" | "drive";
  period_observable: string;
  default_observable: string;
  observables: Record<string, ObservableJson>;
  h_max: number;
  steps_per_period: number;
  bounds: { lo: number[]; hi: number[] };
  initial_condition: number[];
  info?: Record<string, unknown>;
}

/** JSON shape of the whole catalog document. */
export interface CatalogDocument {
  format: string;
  catalog_version: number;
  metadata?: Record<string, unknown>;
  systems: Record<string, EntryJson>;
}

export class CatalogError extends Error {
  override name = "CatalogError";
}

/**
 * NumPy's `interp` for a strictly increasing grid: clamped at both ends, linear inside,
 * using the same arithmetic order (slope·(x − x_j) + y_j) so results match the reference.
 */
export function interp(x: number, xp: Float64Array, fp: Float64Array): number {
  const last = xp.length - 1;
  if (!(x > xp[0]!)) return fp[0]!; // also catches NaN, like clip-then-interp would
  if (x >= xp[last]!) return fp[last]!;
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xp[mid]! <= x) lo = mid;
    else hi = mid;
  }
  if (xp[lo] === x) return fp[lo]!;
  const slope = (fp[lo + 1]! - fp[lo]!) / (xp[lo + 1]! - xp[lo]!);
  return slope * (x - xp[lo]!) + fp[lo]!;
}

/**
 * `out[i] = interp(clip(u[i], 0, 1), xp, fp)` for i < n, with exactly interp's arithmetic.
 * One call per chunk instead of one per sample keeps the audio loop free of boxed numbers.
 */
export function interpInto(
  u: Float64Array,
  xp: Float64Array,
  fp: Float64Array,
  out: Float64Array,
  n: number,
): void {
  const last = xp.length - 1;
  for (let i = 0; i < n; i++) {
    const v = u[i]!;
    const x = v < 0 ? 0 : v > 1 ? 1 : v;
    if (!(x > xp[0]!)) {
      out[i] = fp[0]!;
      continue;
    }
    if (x >= xp[last]!) {
      out[i] = fp[last]!;
      continue;
    }
    let lo = 0;
    let hi = last;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (xp[mid]! <= x) lo = mid;
      else hi = mid;
    }
    if (xp[lo] === x) {
      out[i] = fp[lo]!;
      continue;
    }
    const slope = (fp[lo + 1]! - fp[lo]!) / (xp[lo + 1]! - xp[lo]!);
    out[i] = slope * (x - xp[lo]!) + fp[lo]!;
  }
}

function clip01(u: number): number {
  return u < 0 ? 0 : u > 1 ? 1 : u;
}

/** Tables of one audible variable. */
export interface ObservableTable {
  readonly mean: Float64Array;
  readonly std: Float64Array;
  readonly peak: Float64Array;
  readonly prominence: Float64Array;
}

/** Everything an engine needs to run one system (spec §4.2, §7). */
export class CatalogEntry {
  readonly name: string;
  readonly param: string;
  readonly pMin: number;
  readonly pMax: number;
  readonly pDefault: number;
  readonly pReference: number;
  readonly uGrid: Float64Array;
  readonly periodTable: Float64Array;
  readonly periodMethod: EntryJson["period_method"];
  readonly periodObservable: string;
  readonly defaultObservable: string;
  readonly observables: ReadonlyMap<string, ObservableTable>;
  readonly hMax: number;
  readonly stepsPerPeriod: number;
  readonly boundsLo: Float64Array;
  readonly boundsHi: Float64Array;
  readonly initialCondition: Float64Array;

  constructor(name: string, e: EntryJson) {
    this.name = name;
    this.param = e.param;
    this.pMin = e.p_min;
    this.pMax = e.p_max;
    this.pDefault = e.p_default;
    this.pReference = e.p_reference;
    this.uGrid = Float64Array.from(e.u_grid);
    this.periodTable = Float64Array.from(e.period);
    this.periodMethod = e.period_method;
    this.periodObservable = e.period_observable;
    this.defaultObservable = e.default_observable;
    this.observables = new Map(
      Object.entries(e.observables).map(([k, t]) => [
        k,
        {
          mean: Float64Array.from(t.mean),
          std: Float64Array.from(t.std),
          peak: Float64Array.from(t.peak),
          prominence: Float64Array.from(t.prominence),
        },
      ]),
    );
    this.hMax = e.h_max;
    this.stepsPerPeriod = e.steps_per_period;
    this.boundsLo = Float64Array.from(e.bounds.lo);
    this.boundsHi = Float64Array.from(e.bounds.hi);
    this.initialCondition = Float64Array.from(e.initial_condition);
  }

  /** Knob position of the default parameter value (same formula as the reference). */
  get uDefault(): number {
    return (this.pDefault - this.pMin) / (this.pMax - this.pMin);
  }

  /** p = p_min + clip(u)·(p_max − p_min) (spec §4.2 step 4). */
  paramValue(u: number): number {
    return this.pMin + clip01(u) * (this.pMax - this.pMin);
  }

  /** P(u): the system's characteristic period, linear in u (system time). */
  period(u: number): number {
    return interp(clip01(u), this.uGrid, this.periodTable);
  }

  /** The tables of one audible variable (look them up once, outside per-sample loops). */
  tables(observable: string): ObservableTable {
    const t = this.observables.get(observable);
    if (t === undefined) throw new CatalogError(`${this.name} has no tables for ${observable}`);
    return t;
  }

  /** Value of a table on `u_grid` at knob position u (clipped to [0, 1]). */
  at(table: Float64Array, u: number): number {
    return interp(clip01(u), this.uGrid, table);
  }

  /** μ(u): mean of `observable`. */
  mean(observable: string, u: number): number {
    return this.at(this.tables(observable).mean, u);
  }

  /** σ(u): standard deviation of `observable`. */
  std(observable: string, u: number): number {
    return this.at(this.tables(observable).std, u);
  }

  /** π(u): robust peak (99.9th percentile of |x − μ|) of `observable`. */
  peak(observable: string, u: number): number {
    return this.at(this.tables(observable).peak, u);
  }

  /** Throw if this entry does not fit `system` (dimensions, parameter, observables, grid). */
  checkAgainst(system: SystemDef): void {
    const problems: string[] = [];
    const dim = system.variables.length;
    for (const [label, arr] of [
      ["bounds.lo", this.boundsLo],
      ["bounds.hi", this.boundsHi],
      ["initial_condition", this.initialCondition],
    ] as const) {
      if (arr.length !== dim) problems.push(`${label} has length ${arr.length}, expected ${dim}`);
    }
    if (this.param !== system.modulatedParam) {
      problems.push(`param ${this.param} != ${system.modulatedParam}`);
    }
    const audio = audioVariables(system);
    const have = [...this.observables.keys()].sort().join(",");
    if (have !== [...audio].sort().join(",")) problems.push(`observables ${have} != ${audio}`);
    const g = this.uGrid;
    let increasing = g.length >= 2 && g[0] === 0 && g[g.length - 1] === 1;
    for (let i = 1; i < g.length && increasing; i++) increasing = g[i]! > g[i - 1]!;
    if (!increasing) problems.push("u_grid must increase strictly from 0 to 1");
    if (!this.observables.has(this.defaultObservable)) {
      problems.push(`default observable ${this.defaultObservable} has no table`);
    }
    const tables = [this.periodTable];
    for (const t of this.observables.values()) tables.push(t.mean, t.std, t.peak, t.prominence);
    if (tables.some((t) => t.length !== g.length)) problems.push("a table does not match u_grid");
    // Level normalization divides by σ and π: they must be finite and positive.
    for (const [name, t] of this.observables) {
      const ok = (a: Float64Array, positive: boolean): boolean =>
        a.every((v) => Number.isFinite(v) && (!positive || v > 0));
      if (!(ok(t.mean, false) && ok(t.std, true) && ok(t.peak, true))) {
        problems.push(`tables of ${name} must be finite, with std and peak > 0`);
      }
    }
    if (!this.periodTable.every((v) => Number.isFinite(v) && v > 0)) {
      problems.push("period table must be finite and positive");
    }
    if (!(this.pMin < this.pMax && this.pMin <= this.pDefault && this.pDefault <= this.pMax)) {
      problems.push("p_min < p_max and p_min ≤ p_default ≤ p_max are required");
    }
    if (problems.length > 0) {
      throw new CatalogError(`catalog entry ${this.name}: ${problems.join("; ")}`);
    }
  }
}

/** A parsed catalog: entries by system name. */
export class Catalog {
  readonly entries: ReadonlyMap<string, CatalogEntry>;
  readonly metadata: Readonly<Record<string, unknown>>;

  constructor(doc: CatalogDocument) {
    if (doc === null || typeof doc !== "object" || doc.format !== CATALOG_FORMAT) {
      throw new CatalogError("not a chaotic_sound catalog");
    }
    if (doc.catalog_version !== CATALOG_VERSION) {
      throw new CatalogError(
        `catalog version ${doc.catalog_version} unsupported (expected ${CATALOG_VERSION})`,
      );
    }
    this.entries = new Map(
      Object.entries(doc.systems).map(([k, e]) => [k, new CatalogEntry(k, e)]),
    );
    this.metadata = doc.metadata ?? {};
  }

  get(name: string): CatalogEntry {
    const e = this.entries.get(name);
    if (e === undefined)
      throw new CatalogError(`system ${JSON.stringify(name)} is not in the catalog`);
    return e;
  }
}
