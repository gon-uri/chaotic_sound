<!-- Draft written by an AI agent; numbers come from lab/scripts/studies/aliasing.py and need owner review. Last updated: 2026-10-26 -->

# Aliasing versus note: when does a dynamical box need oversampling?

> **Provenance.** Engine v0.3 (package `chaotic_sound` 0.1.0). Catalog `catalog/systems.json`,
> `metadata.generated` = 2026-10-25T20:00:03+00:00. Systems: Lorenz, Rössler, Chua, Rikitake,
> Duffing. Knob ranges and defaults are the v0.3 ones (default = chaotic point nearest the
> middle of the range).

## Question

A dynamical box point-samples the continuous tuned trajectory x(k·t) at fs (spec §4.2,
steps 6 and 7). There is no band-limiting step, so any power above fs/2 folds
back into the band as inharmonic components. For which notes, knob positions and observables
does this matter at fs = 48 kHz? If oversampling is needed, by what factor and with what
filter?

## Method

Script: `lab/scripts/studies/aliasing.py`. Outputs (gitignored): `lab/outputs/studies/aliasing/`
(`results.json`, `dc_check.json`, `side_checks.json`, figures). Compute: 7.5 min for the main
run, 1 min each for `--dc-check` and `--side-checks`.

1. **Renders.** Every render goes through the real `Dynamical` block (declicker, perceptual amp
   curve, peak-limited normalization, parameter slew, 5 Hz DC blocker) at 8 × 48 kHz. A
   stationary process sampled at fs has the PSD S_fs(f) = Σ_m S(f + m·fs), so every measure
   is an exact functional of the high-rate PSD S(f):
   - **R_nyq**: power above 24 kHz, relative to total power. All of it folds somewhere.
   - **R_aud**: folded power that lands in 20 Hz–20 kHz, relative to total power.
   - **L** (local ratio, new): folded power over true signal power in each 1/3-octave band.
     L_max is the worst band up to 20 kHz; L10 is the worst band centred at or below 10 kHz.
     Bands whose alias is below −130 dBFS are ignored.
   - **M** (audibility screen, new): the alias level in each band minus the larger of two
     thresholds. One is in-band masking, S_b − (14.5 + z_b) dB, with z_b the band's Bark
     number. This is Johnston's tone-masking-noise offset (Johnston 1988, IEEE J. Sel. Areas
     Commun. 6(2); checked here only in secondary sources). It is larger than the tonal
     masking index of MPEG-1 psychoacoustic model 1, 6.025 + 0.275·z_b dB, so it errs towards
     "audible". The other is Terhardt's threshold in quiet, with a full-scale sine
     calibrated to 96 dB SPL. M_max ≤ 0 means "inaudible by this screen". The screen is conservative: it ignores masking from neighbouring bands
     and assumes a loud playback level.
   - Levels in dBFS use the **measured** output power. Since v0.3 the gain is
     min(0.25/σ, 0.8/π), with π the robust peak. Default observables are unaffected
     (0 dB). Rössler z plays 8.4 dB lower at its default knob position (10.6 dB lower at
     u = 1), and Rikitake y plays 1.2 dB lower.
2. **PSD estimator.** Welch with a Hann window, applied to the second difference and divided
   by |2 sin(πf/fs)|⁴ ("prewhitening"). The direct estimate is used below f₀/2. First- and
   second-difference prewhitening agree to ≤ 0.05 dB wherever R_nyq > −200 dB. Values below
   −150 dB are reported as "< −150".
3. **Per-note renders (part A).** Default knob and observable, notes A1…A7 and C8, three seeds,
   8 s each with the first 0.5 s discarded.
4. **Universal spectra (part B).** Time rescaling makes the spectrum at note f₀ equal to
   S₁(f/f₀)/f₀. One render at **A4** per case gives S₁ up to harmonic 436. The DC blocker's
   known response is divided out. Cases: the default (3 seeds), and every audible observable ×
   u ∈ {0, ⅛, …, 1} (1 seed). Every measure is then evaluated at every semitone from A2 to C8,
   at 48 and 44.1 kHz, and for 2× and 4× oversampling. Ceilings are given for three scopes:
   - default knob and observable;
   - default observable over the whole knob range;
   - any observable over the whole knob range.
