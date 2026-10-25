# 0005. Signal ranges, normalization and modulation semantics

- Status: Accepted (provisional, pending owner review). Partly from the owner's answers.
- Date: 2026-10-25

## Context

The owner asked that every range (amplitudes and parameters) be normalized to [0, 1], and that
v1 modulators output values that always stay in [0, 1].

## Decision

1. **Knobs** are in [0, 1]. Exceptions: pitch (note name, octave, cents), because musicians
   think in notes, and durations, in seconds, as the owner asked for envelope length.
2. **Control signals** are in [0, 1]. **Audio** is stereo, nominally in [-1, 1].
3. **Parameter mapping**: u ∈ [0, 1] maps linearly onto the chaotic range [p_min, p_max] chosen
   by the lab. A nonlinear mapping can be added later if a range needs it.
4. **Override**: a connected cable replaces its knob. Several cables into one control input are
   summed and clipped to [0, 1]. This is simple and predictable. A "depth/offset" model can come
   with the future modulator properties.
5. **Amplitude**: linear gain a ∈ [0, 1]. Each dynamical box is normalized to an **RMS of 0.25**
   (about -12 dBFS) at a = 1, using the catalog's mean and standard deviation at the current
   parameter, so systems sound roughly equally loud. A perceptual (dB) amp curve is a later
   option.
6. **Declicking**: a 5 ms one-pole smoother on every control value a dynamical box uses. Square
   and ramp modulators jump, and unsmoothed jumps click.
7. **Output safety**: soft clipper above 0.9 at the Output box, and a 5 Hz DC blocker on every
   dynamical box.

## Consequences

- With RMS normalization, a 3-box mix at full amp has an RMS of about 0.43 (uncorrelated
  sources), and the default output volume of 0.8 keeps it mostly below the clipper.
- Peak-based normalization was rejected: chaotic signals' peaks depend on rare excursions, while
  loudness follows RMS.
