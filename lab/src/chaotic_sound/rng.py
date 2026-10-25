"""Portable seeded randomness (spec §4.2 step 9).

Engines in different languages must produce the same initial-condition perturbations, so we
avoid language-specific generators (NumPy's PCG64, JavaScript's ``Math.random``) and use:

- **seed hash**: CRC-32 (IEEE 802.3, as in zlib) of the block id's UTF-8 bytes, ``& 0x7FFFFFFF``;
- **mulberry32**, a 32-bit generator that is three lines of integer arithmetic in any language
  (JavaScript: ``Math.imul``, ``>>>``);
- **Box–Muller** for normal deviates, ``z = sqrt(−2 ln(1 − u₁)) · cos(2π u₂)``, consuming two
  uniforms per deviate.

The perturbation is ~1e-6 of the attractor size, so 1-ulp differences in ``log``/``cos``
between language runtimes are irrelevant.
"""

from __future__ import annotations

import math
import zlib

_MASK = 0xFFFFFFFF


def stable_seed(block_id: str) -> int:
    """Deterministic seed of a block id: CRC-32 of its UTF-8 bytes, masked to 31 bits."""
    return zlib.crc32(block_id.encode("utf-8")) & 0x7FFFFFFF


class Mulberry32:
    """The mulberry32 generator (public domain, Tommy Ettinger), bit-exact with its JS form.

    >>> r = Mulberry32(1)
    >>> [round(r.uniform(), 9) for _ in range(2)]
    [0.627073941, 0.002735721]
    """

    def __init__(self, seed: int) -> None:
        self._a = seed & _MASK

    def next_uint32(self) -> int:
        """Return the next raw 32-bit output."""
        self._a = (self._a + 0x6D2B79F5) & _MASK
        a = self._a
        t = ((a ^ (a >> 15)) * (a | 1)) & _MASK
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & _MASK)) & _MASK) ^ t
        return (t ^ (t >> 14)) & _MASK

    def uniform(self) -> float:
        """Return a uniform deviate in [0, 1)."""
        return self.next_uint32() / 4294967296.0

    def normal(self) -> float:
        """Return a standard normal deviate (Box–Muller, two uniforms per call)."""
        u1 = self.uniform()
        u2 = self.uniform()
        return math.sqrt(-2.0 * math.log(1.0 - u1)) * math.cos(2.0 * math.pi * u2)