5. **Checks.**
   - A6, A7 and C8 re-rendered at 32×.
   - Native 48 kHz renders compared with the prediction "true PSD + folded PSD".
   - Direct renders (3 seeds) of the scope-defining worst cases, at and above their ceiling
     (part D).
   - Tail variability at u = 1 for Rikitake and Rössler: 3 seeds, two discard lengths, record
     halves (`--side-checks`).
6. **Decimators (part C).** For each target, the Kaiser half-band FIR with the fewest taps whose
   *measured* stopband meets it (β is scanned). The residual alias is computed through the full
   multirate chain.
7. **Fast modulation (part E, new).** The param input is driven by a 0↔1 square wave (20 and
   200 Hz) and a full-swing sine (2 and 20 Hz), at A6 and A7 with the default observable. The
   result is compared with the worst static u.

## Results

### 1. Default knob and observable, per note

R_nyq, dB re total (mean of 3 seeds). Values above −80 dB are in bold.

| System (obs.) | A1–A4 | A5 | A6 | A7 | C8 |
|---|---|---|---|---|---|
| Lorenz (z) | < −150 | < −150 | −130.3 | **−62.6** | **−51.7** |
| Rössler (x) | < −150 | −117.6 | **−65.2** | **−38.1** | **−33.7** |
| Chua (y) | −201 … −138 | −116.9 | −95.9 | **−75.0** | **−69.4** |
| Rikitake (z) | < −150 | −113.8 | **−65.0** | **−35.8** | **−30.6** |
| Duffing (y) | < −150 | < −150 | < −150 | −86.7 | **−71.5** |

At the top notes:

| System | R_aud A6 / A7 / C8 | L10 A7 / C8 (band) | M_max A6 / A7 / C8 |
|---|---|---|---|
| Lorenz | −152.7 / −74.0 / −61.2 | −78.5 / −65.5 (10 kHz) | −124 / −29.7 / −15.9 |
| Rössler | −73.8 / −42.3 / −37.6 | **−17.0 (80 Hz) / −15.2 (500 Hz)** | −24.7 / **+9.1** / **+14.1** |
| Chua | −100.5 / −78.9 / −74.6 | −47.9 / −46.7 | −33.3 / −15.8 / −11.8 |
| Rikitake | −73.7 / −41.2 / −35.3 | −39.7 / −32.8 (10 kHz) | −25.6 / **+6.0** / **+8.5** |
| Duffing | −216 / −102.0 / −84.5 | — / −95.2 | −184 / −65.0 / −43.1 |

- The **band-level view qualifies the old "only Rössler from about A7" statement.** Rössler's
  folded power also lands in the valleys below the fundamental, not only near Nyquist
  (L10 = −17 dB at 80 Hz at A7, and −15 dB at 500 Hz at C8).
  - The ratio is high because the signal is weak there, not because the alias is loud.
  - In those bands the alias is a broad floor, not lines: its PSD peaks only 5–7 dB above
    its median over 22–560 Hz.
  - At A7 it lies at −93 to −101 dBFS in the 25–500 Hz bands, 7 to 71 dB below the screen
    threshold (22.5 dB below it in the 80 Hz band).
  - At C8 it reaches the threshold in the 250–630 Hz bands (up to +4 dB at 500 Hz). The
    12.5 kHz band (+14 dB) is still the worst.
- **Rikitake behaves like Rössler.** It also has a smooth, slowly decaying tail.
- **By the screen, both cross into audibility above E7.** The worst band is 12.5 kHz, where
  the alias is at −64 dBFS (Rössler A7) to −57 dBFS (Rikitake C8).
- **L_max is not a useful ceiling on its own.** It is set by the 17.8–20 kHz band in every case
  (−10 to −41 dB). There, both signal and alias lie on the same tail, so the ratio hardly
  depends on the note. For Chua x it is even true of L10: its f⁻⁶ tail keeps the ratio near
  −35 dB from F4 to A5. L10 ≤ −40 dB then fails from F4, at alias levels far below hearing.

![R_nyq and worst-band ratio versus note](../../lab/outputs/studies/aliasing/aliasing_vs_note.png)

![Band levels at the top notes](../../lab/outputs/studies/aliasing/band_levels.png)

### 2. Ceilings: highest note that meets the criterion at 48 kHz without oversampling

Each cell reads default knob & observable / default observable over the whole knob range /
any observable over the whole knob range.

