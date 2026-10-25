/** Messages to and from the offline-render Web Worker (WAV export off the UI thread). */

import type { CatalogDocument } from "../../core/catalog.ts";
import type { PatchDocument } from "../../core/patch.ts";
import type { Diagnostics } from "../../ports.ts";
import type { WavFormat } from "../wav.ts";

export interface RenderRequest {
  type: "render";
  patch: PatchDocument;
  catalog: CatalogDocument;
  seconds: number;
  sampleRate: number;
  format: WavFormat;
}

export type RenderResponse =
  | {
      type: "done";
      wav: Uint8Array<ArrayBuffer>;
      seconds: number;
      renderMs: number;
      diagnostics: Diagnostics;
    }
  | { type: "error"; message: string };
