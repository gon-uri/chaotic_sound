<!-- Study written by an AI agent (2026-10-25, revised 2026-10-26); numbers from lab/scripts/studies/resolution.py. Needs owner review. -->

# Integration resolution: how many RK4 steps per period?

**Engine v0.3. Catalog `catalog/systems.json`, `metadata.generated` = 2026-10-25T20:00:03+00:00**
(Lorenz, Rössler, Chua, Rikitake, Duffing, with the ADR 0012 knob ranges and defaults, and
`steps_per_period = 256`; the Question explains how the engine and the tables use that number).
Every number below comes from this catalog.

Script: `lab/scripts/studies/resolution.py`. Run it from `lab/` with
`caffeinate -is uv run python scripts/studies/resolution.py` (defaults: 16 realizations × 10 000
periods, 6 workers). A plain run does everything, (f) included; from the parts below it should
take about 9 min. The numbers here come from a full run made before (f) existed (267 s). Parts
(d)–(d2) were then rerun with `--sweep-only` (119 s) after the follow-up (d2) was added, and (f)
was run with `--chaos-only` (250 s). Each time the script checked that the catalog was the same.
Numbers: `lab/outputs/studies/resolution/results.json`. Figures (regenerated, gitignored) are in
the same folder: `short_horizon_error.png`, `long_run_errors.png`, `envelope_default.png`,
`window_sweep.png`, `chaos_vs_n.png`.

## Question

The catalog sets `steps_per_period = 256`. The number is used in two ways:

- **Engine.** h_max = min(P_ref, P_min)/256, with P_min the shortest P(u) over the range. P_min ≤
  P_ref for all five systems, so h_max = P_min/256.
- **Tables.** The catalog builder measures every table node with h = P_ref/256, where P_ref is the
  period at the dysts parameters (the drive period, or the shortest characteristic time of the
  audible variables). A node therefore gets 256·P(u)/P_ref steps per local period: Lorenz 152–283
  (152 at u = 1), Rikitake 197–366, Chua 246–294, Rössler 251–260, Duffing 256. The engine's step
  is P_ref/P_min times finer: 1.68× (Lorenz), 1.30× (Rikitake), 1.04× (Chua), 1.02× (Rössler),
  1 (Duffing).

Is 256 needed, sufficient or overkill for the engine, with the v0.3 ranges, the peak-limited level
and the parameter slew? Compared with a reference integration, "good enough" means:

