/**
 * Dynamical block: a chaotic ODE tuned to a musical note (spec §4.2, ADR 0006, ADR 0013).
 * Mirrors `lab/src/chaotic_sound/blocks/dynamical.py` operation by operation.
 *
 * Per sample: smooth the controls, turn the pitch into a frequency f, map the knob u to the
 * system parameter, set the time scale k = P(u)·f, advance the ODE by k/fs with RK4
 * sub-steps, turn the heard variable into a level-normalized signal, make it more harmonic
 * by the tonality amount (harmonic resynthesis, ADR 0015), and apply the amp curve.
 */

import type { CatalogEntry, ObservableTable } from "../catalog.ts";
import {
  dcBlock,
  dcBlockCoefficient,
  Glide,
  onePole,
  onePoleCoefficient,
  onePoleVarying,
} from "../dsp/filters.ts";
import { type TunedRenderer, tunedRenderer } from "../dsp/kernels.ts";
import { midiToHz, NOTE_MAX, NOTE_MIN, noteToHz, noteToMidi } from "../dsp/pitch.ts";
import { makeRk4Scratch, type TunedRenderArgs } from "../dsp/rk4.ts";
import { Mulberry32, stableSeed } from "../dsp/rng.ts";
import { audioVariables, getSystem, type SystemDef } from "../dsp/systems.ts";
import { TonalChannel, tonal } from "../dsp/tonal.ts";
import { BLOCK_SPECS, defaultParam, type ParamValue, PatchError, withDefaults } from "../patch.ts";
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

/** True if every value is finite (their sum is finite; cheap enough once per chunk). */
function finiteSum(a: Float64Array): boolean {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i]!;
  return Number.isFinite(s);
}

/** Documented default of a dynamical parameter (BLOCK_SPECS). */
const def = (name: string): ParamValue | undefined => defaultParam("dynamical", name);

function blockError(id: string, msg: string): PatchError {
  return new PatchError(`dynamical '${id}': ${msg}`);
}

