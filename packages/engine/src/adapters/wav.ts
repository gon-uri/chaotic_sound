/**
 * WAV encoding (driven adapter). Pure: returns bytes, so it works in Node and the browser.
 * 16-bit PCM rounds like the Python reference (round half to even, after clipping).
 */

import { roundHalfEven } from "../core/numeric.ts";

export type WavFormat = "pcm16" | "float32";
export const WAV_FORMATS: readonly WavFormat[] = ["pcm16", "float32"];

/** Encode stereo float samples as a RIFF/WAVE file. */
export function encodeWav(
  left: ArrayLike<number>,
  right: ArrayLike<number>,
  sampleRate: number,
  format: WavFormat = "pcm16",
): Uint8Array<ArrayBuffer> {
  const n = left.length;
  const channels = 2;
  const bytesPerSample = format === "pcm16" ? 2 : 4;
  const dataBytes = n * channels * bytesPerSample;
  const buf = new ArrayBuffer(44 + dataBytes);
  const v = new DataView(buf);
  const ascii = (offset: number, s: string): void => {
    for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i));
  };
  const rate = roundHalfEven(sampleRate); // Python: round(sample_rate)
  ascii(0, "RIFF");
  v.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, format === "pcm16" ? 1 : 3, true); // 1 = PCM, 3 = IEEE float
  v.setUint16(22, channels, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * channels * bytesPerSample, true);
  v.setUint16(32, channels * bytesPerSample, true);
  v.setUint16(34, bytesPerSample * 8, true);
  ascii(36, "data");
  v.setUint32(40, dataBytes, true);
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (const x of [left[i]!, right[i]!]) {
      if (format === "pcm16") {
        const c = x < -1 ? -1 : x > 1 ? 1 : x;
        v.setInt16(o, roundHalfEven(c * 32767), true);
        o += 2;
      } else {
        v.setFloat32(o, x, true);
        o += 4;
      }
    }
  }
  return new Uint8Array(buf);
}
