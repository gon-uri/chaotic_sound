import numpy as np

from chaotic_sound.wav import read_wav, write_wav


def test_round_trip(tmp_path) -> None:
    rng = np.random.default_rng(0)
    audio = np.clip(rng.normal(scale=0.3, size=(1000, 2)), -1, 1)
    write_wav(tmp_path / "a.wav", audio, 48_000)
    back, rate = read_wav(tmp_path / "a.wav")
    assert rate == 48_000 and back.shape == audio.shape
    np.testing.assert_allclose(back, audio, atol=1 / 32767)
    write_wav(tmp_path / "b.wav", audio, 44_100, fmt="float32")
    back, rate = read_wav(tmp_path / "b.wav")
    assert rate == 44_100
    np.testing.assert_allclose(back, audio, atol=1e-7)


def test_pcm16_clips(tmp_path) -> None:
    write_wav(tmp_path / "c.wav", np.array([[2.0, -3.0]]), 8000)
    back, _ = read_wav(tmp_path / "c.wav")
    np.testing.assert_allclose(back, [[1.0, -1.0]])


def test_reads_8_bit_files(tmp_path) -> None:
    from scipy.io import wavfile

    wavfile.write(tmp_path / "u8.wav", 8000, np.array([0, 128, 255], dtype=np.uint8))
    back, _ = read_wav(tmp_path / "u8.wav")
    np.testing.assert_allclose(back, [-1.0, 0.0, 127 / 128])
