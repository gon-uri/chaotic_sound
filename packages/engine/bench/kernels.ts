/**
 * Benchmark: the specialized RK4 kernels (src/core/dsp/kernels.ts) against the generic
 * `renderTuned` (src/core/dsp/rk4.ts), for every system at A3 and A7, at the default knob and
 * at the worst knob (the u with the longest period P(u), hence the most sub-steps per sample).
 * It measures two levels:
 *
 * - integration: the integrator alone, on the p and Δτ a static box produces (pitch lock on),
 *   in ns per sample and per RK4 step;
 * - box: `Dynamical.process` in 128-sample quanta (everything a box does per quantum), in µs
 *   per quantum. The "generic" box is the same block with `renderTuned` swapped in.
 *
 * Both variants start from the same state and the benchmark checks that they end bit-identical.
 * Timings are wall clock, the minimum over the repeats, after a warm-up of every case.
 *
 * Usage, from the repository root:
 *   node packages/engine/bench/kernels.ts [--quick] [system ...]
 * With no system named, all of them run in one process, so the `rhs(...)` call inside
 * `renderTuned` sees five different functions (megamorphic), as in a patch that mixes
 * systems. Name a single system to measure the monomorphic case.
 */

import { cpus } from "node:os";
import { readCatalog } from "../src/adapters/node/catalog-file.ts";
import { Dynamical } from "../src/core/blocks/dynamical.ts";
import { Catalog, type CatalogEntry } from "../src/core/catalog.ts";
import { type TunedRenderer, tunedRenderer } from "../src/core/dsp/kernels.ts";
import { noteToHz } from "../src/core/dsp/pitch.ts";
import {
  MAX_SUBSTEPS,
  makeRk4Scratch,
  renderTuned,
  type TunedRenderArgs,
} from "../src/core/dsp/rk4.ts";
import { getSystem, SYSTEMS, type SystemDef } from "../src/core/dsp/systems.ts";

const FS = 48_000;
const QUANTUM = 128;
const NOTES = ["A3", "A7"] as const;

const args = process.argv.slice(2);
const QUICK = args.includes("--quick");
const names = args.filter((a) => !a.startsWith("--"));
const systems: SystemDef[] = names.length > 0 ? names.map((n) => getSystem(n)) : [...SYSTEMS];
const REPEATS = QUICK ? 3 : 7;
/** Quanta per timed run: 1 s of audio (0.25 s with --quick). */
const QUANTA = Math.round(((QUICK ? 0.25 : 1) * FS) / QUANTUM);

const catalog = new Catalog(readCatalog());

interface Case {
  readonly system: SystemDef;
  readonly entry: CatalogEntry;
  readonly note: string;
  readonly knob: "default" | "worst";
  readonly u: number;
}

/** The knob position with the longest period on the catalog grid (most sub-steps). */
function worstKnob(e: CatalogEntry): number {
  let best = 0;
  for (let j = 1; j < e.periodTable.length; j++) {
    if (e.periodTable[j]! > e.periodTable[best]!) best = j;
  }
  return e.uGrid[best]!;
}

/** Wall-clock milliseconds of one call of `f`. */
function time(f: () => void): number {
  const t0 = performance.now();
  f();
  return performance.now() - t0;
}

/** Index of the first element whose bits differ, or -1 if the arrays are bit-identical. */
function firstDiff(a: Float64Array, b: Float64Array): number {
  const ua = new BigUint64Array(a.buffer, a.byteOffset, a.length);
  const ub = new BigUint64Array(b.buffer, b.byteOffset, b.length);
  for (let i = 0; i < ua.length; i++) if (ua[i] !== ub[i]) return i;
  return -1;
}

// ---------------------------------------------------------------- integration level

interface Integration {
  readonly nSub: number;
  readonly run: (render: TunedRenderer, a: TunedRenderArgs) => void;
  readonly generic: TunedRenderArgs;
  readonly kernel: TunedRenderArgs;
}

function integration(c: Case): Integration {
  const { system, entry: e } = c;
  const dim = system.variables.length;
  const f = noteToHz(c.note);
  const d = (e.period(c.u) * f) / FS; // Δτ per sample, as Dynamical computes it
  const pValues = new Float64Array(QUANTUM).fill(e.paramValue(c.u));
  const dtau = new Float64Array(QUANTUM).fill(d);
  const make = (): TunedRenderArgs => ({
    rhs: system.rhs,
    x: Float64Array.from(e.initialCondition),
    p: Float64Array.from(system.defaultParams),
    modIndex: system.paramNames.indexOf(system.modulatedParam),
    pValues,
    dtau,
    hMax: e.hMax,
    phaseIndices: system.phaseIndices,
    lo: e.boundsLo,
    hi: e.boundsHi,
    xReset: Float64Array.from(e.initialCondition),
    out: new Float64Array(QUANTUM * dim),
    scratch: makeRk4Scratch(dim),
  });
  const generic = make();
  const kernel = make();
  const q = d / e.hMax;
  const nSub = q > 1 ? Math.min(MAX_SUBSTEPS, Math.ceil(q)) : 1;
  const run = (render: TunedRenderer, a: TunedRenderArgs): void => {
    for (let k = 0; k < QUANTA; k++) render(a, QUANTUM);
  };
  return { nSub, run, generic, kernel };
}