| Criterion | Tolerance | Perceptual scale |
|---|---|---|
| Pitch error | < 1 cent | Pitch discrimination is ≈ 3–10 ct for clean tones and worse for broadband ones. The box's own pitch varies between 10 000-period records (23 s at A4) by typically 0.1–1.4 ct, and by up to 16 ct (Chua, u = 1). |
| Level error | < 0.5 % of the statistic that sets the level (σ, or π where peak-limited) | 0.04 dB; loudness discrimination is ≈ 0.5–1 dB. |
| Spectral envelope | ≤ 1 dB per 1/3-octave band up to 20 f₀ | About one loudness step per band. |
| Chaos | λ·P_ref on the same side of 0.05 as the reference (the catalog's test) | None: it is ADR 0012's rule that both range ends are chaotic. |

The first three tolerances are therefore far stricter than audible. Their margins below are
safety margins, not audible differences.

## Method

- **Points.** All five systems at u = 0, the default and u = 1 (e.g. Lorenz ρ = 24.8 / 48.0 / 69.4,
  Rikitake μ = 0.513 / 1.153 / 1.8).
- **N.** N is the number of steps per period *at that knob position*: h = P(u)/N. In the engine
  N_eff(u) = n_sub·fs/f₀ ≥ N_cat·P(u)/P_min ≥ N_cat. If errors fell steadily with N, a requirement
  "N ≥ N_min at every u tested" would therefore be a requirement on N_cat. (f) shows that this
  fails at Rössler u = 0, so (f) also tests the exact N_eff values the engine uses.
- **Resolutions.** N ∈ {16, 32, 64, 128, 256, 512}. The reference is N = 1024. Its one-period error
  is 15.6–16.4× below that of N = 512 (Chua: 2.9–6.7×); see (a).
- **(a) Short horizon.** 64 points on the attractor, integrated for exactly one period. The error
  is the RMS state error in units of σ, against N = 16384.
- **(b) Long runs.** 16 realizations (32 for Duffing) × 10 000 periods after a 50-period transient.
  - Each realization starts from a point of one long reference trajectory (started from the
    catalog's initial condition, as the engine does), plus a seeded 1e-6·σ kick.
  - Every N is paired with the reference from the same initial condition.
  - Records are kept at S = min(N, 64) samples per period, and the reference is decimated to the
    same S.
  - Measured:
    - the period, with the catalog's estimator (peak centroid on the tuning variable, or the
      exact drive period for Duffing);
    - σ and the robust peak π (99.9th percentile of |x − μ|) of every audible variable;
    - the prominence;
    - 1/3-octave band powers of the heard variable from 0.5 to 20 f₀ (bands below −90 dB re total
      are not judged).
  - **Level criterion.** The engine scales by min(0.25/σ, 0.8/π), so each variable is judged on the
    statistic that sets its level. That is π for Rössler z at every u, and Rikitake y at the default
    and x, y at u = 1; σ elsewhere.
- **Verdicts (direct, no extrapolation).** For each metric, d ± SE is the mean paired difference to
  the reference.
  - **Pass** if |d| + 2 SE < tolerance, **fail** if |d| − 2 SE > tolerance, **open** otherwise.
  - N_confirmed is the smallest N that passes at all three u with no fail above it.
  - N_not-excluded is the smallest N with no fail at or above it.
  - A fit d_N = a + c·N⁻ᵖ (p = 4, Chua 2, from (a)) is kept only as a cross-check, and is rejected
    when χ²_red > 3.
- **(b2) Refinement.** Points left open at N = 64–256, where more data could settle them, got
  48 more realizations (64 in total) at N = 64, 128 and 256. Those were Rössler u = 1, Chua default
  and u = 1, and Lorenz u = 0 and default.
- **(c) Stability.** Survival over 3000 periods, 8 initial conditions, N = 8 … 48.
- **(d) Window sweep.** N = 64 and 128 against the reference at 150 knob positions: 17 uniform
  positions, plus the center of and a point just outside each edge of every catalog periodic
  window. Each position uses 4 initial conditions × 2500 periods. A difference ≥ 5 ct, ≥ 5 pp of
  prominence or ≥ 2 % in σ, and 4 SE from zero, flags an attractor switch.
- **(d2) Follow-up.** At each flagged position: N = 64 … 512 with 8 initial conditions, and the
  reference alone at u ± 1/4096 and u ± 1/1024. The second set shows how sensitive the exact system
  itself is there.
- **(e) Engine path under modulation.** The v0.3 `Dynamical` block at C8, with a 1 Hz 0 ↔ 1 square
  wave on the param input (slewed by max(5 ms, 2/f)). h_max is set for N_cat ∈ {32, 64, 128, 256},
  against N_cat = 512, with 6 seeds × 12 s. At C8, N_eff = 34, 69, 138 and 264 respectively.
  - Below ≈ 400 Hz the slew is shortest in system time (2 periods). There the audio sample grid
    alone already gives N_eff ≥ fs/f ≥ 120, whatever N_cat is.
- **(f) Chaos at the engine's step.** The catalog's chaos measure λ·P_ref (chaotic if > 0.05,
  ADR 0012), with λ from the lab's `max_lyapunov` (two-trajectory method, renormalized every P/4).
  - From 4 initial conditions on the reference attractor: a 1000-period transient at the tested
    step, then 3000 periods. The median over the 4 is classified.
  - N takes 129 values from 64 to 1024, about 2.2 % apart, at the 15 points of (b) and the seven
    (d2) positions.
  - Then, for N_cat ∈ {64, 128, 256}, λ is measured at the exact N_eff of each of the 97 notes
    C0–C8 whose N_eff lies next to a grid N classified differently from the reference (at the 15
    points only).

## Results

### (a) Order, and (c) stability floor

One-period RMS error at the default, in units of σ (order measured between N = 64 and 512, at
u = 0 / default / 1):

| System | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | Order |
|---|---|---|---|---|---|---|---|---|
| Lorenz | 8.5e-3 | 3.6e-4 | 1.7e-5 | 8.8e-7 | 5.1e-8 | 3.1e-9 | 1.9e-10 | 4.1 / 4.1 / 4.1 |
| Rössler | diverges | 5.1e-3 | 4.5e-4 | 3.4e-5 | 2.3e-6 | 1.5e-7 | 9.6e-9 | 3.9 / 3.9 / 3.8 |
| Chua | 6.7e-3 | 8.8e-3 | 5.2e-4 | 1.4e-4 | 3.3e-5 | 1.2e-5 | 4.1e-6 | **2.0 / 1.8 / 2.0** |
| Rikitake | 4.9e-2 | 3.2e-3 | 1.7e-4 | 1.0e-5 | 6.3e-7 | 4.0e-8 | 2.5e-9 | 4.1 / 4.0 / 4.3 |
| Duffing | 4.6e-3 | 2.3e-4 | 1.2e-5 | 6.8e-7 | 4.0e-8 | 2.4e-9 | 1.5e-10 | 4.1 / 4.1 / 4.1 |

- **Order.** RK4 shows order 4, except for Chua. Chua's diode is piecewise linear, so a step that
  straddles |x| = 1 makes an O(h²) error.
- **What these numbers are.** They are local truncation errors over one period. In a chaotic
  system they grow to O(σ) within a few Lyapunov times, so only their effect on the statistics
  in (b) matters.
- **Stability.** Rössler is the only system with a hard floor, set by the stiff z relaxation after
  each spike.
  - It diverges at N ≤ 16 at u = 0, N ≤ 24 at the default and **N ≤ 36 at u = 1** (8/8 runs); all
    runs survive from N = 20, 28 and 40.
  - The frozen-coefficient estimate N = P·max(c − x)/2.785 gives 23, 36 and 49, so it is
    conservative by 1.2–1.3×.
  - Rikitake loses some runs at N ≤ 16: 6/8 survive at u = 1, all survive from N = 20.
  - Lorenz, Chua and Duffing survive even at N = 8.

### (b) Long runs: smallest sufficient N

| System | Pitch < 1 ct | Level < 0.5 % | Envelope ≤ 1 dB | **All: confirmed / not excluded** | Binding point |
|---|---|---|---|---|---|
| Lorenz | 32 | 32 | 16 (to 5 f₀) | **32 / 32** | N = 16: −6.9 ± 0.4 ct at u = 0. |
| Rössler | 256 (128 not excl.) | 128 | 64 | **256 / 128** | u = 1. N = 64: −4.33 ± 0.21 ct, π_z −1.21 ± 0.05 %. N = 128: −0.72 ± 0.28 ct (open). |
| Chua | — (u = 1 unresolvable); 128 at u = 0 and default | 64 | 32 | **— / 64** | Default: −0.89 ± 0.23 ct at 64 (open), −0.40 ± 0.20 at 128. |
| Rikitake | 64 | 32 | 32 | **64 / 64** | u = 1: −2.02 ± 0.05 ct at N = 32. |
| Duffing | exact (drive) | 32 | 16 | **32 / 16** | σ_y at u = 1, N = 16: −0.36 ± 0.14 % (open). |

These are the pitch, level and envelope criteria only. The chaos test of (f) fails Rössler at
N = 128 (u = 0), so with it Rössler's "not excluded" rises to 256.

**Pitch shift at the binding points** (cents, paired difference to N = 1024, ± 1 SE; M = 64
realizations at N = 64–256 at the refined points, otherwise 16):

| System, u | 16 | 32 | 64 | 128 | 256 | 512 |
|---|---|---|---|---|---|---|
| Lorenz, u = 0 | −6.91 ± 0.35 | −0.25 ± 0.28 | +0.07 ± 0.20 | −0.04 ± 0.19 | −0.09 ± 0.17 | −0.77 ± 0.38 |
| Lorenz, default | −1.77 ± 0.16 | +0.26 ± 0.23 | +0.29 ± 0.20 | +0.27 ± 0.18 | +0.41 ± 0.17 | +0.52 ± 0.24 |
| Rössler, u = 1 | diverges | diverges | −4.33 ± 0.21 | −0.72 ± 0.28 | −0.43 ± 0.25 | −0.40 ± 0.36 |
| Chua, default | −4.37 ± 0.43 | −4.12 ± 0.42 | −0.89 ± 0.23 | −0.40 ± 0.20 | −0.46 ± 0.20 | −0.28 ± 0.40 |
| Chua, u = 1 (centroid) | −19.8 ± 6.0 | −9.6 ± 6.4 | −0.8 ± 2.7 | −1.6 ± 2.9 | −0.2 ± 2.4 | −5.6 ± 5.4 |
| Chua, u = 1 (return time) | −10.4 ± 0.9 | −4.2 ± 0.8 | −0.75 ± 0.56 | −0.58 ± 0.48 | −0.98 ± 0.47 | −1.15 ± 0.91 |
| Rikitake, default | −11.43 ± 0.26 | −0.80 ± 0.34 | −0.24 ± 0.26 | +0.04 ± 0.23 | −0.12 ± 0.28 | +0.04 ± 0.34 |
| Rikitake, u = 1 | 1/16 diverge | −2.02 ± 0.05 | −0.15 ± 0.06 | +0.02 ± 0.06 | +0.03 ± 0.04 | +0.01 ± 0.07 |

- **Shared reference.** The N at one point share all or part of their reference records, so a
  common offset is reference noise, not bias. At the refined points N = 64–256 use all 64
  realizations, while N = 16, 32 and 512 use only the first 16. Examples: Lorenz default +0.27 to
  +0.41 ct at N = 64–256 (same 64 references); Rössler u = 1 −0.43 ct at 256 and −0.40 at 512
  (64 references against their first 16).
- **Cross-check fits** (all with χ²_red ≤ 3) give the bias at N = 128:
  - Rössler u = 1: −0.25 ± 0.03 ct. That is N = 64's −4.3 ct scaled by N⁻⁴, consistent with the
    direct −0.72 ± 0.28.
  - Chua default: −0.12 ± 0.12 ct.
  - Lorenz default: 0.00 ± 0.02 ct.
- **Chua at u = 1.** The peak centroid scatters by **16 ct between 10 000-period records**, so
  1 ct cannot be resolved at any N. Resolving it at 95 % would take ≈ 2000 records per N. The
  return time (3 ct scatter) shows −4.2 ct at N = 32 and no resolved bias from N = 64 on (≤ 1–2 ct).
- **Level.** At N ≥ 128 no level error exceeds 0.25 %; the worst is Rössler π_z at u = 1, N = 128,
  −0.23 ± 0.07 %. Below that, the failures are:
  - Rössler at N = 32 (default: σ_x +0.95 ± 0.03 %);
  - Rössler at N = 64, u = 1 (π_z −1.21 %, σ_z −1.01 %);
  - Rikitake at N = 16.

  The peak-limited variables behave like the σ-limited ones: π converges with σ but is noisier.
- **Envelope.** It is the least demanding criterion.
  - At N ≥ 64 every audible band is within 0.85 dB. The worst is Rössler u = 0 (the chaos-onset
    end) at N = 128: +0.85 ± 0.03 dB in the weak 0.63 f₀ band (−35 dB), non-monotone in N
    (−0.37 at 64, −0.02 at 256). N = 128 lies in the non-chaotic band that (f) finds there.
  - The 10–20 f₀ band is within 0.3 dB from N = 64. At N = 32 it can only be measured up to the
    Nyquist frequency, 16 f₀, and the 10–16 f₀ band is −0.17 to −0.69 dB off.

### (d) Window sweep: the interior binding points are Rössler's periodic windows

Of 150 positions, the flags were:

| N | Flags |
|---|---|
| 64 | Rössler u = 0.207, 0.617, 0.676, 0.719, 0.766; Chua 0.25 (pitch); Duffing 0.875 (σ) |
| 128 | Rössler u = 0.676 only |

The follow-up (d2), with 8 initial conditions:

- **Chua and Duffing.** Neither flag reproduces: −0.1 ± 2.4 ct and σ −0.5 ± 0.5 % at N = 64. They
  were noise in the 4-run test.
- **Rössler.** At all five flagged positions the exact system is periodic, and the reference
  shifted in u reproduces the error at N.
  - 0.617, 0.719 and 0.766 are the centers of single-node catalog windows. 0.207 and 0.676 lie
    1/256 below a listed window edge, so those two windows are slightly wider than the catalog
    lists.
  - At 0.207, 0.617, 0.676 and 0.719 the reference is chaotic at u − 1/1024 (also at u − 1/4096,
    except at 0.719) and periodic at u + 1/4096 and u + 1/1024: these are window edges. At 0.766
    it is chaotic at both u − 1/1024 and u + 1/4096, so it is a window narrower than about
    1.2·10⁻³.
  - At u = 0.676:

  | Run | Pitch | Prominence | σ_z |
  |---|---|---|---|
  | N = 64 | −17.7 ct | +6.7 pp | −2.5 % |
  | Reference at u − 1/1024 | −17.7 ct | +6.6 pp | −2.6 % |
  | N = 128 | −10.6 ± 0.5 ct | +3.6 pp | −1.3 % |
  | Reference at u − 1/4096 | −14.2 ct | +5.0 pp | −2.0 % |
  | N = 256 and 512 | ≤ 0.02 ct | ≤ 0.004 pp | — |

  N = 256 and 512 show the same agreement (≤ 0.02 ct, ≤ 0.004 pp) at all five Rössler points.

The integration error near a window edge is therefore a **shift of the edge**:

| N | Edge shift (fraction of the knob range) | Where it shows |
|---|---|---|
| 64 | 2.5·10⁻⁴–10⁻³ (at 0.207 it matches the reference at u − 1/4096; at 0.617, 0.676 and 0.719, at u − 1/1024) | five Rössler positions |
| 128 | < 2.5·10⁻⁴, from the one position where it shows | one of 49 Rössler positions (0.676) |
| 256 | not measurable | — |

For scale, a 7-bit controller step is 8·10⁻³. At N = 128, a box parked exactly at such an edge
sounds like the exact system with its knob at most 0.00025 lower. No switch reproduced for Lorenz,
Chua and Rikitake at their tested positions (17, 38 and 23; Chua's flag at 0.25 did not
reproduce). These criteria cannot see a switch between chaos and a periodic orbit with nearly the
same pitch, prominence and σ; (f) tests for that.

### (e) Engine path under modulation (v0.3 slew)

- **Rössler at N_cat = 32 (N_eff = 34).** 9300 safety resets in 6/6 renders, −9.5 ± 1.1 ct, a band
  −5.0 dB off. This is the stability floor of (c).
- **Every other case** (all systems at N_cat ≥ 64; the others also at 32):
  - 0 resets;
  - |ΔRMS| ≤ 0.02 dB;
  - |Δpitch| ≤ 0.2 ct, except Rössler at N_cat = 64, −0.75 ± 0.12 ct;
  - worst audible band ≤ 0.21 dB.

The slew and the pitch-locked modulation add no requirement beyond the static one.

### (f) Chaos at the engine's step: a non-chaotic band at Rössler's low end

λ·P_ref against N is in `chaos_vs_n.png` (median of 4 initial conditions; the reference
N = 1024 is the last grid point).

**Rössler at u = 0** (c = 4.2375, the low end of the range). The reference gives 0.092–0.103.

| N | λ·P_ref (median of 4) | Classification |
|---|---|---|
| 64–110 | 0.087–0.112 | chaotic |
| 112 | 0.081 (one IC 0.000) | chaotic |
| 115–125 | 0.000 | periodic |
| 128–134 | 0.010–0.019 | not chaotic |
| 137 | 0.069 | chaotic |
| 140–1024 | 0.084–0.106 | chaotic |

- **What the box does there.** At N = 116–136 the maxima of x take 37–42 distinct values (0.01
  bins, 1000 maxima), against 175–187 at N = 256 and for the reference (separate check, not in the
  script). So the box settles on a periodic orbit, or on a thin band around one. At N = 112 the two
  checks disagree (λ: 3 of 4 ICs chaotic; maxima: 39–40 values), so the lower edge of the band is
  near 112–115.
- **Transients.** Chaotic transients there last hundreds of periods. With a 300-period transient
  instead of 1000, 2–3 of 4 ICs at N ≈ 130 still read above 0.05 over the next 1000 periods
  (separate check). At F♯4, 300 periods are 0.8 s.
- **The engine reaches the band.** N_eff = n_sub·fs/f₀ at u = 0, over the 97 notes C0–C8:

  | N_cat | Notes not chaotic at u = 0 (N_eff) |
  |---|---|
  | 64 | F♯4 (129.7); G4, G5 (122.5); G♯4, G♯5 (115.6) |
  | 128 | F♯4, F♯5, F♯6, F♯7 (129.7); C♯6, C♯7 (129.9); G♯7 (130.0); B7 (133.6); D♯7 (135.0); A6, A7 (136.4) |
  | 256 | none: every N_eff is ≥ 258.8 |

  At N_cat = 128, A4, A5 and C8 (N_eff 218.2, 163.6 and 137.6) stay chaotic; C8 is inferred from
  the grid points on either side.
- **(b) barely sees it.** At N = 128 (inside the band) the paired differences at u = 0 are
  −0.005 ct in pitch, +0.20 ± 0.007 % in π_z and +0.85 ± 0.03 dB in the weak 0.63 f₀ band, against
  −0.06 % and −0.37 dB at N = 64 and −0.01 % and −0.02 dB at 256. Whether the band is audible was
  not tested.
- **The exact system has windows close by.** Within 2.2·10⁻³ of u = 0, the reference (N = 1024,
  3 ICs, knob offsets 10⁻⁴ apart; separate check) is not chaotic in three narrow intervals:
  u − (1.9…2.1)·10⁻³, u − 9·10⁻⁴ (narrower than 2·10⁻⁴) and u + (1.0…2.1)·10⁻³. The catalog's
  grid (7.8·10⁻³) cannot see them. The orbit in the band is not the one in the window above u = 0
  (12 distinct maxima at u + 1.1…1.5·10⁻³), so the band is not simply an equivalent knob shift
  into that window. Its cause was not established.

**Everywhere else.**

- At Rössler's default and u = 1, and at all three points of Lorenz, Chua, Rikitake and Duffing,
  no N from 64 to 1024 changes the classification. The smallest margin is Chua u = 0: median
  0.066 at N = 78, against 0.087–0.094 for the reference.
- At the seven (d2) positions (f) agrees with (d)–(d2). At the five Rössler ones the reference is
  periodic, and the discretized system is chaotic from N = 64 up to 79 (u = 0.719), 85 (0.766),
  105 (0.207 and 0.617) and 152 (0.676). So at 128 only 0.676 switches, and at 256 none does.
  Chua 0.25 and Duffing 0.875 are chaotic at every N.

### Side finding: at the test points, the catalog's own errors exceed the integration errors at N ≥ 128

Catalog P(u) against pooled long reference records: 1200·log₂(P_cat/P_ref) in cents, positive =
the box sounds sharp. The z-score is against the scatter of one 2000-period record, the length the
catalog uses.

| | Lorenz | Rössler | Chua | Rikitake | Duffing |
|---|---|---|---|---|---|
| u = 0 | +2.4 ± 0.1 | 0.0 | 0.0 | +0.1 | exact |
| Default | +1.0 ± 0.1 | −0.1 | −2.8 ± 0.1 | +0.4 ± 0.1 | exact |
| u = 1 | −0.8 ± 0.1 | +3.8 ± 0.1 | −12 ± 1 (z = −0.3) | −0.4 | exact |

- **Record noise.** Every |z| ≤ 1.25, so these offsets are the catalog's record noise; Chua u = 1
  is ordinary centroid noise (36 ct per 2000-period record).
- **Estimator sampling.** The catalog samples at 32 per P_ref. Re-measuring the same reference
  trajectories at S = 32 and 16 moves the peak centroid by < 0.001 ct, so the estimator has no
  sampling bias.
- **σ and π tables** are off by up to 2.7 % (Duffing σ_y, u = 1) and 2.0 % (Rikitake π_z, default).
- **Interior (sweep).** Near windows the 129-node tables are worse:
  - P(u) is off by +23, +13, −11 and +11 ct at Rössler window edges, and by +38 ct (Chua, periodic
    orbit at u = 0.254) and +36 ± 3 ct (Chua, u = 0.965);
  - σ is off by up to 3.7 % (Rössler) and 11.6 % (Chua, u = 0.965);
  - over all sweep positions, the median |offset| is 0.2 ct (Rössler) to 2.5 ct (Chua).

At the 15 points of (b) the catalog's error is comparable to the integration bias at N = 128 or
larger. Examples: Rössler u = 1, +3.8 against −0.7 ct; Chua default, −2.8 against −0.4 ct; Lorenz
u = 0, +2.4 against −0.04 ct. Window edges are the exception: at Rössler u = 0.676 the table is off
by +10.7 ct and N = 128 by −10.6 ± 0.5 ct, the same size.

### Cost

RK4 sub-steps per sample with the engine's rule (fs = 48 kHz), at the default (maximum over u in
parentheses where different):

