/**
 * Dynamical block: a chaotic ODE tuned to a musical note (spec §4.2, ADR 0006, ADR 0013).
 * Mirrors `lab/src/chaotic_sound/blocks/dynamical.py` operation by operation.
 *
 * Per sample: smooth the controls, turn the pitch into a frequency f, map the knob u to the
 * system parameter, set the time scale k = P(u)·f, advance the ODE by k/fs with RK4
 * sub-steps, and turn the heard variable into level-normalized audio.
 */

import type { CatalogEntry } from "../catalog.ts";
import {
  dcBlock,
  dcBlockCoefficient,
  onePole,
  onePoleCoefficient,
  onePoleVarying,
} from "../dsp/filters.ts";
import { midiToHz, NOTE_MAX, NOTE_MIN, noteToHz, noteToMidi } from "../dsp/pitch.ts";
import { makeRk4Scratch, type Rk4Scratch, renderTuned } from "../dsp/rk4.ts";
import { Mulberry32, stableSeed } from "../dsp/rng.ts";
import { audioVariables, getSystem, type SystemDef } from "../dsp/systems.ts";
import { BLOCK_SPECS, type ParamValue, PatchError } from "../patch.ts";
import type { BlockContext, BlockRuntime, PortSignal } from "./block.ts";

/** RMS of a dynamical block at amp = 1 (≈ −12 dBFS). */
export const RMS_TARGET = 0.25;
/** Robust peak (99.9th percentile) a block may reach at amp = 1. */
export const PEAK_TARGET = 0.8;
export const DECLICK_TIME_S = 0.005;
/** The parameter smoother is at least this many oscillation periods slow. */
export const PARAM_SLEW_PERIODS = 2;
export const DC_BLOCK_HZ = 5;
export const IC_PERTURBATION = 1e-6;
/** Perceptual amp curve: g = a^(1/(2·log10 2)), so each halving of a is −10 dB. */
export const AMP_EXPONENT = 1 / (2 * Math.log10(2));

function blockError(id: string, msg: string): PatchError {
  return new PatchError(`dynamical '${id}': ${msg}`);
}

export class Dynamical implements BlockRuntime {
  readonly type = "dynamical" as const;
  readonly spec = BLOCK_SPECS.dynamical;
  readonly outputs: readonly PortSignal[];
  readonly id: string;
  readonly system: SystemDef;
  readonly entry: CatalogEntry;
  readonly observable: string;
  readonly observableRight: string | null;
  readonly knobParam: number;
  readonly knobAmp: number;
  readonly frequencyHz: number;
  readonly pitchLock: boolean;
  readonly perceptual: boolean;
  readonly seed: number;
  private readonly midiMin: number;
  private readonly midiMax: number;
  private readonly obsIndex: number;
  private readonly rightIndex: number;
  private readonly modIndex: number;
  private readonly dim: number;

  // State (reset() restores it)
  private sampleRate = 48_000;
  private readonly x: Float64Array;
  private readonly xReset: Float64Array;
  private readonly p: Float64Array;
  private readonly uState = new Float64Array(1);
  private readonly qState = new Float64Array(1);
  private readonly aState = new Float64Array(1);
  private readonly dcLeft = new Float64Array(2);
  private readonly dcRight = new Float64Array(2);
  private uInit = false;
  private qInit = false;
  private alpha = 0;
  private dcR = 0;
  private periodUnlocked = 0;
  private resets = 0;

