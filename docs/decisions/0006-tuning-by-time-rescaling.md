# 0006. Tuning by time rescaling; period from the spectral peak; pitch lock

- Status: Accepted (provisional, pending owner review). Point 2 (the definition of P) and point 3
  (one P per observable) are refined by ADR 0010.
- Date: 2026-10-25

## Context

The owner wants each dynamical box tuned so that its "main frequency" matches a note. They
defined that frequency as the most prominent one in the spectrum, or possibly the one related
to the most-visited unstable periodic orbit. The theory is in `../math/tuning.md`.

## Decision

1. **Tuning = time rescaling.** Integrate dx/dτ = F(x) with τ = k·t and k = P·f₀, where P is
   the characteristic period in system time. The timbre does not depend on pitch.
2. **P is the period of the dominant peak of the observable's power spectrum** (Welch estimate
   with parabolic peak interpolation), measured by the lab. Two cross-checks are recorded in the
   catalog:
   - the mean return time between local maxima;
   - the dysts `period` value.
   For forced systems (Duffing), P is the drive period 2π/ω, which is exact. The
   unstable-periodic-orbit definition is kept as a future research item.
3. **P depends on the observable.** For example, Lorenz's z loops with P ≈ 0.75, while dysts
   lists 1.50, an octave lower. The catalog stores P per observable, and each system has a
   default observable chosen for pitch clarity.
4. **Integration resolution is defined in steps per period**: h_max = P/N, with N = 256 by
   default, so the cost per sample is ⌈N·f₀/fs⌉ RK4 steps whatever the system. The lab checks
   per system that N is high enough.
5. **Pitch lock** (default on): as the parameter moves, k(t) = P(u(t))·f₀, using the catalog
   table P(u). The note stays put and only the timbre changes. With the lock off, k uses P at
   the default parameter, so the pitch drifts naturally.

## Consequences

- Parameter modulation makes the system non-autonomous ("forced"), as the owner noted. For
  slow modulation the trajectory follows the attractor adiabatically. Fast modulation is
  genuine forcing and can produce new behavior; that is a feature to explore, not a bug.
- If the spectral peak jumps between features within the range, P(u) jumps, and pitch lock
  would glitch. The lab must detect jumps and either smooth across them or shrink the range.
