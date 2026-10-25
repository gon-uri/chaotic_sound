/**
 * Portable seeded randomness (spec §4.2 step 9): CRC-32 seed hash, mulberry32, Box–Muller.
 *
 * Bit-exact with the Python reference (`lab/src/chaotic_sound/rng.py`). Only plain integer
 * arithmetic is used, so this also runs in the audio thread (no TextEncoder there).
 */

const CRC_TABLE: Uint32Array = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

/** UTF-8 bytes of a string (code points beyond U+FFFF via surrogate pairs). */
export function utf8Bytes(text: string): number[] {
  const bytes: number[] = [];
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp < 0x80) bytes.push(cp);
    else if (cp < 0x800) bytes.push(0xc0 | (cp >> 6), 0x80 | (cp & 63));
    else if (cp < 0x10000) bytes.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
    else
      bytes.push(
        0xf0 | (cp >> 18),
        0x80 | ((cp >> 12) & 63),
        0x80 | ((cp >> 6) & 63),
        0x80 | (cp & 63),
      );
  }
  return bytes;
}

/** CRC-32 (IEEE 802.3, the zlib polynomial) of a byte sequence, as an unsigned integer. */
export function crc32(bytes: readonly number[]): number {
  let c = 0xffffffff;
  for (const b of bytes) c = (CRC_TABLE[(c ^ b) & 0xff] ?? 0) ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** Deterministic seed of a block id: CRC-32 of its UTF-8 bytes, masked to 31 bits. */
export function stableSeed(blockId: string): number {
  return crc32(utf8Bytes(blockId)) & 0x7fffffff;
}

/** The mulberry32 generator (public domain, Tommy Ettinger). */
export class Mulberry32 {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  /** Next raw 32-bit output (unsigned). */
  nextUint32(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    const a = this.state;
    let t = Math.imul(a ^ (a >>> 15), a | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t;
    return (t ^ (t >>> 14)) >>> 0;
  }

  /** Uniform deviate in [0, 1). */
  uniform(): number {
    return this.nextUint32() / 4294967296;
  }

  /** Standard normal deviate by Box–Muller (two uniforms per call). */
  normal(): number {
    const u1 = this.uniform();
    const u2 = this.uniform();
    return Math.sqrt(-2 * Math.log(1 - u1)) * Math.cos(2 * Math.PI * u2);
  }
}
