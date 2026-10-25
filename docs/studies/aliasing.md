<!-- Draft written by an AI agent; numbers come from lab/scripts/studies/aliasing.py and need owner review. Last updated: 2026-10-25 -->

# Aliasing versus note: when does a dynamical box need oversampling?

## Question

A dynamical box point-samples the continuous tuned trajectory x(k·t) at fs (spec §4.2 steps
5–6). There is no band-limiting step, so any power the trajectory has above fs/2 folds back
into the band as inharmonic components. For which notes does this matter at fs = 48 kHz, for
the five v1 systems? And if oversampling is needed, by what factor and with what filter?

## Method

Script: `lab/scripts/studies/aliasing.py`. Outputs (gitignored):
`lab/outputs/studies/aliasing/` (`results.json`, `worst_case.json`, `dc_check.json`, figures).
Compute was about 3.5 min, plus 1 min for `--worst-case` and 15 s for `--dc-check`.

1. **Per-note renders.** Every system, at its default parameter and observable, is rendered
   through the real `Dynamical` block (declicker, normalization and 5 Hz DC blocker included)
   at fs_hi = 8 × 48 kHz = 384 kHz. Notes A1 … A7 and C8, three seeds each, 8 s per render
   with the first 0.5 s discarded. Chaos makes renders at different rates diverge, so the
   comparison is statistical. A stationary process sampled at fs has the PSD
   S_fs(f) = Σ_m S(f + m·fs). So from the high-rate PSD S(f) I compute:
   - **R_nyq**: power above 24 kHz relative to total power. All of it folds somewhere into 0–24 kHz.
   - **R_aud**: power that folds into 20 Hz–20 kHz, relative to total power.
   - **R_1–5k**: power folding into 1–5 kHz, relative to the signal's own power in 1–5 kHz.
   - **R_A**: A-weighted folded power relative to A-weighted signal power.
2. **PSD estimator.** Welch with a Hann window and 5.86 Hz bins, applied to the *second
   difference* of the signal, then divided by |2 sin(πf/fs)|⁴ ("prewhitening"). This matters.
   Without it, window leakage from the fundamental creates a false floor in R_nyq at about
   −110 dB (Nuttall window) or −200 dB (Hann). With it, the floor is below −250 dB. First- and
   second-difference prewhitening agree to 0.0 dB wherever R_nyq > −200 dB. Total power is
   the time-domain variance. Values below −150 dB are reported as "< −150": they are far below
   any audible effect, and some are estimator floor.
3. **Checks.**
   - (a) A6, A7 and C8 re-rendered at 32× (1.536 MHz), to capture power above 192 kHz.
   - (b) At A7 and C8, the PSD of a **native 48 kHz render** compared with the prediction
     "8× PSD below 24 kHz + folded 8× PSD". The two grids share their bins exactly.
4. **Universal tail.** Time rescaling makes the spectrum at note f₀ equal to S₁(f/f₀)/f₀, so
   aliasing depends only on the harmonic number n = f/f₀. From one 8× render at A2, I compute
   the tail fraction G(n) = P(f > n·f₀)/P_total. Let n_T be the harmonic number where G drops
   to T dB. Then a criterion with fold frequency f_c holds for f₀ < f_c/n_T.
   - Fold frequencies: f_c = 24 kHz (any folding at 48 kHz), 28 kHz = 48 − 20 kHz (folding
     into ≤ 20 kHz), 24.1 kHz (the same at 44.1 kHz), and M·48 kHz − 20 kHz for M× oversampling.
   - Repeated for u ∈ {0, ¼, ½, ¾, 1} and for every audible observable (`--worst-case`).
5. **Oversampling.** The residual audible alias with 2× oversampling and a Kaiser half-band
   FIR decimator (passband 20 kHz, stopband 28 kHz) is computed from the 8× PSDs. The
   computation includes folding at the 96 kHz internal rate.

## Results

### 1. Power above Nyquist (R_nyq, dB re total power), default parameter and observable

| System (obs.) | A1 | A2 | A3 | A4 | A5 | A6 | A7 | C8 |
|---|---|---|---|---|---|---|---|---|
| Lorenz (z) | < −150 | < −150 | < −150 | < −150 | < −150 | −128.9 | **−61.2** | **−50.4** |
| Rössler (x) | < −150 | < −150 | < −150 | < −150 | −130.8 | **−71.0** | **−41.0** | **−36.4** |
| Chua (y) | < −150 | < −150 | < −150 | −137.6 | −116.5 | −95.4 | **−74.3** | **−69.4** |
| Thomas (x) | < −150 | < −150 | < −150 | < −150 | < −150 | −104.9 | **−60.3** | **−52.0** |
| Duffing (y) | < −150 | < −150 | < −150 | < −150 | < −150 | < −150 | −93.5 | **−77.0** |

