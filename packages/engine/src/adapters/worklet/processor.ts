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

  private send(msg: FromWorklet): void {
    this.port.postMessage(msg);
  }

  private onMessage(msg: ToWorklet): void {
    try {
      switch (msg.type) {
        case "load":
          this.engine.load(msg.patch, msg.catalog, sampleRate);
          this.loaded = true;
          this.frames = 0;
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
          this.frames = 0;
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
    this.engine.process(left.length, left, right);
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