// ---------------------------------------------------------------- box level

interface Box {
  readonly generic: Dynamical;
  readonly kernel: Dynamical;
  readonly run: (box: Dynamical) => void;
}

function box(c: Case): Box {
  const ctx = { catalog, maxFrames: QUANTUM };
  const params = { system: c.system.name, note: c.note, param: c.u };
  const generic = new Dynamical("bench", params, ctx);
  const kernel = new Dynamical("bench", params, ctx);
  // Benchmark only: put the generic integrator back into one box (`integrate` is a private
  // field, which TypeScript hides but JavaScript does not).
  (generic as unknown as { integrate: TunedRenderer }).integrate = renderTuned;
  generic.reset(FS);
  kernel.reset(FS);
  const inputs = [null, null, null];
  const run = (b: Dynamical): void => {
    for (let k = 0; k < QUANTA; k++) b.process(QUANTUM, inputs);
  };
  return { generic, kernel, run };
}

// ---------------------------------------------------------------- main

const cases: Case[] = [];
for (const system of systems) {
  const entry = catalog.get(system.name);
  for (const note of NOTES) {
    cases.push({ system, entry, note, knob: "default", u: entry.uDefault });
    cases.push({ system, entry, note, knob: "worst", u: worstKnob(entry) });
  }
}

const integrations = cases.map(integration);
const boxes = cases.map(box);

// Warm-up: every case and variant once, so the JIT has seen all of them before timing.
for (let i = 0; i < cases.length; i++) {
  const it = integrations[i]!;
  const bx = boxes[i]!;
  const render = tunedRenderer(cases[i]!.system);
  for (let w = 0; w < 2; w++) {
    it.run(renderTuned, it.generic);
    it.run(render, it.kernel);
    bx.run(bx.generic);
    bx.run(bx.kernel);
  }
}

const samples = QUANTA * QUANTUM;
const quantumUs = (QUANTUM / FS) * 1e6;
console.log(
  `# RK4 kernels: generic renderTuned vs specialized (Node ${process.version}, V8 ${process.versions.v8}, ${cpus()[0]?.model ?? "?"})`,
);
console.log(
  `# ${systems.length === 1 ? "monomorphic (one system)" : `${systems.length} systems in one process (megamorphic renderTuned)`}; ` +
    `fs = ${FS} Hz, ${QUANTUM}-sample quanta, min of ${REPEATS} runs of ${(samples / FS).toFixed(2)} s of audio`,
);
console.log("");
console.log(
  "| System | Note | Knob | u | Sub-steps | Generic ns/sample | Kernel ns/sample | Generic ns/step | Kernel ns/step | Speed-up | Box generic µs/quantum | Box kernel µs/quantum | Box speed-up | Box kernel × real time |",
);
console.log("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|");
let mismatches = 0;
for (let i = 0; i < cases.length; i++) {
  const c = cases[i]!;
  const it = integrations[i]!;
  const bx = boxes[i]!;
  const render = tunedRenderer(c.system);
  let tg = Infinity;
  let tk = Infinity;
  let bg = Infinity;
  let bk = Infinity;
  for (let r = 0; r < REPEATS; r++) {
    // Alternate the variants so that machine load affects both alike.
    tg = Math.min(
      tg,
      time(() => it.run(renderTuned, it.generic)),
    );
    tk = Math.min(
      tk,
      time(() => it.run(render, it.kernel)),
    );
    bg = Math.min(
      bg,
      time(() => bx.run(bx.generic)),
    );
    bk = Math.min(
      bk,
      time(() => bx.run(bx.kernel)),
    );
  }
  // Same calls from the same start: the states and the last quantum must be bit-identical.
  if (
    firstDiff(it.generic.x, it.kernel.x) !== -1 ||
    firstDiff(bx.generic.outputs[0]![0]!, bx.kernel.outputs[0]![0]!) !== -1
  ) {
    mismatches++;
  }
  const nsG = (tg * 1e6) / samples;
  const nsK = (tk * 1e6) / samples;
  const usG = (bg * 1e3) / QUANTA;
  const usK = (bk * 1e3) / QUANTA;
  const row = [
    c.system.name,
    c.note,
    c.knob,
    c.u.toFixed(3),
    it.nSub,
    nsG.toFixed(0),
    nsK.toFixed(0),
    (nsG / it.nSub).toFixed(1),
    (nsK / it.nSub).toFixed(1),
    `${(nsG / nsK).toFixed(2)}×`,
    usG.toFixed(1),
    usK.toFixed(1),
    `${(usG / usK).toFixed(2)}×`,
    `${(quantumUs / usK).toFixed(0)}×`,
  ];
  console.log(`| ${row.join(" | ")} |`);
}
console.log("");
console.log(
  "ns/step = ns/sample ÷ sub-steps (it includes the per-sample work). × real time = how many such boxes one core runs.",
);
if (mismatches > 0) {
  console.log(`MISMATCH: ${mismatches} case(s) differ between the generic and the kernel path`);
  process.exitCode = 1;
}
