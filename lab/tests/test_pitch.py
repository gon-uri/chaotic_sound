import pytest

from chaotic_sound.pitch import (
    cents_between,
    hz_to_midi,
    midi_to_hz,
    midi_to_note,
    note_to_hz,
    note_to_midi,
)


@pytest.mark.parametrize(
    ("note", "midi"),
    [
        ("A4", 69),
        ("a4", 69),
        ("C4", 60),
        ("C#4", 61),
        ("Db4", 61),
        ("C♯4", 61),
        ("B♭3", 58),
        ("Bb2", 46),
        ("C-1", 0),
        ("E#4", 65),
        ("G9", 127),
    ],
)
def test_note_to_midi(note: str, midi: int) -> None:
    assert note_to_midi(note) == midi


@pytest.mark.parametrize(
    "bad", ["H4", "A", "4", "A#b#4", "", "A4.5", "Cbb4", " A4", "A10", "A-2", "A 4"]
)
def test_note_to_midi_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        note_to_midi(bad)


def test_frequencies() -> None:
    assert note_to_hz("A4") == 440.0
    assert note_to_hz("A3") == pytest.approx(220.0)
    assert note_to_hz("C4") == pytest.approx(261.6255653, rel=1e-9)
    assert note_to_hz("A4", cents=100) == pytest.approx(midi_to_hz(70))
    assert note_to_hz("A4", a4_hz=432.0) == 432.0
    assert hz_to_midi(880.0) == pytest.approx(81.0)
    assert cents_between(880.0, 440.0) == pytest.approx(1200.0)
    assert midi_to_note(69) == "A4" and midi_to_note(61) == "C#4"
