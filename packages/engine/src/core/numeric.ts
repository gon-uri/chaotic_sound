/** Small numeric helpers shared by the core and the adapters. */

/**
 * Round to the nearest integer, ties to even: Python's `round()` and NumPy's `rint`.
 * (`Math.round` sends ties up, so 2.5 → 3; this gives 2, as the reference does.)
 */
export function roundHalfEven(x: number): number {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}
