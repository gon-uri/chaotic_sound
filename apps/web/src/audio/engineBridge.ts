/**
 * Audio bridge (driving adapter of the engine, ADR 0011): owns the AudioContext and the
 * AudioWorkletNode that runs the engine core, and forwards the store's messages to it.
 */

import type { FromWorklet, ToWorklet } from "@chaotic-sound/engine/worklet/protocol";
import { PROCESSOR_NAME } from "@chaotic-sound/engine/worklet/protocol";
import processorUrl from "@chaotic-sound/engine/worklet?worker&url";
import { create } from "zustand";
import { catalogDocument } from "../store/catalog.ts";
import { onEngineMessage, usePatchStore } from "../store/patchStore.ts";

export interface AudioState {
  playing: boolean;
  sampleRate: number | null;
  seconds: number;
  diagnostics: Record<string, Record<string, number>>;
  error: string | null;
}

export const useAudioStore = create<AudioState>(() => ({
  playing: false,
  sampleRate: null,
  seconds: 0,
  diagnostics: {},
  error: null,
}));

let ctx: AudioContext | null = null;
let node: AudioWorkletNode | null = null;
/** Set when the processor crashed: the next Play builds a new context and node. */
let dead = false;

function send(msg: ToWorklet): void {
  node?.port.postMessage(msg);
}

// Forward every accepted patch change to the worklet (if it is running).
onEngineMessage((msg) => send(msg));

export async function play(): Promise<void> {
  try {
    if (dead && ctx !== null) {
      void ctx.close(); // the old node can never play again
      ctx = null;
      node = null;
      dead = false;
    }
    if (ctx === null) {
      ctx = new AudioContext({ latencyHint: "interactive" });
      await ctx.audioWorklet.addModule(processorUrl);
      node = new AudioWorkletNode(ctx, PROCESSOR_NAME, { outputChannelCount: [2] });
      node.connect(ctx.destination);
      // An exception inside the processor stops it for good (the engine guards against this).
      node.onprocessorerror = () => {
        dead = true;
        useAudioStore.setState({
          playing: false,
          error: "The audio engine stopped. Press Play to restart it.",
        });
      };
      node.port.onmessage = (e: MessageEvent<FromWorklet>) => {
        const m = e.data;
        if (m.type === "error") useAudioStore.setState({ error: m.message });
        if (m.type === "diagnostics") {
          useAudioStore.setState({
            diagnostics: m.diagnostics,
            seconds: m.frames / (ctx?.sampleRate ?? 48_000),
          });
        }
      };
    }
    await ctx.resume();
    send({ type: "load", patch: usePatchStore.getState().doc, catalog: catalogDocument });
    send({ type: "play", playing: true });
    useAudioStore.setState({ playing: true, sampleRate: ctx.sampleRate, error: null });
  } catch (e) {
    useAudioStore.setState({ error: `could not start audio: ${String(e)}` });
  }
}

export function stop(): void {
  send({ type: "play", playing: false });
  useAudioStore.setState({ playing: false });
}
