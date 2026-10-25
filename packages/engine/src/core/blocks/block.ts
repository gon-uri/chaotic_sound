/**
 * The runtime interface of a block (architecture layer 4) and the context it receives.
 *
 * Buffers: every block owns preallocated output buffers of length `maxFrames`; a call to
 * `process(n, inputs)` writes the first `n` samples. A control port is one Float64Array; an
 * audio port is a pair [left, right]. Inputs arrive already prepared by the graph (one
 * cable's signal, or the sum of a multi-cable input, control values sanitized).
 */

import type { Catalog } from "../catalog.ts";
import type { BlockSpec, BlockType, ParamValue } from "../patch.ts";

/** What a block may receive from outside (the catalog is data, not a file). */
export interface BlockContext {
  readonly catalog: Catalog;
  /** Largest chunk the engine will ask for; buffers are sized to it. */
  readonly maxFrames: number;
}

/** A signal on one port: [buffer] for control, [left, right] for audio. */
export type PortSignal = readonly Float64Array[];

export interface BlockRuntime {
  readonly id: string;
  readonly type: BlockType;
  readonly spec: BlockSpec;
  /** One entry per output port (in spec order). */
  readonly outputs: readonly PortSignal[];
  /** The sink's result ([left, right]); only the Output block has it. */
  readonly main?: PortSignal;
  /** Prepare to render from t = 0 at `sampleRate`; clears all state. */
  reset(sampleRate: number): void;
  /** Produce the next `n` samples; `inputs[i]` is input port i's signal or null. */
  process(n: number, inputs: readonly (PortSignal | null)[]): void;
  /** Counters reported after a render (e.g. safety resets). */
  diagnostics(): Record<string, number>;
  /**
   * Apply a (validated) parameter change live, keeping state. Returns false if the block
   * must be recreated instead. Optional: blocks without live settings omit it.
   */
  setParam?(name: string, value: ParamValue | undefined): boolean;
}
