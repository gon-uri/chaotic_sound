/**
 * AudioWorklet adapter (driving adapter): the browser's audio thread calls `process()` with
 * 128-frame quanta; we forward them to the engine core. Messages from the UI are applied
 * between quanta. Nothing here allocates inside `process()`.
 *
 * Load it with `audioContext.audioWorklet.addModule(<bundled processor URL>)` (Phase 3 bundles
 * it with Vite), then `new AudioWorkletNode(ctx, PROCESSOR_NAME, { outputChannelCount: [2] })`.
 */

import { Engine } from "../../core/engine.ts";
import { type FromWorklet, PROCESSOR_NAME, type ToWorklet } from "./protocol.ts";

const QUANTUM = 128;

class ChaoticSoundProcessor extends AudioWorkletProcessor {
  private readonly engine = new Engine({ maxFrames: QUANTUM });
  private loaded = false;
  private playing = true;
  private frames = 0;
  private nextReport = 0;

  constructor() {
    super();
    this.port.onmessage = (event: MessageEvent<ToWorklet>) => this.onMessage(event.data);
  }

  /** Count frames from 0 again and report diagnostics on the next quantum. */
  private restartClock(): void {
    this.frames = 0;
    this.nextReport = 0;
  }

  private send(msg: FromWorklet): void {
    this.port.postMessage(msg);
  }

  private onMessage(msg: ToWorklet): void {
    try {
      switch (msg.type) {
        case "load":
          this.engine.load(msg.patch, msg.catalog, sampleRate);
          this.loaded = true;
          this.restartClock();
          this.send({ type: "loaded" });
          break;
        case "edit":
          this.engine.edit(msg.edit);
          break;
        case "setParam":
          this.engine.setParam(msg.blockId, msg.name, msg.value);
          break;
        case "reset":
          this.engine.reset();
          this.restartClock();
          break;
        case "play":
          this.playing = msg.playing;
          break;
      }
    } catch (error) {
      this.send({ type: "error", message: (error as Error).message });
    }
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const out = outputs[0];
    const left = out?.[0];
    if (left === undefined) return true;
    const right = out?.[1] ?? left;
    if (!this.loaded || !this.playing) {
      left.fill(0);
      right.fill(0);
      return true;
    }
    try {
      this.engine.process(left.length, left, right);
    } catch (error) {
      // Never let an exception kill the node (the browser would stop it for good):
      // go silent, report once, and wait for the next 'load'.
      left.fill(0);
      right.fill(0);
      this.loaded = false;
      this.send({ type: "error", message: `render failed: ${(error as Error).message}` });
      return true;
    }
    this.frames += left.length;
    if (this.frames >= this.nextReport) {
      this.nextReport = this.frames + Math.round(sampleRate / 4);
      this.send({
        type: "diagnostics",
        diagnostics: this.engine.diagnostics(),
        frames: this.frames,
      });
    }
    return true;
  }
}

registerProcessor(PROCESSOR_NAME, ChaoticSoundProcessor);