| N_cat | A4: Lorenz / Rikitake / others | C8: Lorenz / Rikitake / others |
|---|---|---|
| 64 | 1 (2) / 1 (2) / 1 | 7 (11) / 9 (11) / 6 (7) |
| 128 | 2 (3) / 2 (3) / 2 | 14 (21) / 17 (21) / 12 (14) |
| 256 (now) | 3 (5) / 4 (5) / 3 | 28 (42) / 33 (42) / 23 (27) |

- **Lorenz and Rikitake cost more than ADR 0006's ⌈N·f₀/fs⌉** (3 at A4 for N = 256). h_max is set
  by their shortest period, and their P(u) spans 1.85× over the range, so at the long-period end
  they take up to 1.8× more sub-steps.
- **Low notes.** At low notes the cost is one sub-step per sample whatever N_cat is: below
  fs·P_min/(N_cat·P(u)), i.e. at most 190 Hz at N = 256 and 375 Hz at N = 128.

## Conclusion

- **N = 256 is sufficient at every tested point.** Every criterion passes at 256, except Chua's
  pitch at u = 1, which no N can resolve against its 16 ct estimator noise. No window edge moves
  measurably at 256 at the seven flagged positions. In (f), no tested position changes between
  chaotic and not chaotic at N ≥ 156, and with N_cat = 256 the engine's smallest N_eff at Rössler
  u = 0 is 258.8. Modulation adds nothing.
