<!-- Study written by an AI agent (2026-10-25), revised after review for engine v0.3 and after a second check (2026-10-26); numbers from lab/scripts/studies/modulation.py. Needs owner review. -->

# How fast can a parameter be modulated?

**Numbers from engine v0.3 and `catalog/systems.json` generated 2026-10-25T20:00:03+00:00.**
Systems: Lorenz (ρ ∈ [24.8, 69.4]), Chua (α ∈ [13.7, 18.05]), Rössler (c ∈ [4.24, 8.82]) and
the Rikitake dynamo (μ ∈ [0.51, 1.8]), each with its default observable (z, y, x, z). Duffing
appears only in the square-jump reset probes. Its period is the drive period 2π/ω, which does
not depend on γ, so pitch lock is exact and question (a) does not apply. Questions (b) and (c)
under smooth modulation were not tested for it.

Script: `lab/scripts/studies/modulation.py`. Run it from `lab/` with
`caffeinate -is uv run python scripts/studies/modulation.py`. It takes about 2 minutes on an
M1 Pro (114 s in the last run, with 5 worker processes). The numbers are in
`lab/outputs/studies/modulation/results.json`. The figures `fig1`–`fig6` and `wav/*.wav` are in
the same folder; the script regenerates them and they are gitignored.

## Changes after review (and for v0.3)

- **Engine v0.3.** Thomas is replaced by Rikitake, and the v0.3 API is used. The parameter
  slew τ = max(5 ms, 2/f₀) is now in the engine. The v0.2 behaviour (5 ms only) is emulated
  for comparison by setting `PARAM_SLEW_PERIODS = 0` at run time; the engine code is not
  changed.
- **Escape statistics.**
  - The Chua probe now pools 9 seeds (540 up-jumps per note). The v0.2 rates are 6.3 % at A0
    and 1.5 % at A1, in line with the reviewer's 7.1 % and 1.8 %.
  - The default modulator (T = 4 s) with square and ramp shapes is tested directly.
  - The mitigation tested is now exactly the engine's slew (a single one-pole), not an extra
    filter in series.
- **Pitch estimator.**
  - A time-warp calibration (known ±50 c FM) measures the gain of the centroid estimator:
    0.71 for Lorenz, 0.85–0.91 for the others, below 0.5 at 100 Hz.
  - A loop-rate estimator (gain ≈ 1 up to 20 Hz) is reported next to it.
  - Pitch errors are now quoted as the range of the two estimators, with the centroid divided
    by its gain.
- **Up/down split.**
  - Bins are taken by the phase of the *slewed* u, using the exact one-pole lag, so up- and
    down-sweep bins at equal u are paired correctly.
  - The sentence "phase-shifted, not a small lag" is withdrawn. Lorenz is hysteresis-dominated
    up to r = 0.12.
  - Hysteresis is no longer claimed for the other systems: Chua's and Rössler's symmetric
    parts are as large as their hysteresis, and Rikitake's is larger.
- **Fair comparisons.**
  - The error of the static reference itself is measured with a second seed.
  - Static and modulated attractor distances use the same quantile (99th percentile).
  - The slow-rate normalization error uses the mean of s before the DC blocker.
  - Levels are relative to the static RMS at the same u. This matters since v0.3's level can
    be peak-limited.
- **Smaller fixes.**
  - The note-dependence of the jumps is stated case by case, and the Lorenz 1 → 0 tail is
    reported.
  - Low-note, full-depth smooth drives on Chua are tested.
  - The badge is shape-aware.
  - The Chua-x count is corrected and re-measured.
  - The stale numba-cache issue and its workaround are removed.
- **Second check (2026-10-26).** The re-run reproduces every earlier number in `results.json`
  exactly. The script only adds new fields: the loop-rate offset over the rising and the
  falling half of the sweep, the jump errors without the jumps that reset, the number of such
  jumps, and the Chua x and z offsets under two other normalizations. The text changes are:
  - The Chua catalog recommendation names the fix, gives the offset that each variant leaves,
    and corrects the range to α ≈ 13.7–14.4.
  - The Rikitake sharp offset is quoted with both estimators (about +10 to +50 c) and with its
    rising/falling asymmetry.
  - The jump table reports the 3 safety resets in the Chua A1 v0.2 runs, with the numbers for
    the reset-free jumps. The Lorenz A1 v0.2 settling time follows the stated rule (> 64).
  - The ramp badge no longer quotes a chirp size, and the 6 102 jumps are split into square
    jumps and ramp edges instead of being called full-range.
  - Limitations now state that the gain correction also inflates the floor, and what was not
    tested for Duffing.

