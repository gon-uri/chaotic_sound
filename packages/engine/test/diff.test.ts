/** diffPatch: the edits between two patches (used by the editor's undo and redo). */

import { describe, expect, test } from "vitest";
import { applyEdit, diffPatch, type PatchDocument } from "../src/core/patch.ts";

const base: PatchDocument = {
  format: "chaotic-sound-patch",
  version: 0,
  blocks: [
    { id: "lfo", type: "modulator", params: { period_s: 2 } },
    { id: "osc", type: "dynamical", params: { system: "lorenz", note: "A3" } },
    { id: "out", type: "output", params: {} },
  ],
  cables: [
    { from: "lfo.out", to: "osc.param" },
    { from: "osc.out", to: "out.in" },
  ],
};

/** Compare two patches ignoring the order of blocks and cables. */
function canonical(doc: PatchDocument): unknown {
  return {
    blocks: [...doc.blocks]
      .map((b) => ({ id: b.id, type: b.type, params: b.params ?? {} }))
      .sort((a, b) => a.id.localeCompare(b.id)),
    cables: doc.cables.map((c) => `${c.from}→${c.to}`).sort(),
  };
}

function roundTrip(from: PatchDocument, to: PatchDocument): void {
  let doc = from;
  for (const e of diffPatch(from, to)) doc = applyEdit(doc, e);
  expect(canonical(doc)).toEqual(canonical(to));
}

describe("diffPatch", () => {
  test("identical patches need no edits", () => {
    expect(diffPatch(base, structuredClone(base))).toEqual([]);
  });

  test("block positions are ignored", () => {
    const moved = structuredClone(base);
    moved.blocks[1]!.ui = { x: 10, y: 20 };
    expect(diffPatch(base, moved)).toEqual([]);
  });

  test("a knob change is one setParams; removing a param sends null (the default)", () => {
    const to = structuredClone(base);
    to.blocks[1]!.params = { system: "lorenz", note: "A3", param: 0.7 };
    expect(diffPatch(base, to)).toEqual([{ op: "setParams", id: "osc", params: { param: 0.7 } }]);
    expect(diffPatch(to, base)).toEqual([{ op: "setParams", id: "osc", params: { param: null } }]);
  });

  test("adding, removing and rewiring boxes round-trips", () => {
    const to = structuredClone(base);
    to.blocks.splice(0, 1); // remove the LFO (and its cable)
    to.blocks.push({ id: "lfo2", type: "modulator", params: { shape: "square" } });
    to.cables = [
      { from: "lfo2.out", to: "osc.amp" },
      { from: "osc.out", to: "out.in" },
    ];
    roundTrip(base, to);
    roundTrip(to, base);
  });

  test("a block whose type changed is removed and added again", () => {
    const to = structuredClone(base);
    to.blocks[0] = { id: "lfo", type: "control_sum", params: {} };
    to.cables = [{ from: "osc.out", to: "out.in" }];
    const edits = diffPatch(base, to);
    expect(edits.map((e) => e.op)).toEqual(["removeBlock", "addBlock"]);
    roundTrip(base, to);
  });

  test("a moved cable is disconnected before it is connected again", () => {
    const to = structuredClone(base);
    to.cables[0] = { from: "lfo.out", to: "osc.amp" };
    expect(diffPatch(base, to)).toEqual([
      { op: "disconnect", from: "lfo.out", to: "osc.param" },
      { op: "connect", from: "lfo.out", to: "osc.amp" },
    ]);
  });
});