- **128 is not safe for Rössler.**
  - At u = 0, its low end, the box is not chaotic at N ≈ 115–136 (f). With N_cat = 128, 11 of the
    97 notes have their N_eff in that band (F♯4, F♯5, F♯6, F♯7, C♯6, C♯7, D♯7, G♯7, A6, A7, B7).
    At those notes the low end breaks ADR 0012's rule that both range ends are chaotic. Pitch,
    level and envelope barely change (−0.005 ct, +0.20 %, +0.85 dB in a −35 dB band), so (b) saw
    only an unexplained deviation within tolerance.
  - At the window edge u = 0.676, N = 128 fails the pitch criterion: −10.6 ± 0.5 ct, a knob shift
    below 2.5·10⁻⁴.
  - At u = 1 its pitch bias is −0.3 to −0.7 ct (95 % bound 1.3 ct), which is not excluded.
- **For Lorenz, Chua, Rikitake and Duffing, 128 is not excluded at the tested points.** It is
  confirmed for all four (Chua except its unresolvable u = 1 pitch), and (f) finds no change
  between chaos and periodicity at any N from 64 to 1024 at their tested positions. For these four,
  256 is about 2× more than needed.
- **Below 128:**
  - Rössler fails at 64: −4.3 ct and π_z −1.2 % at u = 1, edges moved by 2.5·10⁻⁴–10⁻³, 5 notes
    not chaotic at u = 0, and a stability floor at 40.
  - Chua at 64 is open (−0.9 ± 0.2 ct), because its order is 2.
  - Lorenz, Rikitake and Duffing pass at 64 at every tested point.