/** MIDI number of a note setting, restricted to C0 … C8 (spec §4.2). */
function noteToMidiChecked(id: string, name: string, value: string): number {
  let m: number;
  try {
    m = noteToMidi(value);
  } catch (e) {
    throw blockError(id, (e as Error).message);
  }
  if (m < NOTE_MIN || m > NOTE_MAX)
    throw blockError(id, `${name} must be between C0 and C8, got ${value}`);
  return m;
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
  // Live-editable settings (see setParam): knobs and pitch settings change without a reset.
  knobParam: number;
  knobAmp: number;
  knobTonality: number;
  frequencyHz: number;
  pitchLock: boolean;
  perceptual: boolean;
  private note: string;
  private cents: number;
  readonly seed: number;
  /** Gain law: 1 = perceptual, 0 = linear; glides after a live change (spec §6). */
  private readonly curve: Glide;
  /** Tables of the heard variables, looked up once (no map lookups per sample). */
  private readonly tableLeft: ObservableTable;
  private readonly tableRight: ObservableTable;
  private midiMin: number;
  private midiMax: number;
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
  private readonly tState = new Float64Array(1);
  private readonly tonalLeft = new TonalChannel();
  private readonly tonalRight = new TonalChannel();
  private readonly dcLeft = new Float64Array(2);
  private readonly dcRight = new Float64Array(2);
  private uInit = false;
  private qInit = false;
  private tInit = false;
  private tonalWasOn = false;
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
  /** Per-sample gain g(a) from the amp curve. */
  private readonly g: Float64Array;
  private readonly tRaw: Float64Array;
  /** Smoothed tonality τ_s and the fundamental actually heard f_a, per sample. */
  private readonly tau: Float64Array;
  private readonly fA: Float64Array;
  /** Level-normalized signals r (step 7) before the tonality mix. */
  private readonly rLeft: Float64Array;
  private readonly rRight: Float64Array;
  private readonly pValues: Float64Array;
  private readonly dtau: Float64Array;
  private readonly traj: Float64Array;
  private readonly yLeft: Float64Array;
  private readonly yRight: Float64Array;
  private readonly left: Float64Array;
  private readonly right: Float64Array;
  /** Arguments of the RK4 kernel, built once so process() allocates nothing. */
  private readonly rk4: TunedRenderArgs;
  /** The RK4 kernel: this system's specialized one (dsp/kernels.ts), same result as renderTuned. */
  private readonly integrate: TunedRenderer;

  constructor(id: string, given: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    const params = withDefaults("dynamical", given); // documented defaults (spec §4.2)
    let system: SystemDef;
    try {
      system = getSystem(params.system as string);
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
    const note = params.note as string;
    const pitchMin = params.pitch_min as string;
    const pitchMax = params.pitch_max as string;
    const midi = (name: string, value: string): number => noteToMidiChecked(id, name, value);
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
    this.knobAmp = params.amp as number;
    this.knobTonality = params.tonality as number;
    this.note = note;
    this.cents = params.cents as number;
    this.frequencyHz = noteToHz(note, this.cents);
    this.pitchLock = params.pitch_lock as boolean;
    this.perceptual = params.amp_curve === "perceptual";
    this.curve = new Glide(this.perceptual ? 1 : 0);
    this.tableLeft = entry.tables(obs);
    this.tableRight = right === null ? this.tableLeft : entry.tables(right);
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
    this.g = new Float64Array(m);
    this.tRaw = new Float64Array(m);
    this.tau = new Float64Array(m);
    this.fA = new Float64Array(m);
    this.rLeft = new Float64Array(m);
    this.rRight = new Float64Array(m);
    this.pValues = new Float64Array(m);
    this.dtau = new Float64Array(m);
    this.traj = new Float64Array(m * this.dim);
    this.yLeft = new Float64Array(m);
    this.yRight = new Float64Array(m);
    this.left = new Float64Array(m);
    this.right = new Float64Array(m);
    this.outputs = [[this.left, this.right]];
    this.rk4 = {
      rhs: system.rhs,
      x: this.x,
      p: this.p,
      modIndex: this.modIndex,
      pValues: this.pValues,
      dtau: this.dtau,
      hMax: entry.hMax,
      phaseIndices: system.phaseIndices,
      lo: entry.boundsLo,
      hi: entry.boundsHi,
      xReset: this.xReset,
      out: this.traj,
      scratch: makeRk4Scratch(this.dim),
    };
    this.integrate = tunedRenderer(system);
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
    this.curve.reset(DECLICK_TIME_S, sampleRate);
    this.uInit = false;
    this.qInit = false;
    this.tInit = false;
    this.tonalWasOn = false;
    this.tonalLeft.reset();
    this.tonalRight.reset();
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
    const tIn = inputs[3]?.[0] ?? null;

    // 1. Frequency: the note, or the smoothed pitch input mapped A1..A5 (spec §4.2 step 1).
    if (qIn === null) {
      this.freq.fill(this.frequencyHz, 0, n);
      this.qInit = false; // a pitch cable connected later starts from its own first value
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
    if (qIn === null) {
      // Fixed pitch: the same coefficient for the whole chunk (bit-identical, one exp).
      const tau = Math.max(DECLICK_TIME_S, PARAM_SLEW_PERIODS / this.frequencyHz);
      this.alphaU.fill(1 - Math.exp(-1 / (tau * fs)), 0, n);
    } else {
      for (let i = 0; i < n; i++) {
        const tau = Math.max(DECLICK_TIME_S, PARAM_SLEW_PERIODS / this.freq[i]!);
        this.alphaU[i] = 1 - Math.exp(-1 / (tau * fs));
      }
    }
    onePoleVarying(uRaw, this.uState, this.alphaU, this.u, n);
    onePole(aRaw, this.aState, this.alpha, this.a, n);
    this.gains(n);

    // 3–5. Parameter and time scale.
    for (let i = 0; i < n; i++) {
      const u = this.u[i]!;
      this.pValues[i] = e.paramValue(u);
      const period = this.pitchLock ? e.period(u) : this.periodUnlocked;
      this.dtau[i] = (period * this.freq[i]!) / fs;
    }

    // 6. Integrate.
    this.resets += this.integrate(this.rk4, n);

    // 7. Level-normalized signal, tonality mix, amp curve, then the DC blocker.
    const tRaw = tIn ?? this.tRaw.fill(this.knobTonality, 0, n);
    if (!this.tInit) {
      this.tState[0] = tRaw[0]!;
      this.tInit = true;
    }
    // Skip the step only while the knob is 0, no cable is connected and τ_s is 0 (decided
    // at the chunk start, so a glide to 0 finishes before the step switches off).
    const tonalOn = tIn !== null || this.knobTonality > 0 || this.tState[0] !== 0;
    if (tonalOn && !this.tonalWasOn) {
      this.tonalLeft.reset(); // turning tonality on again starts from the reset value
      this.tonalRight.reset();
    }
    this.tonalWasOn = tonalOn;
    onePole(tRaw, this.tState, this.alpha, this.tau, n);
    if (tonalOn) {
      for (let i = 0; i < n; i++) {
        // The fundamental actually heard: f with pitch lock, f·P(u_default)/P(u) without.
        this.fA[i] = this.pitchLock
          ? this.freq[i]!
          : (this.freq[i]! * this.periodUnlocked) / e.period(this.u[i]!);
      }
    }
    this.normalized(this.tableLeft, this.obsIndex, this.rLeft, n);
    this.mix(this.rLeft, this.tonalLeft, tonalOn, this.yLeft, n);
    dcBlock(this.yLeft, this.dcLeft, this.dcR, this.left, n);
    if (this.observableRight === null) {
      dcBlock(this.yLeft, this.dcRight, this.dcR, this.right, n);
    } else {
      this.normalized(this.tableRight, this.rightIndex, this.rRight, n);
      this.mix(this.rRight, this.tonalRight, tonalOn, this.yRight, n);
      dcBlock(this.yRight, this.dcRight, this.dcR, this.right, n);
    }
    // Defense in depth: a non-finite sample would stay in the DC blocker's memory forever.
    const dc = this.dcLeft[0]! + this.dcLeft[1]! + this.dcRight[0]! + this.dcRight[1]!;
    if (!Number.isFinite(dc)) {
      this.dcLeft.fill(0);
      this.dcRight.fill(0);
      this.resets++;
    }
    // Same for each channel's tonal band statistics (spec §4.2 step 8).
    if (!finiteSum(this.tonalLeft.bands)) {
      this.tonalLeft.reset();
      this.resets++;
    }
    if (!finiteSum(this.tonalRight.bands)) {
      this.tonalRight.reset();
      this.resets++;
    }
  }

  /** g(a) per sample: a^1.661 (perceptual), a (linear), or a blend while the law glides. */
  private gains(n: number): void {
    const curve = this.curve;
    for (let i = 0; i < n; i++) {
      const a = this.a[i]!;
      const m = curve.next();
      this.g[i] = m === 1 ? a ** AMP_EXPONENT : m === 0 ? a : m * a ** AMP_EXPONENT + (1 - m) * a;
    }
  }

  /** r = min(0.25/σ, 0.8/π) · (x_obs − μ) (spec §4.2 step 7). */
  private normalized(t: ObservableTable, index: number, r: Float64Array, n: number): void {
    const e = this.entry;
    const dim = this.dim;
    for (let i = 0; i < n; i++) {
      const u = this.u[i]!;
      const scale = Math.min(RMS_TARGET / e.at(t.std, u), PEAK_TARGET / e.at(t.peak, u));
      r[i] = scale * (this.traj[i * dim + index]! - e.at(t.mean, u));
    }
  }

  /** y = g · m, with m the tonality mix of r (or r itself when tonality is off). */
  private mix(r: Float64Array, ch: TonalChannel, on: boolean, y: Float64Array, n: number): void {
    if (on) {
      tonal(r, this.fA, this.tau, this.sampleRate, ch, y, n); // y ← m
      for (let i = 0; i < n; i++) y[i] = this.g[i]! * y[i]!;
    } else {
      for (let i = 0; i < n; i++) y[i] = this.g[i]! * r[i]!;
    }
  }

  /**
   * Change a setting live, keeping the oscillator's state (the declick smoothers make the
   * change gentle). Returns false for settings that need a new block (system, observables,
   * seed). `value === undefined` restores the default. Throws PatchError on invalid values.
   */
  setParam(name: string, value: ParamValue | undefined): boolean {
    switch (name) {
      case "param":
        this.knobParam = value === undefined ? this.entry.uDefault : (value as number);
        return true;
      case "amp":
        this.knobAmp = (value ?? def("amp")) as number;
        return true;
      case "tonality":
        this.knobTonality = (value ?? def("tonality")) as number; // smoothed like amp
        return true;
      case "pitch_lock":
        this.pitchLock = (value ?? def("pitch_lock")) as boolean;
        return true;
      case "amp_curve":
        this.perceptual = (value ?? def("amp_curve")) === "perceptual";
        this.curve.target = this.perceptual ? 1 : 0; // glides over the declick time
        return true;
      case "note":
      case "cents": {
        const note = name === "note" ? ((value ?? def("note")) as string) : this.note;
        const cents = name === "cents" ? ((value ?? def("cents")) as number) : this.cents;
        noteToMidiChecked(this.id, "note", note); // validates the name and the C0–C8 range
        const f = noteToHz(note, cents);
        if (!(f < this.sampleRate / 2))
          throw blockError(this.id, `${f.toFixed(1)} Hz is not below Nyquist`);
        this.note = note;
        this.cents = cents;
        this.frequencyHz = f;
        return true;
      }
      case "pitch_min":
      case "pitch_max": {
        const lo =
          name === "pitch_min"
            ? noteToMidiChecked(this.id, name, (value ?? def("pitch_min")) as string)
            : this.midiMin;
        const hi =
          name === "pitch_max"
            ? noteToMidiChecked(this.id, name, (value ?? def("pitch_max")) as string)
            : this.midiMax;
        if (lo >= hi) throw blockError(this.id, "pitch_min must be lower than pitch_max");
        if (!(midiToHz(hi) < this.sampleRate / 2))
          throw blockError(this.id, "pitch_max is not below Nyquist");
        this.midiMin = lo;
        this.midiMax = hi;
        return true;
      }
      default:
        return false;
    }
  }

  diagnostics(): Record<string, number> {
    return { safety_resets: this.resets };
  }
}
