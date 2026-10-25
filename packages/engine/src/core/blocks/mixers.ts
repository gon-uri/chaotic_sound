/** Sum (audio), Control Sum and Output blocks (spec §4.3–4.5). */

import { softClip } from "../dsp/filters.ts";
import { BLOCK_SPECS, type ParamValue } from "../patch.ts";
import type { BlockContext, BlockRuntime, PortSignal } from "./block.ts";

/** Audio mixer: out = gain · Σ inputs (the graph already added the cables). */
export class Sum implements BlockRuntime {
  readonly type = "sum" as const;
  readonly spec = BLOCK_SPECS.sum;
  readonly outputs: readonly PortSignal[];
  readonly id: string;
  private gain: number;
  private readonly left: Float64Array;
  private readonly right: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.gain = (params.gain ?? 1) as number;
    this.left = new Float64Array(ctx.maxFrames);
    this.right = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.left, this.right]];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "gain") return false;
    this.gain = (value ?? 1) as number;
    return true;
  }

  reset(): void {}

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    const g = this.gain;
    for (let i = 0; i < n; i++) {
      this.left[i] = x ? g * x[0]![i]! : 0;
      this.right[i] = x ? g * x[1]![i]! : 0;
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
  private gain: number;
  private readonly out: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.gain = (params.gain ?? 1) as number;
    this.out = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.out]];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "gain") return false;
    this.gain = (value ?? 1) as number;
    return true;
  }

  reset(): void {}

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    for (let i = 0; i < n; i++) {
      const v = x ? this.gain * x[0]![i]! : 0;
      this.out[i] = v < 0 ? 0 : v > 1 ? 1 : v;
    }
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}

/** The sink: main = softclip(volume · in); silence with nothing connected. */
export class Output implements BlockRuntime {
  readonly type = "output" as const;
  readonly spec = BLOCK_SPECS.output;
  readonly outputs: readonly PortSignal[] = [];
  readonly main: PortSignal;
  readonly id: string;
  private volume: number;
  private readonly left: Float64Array;
  private readonly right: Float64Array;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.volume = (params.volume ?? 0.8) as number;
    this.left = new Float64Array(ctx.maxFrames);
    this.right = new Float64Array(ctx.maxFrames);
    this.main = [this.left, this.right];
  }

  setParam(name: string, value: ParamValue | undefined): boolean {
    if (name !== "volume") return false;
    this.volume = (value ?? 0.8) as number;
    return true;
  }

  reset(): void {}

  process(n: number, inputs: readonly (PortSignal | null)[]): void {
    const x = inputs[0];
    const v = this.volume;
    for (let i = 0; i < n; i++) {
      this.left[i] = x ? softClip(v * x[0]![i]!) : 0;
      this.right[i] = x ? softClip(v * x[1]![i]!) : 0;
    }
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}
