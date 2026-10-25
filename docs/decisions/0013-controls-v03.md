# 0013. Controls in v0.3: single-cable inputs, Control Sum, perceptual amp, pitch input, slew

- Status: Accepted (owner's answers, 2026-10-26, plus measures recommended by the Phase 1
  studies). Supersedes ADR 0005 point 4 (fan-in summing) and point 5 (linear amp).
- Date: 2026-10-26

## Decision

From the owner's answers:

1. **One cable per control input.** To combine controllers, the user patches them into a
   **Control Sum** box (`control_sum`). Its output is clip(gain · Σ inputs, 0, 1), with
   gain ∈ [0, 1]: gain = 0.5 averages two. The addition is always visible in the patch; it
   never happens implicitly. The audio Sum box's `in` and the Control Sum box's `in` are the
   only ports that accept several cables.
2. **Perceptual amp curve**, toggle `amp_curve` (default `"perceptual"`; `"linear"`
   available). Gain g = a^1.661, i.e. a^(1/(2·log₁₀2)). Each halving of the knob is −10 dB,
   which listeners hear as half as loud (Stevens' sone scale), so 0.5 sounds half as loud as
   1. a = 0 is silence.
3. **Pitch input** on dynamical boxes. When connected, it overrides note and cents. The
   control value q ∈ [0, 1] maps linearly in semitones from `pitch_min` to `pitch_max`
   (defaults A1 … A5, so q = 0.5 is A3). It is smoothed like the other controls (5 ms).

From the studies (`docs/studies/modulation.md`, `docs/studies/fifth-system-screening.md`):

4. **Parameter slew in system time.** The parameter smoother's time constant is
   max(5 ms, 2/f), with f the current pitch. Abrupt jumps (square or ramp modulators) then
   take at least about two oscillation periods. That removed Chua's safety resets under
   square modulators.
5. **Peak-limited level.** The level scale is min(0.25/σ(u), 0.8/π(u)), with π the 99.9th
   percentile of |x − μ|. Spiky signals (high crest factor, such as Rikitake) stay below the
   clipper; everything else keeps RMS 0.25.

From the code review:

6. **Portable seeding.**
   - The block id is hashed with CRC-32 (masked to 31 bits).
   - Random numbers come from mulberry32, and normal deviates from Box–Muller.

   This is bit-exact between Python and JavaScript, and documented in spec §4.2 step 9.
7. **Exact recurrences in the spec:**
   - the smoothers, the DC blocker and the modulator phase;
   - flush-to-zero for filter states;
   - a cap on RK4 sub-steps;
   - sanitizing non-finite control values.

## Consequences

- Patches from v0.2 that fed several cables into one control input are now rejected with a
  message suggesting a `control_sum` box. No committed patch did this.
- The pitch input makes the time scale vary every sample. The kernel already supported that.
  At high pitches aliasing grows (`docs/studies/aliasing.md`).
- The Sum gain and the Output volume are still linear. Whether they should use the
  perceptual curve too is listed in `docs/REVIEW.md`.
