"""Render the Phase 1 demo patches to WAV, with spectrograms and a measurement report.

Usage (from ``lab/``)::

    uv run python scripts/render_demos.py

Writes the patch files to ``../examples/patches/`` (committed: they double as cross-engine
test fixtures) and the audio, plots and ``report.md`` to ``outputs/demos/`` (not committed).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from chaotic_sound.analysis.spectrum import measure_pitch
from chaotic_sound.blocks import Dynamical
from chaotic_sound.catalog import load_default_catalog
from chaotic_sound.patch import Patch
from chaotic_sound.pitch import cents_between, note_to_hz
from chaotic_sound.systems import list_systems
from chaotic_sound.wav import write_wav

LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "outputs" / "demos"
PATCHES = LAB.parent / "examples" / "patches"
FS = 48_000


@dataclass
class Demo:
    """A named patch, its render length and a one-line description."""

    name: str
    description: str
    seconds: float
    build: Callable[[], Patch]


def voice(system: str, note: str = "A3") -> Callable[[], Patch]:
    def build() -> Patch:
        p = Patch()
        p.add_block("dynamical", "osc", system=system, note=note)
        p.add_block("output", "out", volume=1.0)
        p.connect("osc.out", "out.in")
        return p

    return build


def owner_example() -> Patch:
    """Build the owner's first idea: LFOs on a Rössler parameter and a Lorenz amplitude."""
    p = Patch()
    p.add_block("modulator", "lfo_param", shape="sine", period_s=8.0)
    p.add_block("modulator", "lfo_amp", shape="triangle", period_s=4.0)
    p.add_block("dynamical", "rossler", system="rossler", note="A3")
    p.add_block("dynamical", "lorenz", system="lorenz", note="E3")
    p.add_block("sum", "mix", gain=0.8)
    p.add_block("output", "out", volume=0.9)
    p.connect("lfo_param.out", "rossler.param")
    p.connect("lfo_amp.out", "lorenz.amp")
    p.connect("rossler.out", "mix.in")
    p.connect("lorenz.out", "mix.in")
    p.connect("mix.out", "out.in")
    return p


def lorenz_sweep(pitch_lock: bool) -> Callable[[], Patch]:
    def build() -> Patch:
        p = Patch()
        p.add_block("modulator", "ramp", shape="ramp_up", period_s=20.0, mode="once")
        p.add_block("dynamical", "lorenz", system="lorenz", note="A3", pitch_lock=pitch_lock)
        p.add_block("output", "out", volume=1.0)
        p.connect("ramp.out", "lorenz.param")
        p.connect("lorenz.out", "out.in")
        return p

    return build


def chua_square() -> Patch:
    """Square modulator: Chua jumps between the bottom and the top of its range."""
    p = Patch()
    p.add_block("modulator", "sq", shape="square", period_s=3.0)
    p.add_block("dynamical", "chua", system="chua", note="D3")
    p.add_block("output", "out", volume=1.0)
    p.connect("sq.out", "chua.param")
    p.connect("chua.out", "out.in")
    return p


def duffing_drive() -> Patch:
    p = Patch()
    p.add_block("modulator", "lfo", shape="sine", period_s=12.0)
    p.add_block("dynamical", "duffing", system="duffing", note="G2")
    p.add_block("output", "out", volume=1.0)
    p.connect("lfo.out", "duffing.param")
    p.connect("duffing.out", "out.in")
    return p