## Question

When u is modulated, dx/dτ = F(x; p(u(t))) is non-autonomous. Pitch lock (k = P(u)·f₀) and
level normalization (s(u)·(x − μ(u))) read tables measured at **fixed** u. How fast can u move
before:

- (a) the pitch leaves its static value;
- (b) the level leaves its static value;
- (c) the trajectory leaves the attractor or triggers safety resets?

**Rate unit.** One sweep is a full traversal 0 → 1. N = f₀T/2 is the number of oscillation
periods per sweep of a full-range sine with LFO period T. The rate r is the number of sweeps per
period *of the slewed u*: r = 2·swing/(f₀T). In v0.3 the slew is a one-pole filter with
τ = 2 periods (for f₀ < 400 Hz). It cuts the swing to N/√(N² + 4π²), so
r = 1/√(N² + 4π²) and **r can never exceed 1/(2π) ≈ 0.16**.

## Method

- **Engine path.** The real `Dynamical.process` is used, with the slew, the perceptual amp
  (a = 1) and the 5 Hz DC blocker. A wrapper on `render_tuned` records the per-sample
  parameter and the state. `Patch.render` with an LFO and an Output block gives identical
  audio below the soft-clip knee and 0 resets.
- **Drive.**
  - A full-range sine at A3 with T from 20 s down to 0.01 s.
  - 3 seeds, a 2 s transient, then ≥ 30 s (≥ 2 cycles) analysed in 24 bins of the phase ψ of
    the slewed u.
  - Each bin is compared with a **static reference** at the same u: 41 fixed-u points, 10 s
    each.
- **(a) Pitch.**
  - *Centroid*: the |z|²-weighted instantaneous frequency of the band f₀/1.6 … 1.6 f₀.
  - *Loop rate*: the inverse duration of each loop between maxima of the heard variable,
    compared with the static loop rate at the u of the loop's midpoint.
  - The profile is split into a hysteresis part, (up − down)/2, and a symmetric part.
- **(b) Level.** The per-bin RMS against the static RMS at the same u, and the mean of
  s = (x − μ(u))/σ(u) before the DC blocker.
- **(c) Attractor.**
  - Safety resets.
  - Box usage: the largest |x − centre|/half-width, without Duffing's phase variable.
  - The 99th-percentile nearest-neighbour distance to the static clouds at the bracketing u,
    in static σ units. The clouds are symmetrized for Lorenz, Chua and Rikitake.
- **Extras.**
  - Square-wave jumps 0 ↔ 1 (64 periods per level, 40 jumps × 3 seeds) at A3 and A1, with
    both slews. Jumps whose 64-period window holds a safety reset are also summarized
    without them.
  - Reset probes at A0–A3 for all five systems, plus the default T = 4 s modulator with
    square and ramp shapes.
  - Chua with full-range sine and triangle drives at A0 and A1.
  - Chua observable x.
  - Lorenz at A2, A3 and A4 at equal N.

## Results

### Floor and estimators

| system | static centroid − note | static loop rate − note | static-reference error, centroid / loop (RMS) | static NN q99 |
|---|---|---|---|---|
| Lorenz | −33 … +36 c | +3 … +49 c | 1.1 / 1.7 c | 0.028 σ |
| Chua | −55 … +13 c | −19 … +100 c | 1.6 / 3.9 c (max 14) | 0.040 σ |
| Rössler | −53 … +11 c | −6 … +28 c | 0.2 / 0.5 c | 0.032 σ |
| Rikitake | +8 … +103 c | 0 … +47 c | 1.6 / 3.4 c (max 12) | 0.043 σ |

- **Absolute pitch.** It depends on the estimator, at the ±50 c level. The catalog's ±10 %
  peak centroid is a third definition. Everything below therefore subtracts the static value
  at the same u.
- **Static reference error.** It is common to every modulated run and is not included in the
  seed spreads.
