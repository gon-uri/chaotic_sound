# 0015. Tonality knob and input: phase-tracked harmonic resynthesis (default 0.3)

- Status: Accepted (owner's request, 2026-10-26: "Go for implementation D (harmonic
  resynthesis), make it also an available input. Lets make the default value for that knob
  to be 30% (0.3)"). The phase-tracking refinement and the mix law are Claude's choices,
  listed in `docs/REVIEW.md` B6.
- Date: 2026-10-26
- Spec: v0.5, §4.2 step 7 ("Tonality"). Background: `docs/ideas/tonal-knob.md`.

## Context

Tuned attractors are noisy: only 16–80% of their power lies on the harmonics of the note.
The owner wanted a knob from the raw attractor (0) to a tonal sound (1) whose tonal part
comes from the attractor's own spectrum, so it stays unique to each system. The offline
prototype compared four designs. Harmonic resynthesis (D) was the only one that reached full
harmonicity while keeping each attractor's brightness.

## Decision

A `tonality` knob and control input on the dynamical box, default **0.3**, smoothed like
`amp`. Per channel:

1. Split the level-normalized signal r into 8 harmonic bands [k − ½, k + ½]·f_a. Each band
   is heterodyned to baseband and low-passed by a 4th-order Butterworth at f_a/2, built from
   two state-variable filters in trapezoidal (TPT) form so it stays well-behaved when f_a
   moves. f_a is the fundamental actually heard; it differs from the note when pitch lock
   is off.
2. Smooth each band's power and complex amplitude with a time constant from 2 ms (τ = 0) to
   2 s (τ = 1), starting as a running mean so the sound appears at once.
3. Replace each band by one partial with the band's smoothed power and **the band's smoothed
   phase**, and mix: m = (1 − τ)^0.75·r + τ^0.75·t. The amp curve and the DC blocker
   follow, so amp envelopes are never smeared by the smoothing.
4. A **coherence floor**: the phase is normalized by max(|v_k|, 0.1·(1 − τ)·√p_k), so a band
   whose smoothed amplitude passes near zero fades out instead of flipping its partial's
   phase in one sample, which would tick.
5. The step is skipped only once the smoothed tonality has reached 0 (so turning it down
   never clicks), and it restarts from a clean state when it comes back on.

Eight harmonics hold more than 99.9% of the power of every v1 system over its whole knob
range (more than 99.99% at the default knob). Time rescaling keeps the spectral shape fixed
in units of f₀, so this holds at every note.

## Why the phase tracking (a refinement of the prototype)

The prototype put partial k at the fixed phase kθ. At intermediate settings those partials
beat against the raw signal, because the attractor's own phase drifts by a few cents relative
to θ. At τ = 0.3 the 50 ms level wobbled by 2–4 dB (Rössler 3.3 dB), against 0.4–0.9 dB for
the raw attractor. Letting each partial follow its band's smoothed phase removes the beating:
the wobble stays at 0.3–1.6 dB.

Measured on all five systems at A3, over 10 seeds (`lab/tests/test_tonality.py`, the
design study and the independent verification):

| | raw (τ = 0) | τ = 0.3 (default) | τ = 1 |
|---|---|---|---|
| Harmonic share of the power | 0.18–0.80 | 0.33–0.91 | 0.88–1.00 (Lorenz 0.88–0.99) |
| Level change | | within ±1.2 dB | within ±1.2 dB |
| Pitch error (catalog estimator) | ≤ 5 c | ≤ 6 c; Lorenz about 8–10 c sharp | ≤ 5 c |

## Fixes after the independent verification (2026-10-26)

A third implementation written from the spec alone, and an audio and real-time review,
found (all confirmed, none refuted):

| Finding | Fix |
|---|---|
| **High:** after a fast pitch drop (a live note change, a pitch cable) the biquads' memories overshot: up to +21 dB and output clipping (C8 → A1), and +13 dB held for 1–2 s at τ = 1 | Band filter rebuilt as TPT state-variable sections (same response, modulation-safe). C8 → A1 now stays within 1.3× the steady level |
| Turning tonality to 0 live stepped from the mix to the raw signal in one sample (a click) | The step is skipped only once τ_s = 0 |
| Phase flips of near-zero bands at the default 0.3 (sporadic ticks, Chua and Duffing) | Coherence floor 0.1·(1 − τ)·√p_k; ticks back to the raw attractor's level, no level change at τ = 1 |
| Turning tonality on again resumed stale state; a non-finite band state silently removed a partial | Fresh state on every switch-on; the safety guard now also covers the tonal state |
| The ADR's ranges came from one seed; the "99.99%" claim failed at the knob ends | Table and claim restated over 10 seeds and the whole range (above) |

Each fix has a test that fails on the previous code (`lab/tests/test_tonality.py`,
`packages/engine/test/tonality.test.ts`). Golden vectors were regenerated.

## Consequences

- **The default sound changed.** Every patch is a little more pitched. Golden vectors and
  demos were regenerated.
- **Cost.** About 0.9% of a core per voice, at any note (TypeScript, M1). That roughly
  doubles a voice's cost at A3 and adds about 25% at A6.
- **Known properties** (for the owner to judge by ear):
  - At τ = 1 the partials keep the attractor's slow phase wander. The tone is steady but
    alive, not a static stack of sines; harmonicity is 0.90–1.00.
  - The band filters leak −24 dB into neighbouring bands. That adds under 1 dB of power and
    slightly brightens the darkest systems (Chua).
  - Lorenz's broad spectrum reads up to about 10 cents sharp at intermediate settings by the
    peak-centroid estimator.
- Partials fade out between 0.40·fs and 0.45·fs, so tonality never adds aliasing.
- Stereo boxes have one tonality state per channel. A knob at 0 with no cable skips the
  computation; the output is then exactly the raw signal.

## Alternatives considered

- **Crossfade with a sine (A)**: the tonal end is always a sine. Rejected by the owner's
  reasoning and confirmed by the prototype.
- **Comb or resonator filtering (B, C)**: the owner's "multiply the spectrum" idea done as
  filtering. It darkens toward a sine because the attractors' harmonic lines are weak.
- **Magnitude-only resynthesis (the prototype's D)**: perfectly in tune and static at
  τ = 1, but it beats at intermediate settings, including the default.
- **A slower phase reference (≥ 0.1–0.5 s)**: it trims Lorenz's pitch offset at τ = 0.3 but
  brings the beating back (wobble up to 2 dB). Rejected.
- **Equal-power (√) or linear mix laws**: the levels moved by up to +2.7 dB (√, coherent
  systems) or −1.7 dB (linear, incoherent ones). The exponent 0.75 keeps all five within
  about ±1.2 dB.
- **A second "brightness" knob**: not requested; possible later (`docs/ideas/tonal-knob.md`).