def chord() -> Patch:
    """Build a 'chaotic chord' (A major over two octaves, all five systems), LFO on Lorenz."""
    p = Patch()
    p.add_block("modulator", "lfo", shape="triangle", period_s=10.0)
    p.add_block("dynamical", "rossler", system="rossler", note="A2", amp=0.9)
    p.add_block("dynamical", "chua", system="chua", note="E3", amp=0.8)
    p.add_block("dynamical", "lorenz", system="lorenz", note="A3", amp=0.8)
    p.add_block("dynamical", "rikitake", system="rikitake", note="C#4", amp=0.7)
    p.add_block("dynamical", "duffing", system="duffing", note="E4", amp=0.7)
    p.add_block("sum", "mix", gain=0.6)
    p.add_block("output", "out", volume=0.9)
    p.connect("lfo.out", "lorenz.param")
    for src in ("rossler", "chua", "lorenz", "rikitake", "duffing"):
        p.connect(f"{src}.out", "mix.in")
    p.connect("mix.out", "out.in")
    return p


def pitch_glide() -> Patch:
    """Pitch input: a slow triangle sweeps Rikitake from A1 to A5 and back (pitch lock on)."""
    p = Patch()
    p.add_block("modulator", "glide", shape="triangle", period_s=12.0)
    p.add_block("dynamical", "rikitake", system="rikitake", pitch_min="A1", pitch_max="A5")
    p.add_block("output", "out", volume=1.0)
    p.connect("glide.out", "rikitake.pitch")
    p.connect("rikitake.out", "out.in")
    return p


def control_sum_vibrato() -> Patch:
    """Control Sum: a slow sine plus a fast small sine on Chua's parameter."""
    p = Patch()
    p.add_block("modulator", "slow", shape="sine", period_s=8.0)
    p.add_block("modulator", "fast", shape="triangle", period_s=0.25)
    p.add_block("control_sum", "both", gain=0.6)
    p.add_block("dynamical", "chua", system="chua", note="E3")
    p.add_block("output", "out", volume=1.0)
    p.connect("slow.out", "both.in")
    p.connect("fast.out", "both.in")
    p.connect("both.out", "chua.param")
    p.connect("chua.out", "out.in")
    return p


def amp_envelope() -> Patch:
    """Perceptual amp curve: a 6 s once ramp-down on Lorenz amp fades evenly to silence."""
    p = Patch()
    p.add_block("modulator", "env", shape="ramp_down", period_s=6.0, mode="once")
    p.add_block("dynamical", "lorenz", system="lorenz", note="D3")
    p.add_block("output", "out", volume=1.0)
    p.connect("env.out", "lorenz.amp")
    p.connect("lorenz.out", "out.in")
    return p


def twins() -> Patch:
    """Two identical Rössler boxes (different seeds): in unison, then chaos pulls them apart."""
    p = Patch()
    p.add_block("dynamical", "twin_a", system="rossler", note="A3")
    p.add_block("dynamical", "twin_b", system="rossler", note="A3")
    p.add_block("sum", "mix", gain=0.6)
    p.add_block("output", "out", volume=1.0)
    p.connect("twin_a.out", "mix.in")
    p.connect("twin_b.out", "mix.in")
    p.connect("mix.out", "out.in")
    return p


DEMOS: list[Demo] = [
    *[
        Demo(f"01_voice_{s}", f"{s} alone at A3, default parameter", 6.0, voice(s))
        for s in list_systems()
    ],
    Demo("02_owner_example", "LFO→Rössler param, LFO→Lorenz amp, Sum, Output", 20.0, owner_example),
    Demo("03_lorenz_sweep_locked", "Lorenz ρ ramps across its range in 20 s; pitch lock ON",
         20.0, lorenz_sweep(True)),
    Demo("03_lorenz_sweep_free", "Same sweep with pitch lock OFF: the pitch rises ~an octave",
         20.0, lorenz_sweep(False)),
    Demo("04_chua_square", "Square LFO flips Chua between both ends of its range", 12.0,
         chua_square),
    Demo("05_duffing_drive", "Slow sine on the Duffing drive amplitude γ", 24.0, duffing_drive),
    Demo("06_chaotic_chord", "Rössler A2, Chua E3, Lorenz A3, Rikitake C#4, Duffing E4", 20.0,
         chord),
    Demo("07_twins", "Two identical Rössler boxes drifting apart (sensitive dependence)", 12.0,
         twins),
    Demo("09_pitch_glide", "Pitch input: Rikitake glides A1 → A5 → A1 in 12 s", 12.0,
         pitch_glide),
    Demo("10_control_sum", "Control Sum: slow sine + fast triangle on Chua's α", 16.0,
         control_sum_vibrato),
    Demo("11_amp_envelope", "Perceptual amp: Lorenz fades out evenly over 6 s", 7.0,
         amp_envelope),
]  # fmt: skip


