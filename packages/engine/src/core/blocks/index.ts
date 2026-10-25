/** Block factory: patch-JSON `type` → runtime block. */

import type { BlockJson, ParamValue } from "../patch.ts";
import type { BlockContext, BlockRuntime } from "./block.ts";
import { Dynamical } from "./dynamical.ts";
import { ControlSum, Output, Sum } from "./mixers.ts";
import { Modulator } from "./modulator.ts";

export type { BlockContext, BlockRuntime, PortSignal } from "./block.ts";
export { Dynamical } from "./dynamical.ts";
export { ControlSum, Output, Sum } from "./mixers.ts";
export { Modulator, shapeValue } from "./modulator.ts";

/** Create the runtime block for a (validated) block entry. */
export function createBlock(b: BlockJson, ctx: BlockContext): BlockRuntime {
  const params = (b.params ?? {}) as Record<string, ParamValue>;
  switch (b.type) {
    case "modulator":
      return new Modulator(b.id, params, ctx);
    case "dynamical":
      return new Dynamical(b.id, params, ctx);
    case "sum":
      return new Sum(b.id, params, ctx);
    case "control_sum":
      return new ControlSum(b.id, params, ctx);
    case "output":
      return new Output(b.id, params, ctx);
  }
}
