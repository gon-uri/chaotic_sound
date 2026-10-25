"""Musical pitch helpers: note names ↔ MIDI numbers ↔ frequency (spec §4.2 step 3).

Conventions: scientific pitch notation (middle C = C4), A4 = 440 Hz, 12-tone equal
temperament. Accidentals: ``#``/``♯`` (sharp) and ``b``/``♭`` (flat), at most two.
"""

from __future__ import annotations

import math
import re

A4_HZ = 440.0
A4_MIDI = 69

_LETTER_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_RE = re.compile(r"^\s*([A-Ga-g])([#♯b♭]{0,2})(-?\d+)\s*$")
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_to_midi(note: str) -> int:
    """MIDI number of a note name.

    Examples
    --------
    >>> note_to_midi("A4"), note_to_midi("C4"), note_to_midi("Bb2"), note_to_midi("C-1")
    (69, 60, 46, 0)
    """
    match = _NOTE_RE.match(note)
    if match is None:
        raise ValueError(f"not a note name: {note!r} (expected e.g. 'A4', 'C#3', 'Bb2')")
    letter, accidentals, octave = match.groups()
    shift = sum(1 if a in "#♯" else -1 for a in accidentals)
    return 12 * (int(octave) + 1) + _LETTER_SEMITONES[letter.upper()] + shift


def midi_to_hz(midi: float, a4_hz: float = A4_HZ) -> float:
    """Frequency in Hz of a (possibly fractional) MIDI number."""
    return a4_hz * 2.0 ** ((midi - A4_MIDI) / 12.0)


def note_to_hz(note: str, cents: float = 0.0, a4_hz: float = A4_HZ) -> float:
    """Frequency in Hz of a note name plus a detune in cents.

    Examples
    --------
    >>> round(note_to_hz("A3"), 6), round(note_to_hz("C4"), 3)
    (220.0, 261.626)
    """
    return midi_to_hz(note_to_midi(note) + cents / 100.0, a4_hz)


def hz_to_midi(freq_hz: float, a4_hz: float = A4_HZ) -> float:
    """Fractional MIDI number of a frequency."""
    if freq_hz <= 0:
        raise ValueError("frequency must be positive")
    return A4_MIDI + 12.0 * math.log2(freq_hz / a4_hz)


def cents_between(f_hz: float, ref_hz: float) -> float:
    """Interval from ``ref_hz`` to ``f_hz`` in cents (positive if ``f_hz`` is higher)."""
    return 1200.0 * math.log2(f_hz / ref_hz)


def midi_to_note(midi: int) -> str:
    """Note name (sharps) of an integer MIDI number, e.g. ``69 → 'A4'``."""
    return f"{_SHARP_NAMES[midi % 12]}{midi // 12 - 1}"