def spectrogram(audio: np.ndarray, path: Path, title: str) -> None:
    """Save a log-frequency spectrogram of the left channel."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.specgram(audio[:, 0], NFFT=4096, Fs=FS, noverlap=3072, cmap="magma", vmin=-140)
    ax.set_yscale("log")
    ax.set_ylim(40, 12_000)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("frequency (Hz)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def pitch_of(patch: Patch, audio: np.ndarray) -> tuple[float, float] | None:
    """Measured frequency and target of a single, unmodulated-pitch voice (catalog's method)."""
    voices = [b for b in patch.blocks.values() if isinstance(b, Dynamical)]
    if len(voices) != 1 or any(c.dst_port == "pitch" for c in patch.cables):
        return None
    block = voices[0]
    if not block.params.pitch_lock:
        return None  # the pitch drifts on purpose
    f = measure_pitch(audio[FS // 2 :, 0], FS, block.entry.period_method, block.frequency_hz)
    return f, block.frequency_hz


def timbre_vs_pitch() -> np.ndarray:
    """Rössler at A2, A3, A4 and A5, 3 s each: same shape, different speed."""
    parts = []
    for note in ("A2", "A3", "A4", "A5"):
        p = voice("rossler", note)()
        parts.append(p.render(seconds=3.0, sample_rate=FS))
    return np.vstack(parts)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PATCHES.mkdir(parents=True, exist_ok=True)
    catalog = load_default_catalog()
    lines = [
        "# Demo renders",
        "",
        f"Catalog generated {catalog.metadata.get('generated')}. Sample rate {FS} Hz, 16-bit WAV.",
        "",
        "| Demo | What | Length | RMS | Peak | Pitch error | Safety resets | Render time |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for demo in DEMOS:
        patch = demo.build()
        patch.save(PATCHES / f"{demo.name}.json")
        start = time.time()
        audio = patch.render(seconds=demo.seconds, sample_rate=FS)
        elapsed = time.time() - start
        write_wav(OUT / f"{demo.name}.wav", audio, FS)
        spectrogram(audio, OUT / f"{demo.name}.png", f"{demo.name}: {demo.description}")
        pitch = pitch_of(patch, audio)
        pitch_txt = f"{cents_between(*pitch):+.1f} cents" if pitch else "n/a"
        resets = patch.last_render.safety_resets if patch.last_render else {}
        lines.append(
            f"| `{demo.name}` | {demo.description} | {demo.seconds:.0f} s | "
            f"{np.std(audio[:, 0]):.3f} | {np.max(np.abs(audio)):.2f} | {pitch_txt} | "
            f"{sum(resets.values())} | {elapsed:.1f} s |"
        )
        print(lines[-1])

    tv = timbre_vs_pitch()
    write_wav(OUT / "08_rossler_A2_to_A5.wav", tv, FS)
    spectrogram(tv, OUT / "08_rossler_A2_to_A5.png", "Rössler at A2, A3, A4, A5 (3 s each)")
    lines += [
        "",
        "`08_rossler_A2_to_A5.wav`: Rössler at A2, A3, A4 and A5 (3 s each), rendered by the "
        "script, not a patch — the waveform shape is the same at every pitch.",
        "",
        f"Targets: A3 = {note_to_hz('A3'):.2f} Hz. Pitch error is measured with the catalog's "
        "method for that system (peak centroid, return time, or drive) on the rendered audio.",
    ]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
