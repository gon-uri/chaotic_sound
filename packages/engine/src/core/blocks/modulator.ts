/** Modulator block: a slow control signal in [0, 1] (spec §4.1). */

import { BLOCK_SPECS, type ParamValue, withDefaults } from "../patch.ts";
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
    const p = withDefaults("modulator", params); // documented defaults (spec §4.1)
    this.shape = p.shape as Shape;
    this.periodS = p.period_s as number;
    this.loop = p.mode === "loop";
    this.out = new Float64Array(ctx.maxFrames);
    this.outputs = [[this.out]];
  }

  reset(sampleRate: number): void {
    this.sampleRate = sampleRate;
    this.count = 0;
  }

  /**
   * t = i/fs, c = t/T, φ = c − floor(c) (loop) or min(c, 1) (once): spec §4.1. The shape is
   * chosen once per chunk; each loop is `shapeValue` written out (same arithmetic), so the
   * audio loop calls no function that returns a number (nothing is boxed).
   */
  process(n: number): void {
    const fs = this.sampleRate;
    const period = this.periodS;
    const loop = this.loop;
    const count = this.count;
    const out = this.out;
    switch (this.shape) {
      case "sine":
        for (let i = 0; i < n; i++) {
          const c = (count + i) / fs / period;
          const phase = loop ? c - Math.floor(c) : Math.min(c, 1);
          out[i] = 0.5 * (1 - Math.cos(2 * Math.PI * phase));
        }
        break;
      case "triangle":
        for (let i = 0; i < n; i++) {
          const c = (count + i) / fs / period;
          const phase = loop ? c - Math.floor(c) : Math.min(c, 1);
          out[i] = 1 - Math.abs(2 * phase - 1);
        }
        break;
      case "square":
        for (let i = 0; i < n; i++) {
          const c = (count + i) / fs / period;
          const phase = loop ? c - Math.floor(c) : Math.min(c, 1);
          out[i] = phase < 0.5 ? 1 : 0;
        }
        break;
      case "ramp_up":
        for (let i = 0; i < n; i++) {
          const c = (count + i) / fs / period;
          out[i] = loop ? c - Math.floor(c) : Math.min(c, 1);
        }
        break;
      case "ramp_down":
        for (let i = 0; i < n; i++) {
          const c = (count + i) / fs / period;
          out[i] = 1 - (loop ? c - Math.floor(c) : Math.min(c, 1));
        }
        break;
    }
    this.count += n;
  }

  diagnostics(): Record<string, number> {
    return {};
  }
}
