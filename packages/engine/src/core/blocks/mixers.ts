/**
 * Sum (audio), Control Sum and Output blocks (spec §4.3–4.5).
 *
 * Their knob (gain, volume) can change live (spec §6). A change glides over the declick time
 * so it does not click; while the knob is steady its value multiplies exactly, as in the
 * reference engine.
 */

import { Glide, softClip } from "../dsp/filters.ts";
import { BLOCK_SPECS, defaultParam, type ParamValue } from "../patch.ts";
import type { BlockContext, BlockRuntime, PortSignal } from "./block.ts";
import { DECLICK_TIME_S } from "./dynamical.ts";

/** A block's single knob as a gliding setting (`undefined` → its documented default). */
function knob(type: "sum" | "control_sum" | "output", name: string, value: ParamValue | undefined) {
  return (value ?? defaultParam(type, name)) as number;
}

/** Audio mixer: out = gain · Σ inputs (the graph already added the cables). */
export class Sum implements BlockRuntime {
  readonly type = "sum" as const;
  readonly spec = BLOCK_SPECS.sum;
  readonly outputs: readonly PortSignal[];
  readonly id: string;
  private readonly gain: Glide;
  private readonly left: Float64Array;
  private readonly right: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.gain = new Glide(knob("sum", "gain", params.gain));
    this.left = new Float64Array(ctx.maxFrames);
    this.right = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.left, this.right]];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "gain") return false;
    this.gain.target = knob("sum", "gain", value);
    return true;
  }

  reset(sampleRate: number): void {
    this.gain.reset(DECLICK_TIME_S, sampleRate);
  }

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    if (!x) {
      this.left.fill(0, 0, n);
      this.right.fill(0, 0, n);
      return;
    }
    const xl = x[0]!;
    const xr = x[1]!;
    const gain = this.gain;
    for (let i = 0; i < n; i++) {
      const g = gain.next();
      this.left[i] = g * xl[i]!;
      this.right[i] = g * xr[i]!;
    }
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}

/** out = clip(gain · Σ inputs, 0, 1); 0 with nothing connected. */
export class ControlSum implements BlockRuntime {
  readonly type = "control_sum" as const;
  readonly spec = BLOCK_SPECS.control_sum;
  readonly outputs: readonly PortSignal[];
  readonly id: string;
  private readonly gain: Glide;
  private readonly out: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.gain = new Glide(knob("control_sum", "gain", params.gain));
    this.out = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.out]];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "gain") return false;
    this.gain.target = knob("control_sum", "gain", value);
    return true;
  }

  reset(sampleRate: number): void {
    this.gain.reset(DECLICK_TIME_S, sampleRate);
  }

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    if (!x) {
      this.out.fill(0, 0, n);
      return;
    }
    const xs = x[0]!;
    const gain = this.gain;
    for (let i = 0; i < n; i++) {
      const v = gain.next() * xs[i]!;
      this.out[i] = v < 0 ? 0 : v > 1 ? 1 : v;
    }
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}

/**
 * The sink: main = softclip(volume · in); silence with nothing connected. A NaN sample
 * (a broken box) becomes 0 so it never reaches the speakers (spec §4.4).
 */
export class Output implements BlockRuntime {
  readonly type = "output" as const;
  readonly spec = BLOCK_SPECS.output;
  readonly outputs: readonly PortSignal[] = [];
  readonly main: PortSignal;
  readonly id: string;
  private readonly volume: Glide;
  private readonly left: Float64Array;
  private readonly right: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.volume = new Glide(knob("output", "volume", params.volume));
    this.left = new Float64Array(ctx.maxFrames);
    this.right = new Float64Array(ctx.maxFrames);
    this.main = [this.left, this.right];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "volume") return false;
    this.volume.target = knob("output", "volume", value);
    return true;
  }

  reset(sampleRate: number): void {
    this.volume.reset(DECLICK_TIME_S, sampleRate);
  }

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    if (!x) {
      this.left.fill(0, 0, n);
      this.right.fill(0, 0, n);
      return;
    }
    const xl = x[0]!;
    const xr = x[1]!;
    const volume = this.volume;
    for (let i = 0; i < n; i++) {
      const v = volume.next();
      const l = softClip(v * xl[i]!);
      const r = softClip(v * xr[i]!);
      this.left[i] = Number.isNaN(l) ? 0 : l;
      this.right[i] = Number.isNaN(r) ? 0 : r;
    }
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}