Bold marks values above −80 dB.

- **Seed spread** (max − min over 3 seeds) is ≤ 0.2 dB for every value above −150 dB.
- **The 32× renders** give the same R_nyq as the 8× ones to ≤ 0.5 dB, so there is no relevant
  power above 192 kHz.
- **The native 48 kHz renders** match the prediction to ≤ 0.13 dB in every band from 5 to
  23.5 kHz. In the top band (20–23.5 kHz) the folded power is visible and predicted correctly:
  it adds 1.2–1.4 dB for Rössler, 0.4–0.9 dB for Chua and Thomas, and 0.05–0.4 dB for Lorenz
  and Duffing. Aliasing is therefore the only difference between 48 kHz and the continuous
  trajectory, and the method measures it.

![R_nyq and R_1–5k versus note](../../lab/outputs/studies/aliasing/aliasing_vs_note.png)

![Native 48 kHz render versus prediction, C8](../../lab/outputs/studies/aliasing/native48_vs_prediction.png)

### 2. Audibility-oriented measures at the top notes (dB)

| System | R_aud A6 / A7 / C8 | R_1–5k A6 / A7 / C8 | R_A A6 / A7 / C8 |
|---|---|---|---|
| Lorenz | < −150 / −72.4 / −59.8 | < −150 / −114.2 / −94.8 | −140.9 / −72.7 / −61.5 |
| Rössler | −81.2 / −45.6 / −40.5 | −118.9 / −65.8 / −57.0 | −82.7 / −50.9 / −45.2 |
| Chua | −100.3 / −78.5 / −73.9 | −114.8 / −94.0 / −88.4 | −104.5 / −83.6 / −78.3 |
| Thomas | −119.6 / −67.7 / −59.5 | < −150 / −92.0 / −78.6 | −112.6 / −69.3 / −61.2 |
| Duffing | < −150 / −111.4 / −92.0 | < −150 / < −150 / −148.0 | < −150 / −105.4 / −88.8 |

- Folds land first near Nyquist, where hearing is weakest. The 1–5 kHz band receives power
  mainly from 43–53 kHz. This is why R_1–5k is about 20–70 dB below R_nyq.
- Rössler's default spectrum is line-like (phase-coherent). Its aliases are therefore
  **inharmonic lines**, not a noise floor. At C8, near 17–23 kHz they reach the level of the
  signal between harmonics (dashed curve in the C8 figure).
- Chua's R_1–5k is about −115 dB at every note up to A6 (see §4). This is harmless.
- For scale: the box output has an RMS of −12 dBFS, so −60 dB re signal is −72 dBFS and −80 dB
  is −92 dBFS.

### 3. Thresholds: highest note that stays at or below the criterion

From the universal tail curves (default parameter and observable; n_T is the worst of 3 seeds):

