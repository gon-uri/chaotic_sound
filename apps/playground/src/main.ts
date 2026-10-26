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
let lastError: string | null = null;

function send(msg: ToWorklet): void {
  node?.port.postMessage(msg);
}

// The patch being played, with the knob changes applied (so WAV export matches what you hear).
let live: PatchDocument | null = null;

function selectedPatch(): PatchDocument {
  return structuredClone(patches[select.value]!);
}

function setLiveParam(blockId: string, name: string, value: number): void {
  const block = live?.blocks.find((b) => b.id === blockId);
  if (block !== undefined) block.params = { ...(block.params ?? {}), [name]: value };
}

/** True if a cable drives this input; the cable then overrides the knob (spec §3). */
function cabled(patch: PatchDocument, blockId: string, input: string): boolean {
  return patch.cables.some((c) => c.to === `${blockId}.${input}`);
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
    if (cabled(patch, blockId, name)) {
      input.disabled = true;
      text.textContent = `${label}: driven by a cable`;
    }
    input.addEventListener("input", () => {
      const value = Number(input.value);
      text.textContent = `${label}: ${value.toFixed(3)}`;
      setLiveParam(blockId, name, value);
      send({ type: "setParam", blockId, name, value });
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
      if (m.type === "error") {
        lastError = m.message;
        status.textContent = `error: ${m.message}`;
      }
      if (m.type === "diagnostics") {
        const seconds = (m.frames / ctx!.sampleRate).toFixed(1);
        status.textContent =
          `playing at ${ctx!.sampleRate} Hz · ${seconds} s rendered\n` +
          `diagnostics ${JSON.stringify(m.diagnostics)}` +
          (lastError === null ? "" : `\nlast error: ${lastError}`);
      }
    };
    // An exception inside the processor stops it for good; say so instead of going silent.
    node.onprocessorerror = () => {
      status.textContent = "the audio processor crashed; reload the page";
    };
  }
  await ctx.resume();
  const patch = selectedPatch();
  live = structuredClone(patch);
  lastError = null;
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
  if (ctx === null) return;
  play().catch((e: unknown) => {
    status.textContent = `could not load the patch: ${String(e)}`;
  });
});
$<HTMLButtonElement>("wav").addEventListener("click", () => {
  status.textContent = "rendering 10 s in a Web Worker…";
  const worker = new Worker(renderWorkerUrl, { type: "module" });
  worker.onerror = (e: ErrorEvent) => {
    worker.terminate();
    status.textContent = `render failed: ${e.message}`;
  };
  worker.onmessage = (e: MessageEvent<RenderResponse>) => {
    const m = e.data;
    worker.terminate();
    if (m.type === "error") {
      status.textContent = `render failed: ${m.message}`;
      return;
    }
    const url = URL.createObjectURL(new Blob([m.wav], { type: "audio/wav" }));
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `${select.selectedOptions[0]?.textContent ?? "patch"}.wav`,
    });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000); // after the download has started
    status.textContent = `rendered ${m.seconds} s in ${(m.renderMs / 1000).toFixed(2)} s · ${JSON.stringify(m.diagnostics)}`;
  };
  const request: RenderRequest = {
    type: "render",
    patch: live ?? selectedPatch(), // the patch as you hear it, knob changes included
    catalog,
    seconds: 10,
    sampleRate: 48_000,
    format: "pcm16",
  };
  worker.postMessage(request);
});
