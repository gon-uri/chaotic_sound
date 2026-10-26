/**
 * Command-line renderer (Node driving adapter):
 *
 *   node packages/engine/src/adapters/node/cli.ts <patch.json> <out.wav>
 *        [--seconds 10] [--rate 48000] [--format pcm16|float32] [--catalog path]
 *
 * Bad arguments exit with status 2 and the usage line.
 *
 * (`npm run render -- …` from the repository root does the same.)
 */

import { writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { renderOffline } from "../offline.ts";
import { encodeWav, WAV_FORMATS, type WavFormat } from "../wav.ts";
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
const USAGE =
  "usage: cli.ts <patch.json> <out.wav> [--seconds 10] [--rate 48000] " +
  "[--format pcm16|float32] [--catalog catalog/systems.json]";

function fail(message: string): never {
  console.error(`${message}\n${USAGE}`);
  process.exit(2);
}

const [patchPath, outPath] = positionals;
if (patchPath === undefined || outPath === undefined) fail("missing <patch.json> or <out.wav>");
const seconds = Number(values.seconds);
const rate = Number(values.rate);
if (!(Number.isFinite(seconds) && seconds > 0))
  fail(`--seconds must be > 0, got ${values.seconds}`);
if (!(Number.isFinite(rate) && rate > 0)) fail(`--rate must be > 0, got ${values.rate}`);
if (!(WAV_FORMATS as readonly string[]).includes(values.format)) {
  fail(`--format must be one of ${WAV_FORMATS.join(", ")}, got ${values.format}`);
}
const format = values.format as WavFormat;
const start = performance.now();
const result = renderOffline(readPatch(patchPath), readCatalog(values.catalog), {
  seconds,
  sampleRate: rate,
});
writeFileSync(outPath, encodeWav(result.left, result.right, result.sampleRate, format));
const ms = performance.now() - start;
console.log(
  `wrote ${outPath} (${values.seconds} s at ${values.rate} Hz, ${format}) in ${(ms / 1000).toFixed(2)} s; ` +
    `diagnostics ${JSON.stringify(result.diagnostics)}`,
);
