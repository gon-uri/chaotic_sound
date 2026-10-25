/**
 * Web Worker adapter: renders a patch offline and returns WAV bytes, so the UI thread stays
 * responsive. Start it with `new Worker(url, { type: "module" })` (Vite: `?worker&url`).
 */

import { renderOffline } from "../offline.ts";
import { encodeWav } from "../wav.ts";
import type { RenderRequest, RenderResponse } from "./protocol.ts";

interface WorkerScope {
  onmessage: ((e: { data: RenderRequest }) => void) | null;
  postMessage(msg: RenderResponse, transfer?: ArrayBuffer[]): void;
}

const scope = globalThis as unknown as WorkerScope; // the worker global scope (`self`)

scope.onmessage = (e) => {
  const req = e.data;
  try {
    const t0 = Date.now();
    const r = renderOffline(req.patch, req.catalog, {
      seconds: req.seconds,
      sampleRate: req.sampleRate,
    });
    const wav = encodeWav(r.left, r.right, r.sampleRate, req.format);
    scope.postMessage(
      {
        type: "done",
        wav,
        seconds: req.seconds,
        renderMs: Date.now() - t0,
        diagnostics: r.diagnostics,
      },
      [wav.buffer],
    );
  } catch (error) {
    scope.postMessage({ type: "error", message: (error as Error).message });
  }
};