- **What v0.3 changed.**
  - Rikitake (needs 64) replaces Thomas (which needed 128–256).
  - Lorenz now passes at 32. The earlier 64 came from the fit's conservative bound, not from the
    new range.
  - All binding points are Rössler's: its low end (chaos, (f)), its top end (pitch, (b)) and its
    interior window edges ((d)).
  - Peak-limited normalization and the slew change no verdict.

## Recommendations

1. **Keep `steps_per_period = 256` for v1.** It is the only value confirmed everywhere, and the only
   tested value that keeps Rössler's low end chaotic at every note.
2. **If CPU matters in the browser, use 128 for Lorenz, Chua, Rikitake and Duffing, and keep 256 for
   Rössler.** This needs per-system values in `BuildSettings.steps_per_period`.
   - It halves the high-note cost of those four (C8: 23–42 → 12–21 sub-steps per sample).
   - Do not use 128 for Rössler. At u = 0, 11 notes would not be chaotic (f); at u = 0.676 a window
     edge would move by up to 2.5·10⁻⁴ (−10.6 ct); and at u = 1 the box would be 0.3–0.7 ct flat.
   - A Rössler value between about 136 and 256 would keep N_eff above the band at u = 0 (there
     N_eff ≥ 1.011·N_cat). Only 256 was tested in (b), and other narrow windows may give other
     bands (see Uncertainties).
   - Going further, to 64 for Lorenz, Rikitake and Duffing, halves their cost again.