- **Static level.**
  - RMS 0.237–0.259.
  - The robust peak is ≤ 0.75.
  - π/σ ≤ 3.0 for all four default observables (3.1 for Chua x), so the v0.3 peak limit
    (0.8/π, active when π/σ > 3.2) never engages in this study.

**Estimator gain** (`fig6`). This is |measured/true| for a known ±50 c sine FM applied to
static audio, mean of 3 seeds:

| FM rate | 0.5–20 Hz | 50 Hz | 100 Hz |
|---|---|---|---|
| centroid | 0.71 (Lorenz); 0.85–0.91 (others) | 0.66–0.87 | 0.31–0.47 |
| loop rate | 0.92–1.04 | 0.84–0.99 | 0.68–0.73 |

The loop rate is unbiased up to about 20 Hz. The centroid's gain below 1 comes from the
broadband carrier: the old report's numbers were about 30 % low for Lorenz.

### Sine sweep at A3 (mean of 3 seeds; `fig1`, `fig2`)

Pitch error is the RMS over phase of (pitch − static pitch at the same u). Each cell gives the
range of the two estimators (centroid ÷ gain, and loop rate), in cents.

| T (s) | N | swing | r | Lorenz | Chua | Rössler | Rikitake |
|---|---|---|---|---|---|---|---|
| 20 | 2200 | 1.00 | 0.0005 | 6 | 6–9 | 1–3 | 6–8 |
| 2 | 220 | 1.00 | 0.005 | 6–7 | 12–18 | 3–10 | 8–9 |
| 1 | 110 | 1.00 | 0.009 | 7–10 | 14–21 | 3–9 | 12–17 |
| 0.5 | 55 | 0.99 | 0.018 | 9–11 | 15–22 | 5–11 | 21–28 |
| 0.2 | 22 | 0.96 | 0.044 | 18–22 | 21–31 | 11–20 | 39–53 |
| 0.1 | 11 | 0.87 | 0.079 | 29–30 | 23–36 | 22–28 | 57–83 |
| 0.05 | 5.5 | 0.66 | 0.12 | 38–43 | 27–36 | 31–58 | 59–79 |
| 0.02 | 2.2 | 0.33 | 0.15 | 52–59 | 23–25 | 68–94 | 50–64 |
| 0.01 † | 1.1 | 0.17 | 0.16 | 88–97 | 12–27 | 31–78 | 34–39 |

† At 100 Hz both estimators lose 30–70 % (table above), so this row is unreliable and probably
low.

**Character of the error.** Pairs below are hysteresis / symmetric parts, centroid ÷ gain:

- **Lorenz** is hysteresis-dominated up to r = 0.12: 17 / 6 c at T = 0.2 s, 28 / 11 at 0.1 s
  and 41 / 13 at 0.05 s. The pitch runs sharp while ρ rises and flat while it falls. Both
  parts are equal at r = 0.15.
- **Chua** has equal parts at every rate (9 / 10 at 1 s, 16 / 16 at 0.1 s). Its symmetric part
  is already 5–11 c at T = 20–0.5 s. We read it as periodic windows that the sweep crosses too
  fast to lock onto, and that the 41-point static grid does not resolve.
- **Rössler** has equal parts up to r = 0.12 (15 / 16 at 0.1 s). Hysteresis dominates at 0.15
  (64 / 22).
- **Rikitake** turns symmetric from r ≈ 0.04 (26 / 28 at 0.2 s, 20 / 53 at 0.1 s). It also
  runs **sharp on average** under fast modulation. At T = 0.2 / 0.1 / 0.05 s the mean offset is
  +7 / +18 / +27 c with the centroid (+9 / +20 / +31 c after dividing by its gain, 0.87–0.88)
  and +24 / +45 / +49 c with the loop rate.
  - At T = 0.2 and 0.1 s most of the offset comes while μ rises: the loop rate is +41 / +54 c
    over the rising half of the cycle, against +6 / +33 c over the falling half. At 0.05 s
    both halves are about +48 c.
  - It is the most rate-sensitive system: about 6–9 c per 0.01 of r in the transitional
    range, against 1.5–3.5 for the others.

**Level and attractor.** Level is the maximum over phase of |RMS re static|. Distance is the
99th-percentile distance to the static attractor, as a multiple of the static 99th percentile.

