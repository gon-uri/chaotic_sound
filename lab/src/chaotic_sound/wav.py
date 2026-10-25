"""WAV file input/output (architecture layer 6)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.io import wavfile

WavFormat = Literal["pcm16", "float32"]


def write_wav(
    path: str | Path,
    audio: NDArray[np.float64],
    sample_rate: float,
    fmt: WavFormat = "pcm16",
) -> Path:
    """Write audio of shape ``(n,)`` or ``(n, channels)`` to a WAV file.

    ``pcm16`` (default, the most compatible) clips to [-1, 1] and rounds to 16-bit integers;
    ``float32`` stores the samples as they are. Returns the path written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(audio, dtype=np.float64)
    if fmt == "pcm16":
        data: NDArray[np.generic] = np.round(np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
    elif fmt == "float32":
        data = x.astype(np.float32)
    else:
        raise ValueError(f"unknown WAV format {fmt!r}")
    wavfile.write(path, round(sample_rate), data)
    return path


def read_wav(path: str | Path) -> tuple[NDArray[np.float64], int]:
    """Read a WAV file as float64 in [-1, 1] (integers are rescaled). Returns (audio, rate)."""
    rate, data = wavfile.read(Path(path))
    if data.dtype == np.int16:
        return data.astype(np.float64) / 32767.0, int(rate)
    if data.dtype == np.int32:
        return data.astype(np.float64) / 2147483647.0, int(rate)
    return data.astype(np.float64), int(rate)
