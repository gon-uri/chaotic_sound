"""Export golden vectors for cross-engine tests (ADR 0011, spec §6).

Usage (from ``lab/``; about a minute)::

    caffeinate -is uv run python scripts/export_golden.py

Sources:

- every demo patch in ``../examples/patches/``, rendered at 48 kHz;
- the fixtures in :data:`FIXTURES` below. They cover what the demos leave at one value:
  defaults (a patch with only ``system`` and cables), stereo, other sample rates, the linear
  amp curve, cents, an explicit seed, a pitch cable that starts high, a short ``once``
  envelope and the output soft clip. The script writes their patches to
  ``../examples/golden/patches/`` so that any engine can load them like any other patch.

For each source this writes ``../examples/golden/<name>.json`` with:

- ``patch``: the patch file, relative to ``examples/``; ``sample_rate`` and ``block_size``.
- ``initial_states``: the exact seeded initial state of each dynamical block (spec §4.2
  step 9). Engines must reproduce these to the last bit (up to 1 ulp from ``log``/``cos``).
- ``modulators``: windows of each modulator's output: the first :data:`PREFIX` samples, and
  a few samples around each of the first :data:`WRAPS` cycle edges k·T·fs (for ``once``: the
  end of the envelope and the held value). Exact for every shape except ``sine``, where
  1 ulp from ``cos`` is allowed.
- ``prefix``: the first samples of the rendered stereo output. Engines agree to about 1e-9
  (spec §6). ``ts_max_abs_error`` and ``ts_platform`` record what the TypeScript engine
  achieves. The TypeScript test writes them (``GOLDEN_RECORD=1``); this script keeps them
  while the prefix stays bit-identical and resets them to ``null`` when it changes.
- ``stats``: statistics of a longer render (level, level per segment, octave-band levels and
  safety resets), of the whole patch and, for patches with several voices, of each voice
  alone (``solo``: the other dynamical boxes and their cables removed). Each statistic has a
  ``value`` and a ``spread``: the standard deviation over an ensemble of renders that differ
  only in the voices' seeds (the reference and :data:`ENSEMBLE` variants). Chaos turns a
  seed change (an initial-condition change of 1e-6) into a fresh sample of the statistic,
  just as it does with round-off differences between engines, so the spread is the
  tolerance scale that spec §6 needs ("agree statistically").

Arrays are stored as base64 of little-endian float64 (compact and exact).
"""

from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from chaotic_sound.analysis.spectrum import measure_pitch
from chaotic_sound.blocks import Dynamical, Modulator
from chaotic_sound.patch import PATCH_FORMAT, PATCH_VERSION, Patch
from chaotic_sound.rng import stable_seed

LAB = Path(__file__).resolve().parents[1]
EXAMPLES = LAB.parent / "examples"
PATCHES = EXAMPLES / "patches"
GOLDEN = EXAMPLES / "golden"
FIXTURE_PATCHES = GOLDEN / "patches"
FS = 48_000
BLOCK = 512
PREFIX = 2048
WRAPS = 3  # modulator windows around k·T·fs for k = 1 … WRAPS
EDGE = 4  # samples on each side of a cycle edge
STATS_SECONDS = 8.0  # long enough to hear the end of 11_amp_envelope (6 s)
SEGMENT_S = 2.0
ENSEMBLE = 12  # seed variants per render for the spread of the statistics
BANDS_HZ = [31.25 * 2**k for k in range(10)]  # octave bands centred 31 Hz … 16 kHz

Doc = dict[str, Any]


def patch_doc(blocks: list[Doc], cables: list[tuple[str, str]]) -> Doc:
    """Build a patch document (spec §5) from blocks and (from, to) cable pairs."""
    return {
        "format": PATCH_FORMAT,
        "version": PATCH_VERSION,
        "blocks": blocks,
        "cables": [{"from": a, "to": b} for a, b in cables],
    }


def one_voice(params: Doc, *, control: Doc | None = None, port: str = "") -> Doc:
    """One dynamical box ``osc`` into the output, optionally driven by modulator ``mod``."""
    blocks = [{"id": "osc", "type": "dynamical", "params": params}, {"id": "out", "type": "output"}]
    cables = [("osc.out", "out.in")]
    if control is not None:
        blocks.insert(0, {"id": "mod", "type": "modulator", "params": control})
        cables.insert(0, ("mod.out", f"osc.{port}"))
    return patch_doc(blocks, cables)