  // Preallocated work buffers (length maxFrames)
  private readonly freq: Float64Array;
  private readonly qs: Float64Array;
  private readonly uRaw: Float64Array;
  private readonly u: Float64Array;
  private readonly alphaU: Float64Array;
  private readonly aRaw: Float64Array;
  private readonly a: Float64Array;
  private readonly pValues: Float64Array;
  private readonly dtau: Float64Array;
  private readonly traj: Float64Array;
  private readonly yLeft: Float64Array;
  private readonly yRight: Float64Array;
  private readonly left: Float64Array;
  private readonly right: Float64Array;
  private readonly scratch: Rk4Scratch;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    let system: SystemDef;
    try {
      system = getSystem((params.system ?? "rossler") as string);
    } catch (e) {
      throw blockError(id, (e as Error).message);
    }
    this.system = system;
    let entry: CatalogEntry;
    try {
      entry = ctx.catalog.get(system.name);
      entry.checkAgainst(system);
    } catch (e) {
      throw blockError(id, (e as Error).message);
    }
    this.entry = entry;
    const note = (params.note ?? "A3") as string;
    const pitchMin = (params.pitch_min ?? "A1") as string;
    const pitchMax = (params.pitch_max ?? "A5") as string;
    const midi = (name: string, value: string): number => {
      let m: number;
      try {
        m = noteToMidi(value);
      } catch (e) {
        throw blockError(id, (e as Error).message);
      }
      if (m < NOTE_MIN || m > NOTE_MAX) {
        throw blockError(id, `${name} must be between C0 and C8, got ${value}`);
      }
      return m;
    };
    midi("note", note);
    this.midiMin = midi("pitch_min", pitchMin);
    this.midiMax = midi("pitch_max", pitchMax);
    if (this.midiMin >= this.midiMax)
      throw blockError(id, "pitch_min must be lower than pitch_max");
    const audio = audioVariables(system);
    const obs = (params.observable ?? entry.defaultObservable) as string;
    const right = (params.observable_right ?? null) as string | null;
    for (const [name, v] of [
      ["observable", obs],
      ["observable_right", right],
    ] as const) {
      if (v !== null && !audio.includes(v)) {
        throw blockError(
          id,
          `${name} ${v} is not an audible variable of ${system.name}: ${audio.join(", ")}`,
        );
      }
    }
    this.observable = obs;
    this.observableRight = right;
    this.obsIndex = system.variables.indexOf(obs);
    this.rightIndex = right === null ? -1 : system.variables.indexOf(right);
    this.knobParam = params.param === undefined ? entry.uDefault : (params.param as number);
    this.knobAmp = (params.amp ?? 1) as number;
    this.frequencyHz = noteToHz(note, (params.cents ?? 0) as number);
    this.pitchLock = (params.pitch_lock ?? true) as boolean;
    this.perceptual = (params.amp_curve ?? "perceptual") === "perceptual";
    this.seed = params.seed === undefined ? stableSeed(id) : (params.seed as number);
    this.modIndex = system.paramNames.indexOf(system.modulatedParam);
    this.dim = system.variables.length;