3. **If N_cat changes, rebuild the catalog with the engine's step convention.** The builder uses
   h = P_ref/N_cat at every node, the engine h_max = P_min/N_cat (see Question).
   - The measured effect on the pitch tables is small. The 11 ct between N = 128 and 256 at Rössler
     u = 0.676 is an integration difference at a point that is not a table node, and the table's
     own error there (+10.7 ct) is as large. The node spacing (7.8·10⁻³) is more than 30× the
     N = 128 edge shift (< 2.5·10⁻⁴), so a table rebuilt at 128 would rarely differ.
   - The chaos test is the stronger reason. The builder's range selection (ADR 0012) classifies
     each node at its own step. At N_cat = 128 with the builder's convention, Rössler u = 0 would be
     integrated with 127 steps per period, inside the non-chaotic band of (f) (inferred from the
     grid, not run).
4. **Never go below 64, nor below 128 for Chua, nor below 256 for Rössler without a new test.** For
   Lorenz and Duffing, which pass at 32, the floor of 64 is a safety margin. Rössler's measured
   stability floor is 40 at u = 1 (49 by the frozen-coefficient estimate), and its low end is not
   chaotic at N ≈ 115–136.
5. **Spend effort on the tables, not on finer steps.** For tuning accuracy:
   - the 129-node tables are off by 10–38 ct and up to 12 % in σ next to periodic windows (finer
     tables or local smoothing there would help);
   - Chua's top end needs longer or repeated records, since its centroid pitch scatters by ±36 ct
     per 2000-period record.