| T (s) | r | level, dB (L / C / R / K) | distance (L / C / R / K) |
|---|---|---|---|
| 20 | 0.0005 | 0.2 / 0.3 / 0.3 / 0.2 | 0.9 / 1.4 / 1.1 / 2.0 |
| 5 | 0.0018 | 0.3 / 0.4 / 0.5 / 0.2 | 0.9 / 2.1 / 4.7 / 1.9 |
| 1 | 0.009 | 0.4 / 0.8 / 0.8 / 0.4 | 0.9 / 4.2 / 8.9 / 2.9 |
| 0.2 | 0.044 | 0.7 / 1.2 / 1.1 / 1.0 | 1.2 / 12 / 12 / 4.2 |
| 0.1 | 0.079 | 1.0 / 1.7 / 2.0 / 1.5 | 1.4 / 11 / 13 / 4.5 |
| 0.05 | 0.12 | 1.1 / 1.3 / 1.9 / 1.6 | 2.0 / 8.0 / 23 / 2.3 |

- **Overall RMS.** It stays within ±0.1 dB of static up to T = 1 s for every system (Rössler
  is +0.11 dB at 0.5 s). At faster rates Rössler reaches +0.22 / +0.32 / +0.58 dB and Rikitake
  −0.15 / −0.28 / −0.32 dB at T = 0.2 / 0.1 / 0.05 s.
- **Mean of s before the DC blocker.** It is ≤ 0.04 up to r = 0.018, which is ≤ 0.01 in audio
  units. Lorenz reaches 0.08–0.13 at r = 0.04–0.12, and Rössler 0.25 at 0.05 s.
- **Peaks.** The robust peak is ≤ 0.72.
- **Distance to the attractor.**
  - Lorenz stays on its static attractor up to r ≈ 0.02.
  - Rössler's thin band departs already at T = 5 s (4.7×), long before anything is audible.
    The largest distance seen is 5.2 σ (Rössler, T = 0.02 s).
  - Rikitake's ratio of 2 at T = 20 s is a floor effect: 10 s static clouds under-sample its
    slow reversals.
- **Safety.** Box usage is ≤ 0.40, and no sine run reset at any rate.

**Rate unit check** (Lorenz, equal N; centroid and loop rate in cents):

| N | A2 | A3 | A4 |
|---|---|---|---|
| 11 | 20.5 / 33 | 21.1 / 29 | 19.6 / 26 |
| 55 | 8.3 / 16 | 6.4 / 11 | 5.6 / 9 |

- At N = 11 the three notes agree within ±15 %, and the swing is the same at all three
  (0.07–0.93; 0.08–0.92 at A4), since the v0.3 slew is about 2 periods at each note.
  Counting the rate in periods therefore transfers across notes.
- At N = 55 the signal is close to the floor, and the floor is higher at low notes because
  30 s contain fewer loops.

### Jumps (square 0 ↔ 1; loop rate against the static value at the *current* slewed u; `fig3`)

With the v0.3 slew a full-range jump becomes an exponential glide: u covers 39 % of the way in
1 period and 95 % in 6 periods.

| system | jump | max \|error\|, A3: v0.3 / v0.2 | A1: v0.3 / v0.2 | settles to ±20 c (periods), A3: v0.3 / v0.2 | A1: v0.3 / v0.2 |
|---|---|---|---|---|---|
| Lorenz | 0 → 1 | 111 / 207 c | 106 / 515 c | 4 / 2 | 2 / > 64 * |
| Lorenz | 1 → 0 | 80 / 259 c | 61 / 497 c | 16 / > 64 | 12 / 4 |
| Chua | 0 → 1 | 104 / 81 c | 116 / 67 c ‡ | 4 / 8 | 4 / 1 ‡ |
| Chua | 1 → 0 | 37 / 50 c | 39 / 79 c | 8 / 6 | 8 / 3 |
| Rössler | 0 → 1 | 65 / 91 c | 71 / 97 c | 8 / 12 | 8 / 8 |
| Rössler | 1 → 0 | 126 / 136 c | 128 / 272 c | 6 / 3 | 3 / 2 |
| Rikitake | 0 → 1 | 252 / 218 c | 237 / 182 c | 32 / 24 | 32 / 16 |
| Rikitake | 1 → 0 | 80 / 202 c | 66 / 359 c | 8 / 6 | 8 / 8 |

