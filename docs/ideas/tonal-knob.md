# Idea: a "tonality" knob (raw attractor → tonal)

- Status: **idea, prototyped offline** (2026-10-26). Not part of the spec yet. Proposed by the
  owner; analysis and prototype by Claude.
- Prototype: `lab/scripts/studies/tonal_prototype.py`. It writes WAVs and `metrics.md` to
  `lab/outputs/studies/tonal/`, with all five systems at A3 and τ = 0, 0.5, 1 for each method.

## The owner's idea

The attractor voices are noisy even when tuned, because their spectrum is wide. The owner likes
that, but wants a knob from 0 (the full attractor) to 1 (fully tonal):

- A plain crossfade with a pure tone at the main frequency would always end up sounding like a
  sine.
- Better: build the tonal part from the attractor's own spectrum. Multiply the spectrum by a
  set of harmonics k·f₀ with decaying amplitudes, so each attractor's spectrum sets how
  strongly each harmonic is present. The tonal sound is then unique to each attractor.
- Perhaps it can be done efficiently as filtering (a convolution) instead of in Fourier space.

## What the measurements say

The prototype measures three things on each output:
- the **harmonicity**: the share of the power within ±1% of the harmonics;
- the **fundamental's share** of that harmonic power;
- the **brightness**: the spectral centroid, in multiples of f₀.

Values at τ = 1 (raw values at τ = 0 in brackets):

| System | A: sine crossfade | B: resonator bank | B2: resonators + brightness | **D: harmonic resynthesis** |
|---|---|---|---|---|
| Lorenz [0.16 / 0.92 / 1.07] | 1.00 / 1.00 / 1.00 | 0.93 / 0.99 / 1.01 | 0.84 / 0.80 / 1.35 | **1.00 / 0.91 / 1.10** |
| Rössler [0.80 / 0.98 / 1.05] | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.01 | 0.99 / 0.87 / 1.26 | **1.00 / 0.96 / 1.05** |
| Chua [0.33 / 1.00 / 0.97] | 1.00 / 1.00 / 1.00 | 0.98 / 1.00 / 1.00 | 0.92 / 1.00 / 1.00 | **1.00 / 0.99 / 1.01** |
| Rikitake [0.33 / 0.86 / 1.26] | 1.00 / 1.00 / 1.00 | 0.97 / 0.98 / 1.03 | 0.93 / 0.75 / 1.47 | **1.00 / 0.81 / 1.24** |
| Duffing [0.37 / 0.99 / 0.92] | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 | 0.98 / 0.99 / 1.02 | **1.00 / 0.93 / 1.07** |

(Each cell: harmonicity / fundamental share / centroid.)

The key finding is that **the noise lies between the harmonics, not in missing harmonics.**
After tuning, the attractors' harmonic envelopes are dark: each harmonic band is 5–20 dB weaker
than the one below it (Lorenz about −10 dB per harmonic, Chua −23 dB at k = 2, Rössler and
Rikitake about −5 dB). As a result:

- **A (crossfade with a sine)** becomes a pure sine, as the owner expected.
- **B (multiply the spectrum by a harmonic comb).** This is the owner's idea, implemented as
  filtering: a bank of 2-pole resonators at k·f₀ whose sharpness grows with τ.
  - It becomes tonal (93–100%).
  - It also **darkens toward a sine** (centroid 1.00–1.03), because it keeps only the energy
    that already sits on the weak harmonic lines.
  - Decaying harmonic weights would make it darker still.
- **B2** compresses the attractor's envelope (harmonic k gets energy ∝ E_k^β, with β = 0.5).
  - It is brighter while still shaped by the attractor.
  - But boosting nearly empty high bands amplifies noise: uncapped, Lorenz's harmonicity fell
    to 0.16, so the gains had to be capped.
- **D (harmonic resynthesis)** moves the energy of each harmonic band [k−½, k+½]·f₀, *including
  the noise between harmonics*, onto a clean partial at k·f₀.
  - It is fully tonal (1.00).
  - It **keeps each attractor's own brightness and harmonic balance**: centroid 1.10 vs 1.07
    raw for Lorenz, 1.24 vs 1.26 for Rikitake.
  - This is the closest to the owner's intent: a tonal sound unique to each attractor.

The C variant (a damped feedback comb, Karplus–Strong style) is the cheapest. It behaves like B,
but the knob response is very uneven: it stays noisy until τ ≈ 0.9, then rings like a string.

## Assessment

**It is a good idea**, for several reasons:
1. A noise ↔ tone continuum is one of the most expressive controls in synthesis. Physical
   models (bow pressure, breath noise) and resonant filters are loved for exactly this.
2. It keeps the project's identity: the tonal end is still the attractor, not a generic
   oscillator.
3. It is educational:
   - spectra and Fourier series ("what makes a sound pitched?");
   - the difference between harmonic lines and broadband noise;
   - why chaotic signals have continuous spectra (decay of correlations).

**It is very feasible**, with design D as the core:

- **DSP.** One phase accumulator θ(t) = 2π∫f dt follows the pitch, so it also works with the
  pitch input. For each harmonic k ≤ K (K ≈ 16–32, below about 8 kHz):
  - c_k = LPF(x·e^{−ikθ}) (heterodyne plus a 4th-order low-pass at f₀/2);
  - m_k = smooth(|c_k|), with a time constant τ_env growing with the knob;
  - tonal = Σ 2·g_k·m_k·cos(kθ).

  The partial phases are locked to θ, so the tonal waveform is periodic. Brightness, if
  wanted, is g_k = (m̄_k/m̄₁)^(β−1), with m̄ taken from a long-term average or tabulated in the
  catalog; on clean partials it does not amplify noise.
- **The knob.** τ ∈ [0, 1] sets the mix and the envelope smoothing together: τ_env from about
  2 ms (raw-like fluctuations) to about 2 s (stable partials). τ = 0 is bit-identical to today.
  A refinement: morph the raw signal into the tonal one by narrowing each band's phase and
  magnitude bandwidth, with no crossfade (energy-preserving, no beating). It is more complex
  and can be a second step.
- **Cost.** About 40 flops per partial per sample, so about 1000–1500 flops per sample at
  K = 24–32. That is 2–4× the cost of the ODE itself, still cheap: about 1–1.5% of a core per
  box at A3 in JavaScript (`docs/studies/cost.md`). It needs no FFT and adds no latency, so it
  is real-time safe, and it ports cleanly to C++.
- **Effort.** About 2–3 days:
  1. a spec section (knobs `tonality`, optionally `brightness`);
  2. the Python reference and tests (harmonicity vs τ, level, block-size independence);
  3. the TypeScript port and golden vectors;
  4. UI knobs.
- **Risks:**
  - level matching between raw and tonal (use RMS-matched gains, tabulated per system);
  - beating at intermediate mixes, because raw and tonal partials are not phase-coherent
    (addressed by the morph refinement);
  - how the result is perceived. The owner should listen to
    `lab/outputs/studies/tonal/*_D_resynth_*.wav` against `*_B_resonators_*` and `*_A_sine_*`.

**Where it lives:**
- first, a `tonality` knob on the Dynamical box, default 0 so today's sound is unchanged;
- later, the same DSP module as a standalone "Harmonizer" effect box with its own note
  setting, applicable to any audio, which fits the roadmap's filter and effect boxes.

## Open questions for the owner

1. Listen to the prototype WAVs. Is D's tonal end the character you imagined?
2. One knob (tonality) or two (tonality + brightness)?
3. Should the knob also be a control input (to modulate tonality with an LFO)? It is easy, and
   very expressive.