| System | R_aud ≤ −80 dB | screen M ≤ 0 | R_nyq ≤ −80 dB |
|---|---|---|---|
| Lorenz | G7 / G7 / G7 | > C8 / > C8 / > C8 | F7 / E7 / E7 |
| Rössler | G6 / D#6 / **G5** | E7 / C7 / **F#6** | E6 / C6 / F5 |
| Chua | G#7 / E7 / C#6 | > C8 / > C8 / C7 | F7 / C#7 / B5 |
| Rikitake | F#6 / **C6** / A#5 | E7 / **A#6** / A#6 | E6 / A#5 / G#5 |
| Duffing | > C8 / B7 / B7 | > C8 / > C8 / > C8 | A7 / G#7 / G#7 |
| **All systems** | **F#6 / C6 / G5** | **E7 / A#6 / F#6** | **E6 / A#5 / F5** |

- Over the knob range the worst position is at or next to u = 1 for Rössler (x and z),
  Rikitake (all observables) and Duffing. Rössler's spikes sharpen as c grows, and
  Rikitake's as μ grows. For Chua it is u = 0 (x) or u = 0.75 (y).
- At 44.1 kHz, R_aud ≤ −80 gives E6 / A#5 / F5 and the screen gives D7 / G#6 / E6.
- **Direct renders confirm the ceilings** (part D, 3 seeds):
  - Rössler: within 0.3 dB of the prediction. At its knob-range screen ceiling, Rössler x at
    u = 1 measures M = −1.7 dB at C7 and +0.6 dB at C#7. Rössler z measures −0.7 dB at F#6
    and +2.4 dB at G6.
  - Rikitake: the universal spectrum is **conservative**. Rikitake z at u = 1 measures
    R_aud = −82.8 dB at C#6 (predicted −79.0) and M = −0.5 dB at B6 (predicted +0.3). Its true
    ceilings for the default observable are therefore about C#6 (R_aud) and B6 (screen).
  - Reason for the Rikitake bias: its tail varies from window to window. At u = 1, n₈₀ of z
    spans 24.1–25.6 over the 8 s windows (3 seeds × 2 discard lengths), about ±0.5 semitone.
    With the 4 s record halves included it spans 23.8–26.3, about ±0.9 semitone. The A4
    render used for part B (seed 11) fell on the high side: n₈₀ = 25.7, against 24.0 and
    24.1 for the same render with seeds 22 and 33. Rössler's n₈₀ varies by
    ±0.3–0.4 % over the 8 s windows and ±0.9–1.2 % with the halves, at most ±0.2 semitone
    (`side_checks.json`).

### 3. Validation

- **Seed spread** (max − min over 3 seeds, values above −150 dB).
  - Broad-band ratios (R_nyq, R_aud, R_A): ≤ 0.6 dB, except Rikitake at A5 (4.7–6.4 dB, at
    −112 to −133 dB).
  - Band measures spread more: up to 1.9 dB for R_1_5k (Lorenz A1, at about −149 dB),
    1.4 dB for M_max (Lorenz A6, at −124 dB), 1.3 dB for R_1_5k, 1.0 dB for L10 and 0.8 dB
    for M_max (Rikitake A6), and 0.7 dB for L10 (Chua C8).
  - Rikitake A5 M_max spreads by 10 dB (−91 to −81 dB).
- **32× renders.** They agree with the 8× renders to ≤ 0.3 dB (R_nyq and R_aud).
- **Universal versus direct.** At the default, A6–C8, the universal spectrum agrees with the
  direct renders to ≤ 0.5 dB in R_nyq, R_aud, L_max and M_max, for every value above
  −150 dB.
- **Native 48 kHz renders.** They match "true + folded" to ≤ 0.09 dB in every band from 5 to
  23.5 kHz. That test only discriminates where aliasing adds clearly more than this scatter.
  That holds in the 20–23.5 kHz band for Rössler (+1.3 dB), Rikitake (+0.9), Chua (+0.6) and
  Lorenz C8 (+0.35). It does not hold for Duffing or Lorenz A7, where the alias adds less
  than 0.25 dB.
- **What the −80 dB ceilings rest on.** They lie outside that native-render regime, so they
  rest on the 8× versus 32× agreement, the estimator analysis and the direct renders.

![Native 48 kHz render versus prediction, C8](../../lab/outputs/studies/aliasing/native48_vs_prediction.png)

### 4. Tail shapes

