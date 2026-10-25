/**
 * Command-line renderer (Node driving adapter):
 *
 *   node packages/engine/src/adapters/node/cli.ts <patch.json> <out.wav>
 *        [--seconds 10] [--rate 48000] [--format pcm16|float32] [--catalog path]
 *
 * (`npm run render -- …` from the repository root does the same.)
 */

import { writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { renderOffline } from "../offline.ts";
import { encodeWav, type WavFormat } from "../wav.ts";
import { readCatalog, readPatch } from "./catalog-file.ts";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    seconds: { type: "string", default: "10" },
    rate: { type: "string", default: "48000" },
    format: { type: "string", default: "pcm16" },
    catalog: { type: "string" },
  },
});
const [patchPath, outPath] = positionals;
if (patchPath === undefined || outPath === undefined) {
  console.error(
    "usage: cli.ts <patch.json> <out.wav> [--seconds 10] [--rate 48000] [--format pcm16|float32]",
  );
  process.exit(2);
}
const format = values.format as WavFormat;
const start = performance.now();
const result = renderOffline(readPatch(patchPath), readCatalog(values.catalog), {
  seconds: Number(values.seconds),
  sampleRate: Number(values.rate),
});
writeFileSync(outPath, encodeWav(result.left, result.right, result.sampleRate, format));
const ms = performance.now() - start;
console.log(
  `wrote ${outPath} (${values.seconds} s at ${values.rate} Hz, ${format}) in ${(ms / 1000).toFixed(2)} s; ` +
    `diagnostics ${JSON.stringify(result.diagnostics)}`,
);