    this.x = new Float64Array(this.dim);
    this.xReset = new Float64Array(this.dim);
    this.p = Float64Array.from(system.defaultParams);
    const m = ctx.maxFrames;
    this.freq = new Float64Array(m);
    this.qs = new Float64Array(m);
    this.uRaw = new Float64Array(m);
    this.u = new Float64Array(m);
    this.alphaU = new Float64Array(m);
    this.aRaw = new Float64Array(m);
    this.a = new Float64Array(m);
    this.pValues = new Float64Array(m);
    this.dtau = new Float64Array(m);
    this.traj = new Float64Array(m * this.dim);
    this.yLeft = new Float64Array(m);
    this.yRight = new Float64Array(m);
    this.left = new Float64Array(m);
    this.right = new Float64Array(m);
    this.scratch = makeRk4Scratch(this.dim);
    this.outputs = [[this.left, this.right]];
  }

  /** Catalog initial condition plus the seeded perturbation (spec §4.2 step 9). */
  initialState(): Float64Array {
    const e = this.entry;
    const rng = new Mulberry32(this.seed);
    const x = Float64Array.from(e.initialCondition);
    for (let j = 0; j < this.dim; j++) {
      const name = this.system.variables[j]!;
      const scale = this.system.phaseIndices.includes(j) ? 1 : e.std(name, e.uDefault);
      x[j] = x[j]! + IC_PERTURBATION * scale * rng.normal();
    }
    return x;
  }

  reset(sampleRate: number): void {
    const highest = Math.max(this.frequencyHz, midiToHz(this.midiMax));
    if (!(highest < sampleRate / 2)) {
      throw new PatchError(
        `dynamical '${this.id}': ${highest.toFixed(1)} Hz is not below ${sampleRate / 2} Hz`,
      );
    }
    this.sampleRate = sampleRate;
    this.x.set(this.initialState());
    this.xReset.set(this.x);
    this.p.set(this.system.defaultParams);
    this.alpha = onePoleCoefficient(DECLICK_TIME_S, sampleRate);
    this.uInit = false;
    this.qInit = false;
    this.aState[0] = 0; // amp starts at 0: every box fades in over a few ms
    this.dcR = dcBlockCoefficient(DC_BLOCK_HZ, sampleRate);
    this.dcLeft.fill(0);
    this.dcRight.fill(0);
    this.periodUnlocked = this.entry.period(this.entry.uDefault);
    this.resets = 0;
  }

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    if (n === 0) return;
    const e = this.entry;
    const fs = this.sampleRate;
    const uIn = inputs[0]?.[0] ?? null;
    const aIn = inputs[1]?.[0] ?? null;
    const qIn = inputs[2]?.[0] ?? null;

    // 1. Frequency: the note, or the smoothed pitch input mapped A1..A5 (spec §4.2 step 1).
    if (qIn === null) {
      this.freq.fill(this.frequencyHz, 0, n);
    } else {
      if (!this.qInit) {
        this.qState[0] = qIn[0]!;
        this.qInit = true;
      }
      onePole(qIn, this.qState, this.alpha, this.qs, n);
      for (let i = 0; i < n; i++) {
        const midi = this.midiMin + this.qs[i]! * (this.midiMax - this.midiMin);
        this.freq[i] = 440 * 2 ** ((midi - 69) / 12);
      }
    }

    // 2. Controls: the parameter slew is at least 5 ms and 2 periods (ADR 0013).
    const uRaw = uIn ?? this.uRaw.fill(this.knobParam, 0, n);
    const aRaw = aIn ?? this.aRaw.fill(this.knobAmp, 0, n);
    if (!this.uInit) {
      this.uState[0] = uRaw[0]!;
      this.uInit = true;
    }
    for (let i = 0; i < n; i++) {
      const tau = Math.max(DECLICK_TIME_S, PARAM_SLEW_PERIODS / this.freq[i]!);
      this.alphaU[i] = 1 - Math.exp(-1 / (tau * fs));
    }
    onePoleVarying(uRaw, this.uState, this.alphaU, this.u, n);
    onePole(aRaw, this.aState, this.alpha, this.a, n);

    // 3–5. Parameter and time scale.
    for (let i = 0; i < n; i++) {
      const u = this.u[i]!;
      this.pValues[i] = e.paramValue(u);
      const period = this.pitchLock ? e.period(u) : this.periodUnlocked;
      this.dtau[i] = (period * this.freq[i]!) / fs;
    }

    // 6. Integrate.
    this.resets += renderTuned(
      {
        rhs: this.system.rhs,
        x: this.x,
        p: this.p,
        modIndex: this.modIndex,
        pValues: this.pValues,
        dtau: this.dtau,
        hMax: e.hMax,
        phaseIndices: this.system.phaseIndices,
        lo: e.boundsLo,
        hi: e.boundsHi,
        xReset: this.xReset,
        out: this.traj,
        scratch: this.scratch,
      },
      n,
    );

    // 7. Audio, then the DC blocker.
    this.audio(this.observable, this.obsIndex, this.yLeft, n);
    dcBlock(this.yLeft, this.dcLeft, this.dcR, this.left, n);
    if (this.observableRight === null) {
      dcBlock(this.yLeft, this.dcRight, this.dcR, this.right, n);
    } else {
      this.audio(this.observableRight, this.rightIndex, this.yRight, n);
      dcBlock(this.yRight, this.dcRight, this.dcR, this.right, n);
    }
  }

  /** y = g · min(0.25/σ, 0.8/π) · (x_obs − μ), with g from the amp curve (spec §4.2 step 7). */
  private audio(observable: string, index: number, y: Float64Array, n: number): void {
    const e = this.entry;
    const dim = this.dim;
    for (let i = 0; i < n; i++) {
      const u = this.u[i]!;
      const a = this.a[i]!;
      const gain = this.perceptual ? a ** AMP_EXPONENT : a;
      const scale = Math.min(
        RMS_TARGET / e.std(observable, u),
        PEAK_TARGET / e.peak(observable, u),
      );
      y[i] = gain * scale * (this.traj[i * dim + index]! - e.mean(observable, u));
    }
  }

  diagnostics(): Record<string, number> {
    return { safety_resets: this.resets };
  }
}