| System | n₆₀ | n₈₀ | R_nyq ≤ −60 | R_nyq ≤ −80 | ≤ 20 kHz fold ≤ −60 | ≤ 20 kHz fold ≤ −80 | 44.1 kHz, ≤ 20 kHz fold ≤ −80 |
|---|---|---|---|---|---|---|---|
| Lorenz | 6.74 | 8.77 | A7 | E7 | B7 | G7 | E7 |
| Rössler | 11.07 | 15.68 | C7 | F#6 | D#7 | A6 | F#6 |
| Chua | 4.42 | 8.39 | > C8 (E8) | F7 | > C8 | G#7 | F7 |
| Thomas | 6.90 | 10.04 | G#7 | D7 | B7 | E7 | D7 |
| Duffing | 4.64 | 5.96 | > C8 (D#8) | B7 | > C8 | C#8 | B7 |

- Read the table as: aliasing exceeds the criterion from the next semitone up.
- The thresholds agree with the direct per-note values in table 1 to within 0.5 dB, which
  confirms the time-rescaling argument. Near a boundary they are uncertain by ±1 semitone:
  Thomas A7 measures −60.3 dB and sits right at the −60 dB line.

**Dependence on the knob and the observable** (n₈₀, worst over u ∈ {0, ¼, ½, ¾, 1}):

| System | default obs., u_default | default obs., worst u | any observable, worst u |
|---|---|---|---|
| Lorenz | 8.77 | 8.83 (u = 0) | 8.86 (y, u = 0) |
| Rössler | 15.68 | 22.36 (u = 1) | **34.10 (z, u = 1)** |
| Chua | 8.39 | 10.47 (u = 1) | 24.01 (x, u = 0) |
| Thomas | 10.04 | 10.64 (u = 1) | 10.64 |
| Duffing | 5.96 | 7.09 (u = 1) | 7.09 |

Only Rössler and Chua move appreciably.

- Rössler's spikes sharpen as c grows. Its x observable at u = 1 loses 6 semitones of
  headroom; z at u = 1 loses 13.
- The criterion "fold into ≤ 20 kHz stays at or below −80 dB" then holds only up to **G5** for
  Rössler z at u = 1, and up to D#6 for Rössler x at u = 1.

### 4. Shape of the tails, and why Chua is different

![Universal tail G(n) and PSD per harmonic](../../lab/outputs/studies/aliasing/tail_universal.png)

**Smooth systems.** For Lorenz, Rössler, Thomas and Duffing, which have analytic vector
fields, G(n) falls roughly exponentially in n. Between the A5 and C8 fold points the decay is
about 10 dB per harmonic for Lorenz z, 4.3 for Rössler x, 6–8 for Thomas x and 15 for Duffing y.
Raising the note by a semitone shortens the alias-free harmonic range by 5.6 %, so aliasing
switches on abruptly: Lorenz goes from −129 dB at A6 to −61 dB at A7.

**Chua.** The piecewise-linear h(x) makes ẍ jump whenever x crosses ±1. In that case x is C¹,
y is C² and z is C³, which predicts PSD tails proportional to f⁻⁶, f⁻⁸ and f⁻¹⁰. The measured
slopes over 16 ≤ n ≤ 128 are −18.0, −24.0 and −30.1 dB per octave, exactly that prediction
(the y slope stays within 0.3 dB/oct of −24 across all u and seeds).

The tail comes from the vector field, not from RK4. The per-note R_nyq of Chua follows one
law, −21.1 ± 0.1 dB per octave of note, from A1 to A7. Over that range the RK4 step in the 8×
renders varies 21-fold, from P/6982 to P/327. RK4 error at the kink would scale steeply with
the step, so it would have bent the law.

**Consequences of the Chua tail.**

- Chua's R_nyq grows by only 21 dB per octave of note.
- It is the most aliased system at low notes (−138 dB at A4) but the second-best at C8.
- Its 1–5 kHz ratio stays near −115 dB at every note up to A6. In the power-law regime the
  ratio of the two bands is fixed by (43 kHz / 1–5 kHz)⁻⁷.
- If the x observable is heard, its heavier tail (n₁₀₀ = 41) matters for very strict criteria.

### 5. The DC blocker

The DC blocker cannot create or remove aliases. It is a linear filter applied *after*
sampling, and its gain between 20 and 24 kHz differs from 1 by less than 0.003 dB.

It does matter elsewhere: it breaks the time-rescaling invariance at the bottom of the range.
The side check below compares the 5 Hz blocker with a 0.01 Hz one (`--dc-check`, 40 s
renders, 3 seeds):

| System | A1 | A2 | A4 |
|---|---|---|---|
| Thomas | −0.98 dB | −0.38 dB | −0.05 dB |
| Duffing | −0.17 dB | −0.05 dB | 0.00 dB |
| Lorenz | −0.10 dB | −0.03 dB | 0.00 dB |
| Rössler and Chua | ≤ 0.07 dB | ≤ 0.02 dB | 0.00 dB |

Thomas has slow wandering below about 0.1 f₀. The blocker removes it, so at A1 the box falls
about 1 dB short of the 0.25 RMS target (spec §3), and its timbre there is not the
time-rescaled one. This is unrelated to aliasing, but the owner may want to know.

### 6. Oversampling: residual audible alias (R_aud, dB re total), default parameter and observable

| System | A7: 1× | A7: 2× + HB60 | A7: 2× + HB80 | C8: 1× | C8: 2× + HB60 | C8: 2× + HB80 |
|---|---|---|---|---|---|---|
| Lorenz | −72.4 | −136.5 | −155.9 | −59.8 | −124.3 | −143.6 |
| Rössler | −45.6 | −104.6 | −106.0 | −40.5 | −91.3 | −91.3 |
| Chua | −78.5 | −109.6 | −109.6 | −73.9 | −104.3 | −104.3 |
| Thomas | −67.8 | −133.2 | −150.3 | −59.5 | −124.7 | −133.2 |
| Duffing | −111.3 | −174.3 | −193.7 | −92.0 | −156.1 | −175.0 |

**Filters.** Kaiser half-band FIRs at 96 kHz with passband 20 kHz and stopband 28 kHz:

| Filter | Taps | Non-zero taps | Stopband |
|---|---|---|---|
| HB60 | 47 | 25 | −59.4 dB |
| HB80 | 63 | 33 | −78.8 dB |

For 4×, a first stage from 192 to 96 kHz (stopband from 76 kHz) needs only 19 taps (11 non-zero)
for 80 dB. At 44.1 kHz the transition is 20 → 24.1 kHz, which needs 79 taps (60 dB) or
111 taps (80 dB).

**What limits the residual.** Where 2× leaves a residual near −90 dB (Rössler, Chua), the
limit is folding at the 96 kHz internal rate, not the filter.

**Worst case** (Rössler z, u = 1, C8):

- Power above 28 kHz is −10.8 dB, so the decimator needs at least 70 dB of stopband.
- Power above 76 kHz is −38 dB, so 2× is not enough.
- Power above 172 kHz is −99 dB, so 4× suffices.

**The cost is nearly free.** The integrator already computes intermediate states. At 48 kHz,
n = ⌈Δτ/h_max⌉ is already 5–9 sub-steps at A5, 10–17 at A6, 19–33 at A7 and 23–39 at C8. The
sub-steps are equally spaced in real time within a sample. Tapping every (n/M)-th sub-step
therefore gives an M× oversampled signal with no extra RHS evaluations, provided n is rounded
up to a multiple of M. That rounding costs at most M − 1 extra sub-steps, which is below 25 %
wherever oversampling is needed. The decimator costs about 33 multiply-adds per output
sample per channel for 2× and about 55 for 4×, half that with coefficient symmetry. That is
small next to 20+ RK4 sub-steps of four RHS evaluations each.

## Conclusion

At 48 kHz, aliasing is a **top-octave problem**. Up to about A5 (880 Hz) it is below
−110 dB in every system, so oversampling is unnecessary there.

**At the default parameter and observable** (criterion R_nyq):

- The −80 dB line (R_nyq) is crossed above F#6 (Rössler), D7 (Thomas), E7 (Lorenz), F7 (Chua)
  and B7 (Duffing).
- The −60 dB line is crossed above C7 (Rössler), G#7 (Thomas) and A7 (Lorenz). Chua and
  Duffing never cross it on the piano range.
- Measured in the most sensitive band (1–5 kHz) or with A-weighting, the only clearly exposed
  case is **Rössler from about A7 up**: R_A is −51 dB at A7 and −45 dB at C8, and R_1–5k is
  −66 dB and −57 dB. Its aliases are inharmonic lines.
- Lorenz and Thomas reach R_A ≈ −61 dB only at C8.

**Over the whole knob range and all observables**, the worst case is Rössler z at u = 1. There
the audible-band fold exceeds −80 dB above G5 (about 800 Hz).

**Uncertainty.**

- Statistical errors are small: ≤ 0.2 dB from seeds, ≤ 0.5 dB between 8× and 32×, and
  ≤ 0.13 dB between the native renders and the prediction.
- The threshold notes are uncertain by ±1 semitone near boundaries.
- The real uncertainty is perceptual: −60 and −80 dB are conventional criteria, not the
  result of listening tests.
- I did not study fast parameter modulation, which acts as forcing and could broaden the
  spectrum, nor the Output box's soft clipper, a separate nonlinearity that can alias.

## Recommendations

1. **v1 can ship without oversampling if notes stop at about F#6.** Up to F#6, every system's
   total folded power (R_nyq) stays at or below −80 dB at the default parameter and
   observable. For the knob's full range and all observables, the audible-band criterion
   holds only up to G5.
2. **Oversampling rule.** Use the smallest power of two M such that M·fs ≥ 20 kHz + n_T·f₀.
   - n_T is the harmonic beyond which the tail is below −80 dB, taken as the worst case over u
     for each (system, observable). Store it in the catalog: about 9 for Lorenz, 22 for
     Rössler x (34 for z), 10.5 for Chua y (24 for x), 10.6 for Thomas and 7 for Duffing.
   - With the single global value n_T = 34, the rule at 48 kHz gives:

     | Notes | Frequency | M |
     |---|---|---|
     | up to G5 | ≤ 820 Hz | 1 |
     | G#5 to C#7 | ≤ 2.23 kHz | 2 |
     | above C#7 | to D#8 | 4 |

   - At 44.1 kHz the same rule gives M = 1 up to F5, M = 2 up to B6, and M = 4 above that.
3. **Filter.** Use a linear-phase half-band FIR at 2·fs: passband 0–20 kHz, stopband from
   fs − 20 kHz, attenuation at least 80 dB (63 taps, 33 non-zero at 48 kHz). For 4×, put a
   19-tap half-band (192 → 96 kHz) in front of it. With the default observables only, 60 dB
   (47 taps) is enough. Group delay is about 0.3 ms.
4. **Implementation.** Get the oversampled signal by tapping the RK4 sub-steps the integrator
   already computes, with n rounded up to a multiple of M. This adds no RHS evaluations. Apply
   the normalization at the internal rate and the DC blocker after decimation.
5. **This needs a spec change.** Spec §4.2 steps 5–6 would gain a rule for M and the
   decimator. The rounding of n changes outputs at the bit level, so the cross-engine tests
   must use the same filter coefficients.
6. **Optional.** Make the DC-blocker cut-off scale with the note, for example min(5 Hz, f₀/100).
   Thomas would then keep its level and timbre at A1–A2 (§5).