@dataclass(frozen=True)
class Fixture:
    """A golden-only patch: what it covers, the patch and how to render it."""

    name: str
    about: str
    doc: Doc
    sample_rate: int = FS
    block_size: int = BLOCK


FIXTURES = [
    Fixture(
        "f01_defaults",
        "Only system and cables: every default (rossler, A3, A1–A5, pitch lock, seed, sine "
        "4 s, gain, volume) is compared; the lfo starts the pitch smoother at 0 and moves the "
        "lorenz knob away from its default, where pitch lock matters.",
        patch_doc(
            [
                {"id": "lfo", "type": "modulator"},
                {"id": "lorenz", "type": "dynamical", "params": {"system": "lorenz"}},
                {"id": "ross", "type": "dynamical"},
                {"id": "mix", "type": "sum"},
                {"id": "out", "type": "output"},
            ],
            [
                ("lfo.out", "ross.pitch"),
                ("lfo.out", "lorenz.param"),
                ("lorenz.out", "mix.in"),
                ("ross.out", "mix.in"),
                ("mix.out", "out.in"),
            ],
        ),
    ),
    Fixture(
        "f02_stereo",
        "Stereo: a non-default observable on the left, observable_right on the right.",
        one_voice({"system": "lorenz", "note": "E3", "observable": "x", "observable_right": "y"}),
    ),
    Fixture(
        "f03_linear_44k1",
        "The linear amp curve at amp 0.5, rendered at 44.1 kHz in AudioWorklet quanta.",
        one_voice({"system": "rossler", "amp_curve": "linear", "amp": 0.5}),
        sample_rate=44_100,
        block_size=128,
    ),
    Fixture(
        "f04_cents_96k",
        "A note with cents, rendered at 96 kHz.",
        one_voice({"system": "chua", "note": "C4", "cents": 37}),
        sample_rate=96_000,
    ),
    Fixture(
        "f05_seed",
        "An explicit seed instead of the hash of the block id, and a knob away from its "
        "default (the seeded perturbation still uses σ at the default knob).",
        one_voice({"system": "rikitake", "seed": 123_456_789, "param": 0.3}),
    ),
    Fixture(
        "f06_pitch_starts_high",
        "A pitch cable that starts at 1 (the smoother starts at the first value), a custom "
        "pitch range (C2–C4) and a loop that wraps every 0.37 s; a fast lfo sweeps the knob "
        "while the parameter slew time 2/f follows the gliding pitch.",
        patch_doc(
            [
                {
                    "id": "mod",
                    "type": "modulator",
                    "params": {"shape": "ramp_down", "period_s": 0.37},
                },
                {
                    "id": "lfo",
                    "type": "modulator",
                    "params": {"shape": "triangle", "period_s": 0.09},
                },
                {
                    "id": "osc",
                    "type": "dynamical",
                    "params": {"system": "rossler", "pitch_min": "C2", "pitch_max": "C4"},
                },
                {"id": "out", "type": "output"},
            ],
            [("mod.out", "osc.pitch"), ("lfo.out", "osc.param"), ("osc.out", "out.in")],
        ),
    ),
    Fixture(
        "f07_once_short",
        "A short once envelope (ramp_down, 0.5 s) on amp: silent after it ends.",
        one_voice(
            {"system": "duffing", "note": "D3"},
            control={"shape": "ramp_down", "period_s": 0.5, "mode": "once"},
            port="amp",
        ),
    ),
    Fixture(
        "f08_softclip",
        "Two voices with the same explicit seed (so identical) summed at full volume: their "
        "peaks (up to 1.6) drive the output soft clip.",
        patch_doc(
            [
                {"id": "a", "type": "dynamical", "params": {"system": "rossler", "seed": 7}},
                {"id": "b", "type": "dynamical", "params": {"system": "rossler", "seed": 7}},
                {"id": "mix", "type": "sum"},
                {"id": "out", "type": "output", "params": {"volume": 1.0}},
            ],
            [("a.out", "mix.in"), ("b.out", "mix.in"), ("mix.out", "out.in")],
        ),
    ),
]


def b64(x: np.ndarray) -> str:
    """Base64 of little-endian float64."""
    return base64.b64encode(np.ascontiguousarray(x, dtype="<f8").tobytes()).decode("ascii")