6. **Update ADR 0006 item 4.** The cost is ⌈N·(P(u)/P_min)·f₀/fs⌉, not ⌈N·f₀/fs⌉: Lorenz and
   Rikitake take up to 1.8× more.
7. **Run this script on every new system** (`--systems name`). The window sweep (d)–(d2) is what
   finds interior sensitivities, and (f) is what finds changes between chaos and periodicity at the
   engine's actual N_eff.
8. **Optionally, smooth Chua's diode** to restore order 4. This is an owner decision, because it
   changes the system's definition.

## Uncertainties

- **Statistical floor.** The 1-ct test is below it at Chua u = 1 (any N) and at it for Rössler
  u = 1 at N = 128. There the verdicts are bounds, not values. Differences at different N share all
  or part of their reference records, so they are correlated.
- **Sweep sensitivity.** The sweep (4 × 2500 periods) only detects gross switches (≥ 5 ct, ≥ 5 pp
  or ≥ 2 %).
  - Windows narrower than the catalog's sweep grid were not targeted.
  - N = 256 was tested only at the seven flagged positions.
  - Rössler has 11 windows; edges other than those tested may also move at N = 128, by similarly
    tiny amounts.
  - Its criteria cannot see a switch between chaos and a periodic orbit with nearly the same
    statistics, as at Rössler u = 0 and N = 128.