\* By the stated rule. Every bin from 4 to 48 periods is within the tolerance; only the last
bin (48–64 periods, −20.5 c, 2 SE = 8 c) is outside it. Without that bin the rule gives 4.

‡ These runs had 3 safety resets, one per seed, each after an up-jump (peak audio 1.72–1.80).
Without those 3 of 120 up-jumps the maximum is 64 c and the error settles in 1 period. No other
jump run had a reset.

- **Note-independence.** v0.3 makes jumps nearly note-independent: the maximum errors at A3
  and A1 differ by ≤ 20 c. With v0.2 they differed by up to 310 c.
- **Where v0.3 helps.** The worst v0.2 chirps shrink a lot: Lorenz at A1 from ±5 semitones to
  about ±1, Rössler 1 → 0 at A1 by 2×, and Rikitake 1 → 0 by 2.5–5×.
- **Where it does not.** Chua's maximum error grows by 29 % at A3 (81 → 104 c) and by 73 % at
  A1 (67 → 116 c; 64 c without the 3 v0.2 jumps that reset). In exchange, those resets are
  gone. Rikitake 0 → 1 is a sharp overshoot of +190–250 c from 2 to 12 periods, decaying
  through +150 c (12–16 periods) and +94 c (16–24), and settled by 32. It is nearly as large
  with v0.2 (218 and 182 c), so we read it as the dynamo's own relaxation, not a slew effect
  (not proven). It lasts about 90 ms at A3 and 0.36 s at A1.
- **Lorenz 1 → 0.** With v0.2 the pitch stays ≥ +22 c for 64 periods (+46, +37, +30, +22 c
  in the 16–64-period bins; ≥ 290 ms at A3). With v0.3 it is +40–73 c from 2 to 16 periods,
  then ≤ 15 c from 16 periods.
- **Peaks after jumps.** At most 1.00 (A3) and 1.19 (A1) for Lorenz, against 0.96 and 1.27
  with v0.2. The Output soft clip catches them. The three Chua A1 v0.2 resets reached
  1.72–1.80.

### Safety (`fig5`)

| case | v0.2 slew (5 ms) | v0.3 slew |
|---|---|---|
| Chua 0 ↔ 1, 64 periods per level, A0, 540 up-jumps | **34 (6.3 %, CI 4.4–8.7 %)** | 0 (< 0.7 %) |
| same, A1 | **8 (1.5 %, CI 0.6–2.9 %)** | 0 (< 0.7 %) |
| same, A2 and A3 | — | 0 / 540 each |
| Chua, default modulator T = 4 s, A0, square, 177 jumps | **8 (4.5 %): a pop every ~90 s** | 0 |
| same, ramp_down | **18 (10.2 %): a pop every ~40 s** | 0 |
| same, ramp_up | — | 0 |
| Chua, T = 4 s, A1: square, ramp_up, ramp_down | — | 0 each |
| Lorenz, Rössler, Rikitake and Duffing, 0 ↔ 1 at A0–A3, 180 jumps each | — | 0 (box usage ≤ 0.36 / 0.50 / 0.35 / 0.34) |
| Chua at A0 and A1: sine T = 0.1–2 s, triangle T = 0.2 and 0.5 s, 3 × 60 s each | — | 0 (box usage 0.33) |

- **Statistics.** Fisher exact test, v0.2 against v0.3: p = 7·10⁻¹¹ at A0 and p = 0.008 at A1.
  In total v0.3 had **0 resets in 6 102 jumps** over the five systems:
  - 5 394 full-range square up-jumps (0 → 1);
  - 708 ramp edges at T = 4 s, which the slew shortens. At A0 the ramp_up edge goes from 0.98
    to 0.07 and the ramp_down edge from 0.02 to 0.93; at A1, 0.99 → 0.04 and 0.01 → 0.96.
- **Mechanism.** With v0.2 the resets come 3.9–6.9 periods after an up-jump. `fig5` starts the
  same jump from the same state with both slews: the v0.2 trajectory spirals out over about 5
  loops and hits the box (audio about 1.8, then a pop), while the v0.3 one stays bounded. The
  WAVs `wav/chua_square_A1_seed0_v02slew.wav` and `_v03slew.wav` let you hear the difference.
