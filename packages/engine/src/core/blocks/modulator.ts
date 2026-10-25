/** Modulator block: a slow control signal in [0, 1] (spec §4.1). */

import { BLOCK_SPECS, type ParamValue } from "../patch.ts";
import type { BlockContext, BlockRuntime, PortSignal } from "./block.ts";

export type Shape = "sine" | "triangle" | "square" | "ramp_up" | "ramp_down";

/** shape(φ) on the closed interval [0, 1] (spec §4.1 table). */
export function shapeValue(shape: Shape, phase: number): number {
  switch (shape) {
    case "sine":
      return 0.5 * (1 - Math.cos(2 * Math.PI * phase));
    case "triangle":
      return 1 - Math.abs(2 * phase - 1);
    case "square":
      return phase < 0.5 ? 1 : 0;
    case "ramp_up":
      return phase;
    case "ramp_down":
      return 1 - phase;
  }
}

export class Modulator implements BlockRuntime {
  readonly type = "modulator" as const;
  readonly spec = BLOCK_SPECS.modulator;
  readonly outputs: readonly PortSignal[];
  readonly id: string;
  private readonly shape: Shape;
  private readonly periodS: number;
  private readonly loop: boolean;
  private readonly out: Float64Array;
  private sampleRate = 48_000;
  private count = 0;

  constructor(id: string, params: Record<string, ParamValue>, ctx: BlockContext) {
    this.id = id;
    this.shape = (params.shape ?? "sine") as Shape;
    this.periodS = (params.period_s ?? 4) as number;
    this.loop = (params.mode ?? "loop") === "loop";
    this.out = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.out]];
  }

  reset(sampleRate: number): void {
    this.sampleRate = sampleRate;
    this.count = 0;
  }

  /** t = i/fs, c = t/T, φ = c − floor(c) (loop) or min(c, 1) (once): spec §4.1. */
  process(n: number): void {
    const fs = this.sampleRate;
    const period = this.periodS;
    for (let i = 0; i < n; i++) {
      const c = (this.count + i) / fs / period;
      const phase = this.loop ? c - Math.floor(c) : Math.min(c, 1);
      this.out[i] = shapeValue(this.shape, phase);
    }
    this.count += n;
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}
