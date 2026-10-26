/**
 * Documented defaults (TS engine review, findings 4 and 29). Spec §5 tells writers to omit
 * defaulted values, so a patch that omits them must sound exactly like one that spells
 * them out, and the defaults must be the ones in the spec §4 tables.
 */

import { describe, expect, test } from "vitest";
import { stableSeed } from "../src/core/dsp/rng.ts";
import {
  BLOCK_SPECS,
  type BlockJson,
  type BlockType,
  defaultParam,
  type ParamValue,
  withDefaults,
} from "../src/core/patch.ts";
import { catalog } from "./helpers.ts";
import { firstDifference, patch, render } from "./rules-helpers.ts";

/** The "Default" columns of spec §4.1–4.5, copied from the spec (not from the code). */
const SPEC_DEFAULTS: Record<BlockType, Record<string, ParamValue>> = {
  modulator: { shape: "sine", period_s: 4, mode: "loop" },
  dynamical: {
    system: "rossler",
    note: "A3",
    cents: 0,
    pitch_min: "A1",
    pitch_max: "A5",
    pitch_lock: true,
    amp_curve: "perceptual",
    amp: 1,
    tonality: 0.3,
  },
  sum: { gain: 1 },
  control_sum: { gain: 1 },
  output: { volume: 0.8 },
};
/** Defaults that depend on context: the catalog (param, observable), mono, the block id. */
const CONTEXT_DEFAULTS: Record<BlockType, string[]> = {
  modulator: [],
  dynamical: ["param", "observable", "observable_right", "seed"],
  sum: [],
  control_sum: [],
  output: [],
};
const TYPES = Object.keys(SPEC_DEFAULTS) as BlockType[];

describe.each(TYPES)("%s defaults", (type) => {
  test("withDefaults and defaultParam give the spec §4 defaults", () => {
    expect(withDefaults(type, {})).toEqual(SPEC_DEFAULTS[type]);
    for (const [name, value] of Object.entries(SPEC_DEFAULTS[type])) {
      expect(defaultParam(type, name), name).toBe(value);
    }
    for (const name of CONTEXT_DEFAULTS[type])
      expect(defaultParam(type, name), name).toBeUndefined();
    // Every parameter of the block is listed above: none was added without a documented default.
    expect(Object.keys(BLOCK_SPECS[type].params).sort()).toEqual(
      [...Object.keys(SPEC_DEFAULTS[type]), ...CONTEXT_DEFAULTS[type]].sort(),
    );
  });

  test("given values win over defaults", () => {
    const [name] = Object.keys(SPEC_DEFAULTS[type]);
    const given = {
      [name!]: type === "modulator" ? "square" : type === "dynamical" ? "chua" : 0.3,
    };
    expect(withDefaults(type, given)).toEqual({ ...SPEC_DEFAULTS[type], ...given });
  });
});

test("a patch that omits every optional param renders exactly like one that spells them out", () => {
  // Every block type, and every input of the dynamical box: the modulator drives the knob of
  // one voice, the pitch of another, and (through a Control Sum) the amp of a third.
  const minimal = patch(
    [
      { id: "lfo", type: "modulator" },
      { id: "cs", type: "control_sum", params: {} },
      { id: "knob", type: "dynamical" },
      { id: "swept", type: "dynamical" },
      { id: "pitched", type: "dynamical" },
      { id: "faded", type: "dynamical" },
      { id: "mix", type: "sum" },
      { id: "out", type: "output" },
    ],
    [
      ["lfo.out", "swept.param"],
      ["lfo.out", "pitched.pitch"],
      ["lfo.out", "cs.in"],
      ["cs.out", "faded.amp"],
      ["knob.out", "mix.in"],
      ["swept.out", "mix.in"],
      ["pitched.out", "mix.in"],
      ["faded.out", "mix.in"],
      ["mix.out", "out.in"],
    ],
  );
  const rossler = catalog.systems.rossler!;
  const spelled = structuredClone(minimal);
  spelled.blocks = minimal.blocks.map((b): BlockJson => {
    const params: Record<string, ParamValue | null> = { ...SPEC_DEFAULTS[b.type] };
    if (b.type === "dynamical") {
      params.param = rossler.u_default; // the catalog's default knob position
      params.observable = rossler.default_observable;
      params.observable_right = null; // null means omitted: mono
      params.seed = stableSeed(b.id); // CRC-32 of the id (spec §4.2 step 9)
    }
    return { ...b, params };
  });
  // Past one modulator period (4 s), so the default mode (loop) matters too.
  const frames = Math.round(4.1 * 48_000);
  const a = render(minimal, frames, { blockSize: 4096 });
  const b = render(spelled, frames, { blockSize: 4096 });
  expect(firstDifference(a.left, b.left)).toBe(-1);
  expect(firstDifference(a.right, b.right)).toBe(-1);
  expect(a.diagnostics).toEqual(b.diagnostics);
});
