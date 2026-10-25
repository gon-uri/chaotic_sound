"""Export golden vectors for cross-engine tests (ADR 0011, spec §6).

Usage (from ``lab/``)::

    uv run python scripts/export_golden.py

For every patch in ``../examples/patches/`` this writes ``../examples/golden/<name>.json``:

- ``initial_states``: the exact seeded initial state of each dynamical block (spec §4.2
  step 9). Engines must reproduce these to the last bit (up to 1 ulp from ``log``/``cos``).
- ``modulators``: the first samples of each modulator's output (exact for every shape except
  ``sine``, where 1 ulp from ``cos`` is allowed).
- ``prefix``: the first samples of the rendered stereo output. They agree across engines to
  about 1e-9 before chaos amplifies round-off.
- ``stats``: statistics of a longer render (RMS, peak, octave-band levels, pitch of
  single-voice patches, safety resets). Engines must agree within statistical tolerances.

Arrays are stored as base64 of little-endian float64 (compact and exact).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from chaotic_sound.analysis.spectrum import measure_pitch
from chaotic_sound.blocks import Dynamical, Modulator
from chaotic_sound.patch import Patch

LAB = Path(__file__).resolve().parents[1]
PATCHES = LAB.parent / "examples" / "patches"
GOLDEN = LAB.parent / "examples" / "golden"
FS = 48_000
BLOCK = 512
PREFIX = 2048
STATS_SECONDS = 4.0
BANDS_HZ = [31.25 * 2**k for k in range(10)]  # octave bands centred 31 Hz … 16 kHz


def b64(x: np.ndarray) -> str:
    """Base64 of little-endian float64."""
    return base64.b64encode(np.ascontiguousarray(x, dtype="<f8").tobytes()).decode("ascii")


def octave_bands_db(x: np.ndarray, fs: int) -> list[float]:
    """Energy per octave band (dB relative to total), from a single long FFT."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / fs)
    total = spec[1:].sum()
    out = []
    for fc in BANDS_HZ:
        band = (freqs >= fc / np.sqrt(2)) & (freqs < fc * np.sqrt(2))
        out.append(float(10 * np.log10(max(spec[band].sum() / total, 1e-30))))
    return out


def export(path: Path) -> dict[str, object]:
    patch = Patch.load(path)
    initial = {
        b.id: b.initial_state().tolist() for b in patch.blocks.values() if isinstance(b, Dynamical)
    }
    modulators = {}
    for b in patch.blocks.values():
        if isinstance(b, Modulator):
            m = Modulator(b.id, **b.params.to_dict())
            m.reset(FS)
            modulators[b.id] = b64(m.process(PREFIX, {})["out"])
    prefix = patch.render(n_samples=PREFIX, sample_rate=FS, block_size=BLOCK)
    long = patch.render(seconds=STATS_SECONDS, sample_rate=FS, block_size=BLOCK)
    stats: dict[str, object] = {
        "seconds": STATS_SECONDS,
        "rms": [float(np.std(long[:, c])) for c in range(2)],
        "peak": [float(np.max(np.abs(long[:, c]))) for c in range(2)],
        "octave_bands_db": octave_bands_db(long[:, 0], FS),
        "band_centres_hz": BANDS_HZ,
        "safety_resets": patch.last_render.safety_resets if patch.last_render else {},
    }
    voices = [b for b in patch.blocks.values() if isinstance(b, Dynamical)]
    pitched = (
        len(voices) == 1
        and voices[0].params.pitch_lock
        and not any(c.dst_block == voices[0].id for c in patch.cables)
    )
    if pitched:
        v = voices[0]
        stats["pitch_hz"] = measure_pitch(
            long[FS // 2 :, 0], FS, v.entry.period_method, v.frequency_hz
        )
        stats["pitch_method"] = v.entry.period_method
        stats["nominal_hz"] = v.frequency_hz
    return {
        "patch": path.name,
        "sample_rate": FS,
        "block_size": BLOCK,
        "initial_states": initial,
        "modulators": {"n": PREFIX, "values_f64_b64": modulators},
        "prefix": {
            "n": PREFIX,
            "left_f64_b64": b64(prefix[:, 0]),
            "right_f64_b64": b64(prefix[:, 1]),
        },
        "stats": stats,
    }


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for path in sorted(PATCHES.glob("*.json")):
        data = export(path)
        (GOLDEN / path.name).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        print(f"{path.name}: rms {data['stats']['rms'][0]:.3f}")  # type: ignore[index]
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    main()