- **Depth cost of the slew.**
  - Fast LFOs lose swing at every note, as a function of N only: 0.87 at N = 11 and 0.66 at
    N = 5.5.
  - At A0 (τ = 73 ms) a T = 0.5 s sine sweeps only 0.13–0.87.
  - T = 4 s ramps at A0 reach 0.07–0.98 (ramp_up) and 0.02–0.93 (ramp_down).
  - The smooth low-note runs above all used the slewed swing. Full depth is no longer
    reachable at fast rates, so the old report's depth confound is now built into the engine.

### Minor: Chua with observable x

- 10 of 18 single-scroll entries (T = 5 s) landed on the x > 0 scroll. There s sits at +3.48
  (0.87 in audio units before the DC blocker), and peaks reach 0.72–1.15.
- The reason is that the rebuilt catalog's μ_x(u = 0) = −1.18 belongs to the x < 0 scroll. The
  v0.2 catalog had +1.18, and its run found 6 of 18 entries on the other scroll. Which scroll
  the catalog run lands on is arbitrary.
- The default observable y is unaffected.

## Conclusion

1. **Adiabatic: r ≲ 0.01, i.e. N ≳ 100** (a full-range sine with T ≳ 200/f₀: 0.9 s at A3,
   3.6 s at A1).
   - Over its slow-rate floor, the modulation adds ≤ about 8 c RMS for Lorenz and Rössler,
     10–18 c for Chua (skipped windows, already at r = 0.005) and up to 15 c for Rikitake.
   - The level stays within 0.8 dB per phase and ±0.1 dB overall, with no resets.
   - The default `period_s = 4 s` gives r = 0.0023 at A3, 0.009 at A1 and 0.018 at A0.
2. **Transitional: 0.01 ≲ r ≲ 0.1** (A3: 1 s ≳ T ≳ 0.1 s).
   - The error grows roughly linearly. Per 0.01 of r, depending on the estimator, it is
     3–3.5 c for Lorenz, about 3 c for Rössler, 1.5–2.4 c for Chua and 6–9 c for Rikitake.
   - At r = 0.08 that gives 22–36 c RMS (57–83 c for Rikitake) and level swings of ±1–2 dB.
3. **Forcing: r ≳ 0.1.** In v0.3 this needs N ≲ 8 and comes with a reduced swing.
   - The rate saturates at 1/(2π) ≈ 0.16 below about 400 Hz, so the "audio-rate" regime of
     the old report (r up to 0.9) no longer exists.
   - Errors are 12–97 c RMS (Chua lowest) and the box stays bounded.
4. **Discontinuous shapes** (square, ramps).
   - The v0.3 slew removes Chua's escapes: 0 / 540 against 6.3 % at A0, and 0 / 177 against
     4.5–10 % for the default 4 s modulator.
   - It also makes jump responses note-independent.
   - Each jump is still a 6-period glide with non-adiabatic chirps of 35–130 c for 2–16
     periods (Lorenz, Chua, Rössler). Rikitake 0 → 1 overshoots by about +250 c for about
     20 periods.
5. **Effect of the other v0.3 changes.**
   - New defaults: none, because a cabled param input overrides the knob.
   - New ranges: little effect. Lorenz and Chua are similar; Rössler is wider, but its P varies
     by only 3.4 %.
   - Peak-limited level: never engaged for these observables.
   - The old conclusions on the adiabatic threshold and the rate unit stand. The ones on
     audio-rate forcing, escapes and jump chirps change as stated above.

## Recommendations

- **Keep the v0.3 slew** (ADR 0013). It is confirmed by 0 resets in 6 102 jumps, and no lower
  Chua p_max is needed. Its cost is the swing at fast rates; explain this in the educational
  text.
- **Do not cap `period_s`.** Show an informational badge instead.
  - For smooth shapes, compute r = 2·depth·|H|/(f₀T), with |H| = 1/√(1 + (2πτ/T)²) and
    τ = max(5 ms, 2/f₀). Show "pitch lock approximate" for r > 0.01 and "forcing: pitch and
    level not locked" for r > 0.08. When |H| < 0.9, add "the slew narrows this sweep to
    |H|·100 %".
  - For square shapes, always show "each jump glides over about 6 periods; the pitch may
    chirp by up to 1–2.5 semitones", whatever T is. The range is the largest v0.3 error per
    system measured at A3 and A1 (111–252 c).
  - For ramp shapes, show "each ramp reset glides over about 6 periods", without a chirp
    size. Ramps were tested only for resets (0 in 708 edges), not for pitch.
  - Depth here is the Control Sum gain, which this study did not test.
