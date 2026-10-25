import numpy as np

from chaotic_sound.rng import Mulberry32, stable_seed


def test_mulberry32_reference_values() -> None:
    # The JavaScript reference: mulberry32(1) → 0.6270739405881613, 0.002735721180215478, ...
    r = Mulberry32(1)
    assert [r.uniform() for _ in range(3)] == [
        0.6270739405881613,
        0.002735721180215478,
        0.5274470399599522,
    ]
    r = Mulberry32(1)
    assert r.next_uint32() == 2693262067


def test_normal_deviates_look_normal() -> None:
    r = Mulberry32(12345)
    z = np.array([r.normal() for _ in range(20_000)])
    assert abs(z.mean()) < 0.03 and abs(z.std() - 1) < 0.03


def test_stable_seed() -> None:
    assert stable_seed("osc") == 1818447832
    assert stable_seed("Rössler-1") == stable_seed("Rössler-1") < 2**31