- **The smooth systems** (Lorenz, Rössler, Rikitake, Duffing) have G(n) = P(f > n·f₀)/P_total
  falling roughly exponentially in n. Aliasing therefore switches on abruptly: Lorenz goes from
  −130 dB at A6 to −63 dB at A7.
- **n₈₀ at the default** (harmonic where G = −80 dB; worst of 3 seeds):

  | System | n₈₀ |
  |---|---|
  | Lorenz | 8.6 |
  | Rössler | 17.5 |
  | Chua | 8.3 |
  | Rikitake | 18.0 |
  | Duffing | 6.5 |

- **Worst over the knob range:** Rössler x 22.4, Rössler z 34.1, Rikitake z 25.7, Rikitake
  y 28.4, Chua x 24.0.
- **Chua's tail follows a power law.** Its piecewise-linear h(x) makes x C¹, y C² and z C³.
  The measured PSD slopes over 16 ≤ n ≤ 128 are −18.0, −24.0 and −30.1 dB per octave, as
  that predicts. So Chua is the most aliased system at low notes (−138 dB at A4) but grows by
  only 21 dB per octave of note.

![Universal tail G(n) and PSD per harmonic](../../lab/outputs/studies/aliasing/tail_universal.png)

### 5. Fast parameter modulation (new in v0.3)

The parameter slew (one-pole, τ = max(5 ms, 2/f₀)) makes even a square wave move u
gradually. R_nyq in dB, default observable, seed 11:

| System, note | worst static u | square 20 Hz | square 200 Hz | sine 2 Hz | sine 20 Hz |
|---|---|---|---|---|---|
| Lorenz A6 | −127.4 | −82.7 | −78.6 | −121.7 | −94.7 |
| Chua A6 | −88.1 | −68.8 | −70.7 | −91.5 | −80.2 |
| Duffing A6 | −172.1 | −78.6 | −77.0 | −115.4 | −87.6 |
| Rössler A7 | −32.8 | −36.7 | −38.0 | −36.4 | −37.0 |
| Rikitake A7 | −25.5 | −30.2 | −35.6 | −30.7 | −31.8 |

- **Rössler and Rikitake.** Modulation stays below the worst static u at both notes (at A6,
  −59.0 against −53.7 dB for Rössler and −54.4 against −48.2 dB for Rikitake), because the
  box spends only part of the time at the sharp end of the range.
- **Lorenz, Chua and Duffing.** Modulation adds a **power-law tail** of −12 dB per octave
  (f⁻⁴) that sits far above their own steep tails at A6.
- **The tail has two sources.** Both are slope breaks in the output gain and offset, and a
  slope break gives an f⁻⁴ tail.
  - **Table nodes.** μ(u), σ(u), π(u) and P(u) are interpolated linearly in u, so the gain
    and offset have a slope break each time the slewed u_s(t) crosses a grid node. This is
    why the tail appears even with the smooth 2 Hz sine. Side check, Duffing at A6, a
    ±0.2-cell 20 Hz sine: R_nyq = −183 dB (slope −31 dB/oct) inside one cell, and −159 dB
    (slope −12 dB/oct) across a node.
  - **Square edges.** The slew is a one-pole, so after a step u_s is continuous but its
    slope jumps. Duffing at A6, a 20 Hz square of 0.4 cell entirely inside one cell:
    R_nyq = −157 dB (slope −10 dB/oct). The same square with 5 ms smoothstep (C¹) edges gives
    −183.5 dB, the static level (−182.9 dB). For Lorenz at A6 the in-cell square raises R_aud
    from −154 to −144 dB and M_max from −125 to −78 dB.
  - **At full swing the table nodes dominate.** The same 5 ms C¹ edges lower R_nyq of the
    20 Hz square by only 2.5–4.8 dB at A6: Lorenz −87.5 against −82.7, Chua −72.9 against
    −68.8, Duffing −81.0 against −78.6 dB.
  - A 20 Hz square gives 9–12 dB more than a 20 Hz sine. It sweeps faster after each edge,
    and its edges add their own slope breaks.
- **Audibility.** By the screen the effect is inaudible for Lorenz and Duffing
  (M_max ≤ −8.6 dB). Chua is marginal at +0.8 dB (8 kHz band) at A6 with the 20 Hz
  square; its other square cases reach −2.8 to −1.8 dB, and its sine cases ≤ −11 dB. With
  C¹ edges the marginal case drops to −2.8 dB, so part of it comes from the edges.