def octave_bands_db(x: np.ndarray, fs: float) -> list[float]:
    """Energy per octave band (dB relative to total) from one Hann-windowed FFT.

    The FFT is zero-padded to the next power of two, like the radix-2 FFT of the TypeScript
    test, so both engines measure on the same frequency grid.
    """
    nfft = 1 << (len(x) - 1).bit_length()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=nfft)) ** 2
    freqs = np.arange(len(spec)) * (fs / nfft)
    total = spec[1:].sum()
    out = []
    for fc in BANDS_HZ:
        band = (freqs >= fc / np.sqrt(2)) & (freqs < fc * np.sqrt(2))
        out.append(float(10 * np.log10(max(spec[band].sum() / total, 1e-30))))
    return out


def statistics(audio: np.ndarray, fs: float, channels: int) -> dict[str, list[float]]:
    """Level (standard deviation), level per segment and octave bands, channel after channel."""
    seg = round(SEGMENT_S * fs)
    out: dict[str, list[float]] = {"std": [], "segment_std": [], "bands_db": []}
    for c in range(channels):
        x = audio[:, c]
        out["std"].append(float(np.std(x)))
        out["segment_std"] += [float(np.std(x[i : i + seg])) for i in range(0, len(x), seg)]
        out["bands_db"] += octave_bands_db(x, fs)
    return out


def solo(doc: Doc, voice: str) -> Doc:
    """``doc`` with every dynamical box except ``voice`` removed, with their cables."""
    others = {b["id"] for b in doc["blocks"] if b["type"] == "dynamical" and b["id"] != voice}
    return {
        **doc,
        "blocks": [b for b in doc["blocks"] if b["id"] not in others],
        "cables": [
            c
            for c in doc["cables"]
            if c["from"].split(".")[0] not in others and c["to"].split(".")[0] not in others
        ],
    }


def reseeded(doc: Doc, k: int) -> Doc:
    """``doc`` for ensemble member ``k``: each voice's seed s becomes s + k·1000003 mod 2³¹.

    Voices that share a seed keep sharing one, so the patch keeps its structure.
    """
    out = copy.deepcopy(doc)
    for b in out["blocks"]:
        if b["type"] == "dynamical":
            params = b.get("params", {})
            seed = params.get("seed")
            seed = stable_seed(b["id"]) if seed is None else seed
            b["params"] = {**params, "seed": (seed + 1_000_003 * k) % 2**31}
    return out


def render(doc: Doc, fs: int, block: int, **length: Any) -> tuple[np.ndarray, Patch]:
    patch = Patch.from_dict(doc)
    return patch.render(sample_rate=fs, block_size=block, **length), patch


def stats_with_spread(
    doc: Doc, fs: int, block: int, channels: int, audio: np.ndarray | None = None
) -> dict[str, Any]:
    """Statistics of ``doc`` (rendered as ``audio`` if given) and their spread over the seeds."""
    if audio is None:
        audio = render(doc, fs, block, seconds=STATS_SECONDS)[0]
    value = statistics(audio, fs, channels)
    members = [value] + [
        statistics(render(reseeded(doc, k), fs, block, seconds=STATS_SECONDS)[0], fs, channels)
        for k in range(1, ENSEMBLE + 1)
    ]
    spread = {name: np.std([m[name] for m in members], axis=0, ddof=1).tolist() for name in value}
    return {"value": value, "spread": spread}


def modulator_windows(block: Modulator, fs: int) -> list[dict[str, Any]]:
    """Cut the first PREFIX samples and EDGE samples around each cycle edge k·T·fs."""
    edges = [round(k * block.params.period_s * fs) for k in range(1, WRAPS + 1)]
    m = Modulator(block.id, **block.params.to_dict())
    m.reset(fs)
    y = m.process(max(PREFIX, edges[-1] + EDGE + 1), {})["out"]
    starts = [(0, PREFIX)] + [(e - EDGE, e + EDGE + 1) for e in edges]
    return [{"start": a, "values_f64_b64": b64(y[a:b])} for a, b in starts]