- **Chaos check (f).**
  - It covers 22 positions. Rössler's low end has windows narrower than 2·10⁻⁴ next to it, so
    similar non-chaotic bands may exist at other u and other N, including near 256.
  - Grid N are 2.2 % apart. A band narrower than that between two agreeing grid points would be
    missed, and notes whose N_eff falls between two agreeing grid points were not run directly.
    Notes with N_eff above 1024 (the lowest notes) are assumed to behave like the reference.
  - Near the band edges single ICs scatter (at N = 134 one IC gives 0.058, the others 0.016–0.019),
    and transients last hundreds of periods.
- **Modulation.** It was tested at one note (C8) with one waveform (a 1 Hz square), 6 seeds, on the
  param input only. The v0.3 pitch input was never driven. With a pitch cable N_eff changes
  continuously with f₀, down to N_cat·P(u)/P_min (129.4 at Rössler u = 0 for N_cat = 128), so at
  N_cat = 128 some pitches fall in the band of (f). Arithmetic below float64 was not tested.
- **Robust peak.** π (99.9th percentile) is noisier than σ, so its level verdicts are less tight.

## Changes after review

- **Verdicts.** They now come only from direct paired differences, with automatic refinement
  (64 realizations) at the open binding points. The N⁻ᵖ fit is a cross-check and is rejected above
  χ²_red 3. Chua's default is now stated as a measured −0.40 ± 0.20 ct at N = 128.
- **Thomas.** Its claims, including the extrapolation through the attractor switch, are gone with
  the system; Rikitake is covered instead.
- **Catalog pitch offsets.** They are measured against pooled records (48–144 per point), with the
  record scatter and a z-score. Chua u = 1 is −12 ± 1 ct with z = −0.3, i.e. noise.
- **Estimator sampling bias.** It is measured on the same trajectories: < 0.001 ct for the peak
  centroid, the only estimator in v0.3. The return-time bias the reviewer found applied to Thomas.
- **Rössler stability.** It is measured (20 / 28 / 40), and the frozen-coefficient value is called
  conservative.
- **Attractor switches and coverage.** The three-point claims are replaced by the 150-position
  sweep and its follow-up. These show that switches are window-edge shifts of 2.5·10⁻⁴–10⁻³
  (N = 64) and < 2.5·10⁻⁴ (N = 128) of the knob range.
- **Catalog against integration.** This comparison now covers all three u, against direct
  integration biases. The claim of 10–1000× was dropped.
- **Perception.** The tolerances are related to perceptual scales.
- **Reproducibility.**
  - The default `--periods` is 10 000, and the wall times are stated.
  - The N = 32 high-frequency band is labeled 10–16 f₀.
  - The "80 dB" sentence is now about local truncation error only.
- **Engine v0.3.**
  - It covers the new ranges and defaults, and Rikitake.
  - The level criterion follows the peak-limited normalization.
  - The engine-path test under square modulation exercises the v0.3 slew.
  - The reference is N = 1024, and the cost table uses the v0.3 block API.
- **Second review (2026-10-26).**
  - Part (f), a Lyapunov check at the engine's N_eff, was added. It found the non-chaotic band at
    Rössler u = 0 (N ≈ 115–136), so 128 is no longer recommended for Rössler. The conclusion and
    recommendations 1–4 and 7 changed.
  - "128 is not excluded anywhere" and the side finding's title are now limited to the test
    points; N = 128 fails at the edge u = 0.676.
  - The two uses of `steps_per_period` (engine h_max = P_min/256, tables h = P_ref/256) are stated.
    Recommendation 3 now rests on the chaos test, not on the 11 ct.
  - The edge descriptions now separate window centers from points outside an edge, describe the
    narrow window at 0.766, and give the N = 64 shift as 2.5·10⁻⁴–10⁻³.
  - Smaller fixes: the reference sets at refined points, "at the tested positions", the sweep's
    median offset (0.2–2.5 ct), the N = 512/1024 error ratio, the untested pitch input, and the
    floor of 64 labelled as a safety margin.