- **Oversampling is not the fix.** The tail's own unaliased part in the band is larger than
  its alias (L_max is about −6 to −10 dB, in the top band). That unaliased part is a faint
  click, so oversampling would not remove it.

### 6. Oversampling

**Ceilings with M× oversampling** (same scopes as §2, all systems):

| | R_aud ≤ −80 dB | screen M ≤ 0 |
|---|---|---|
| 1× | F#6 / C6 / G5 | E7 / A#6 / F#6 |
| 2× + HB80 | > C8 / F7 / C#7 | > C8 / > C8 / B7 |
| 4× + HB80 + stage 1 | > C8 / > C8 / > C8 | > C8 / > C8 / > C8 |

- With 2×, Rikitake z at u = 1 sets F7 and Rössler z at u = 1 sets C#7 and B7.
- The F7 comes from the seed-11 spectrum, which is biased high (§2). Spectra from seeds 22
  and 33 give G7 for Rikitake z at u = 1, so F7 is conservative by two semitones. Rössler x
  at u = 1 gives G#7 with all three seeds. The 2× ceiling for the default observable is
  therefore about G7. At C8, R_aud with 2× is −62.6 to −62.7 dB for Rikitake z (seeds 22
  and 33) and −67.2 to −67.5 dB for Rössler x.

**Residual R_aud at the default** (dB re total):

| System | A7: 1× / 2× HB80 / 4× | C8: 1× / 2× HB80 / 4× |
|---|---|---|
| Lorenz | −73.8 / −168.0 / −168.1 | −61.2 / −155.1 / −155.3 |
| Rössler | −42.4 / −95.8 / −137.1 | −37.6 / −82.4 / −132.0 |
| Chua | −78.9 / −110.0 / −135.7 | −74.6 / −104.6 / −130.4 |
| Rikitake | −41.2 / −94.3 / −135.5 | −35.3 / −83.2 / −130.0 |
| Duffing | −102.0 / −197.8 / −197.6 | −84.6 / −179.9 / −179.8 |

For Rössler, Chua and Rikitake at 2×, HB60 and HB80 give the same residual. The limit there is
folding at the 96 kHz internal rate, not the filter.

**Filters.** Kaiser half-bands with passband 0–20 kHz. The stopband starts at
rate/2 − 20 kHz, where rate is the filter's input rate: 28 kHz for the 2× filters at 96 kHz,
76 kHz for the 4× first stage at 192 kHz, and 24.1 kHz at 88.2 kHz. Each has the fewest taps
whose measured stopband meets the target:

| Filter | Rate | Taps (non-zero) | β | Stopband | Group delay |
|---|---|---|---|---|---|
| HB60 | 96 kHz | 47 (25) | 6.0 | −62.0 dB | 0.24 ms |
| **HB80** | 96 kHz | **63 (33)** | 8.1 | **−81.2 dB** | **0.32 ms** |
| HB100 | 96 kHz | 79 (41) | 10.15 | −101.0 dB | 0.41 ms |
| 4× stage 1 (192 → 96 kHz) | 192 kHz | 19 (11) | 8.2 | −82.5 dB | 0.05 ms |
| HB80 at 44.1 kHz | 88.2 kHz | 111 (57) | 8.05 | −80.9 dB | 0.62 ms |

**Latency by M at 48 kHz:** 0 ms for 1×, 0.32 ms for 2×, 0.37 ms for 4×.

**Cost.** The integrator already computes intermediate states. At 48 kHz, n = ⌈Δτ/h_max⌉ is
already 5–7 sub-steps at A5, 10–14 at A6, 19–28 at A7 and 23–33 at C8. The sub-steps are
equally spaced within a sample, so tapping every (n/M)-th one gives the M× signal with no
extra RHS evaluations, provided n is rounded up to a multiple of M.

- **Integration.** Rounding n up costs at most M − 1 sub-steps. At C8 that is ≤ 5 % for 2×
  (one sub-step) and about 9 % for 4× (Rikitake, 33 → 36). It doubles (2×) or quadruples (4×)
  the small cost of the lowest notes, where n = 1.
- **Decimator.** About 33 multiply-adds per output sample per channel for 2×, or 17 with
  coefficient symmetry.

### 7. DC blocker, low notes and pitch reach

