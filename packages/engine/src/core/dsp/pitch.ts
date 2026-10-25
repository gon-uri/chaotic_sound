/**
 * Musical pitch helpers: note names ↔ MIDI numbers ↔ frequency (spec §4.2).
 *
 * Scientific pitch notation (middle C = C4), A4 = 440 Hz, 12-tone equal temperament.
 * Grammar: a letter A–G (either case), at most one accidental (# or ♯ = sharp, b or ♭ =
 * flat), then an octave from -1 to 9, with no spaces. Boxes accept C0 … C8.
 */

export const A4_HZ = 440;
export const A4_MIDI = 69;
/** MIDI number of C0, the lowest note a dynamical box accepts. */
export const NOTE_MIN = 12;
/** MIDI number of C8, the highest note a dynamical box accepts. */
export const NOTE_MAX = 108;

const LETTER_SEMITONES: Readonly<Record<string, number>> = {
  C: 0,
  D: 2,
  E: 4,
  F: 5,
  G: 7,
  A: 9,
  B: 11,
};
const NOTE_RE = /^([A-Ga-g])([#♯b♭]?)(-1|[0-9])$/u;

/** MIDI number of a note name, e.g. `noteToMidi("A4") === 69`. Throws on bad names. */
export function noteToMidi(note: string): number {
  const match = typeof note === "string" ? NOTE_RE.exec(note) : null;
  if (match === null) {
    throw new RangeError(
      `not a note name: ${JSON.stringify(note)} (expected e.g. 'A4', 'C#3', 'Bb2')`,
    );
  }
  const [, letter = "", accidental = "", octave = "0"] = match;
  const shift = accidental === "" ? 0 : accidental === "#" || accidental === "♯" ? 1 : -1;
  return 12 * (Number(octave) + 1) + (LETTER_SEMITONES[letter.toUpperCase()] ?? 0) + shift;
}

/** Frequency in Hz of a (possibly fractional) MIDI number. */
export function midiToHz(midi: number, a4Hz: number = A4_HZ): number {
  return a4Hz * 2 ** ((midi - A4_MIDI) / 12);
}

/** Frequency in Hz of a note name plus a detune in cents. */
export function noteToHz(note: string, cents = 0, a4Hz: number = A4_HZ): number {
  return midiToHz(noteToMidi(note) + cents / 100, a4Hz);
}

/** Interval from `refHz` to `fHz` in cents (positive if `fHz` is higher). */
export function centsBetween(fHz: number, refHz: number): number {
  return 1200 * Math.log2(fHz / refHz);
}
