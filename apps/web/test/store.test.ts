import type { ToWorklet } from "@chaotic-sound/engine/worklet/protocol";
import { beforeEach, describe, expect, test } from "vitest";
import { defaultPatch, layout, onEngineMessage, usePatchStore } from "../src/store/patchStore.ts";

const store = usePatchStore.getState;

beforeEach(() => {
  store().load(defaultPatch());
});

describe("patch store (every action validated by the engine)", () => {
  test("starts from a valid default patch", () => {
    expect(store().doc.blocks.map((b) => b.type)).toEqual(["dynamical", "output"]);
    expect(store().error).toBeNull();
  });

  test("adding and connecting boxes", () => {
    const mod = store().addBlock("modulator", { x: 0, y: 0 });
    expect(mod).toBe("mod1");
    expect(store().edit({ op: "connect", from: "mod1.out", to: "osc1.param" })).toBe(true);
    expect(store().doc.cables).toContainEqual({ from: "mod1.out", to: "osc1.param" });
  });

  test("a second control cable is rejected with the Control Sum hint", () => {
    store().addBlock("modulator", { x: 0, y: 0 });
    store().addBlock("modulator", { x: 0, y: 0 });
    store().edit({ op: "connect", from: "mod1.out", to: "osc1.amp" });
    expect(store().edit({ op: "connect", from: "mod2.out", to: "osc1.amp" })).toBe(false);
    expect(store().error).toMatch(/control_sum/);
    expect(store().doc.cables).toHaveLength(2); // unchanged
  });

  test("only one Output box", () => {
    expect(store().addBlock("output", { x: 0, y: 0 })).toBeNull();
    expect(store().error).toMatch(/one Output/);
  });

  test("invalid parameter values are rejected", () => {
    store().setParam("osc1", "note", "C9");
    expect(store().error).toMatch(/C0 and C8/);
    expect(store().doc.blocks[0]!.params).toEqual({ system: "rossler" });
  });

  test("knob drags coalesce into one undo step; undo/redo", () => {
    store().setParam("osc1", "param", 0.2);
    store().setParam("osc1", "param", 0.3);
    store().setParam("osc1", "param", 0.4);
    expect(store().past).toHaveLength(1);
    store().setParam("osc1", "amp", 0.5);
    expect(store().past).toHaveLength(2);
    store().undo();
    expect(store().doc.blocks[0]!.params).toEqual({ system: "rossler", param: 0.4 });
    store().undo();
    expect(store().doc.blocks[0]!.params).toEqual({ system: "rossler" });
    store().redo();
    expect(store().doc.blocks[0]!.params).toEqual({ system: "rossler", param: 0.4 });
  });

  test("automatic layout follows the signal flow", () => {
    const doc = {
      ...defaultPatch(),
      blocks: defaultPatch().blocks.map(({ ui: _ui, ...b }) => b),
    };
    store().load(doc);
    store().addBlock("modulator", { x: 0, y: 0 });
    const { blocks } = store().doc;
    const noUi = { ...store().doc, blocks: blocks.map(({ ui: _ui, ...b }) => b) };
    noUi.cables = [...noUi.cables, { from: "mod1.out", to: "osc1.param" }];
    const pos = layout(noUi);
    expect(pos.get("mod1")!.x).toBeLessThan(pos.get("osc1")!.x);
    expect(pos.get("osc1")!.x).toBeLessThan(pos.get("out")!.x);
  });
});

describe("undo and redo keep unchanged boxes playing", () => {
  const sent: ToWorklet[] = [];
  let unsubscribe: () => void = () => {};
  beforeEach(() => {
    sent.length = 0;
    unsubscribe();
    unsubscribe = onEngineMessage((m) => sent.push(m));
  });

  test("undoing a knob move sends a live setParams edit, not a reload", () => {
    store().setParam("osc1", "param", 0.4);
    sent.length = 0;
    store().undo();
    expect(sent).toEqual([
      { type: "edit", edit: { op: "setParams", id: "osc1", params: { param: null } } },
    ]);
    sent.length = 0;
    store().redo();
    expect(sent).toEqual([
      { type: "edit", edit: { op: "setParams", id: "osc1", params: { param: 0.4 } } },
    ]);
  });

  test("undoing a new box and its cable removes just that box", () => {
    store().addBlock("modulator", { x: 0, y: 0 });
    store().edit({ op: "connect", from: "mod1.out", to: "osc1.param" });
    sent.length = 0;
    store().undo(); // the cable
    store().undo(); // the box
    expect(sent).toEqual([
      { type: "edit", edit: { op: "disconnect", from: "mod1.out", to: "osc1.param" } },
      { type: "edit", edit: { op: "removeBlock", id: "mod1" } },
    ]);
  });
});