- **DC blocker.** It is linear and applied after sampling, so it cannot create or remove
  aliases. Its effect on level is now negligible. Against a 0.01 Hz blocker, the 5 Hz one
  loses at most 0.14 dB (Duffing, A1). The worst share of power below 20 Hz at A1 is 10 %
  (Duffing), then 6 % (Lorenz). The Thomas problem of the previous version (−1 dB, with most
  of the power infrasonic) left with Thomas.
- **Pitch lock off.** The fundamental is f₀·P(u_default)/P(u). It can rise by up to
  **6.4 semitones (Rikitake, at u = 0)** and 3.6 semitones (Lorenz, at u = 1), against
  ≤ 0.5 semitone for the others. The effect on a ceiling depends on where in the knob range
  the rise happens, because the tail also depends on u. Values below are for the default
  observable over the knob range, from the seed-11 universal spectra:
  - **Lorenz** rises at u = 1. Its R_aud ceiling falls from G7 to D#7. Its screen ceiling
    stays above C8.
  - **Rikitake** rises at u = 0, where its tail is mildest. At u = 1, where the tail is
    worst, lock off lowers the pitch by 4.3 semitones (P = 3.78 at u = 0, 5.47 at u_default,
    7.02 at u = 1). Its ceilings therefore rise: R_aud from C6 to E6, and the screen from
    A#6 to D#7.
  - **With 2×**, the screen still clears C8 at every u with lock off. At nominal C8 the
    worst M_max is −28 dB (Rikitake z, u = 1) and −95 dB (Lorenz z, u = 1). At C8 + 100
    cents it is −25 dB and −88 dB.
- **Pitch input.** It can drive a box up to `pitch_max`. The relevant frequency is therefore
  the highest reachable one, max(note + cents, pitch_max), not the note.

## Conclusion

At 48 kHz, aliasing is below −110 dB up to A5 for every system at its default. Where it
matters depends on the knob, because the knob is meant to be modulated.

- **Default knob and observable.**
  - R_aud ≤ −80 dB holds up to **F#6**. R_nyq ≤ −80 dB holds up to E6 (it was F#6 in v0.2).
  - By the audibility screen, aliases stay inaudible up to **E7**.
  - Rössler and Rikitake set these ceilings. In the low bands Rössler's alias sits only
    15–17 dB below the signal, but there it is a weak broad floor (−93 to −101 dBFS at A7),
    at least 7 dB below the screen threshold at A7.