- **Rikitake.** Document in its Learn-more text that fast modulation makes it run sharp:
  about +10 to +50 c at r ≈ 0.04–0.12, depending on the estimator (centroid ÷ gain +9 to
  +31 c, loop rate +24 to +49 c), and more while μ rises than while it falls. Also document
  that upward jumps overshoot by up to about 2.5 semitones and settle within 32 periods. No
  engine change is proposed.
- **Catalog (not done here).** Chua's single-scroll table covers u ≤ 0.164, i.e.
  α ≈ 13.7–14.4. It holds the moments of the x < 0 scroll only (μ_x ≈ −1.30 … −1.17,
  σ_x ≈ 0.58–0.68), so the x > 0 scroll sits at s = +3.48 for x (0.87 in audio units) and at
  −1.59 for z. One more grid point, u = 0.969 (α ≈ 17.9), has μ_x = −0.51. Two fixes were
  computed on the same single-scroll episodes:
  - μ = 0 with the catalog σ leaves ±1.74 in s (±0.43 in audio) for x and ±0.80 for z, on
    both scrolls.
  - μ = 0 with σ′ = √(σ² + μ²), the pooled moments of the two mirror scrolls, leaves ±0.86
    (±0.22 in audio) for x and ±0.62 for z. σ′_x is 1.35–1.42 in the range, within 3 % of
    the double-scroll σ_x ≈ 1.38 just above it, and σ′ = σ wherever μ ≈ 0.
  - We recommend the second. The 5 Hz DC blocker removes any constant offset with a 32 ms
    time constant, so the offset matters as a step when a scroll is entered: up to 0.87 in
    audio now, 0.22 with σ′. The alternative is to document that only y is safe under
    modulation for α ≲ 14.4.
- **Follow-ups.**
  - Partial depth through `control_sum`.
  - The main sweep at other notes.
  - Whether the heard pitch follows the centroid or the loop rate.
  - Parameter modulation combined with the pitch input. A pitch input changes only k, which
    leaves the orbit unchanged, so on its own it is not subject to these limits.
  - Observables where the peak limit engages (Rössler z, Rikitake x and y).

## Uncertainties and limitations

- **Estimators.** The two estimators differ by up to 2× (Rössler, T = 0.05 s: 31 against
  58 c). The time-warp gain corrects only pure FM, not changes of waveform shape. Dividing the
  centroid by its gain also scales up its floor (Lorenz, T = 20 s: 3.9 → 5.5 c with gain
  0.71), although the gain applies to the part of the error that follows u, not to chaotic
  phase noise. Ratios to the floor change by ≤ 7 %, since each system's gain varies by ≤ 7 %
  from 0.5 to 20 Hz, so the conclusions stand. Which estimator the ear follows for a
  broadband chaotic tone is open.
- **Floor.** It combines in-bin chaotic phase noise with the static-reference error
  (0.2–3.9 c RMS). The latter is common to all seeds and not part of the ± spreads in
  `results.json`. Differences below about 2× the T = 20 s row are not significant.
- **Static grid.** Its 41 points do not resolve narrow periodic windows. This inflates Chua's
  floor and the distances of Chua and Rössler, and the 10 s clouds under-sample Rikitake's
  slow dynamics.
- **v0.2 comparison.** It is an emulation: the v0.3 engine and catalog with the slew set to
  5 ms. Chua's range is the same in both catalogs, so the escape comparison is direct.
- **Coverage.**
  - Full-range sine for the main sweep, at A3 only.
  - Square for the jumps, at A3 and A1. Ramps only in the reset probes (T = 4 s, A0 and A1).
  - Duffing only in the square-jump reset probes. Its pitch lock is exact, which justifies
    leaving it out of (a) only: (b) level and (c) attractor distance under smooth modulation
    were not tested for it.
  - 3 seeds (9 for the Chua probes).
  - The settling criterion (±20 c or 2 SE) is a choice.
- **Interpretations.** The mechanisms behind the Rikitake overshoot, the Lorenz 1 → 0 tail and
  Chua's symmetric part are interpretations and are not proven.
