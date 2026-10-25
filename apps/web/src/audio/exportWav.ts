/** WAV export in a Web Worker (offline render with the engine core; spec §4.4). */

import type { PatchDocument } from "@chaotic-sound/engine";
import type { RenderRequest, RenderResponse } from "@chaotic-sound/engine/worker/protocol";
import renderWorkerUrl from "@chaotic-sound/engine/worker?worker&url";
import { catalogDocument } from "../store/catalog.ts";

export function exportWav(
  patch: PatchDocument,
  seconds: number,
  fileName: string,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(renderWorkerUrl, { type: "module" });
    worker.onmessage = (e: MessageEvent<RenderResponse>) => {
      worker.terminate();
      const m = e.data;
      if (m.type === "error") {
        reject(new Error(m.message));
        return;
      }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([m.wav], { type: "audio/wav" }));
      a.download = fileName;
      a.click();
      resolve(`rendered ${m.seconds} s in ${(m.renderMs / 1000).toFixed(2)} s`);
    };
    const request: RenderRequest = {
      type: "render",
      patch,
      catalog: catalogDocument,
      seconds,
      sampleRate: 48_000,
      format: "pcm16",
    };
    worker.postMessage(request);
  });
}