- **Default observable over the whole knob range.**
  - R_aud ≤ −80 dB holds up to **C6**, about C#6 by direct renders.
  - The screen holds up to about **B6**.
  - Rikitake z at u = 1 sets both. Rössler x is next (D#6 at u = 0.875 and C7 at u = 1).
- **Any observable over the whole knob range.**
  - R_aud ≤ −80 dB holds up to **G5**, and the screen up to **F#6**. Rössler z at u = 1 sets
    both.
- **2× oversampling** with a 63-tap half-band clears the screen to C8 for all default
  observables at every knob position. It clears R_aud ≤ −80 dB to about G7 (default
  observable; F7 with the seed-11 spectrum) and C#7 (any observable).
- **4×** clears everything to C8.
- **Fast parameter modulation** adds a separate, small f⁻⁴ tail. It comes from slope breaks
  in the gain and offset: at table nodes (linear interpolation in u) and, for square or step
  modulators, at each edge (one-pole slew). It is a modulation artefact rather than an
  aliasing problem.

## Recommendations

1. **Pick the no-oversampling ceiling by scope, not at the default alone.** If v1 ships
   without oversampling, aliasing stays ≤ −80 dB over the whole knob range only up to about
   C6 (C#6 by direct renders). It stays inaudible by the screen up to about B6, and up to
   F#6 for non-default observables.
2. **Prefer a constant 2× for every box over a per-note M.**
   - Use HB80: 63 taps, 33 non-zero, β = 8.1, −81 dB, 0.32 ms at 48 kHz.
   - Every box then has the same latency. Nothing switches under glides, the pitch input or
     ±100 cents.
   - It costs ≤ 1 extra sub-step at the top notes and 33 multiply-adds per sample.
   - Use 4× (add the 19-tap first stage; 0.37 ms) only if R_aud ≤ −80 dB must hold
     everywhere. With 2×, default observables fail it from about G#7 (Rikitake z at u = 1;
     F#7 by the seed-11 spectrum) and any observable from D7 (Rössler z at u = 1). For
     default observables, 2× already meets the screen up to C8.
   - If the owner still wants a variable M, fix it per box when the box is configured. Base
     it on the highest reachable frequency, max(note + cents, pitch_max), with n₈₀ from §4.
     With pitch lock off, evaluate the pitch ratio P(u_default)/P(u) together with the tail
     at the same u. Multiplying the largest reach by the worst tail over-provisions
     Rikitake, whose reach is at u = 0 and worst tail at u = 1 (§7). Accept that boxes then
     differ in latency (0 / 0.32 / 0.37 ms).
3. **At 44.1 kHz,** the 80 dB half-band needs 111 taps (57 non-zero) and adds 0.62 ms.
4. **Implementation.**
   - Tap the RK4 sub-steps already computed, with n rounded up to a multiple of M.
   - Apply the normalization at the internal rate and the DC blocker after decimation.
   - This needs a spec change (§4.2, steps 6 and 7).
   - Cross-engine tests must use identical filter coefficients, because the rounding of n
     changes outputs at the bit level.
5. **Optional, for the modulation work.** The f⁻⁴ tail has two sources (§5), and each needs
   its own fix:
   - table nodes: interpolate μ, σ, π and P in u with a C¹ scheme (e.g. monotone cubic);
   - square or step edges: make the slew C¹, for example two cascaded one-poles. Only C¹
     (smoothstep) edges on the input were tested here, not a cascaded slew.
   - C¹ table interpolation alone leaves the edge tail for square or step modulators.
     Smoothing the computed gain and offset after the lookup would address both sources at
     once (not tested here).
   - With both slope breaks removed, the tail falls at least as f⁻⁶. In-cell tests with C¹
     edges reach the static level.
   - It is low priority: the effect is inaudible by the screen except one marginal case.
6. The previous draft's recommendation to scale the DC-blocker cut-off with the note is
   **dropped**. It addressed Thomas only, and it would have restored inaudible power.

## Uncertainties

- **Statistics.** Errors are small: from seeds, ≤ 0.6 dB for the broad-band ratios above
  −150 dB and ≤ 1.9 dB for the band measures (Rikitake A5 excepted, §3); ≤ 0.3 dB between
  8× and 32×; and ≤ 0.09 dB between native renders and the prediction. Rikitake is the
  exception: its n₈₀ varies by about ±0.5 semitone between 8 s windows (±0.9 semitone with
  4 s windows), so its ceilings carry about ±1 semitone. All Rikitake knob-grid ceilings use
  seed 11 only.
- **Boundaries.** Ceilings are uncertain by ±1 semitone near a boundary.
- **Knob grid.** It has 9 points. The worst case sits at u = 1 for Rössler, Rikitake and
  Duffing, where the trend is monotone. Chua's worst u is not monotone, so a finer grid could
  move its ceilings by about a semitone.
- **Perception.** The −80 dB and screen criteria are conventions, not listening tests. The
  screen uses in-band masking only, a tonal-masker offset and a loud calibration (96 dB SPL
  for a full-scale sine). It is meant to err towards "audible".
- **Not studied:**
  - the Output box's soft clipper (a separate nonlinearity);
  - the sum of several boxes (their aliases add in power);
  - fast modulation of the amp and pitch inputs. For the pitch input only the reach argument
    of §7 applies.

## Changes after review

| Review finding (severity) | What changed |
|---|---|
| Ceiling quoted at u_default only; "top octave" headline (medium) | Ceilings now come for three scopes and three criteria (§2). The headline is scoped, and the knob-range ceilings lead the conclusion. |
| Broad-band ratios hide local exposure (medium) | Added per-1/3-octave alias/signal ratios (L_max, L10), alias levels in dBFS and an audibility screen (§1, §2). This shows Rössler's folds in the low valleys (−15 to −17 dB). |
| 63-tap filter quoted as ≥ 80 dB; 44.1 kHz delay (low) | Designs now scan β and report the measured stopband: 63 taps give −81.2 dB at β = 8.1. The 44.1 kHz delay (0.62 ms) is stated separately. |
| Universal tail from A2 biased by the DC blocker (low) | Now built from A4 with the blocker response divided out. It agrees with the direct renders to ≤ 0.5 dB, and direct multi-seed checks cover the worst cases. |
| Rec 6 rests on infrasonic power (low) | Dropped. The DC check, re-run for v0.3, shows ≤ 0.14 dB loss and reports the share below 20 Hz. |
| Native-48 kHz check over-claimed (low) | Each band is now flagged as discriminating or not. The −80 dB claims rest on 32× and direct renders (§3). |
| Numba-cache engine issue stale (low) | Dropped. The engine does not disk-cache RHS kernels; the script keeps a private cache directory. |
| Per-note M ignores latency, glides and cents (low) | Constant 2× is now recommended. A per-box M would be fixed from the highest reachable frequency, and latencies are stated per M. |

**Effect of the v0.3 engine on the conclusions:**

- **Rikitake replaces Thomas.** With Rössler it is the most exposed system. It sets the
  default-observable ceilings over the knob range (§2); only Rössler z, a non-default
  observable, is worse.
- **New defaults.** Rössler's default moved from c = 5.7 to 6.56, which raises its n₈₀ from
  15.7 to 17.5. The default-position ceiling falls from F#6 to E6 (R_nyq).
- **Knob-range worst cases** are essentially unchanged for Rössler, because the top of its
  range is the same. Rikitake's are new. For the default observable they lie 3 semitones
  below Rössler's (R_aud: C6 against D#6).
- **Peak-limited normalization** changes only absolute levels. Rössler z is 8–11 dB quieter,
  which helps it under the screen. The ratios are unchanged.
- **The parameter slew** keeps modulated aliasing within the static range for the spiky systems
  (§5).
- **The pitch input** makes the highest reachable frequency, not the note, the quantity that
  matters. With pitch lock off, the reach must be read together with the tail at the same u
  (§7).

**Changes after the independent check (2026-10-26).** Text only; the main run was not
repeated. New numbers come from throwaway runs that reuse the script's functions (universal
spectra for seeds 22 and 33, pitch lock off on the seed-11 spectra, C¹-edged squares, band
levels of Rössler at A7 and C8).

| Check finding (severity) | What changed |
|---|---|
| §5 credits the modulation tail to the tables only; Rec 5 (low-medium) | §5 now names two sources, table nodes and the slew's slope break at square edges, with the in-cell and C¹-edge tests. Rec 5 lists a fix for each. |
| Rec 2's condition for 4× (low-medium) | 4× is needed only if R_aud ≤ −80 dB must hold everywhere: default observables fail from about G#7 at 2×, any observable from D7. The Rikitake 2× bias is two semitones (§6). "Top octave" removed. |
| §7 says every ceiling falls with pitch lock off (low) | Rewritten per system: Lorenz's R_aud ceiling falls to D#7, Rikitake's ceilings rise. Rec 2 evaluates the reach together with u. The spectra are evaluated at the shifted frequency itself, which gives D#7 for Rikitake's screen ceiling (the check's estimate from the semitone scan gave about D7). |
| Stale spec step references (low) | Steps cited by number (§4.2 steps 6 and 7), also in the script. |
| Wrong stopband edge in the filter text (low) | Stated as rate/2 − 20 kHz with the value for each filter. |
| Variability numbers (low) | Rikitake: ±0.5 semitone over 8 s windows, ±0.9 with 4 s halves. Rössler: ±0.3–0.4 % and ±0.9–1.2 %. |
| Seed spread understated (low) | §3 now gives the spread of the band measures separately. |
| Rössler's low-band ratio read as an audibility problem (low) | §1 and the Conclusion give absolute levels and screen margins. The low-band alias is a broad floor, not lines. Over the 25–500 Hz bands at A7 it lies 7 to 71 dB below the threshold; the smallest margin, 7.0 dB, is in the 200 Hz band. The check's "17–71 dB" matches the 25–100 Hz bands only. |
| Masking-offset attribution (nit) | 14.5 + z is attributed to Johnston (1988), and compared with the MPEG-1 model-1 tonal masking index. |

A second pass on the same day re-checked every number above against the throwaway outputs.
It corrected small slips: the seed-11 n₈₀ (25.7), the C¹-edge levels (−183.5 against
−182.9 dB), the Rikitake 2× level at C8 (−62.6 to −62.7 dB), the cost of rounding n for 4×
(≤ 9 % at C8), and the Rikitake ranking in the v0.3 notes. The masking offset is now cited
to Johnston (1988), as secondary sources give it; the earlier citation (Jayant, Johnston and
Safranek 1993) could not be checked.