def export(doc: Doc, patch_path: str, about: str, fs: int, block: int) -> dict[str, Any]:
    patch = Patch.from_dict(doc)
    initial = {
        b.id: b.initial_state().tolist() for b in patch.blocks.values() if isinstance(b, Dynamical)
    }
    modulators = {
        b.id: modulator_windows(b, fs) for b in patch.blocks.values() if isinstance(b, Modulator)
    }
    prefix = patch.render(n_samples=PREFIX, sample_rate=fs, block_size=block)
    long, long_patch = render(doc, fs, block, seconds=STATS_SECONDS)
    channels = 1 if np.array_equal(long[:, 0], long[:, 1]) else 2
    voices = [b for b in patch.blocks.values() if isinstance(b, Dynamical)]
    renders = [{"solo": None, **stats_with_spread(doc, fs, block, channels, long)}]
    if len(voices) > 1:
        renders += [
            {"solo": v.id, **stats_with_spread(solo(doc, v.id), fs, block, channels)}
            for v in voices
        ]
    last = long_patch.last_render
    stats: dict[str, Any] = {
        "seconds": STATS_SECONDS,
        "segment_s": SEGMENT_S,
        "channels": channels,
        "ensemble": ENSEMBLE,
        "band_centres_hz": BANDS_HZ,
        "safety_resets": last.safety_resets if last else {},
        "renders": renders,
    }
    pitched = (
        len(voices) == 1
        and voices[0].params.pitch_lock
        and not any(c.dst_block == voices[0].id for c in patch.cables)
    )
    if pitched:  # for engines that measure pitch (the TypeScript test does not)
        v = voices[0]
        stats["pitch_hz"] = measure_pitch(
            long[fs // 2 :, 0], fs, v.entry.period_method, v.frequency_hz
        )
        stats["pitch_method"] = v.entry.period_method
        stats["nominal_hz"] = v.frequency_hz
    return {
        "about": about,
        "patch": patch_path,
        "sample_rate": fs,
        "block_size": block,
        "initial_states": initial,
        "modulators": modulators,
        "prefix": {
            "n": PREFIX,
            "left_f64_b64": b64(prefix[:, 0]),
            "right_f64_b64": b64(prefix[:, 1]),
            "ts_max_abs_error": None,
            "ts_platform": None,
        },
        "stats": stats,
    }


def keep_typescript_record(data: dict[str, Any], path: Path) -> bool:
    """Copy the TypeScript record from the old file if the prefix is unchanged."""
    if not path.exists():
        return False
    old = json.loads(path.read_text(encoding="utf-8")).get("prefix", {})
    new = data["prefix"]
    if (old.get("left_f64_b64"), old.get("right_f64_b64")) != (
        new["left_f64_b64"],
        new["right_f64_b64"],
    ):
        return False
    new["ts_max_abs_error"] = old.get("ts_max_abs_error")
    new["ts_platform"] = old.get("ts_platform")
    return new["ts_max_abs_error"] is not None


def sources() -> list[tuple[str, Doc, str, str, int, int]]:
    """(name, patch, path relative to examples/, about, sample rate, block size) per golden."""
    demos = [
        (p.stem, json.loads(p.read_text(encoding="utf-8")), f"patches/{p.name}", "demo patch")
        for p in sorted(PATCHES.glob("*.json"))
    ]
    out = [(name, doc, rel, about, FS, BLOCK) for name, doc, rel, about in demos]
    for f in FIXTURES:
        out.append(
            (f.name, f.doc, f"golden/patches/{f.name}.json", f.about, f.sample_rate, f.block_size)
        )
    return out


def write_fixture_patches() -> None:
    FIXTURE_PATCHES.mkdir(parents=True, exist_ok=True)
    for f in FIXTURES:
        text = json.dumps(f.doc, indent=2, ensure_ascii=False) + "\n"
        (FIXTURE_PATCHES / f"{f.name}.json").write_text(text, encoding="utf-8")


def main() -> None:
    write_fixture_patches()
    stale = []
    for name, doc, rel, about, fs, block in sources():
        data = export(doc, rel, about, fs, block)
        path = GOLDEN / f"{name}.json"
        if not keep_typescript_record(data, path):
            stale.append(name)
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        level = data["stats"]["renders"][0]["value"]["std"][0]
        print(f"{name}: level {level:.3f}", flush=True)
    print(f"wrote {GOLDEN}")
    if stale:
        print(
            f"prefix changed or not yet measured for {', '.join(stale)}: record the TypeScript "
            "error with `GOLDEN_RECORD=1 npx vitest run packages/engine/test/golden.test.ts` "
            "(repository root)"
        )


if __name__ == "__main__":
    main()
