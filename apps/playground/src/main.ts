/**
 * Playground (a driving adapter of the engine, ADR 0011): loads an example patch, starts an
 * AudioWorklet running the engine core, and sends knob changes as messages.
 */

import type { CatalogDocument, PatchDocument } from "@chaotic-sound/engine";
import type { RenderRequest, RenderResponse } from "@chaotic-sound/engine/worker/protocol";
import renderWorkerUrl from "@chaotic-sound/engine/worker?worker&url";
import {
  type FromWorklet,
  PROCESSOR_NAME,
  type ToWorklet,
} from "@chaotic-sound/engine/worklet/protocol";
// Vite compiles the processor (and the core it imports) into one module and gives its URL.
import processorUrl from "@chaotic-sound/engine/worklet?worker&url";
import catalogJson from "../../../catalog/systems.json";

const catalog = catalogJson as unknown as CatalogDocument;
const patches = import.meta.glob<PatchDocument>("../../../examples/patches/*.json", {
  eager: true,
  import: "default",
});

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const select = $<HTMLSelectElement>("patch");
const status = $<HTMLPreElement>("status");
const knobs = $<HTMLFieldSetElement>("knobs");

const names = Object.keys(patches).sort();
for (const path of names) {
  const opt = document.createElement("option");
  opt.value = path;
  opt.textContent = path.split("/").pop()!.replace(".json", "");
  select.append(opt);
}

let ctx: AudioContext | null = null;
let node: AudioWorkletNode | null = null;

function send(msg: ToWorklet): void {
  node?.port.postMessage(msg);
}

function currentPatch(): PatchDocument {
  return structuredClone(patches[select.value]!);
}

function buildKnobs(patch: PatchDocument): void {
  knobs.replaceChildren(
    Object.assign(document.createElement("legend"), { textContent: "Live knobs" }),
  );
  const dyn = patch.blocks.find((b) => b.type === "dynamical");
  const out = patch.blocks.find((b) => b.type === "output");
  const add = (blockId: string, name: string, label: string, initial: number): void => {
    const wrap = document.createElement("label");
    const input = Object.assign(document.createElement("input"), {
      type: "range",
      min: "0",
      max: "1",
      step: "0.001",
      value: String(initial),
    });
    const text = document.createTextNode(`${label}: ${initial.toFixed(3)}`);
    input.addEventListener("input", () => {
      text.textContent = `${label}: ${Number(input.value).toFixed(3)}`;
      send({ type: "setParam", blockId, name, value: Number(input.value) });
    });
    wrap.append(text, input);
    knobs.append(wrap);
  };
  if (dyn) {
    const entry = catalog.systems[(dyn.params?.system as string) ?? "rossler"];
    const u = (dyn.params?.param as number | undefined) ?? entry?.u_default ?? 0.5;
    add(dyn.id, "param", `${dyn.id} · parameter (u)`, u);
    add(dyn.id, "amp", `${dyn.id} · amp`, (dyn.params?.amp as number | undefined) ?? 1);
  }
  if (out)
    add(out.id, "volume", `${out.id} · volume`, (out.params?.volume as number | undefined) ?? 0.8);
}

async function play(): Promise<void> {
  if (ctx === null) {
    ctx = new AudioContext({ latencyHint: "interactive" });
    await ctx.audioWorklet.addModule(processorUrl);
    node = new AudioWorkletNode(ctx, PROCESSOR_NAME, { outputChannelCount: [2] });
    node.connect(ctx.destination);
    node.port.onmessage = (e: MessageEvent<FromWorklet>) => {
      const m = e.data;
      if (m.type === "error") status.textContent = `error: ${m.message}`;
      if (m.type === "diagnostics") {
        status.textContent =
          `playing at ${ctx!.sampleRate} Hz · ${(m.frames / ctx!.sampleRate).toFixed(1)} s rendered\n` +
          `diagnostics ${JSON.stringify(m.diagnostics)}`;
      }
    };
  }
  await ctx.resume();
  const patch = currentPatch();
  buildKnobs(patch);
  send({ type: "load", patch, catalog });
  send({ type: "play", playing: true });
  $<HTMLButtonElement>("stop").disabled = false;
}

$<HTMLButtonElement>("play").addEventListener("click", () => {
  play().catch((e: unknown) => {
    status.textContent = `could not start audio: ${String(e)}`;
  });
});
$<HTMLButtonElement>("stop").addEventListener("click", () => {
  send({ type: "play", playing: false });
  status.textContent = "stopped";
});
select.addEventListener("change", () => {
  if (ctx !== null) void play();
});
$<HTMLButtonElement>("wav").addEventListener("click", () => {
  status.textContent = "rendering 10 s in a Web Worker…";
  const worker = new Worker(renderWorkerUrl, { type: "module" });
  worker.onmessage = (e: MessageEvent<RenderResponse>) => {
    const m = e.data;
    worker.terminate();
    if (m.type === "error") {
      status.textContent = `render failed: ${m.message}`;
      return;
    }
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([m.wav], { type: "audio/wav" })),
      download: `${select.selectedOptions[0]?.textContent ?? "patch"}.wav`,
    });
    a.click();
    status.textContent = `rendered ${m.seconds} s in ${(m.renderMs / 1000).toFixed(2)} s · ${JSON.stringify(m.diagnostics)}`;
  };
  const request: RenderRequest = {
    type: "render",
    patch: currentPatch(),
    catalog,
    seconds: 10,
    sampleRate: 48_000,
    format: "pcm16",
  };
  worker.postMessage(request);
});
