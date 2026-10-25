# A 5th voice to replace Thomas: screening summary

Study date: 2026-10-25. This summary merges three screenings (24 dysts flows):
`screening-halvorsen-set.md`, `screening-batch-b.md`, and the Moore–Spiegel group (Rikitake,
Rucklidge, Lü, Moore–Spiegel, Colpitts, Chen, Arneodo, Genesio–Tesi; scripts and data only,
`lab/scripts/studies/screening/screen_moorespiegel_group.py`). I re-ran the leading candidates
myself before recommending (scripts `lab/scripts/studies/screening/fifth_system_*.py`, outputs
and figures in `lab/outputs/studies/screening/fifth_system/`). Compute for the re-runs: about
4 minutes of wall time.

## Question

Thomas (dysts a = 1.85, b = 10) is a weak voice:

- its chaotic band is narrow (a ≈ 1.78–1.95, 73 % chaotic, 4 periodic windows);
- it has no sharp spectral peak (prominence 0.18), so it is tuned on return times;
- its pitch depends on the realization (−9…+34 cents) and jumps by up to ±1 semitone across
  the band.

Which dysts flow should replace it? The criteria, in order:

1. **Robust.** Bounded at the default and across a usable range of one parameter, with no
   escape.
2. **Pitched.** A variable with high spectral prominence, ideally ≥ 0.3. For reference: Rössler
   x 0.85, Chua y 0.60, Lorenz z 0.43.
3. **A wide chaotic range** of one parameter around the default, with a smooth P(u).
4. **Story and diversity.** A well-known model with a good story (who, when, why), from a field
   other than meteorology (Lorenz), chemistry (Rössler), electronics (Chua) and mechanics
   (Duffing).

## Method

The screeners wrapped each dysts `_rhs` as an `@njit rhs(x, p, out)`, with the parameters in
dysts' sorted order. Every wrapper matches `model.rhs` to 0 relative error. They then ran:

- a coarse 41-point scan of every genuine parameter;
- `build_system` with `BuildSettings(sweep_points=121, table_points=33)` for the best
  parameter;
- an engine check through the real `Dynamical` block (system registered in-process only):
  tuning at A3 and a full-range LFO.

I re-ran the five strongest candidates (Rikitake, Rucklidge, Halvorsen, Moore–Spiegel, Forced
Brusselator), plus Rikitake's second knob μ, with my own wrapper (`fifth_system_verify.py`).
I added four checks the screeners had not made:

- **Production resolution.** `build_system` at 241/129, the catalog's own resolution, as well
  as at 121/33.
- **Multi-initial-condition check.** At u = 0, 0.125, …, 1 and at u_default: 8 random ICs drawn
  from N(mean, (1.5σ)²) of the default attractor, 300 + 2000 P_ref each. I recorded whether the
  orbit stays bounded, the spread of the spectral-centroid period between ICs, and its agreement
  with the table P(u).
- **Stress test** (`fifth_system_stress.py`), 8 seeds per case:
  - holds at u = 0, u_default and 1;
  - full-range sine LFOs at A3 (T = 4 s and 1 s) and at A1 (T = 0.25 s).
- **Modulation-rate test** (`fifth_system_rate.py`), 8 seeds per case, all at A1:
  - full-range sine, square and ramp LFOs with 7–220 system cycles per LFO period;
  - the same test on the five shipped systems, as a baseline.

  A run counts as **quiet** in a 0.25 s window if the window's RMS is below 0.1, i.e. 40 % of
  the 0.25 target.

The pitch estimator is the one the screeners used: the spectral centroid of the audio, with
nperseg = 2¹⁶ and f_min = f₀/4, or return times when the period method is `return_time`.
"Seeds" in engine tests perturb the IC by only 10⁻⁶ (spec §4.2 step 9). They therefore
underestimate realization dependence, which is why I added the multi-IC check.

## Results

### Table 1: all candidates, ranked

Rows marked ✓ were re-run by me and use my numbers, at 241/129 where a production build was
made. The other rows use the screeners' numbers (121/33). λ·P is in nats per P_ref, at the
default. "Score" is the screener's 0–5 score.

| # | System (knob) | Field | Bounded | Pitch var., prominence at default (table min) | Chaotic range (default) | Rel. width | Chaotic frac. | λ·P | Max P step | Score | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 ✓ | **Rikitake dynamo (μ)** | geophysics | yes, 80/80 random ICs | z, 0.54 (0.45) | [0.513, 1.8] (1) | 1.29 | 0.98, 3 one-point windows | 0.63 | 1.3 % | 5 | **Recommended** |
| — ✓ | Rikitake dynamo (a) | | yes | z, 0.54 (0.43) | [0.144, 4] at 121/33; [0.02, 4] at 241/129 (1) | 3.86 | 1.00 | 0.63 | 7.4 % | 5 | Goes quiet under fast or abrupt modulation (Table 3) |
| 2 ✓ | **Rucklidge (b)** | fluid convection | yes, 80/80 | z, 0.44 (0.18) | [4.6, 8.5] chosen by hand (6.7); prominence < 0.3 above b = 7.6 | 0.58 (0.45 on [4.6, 7.6]) | 1.00 | 0.65 | 1.2 % | 4 | Runner-up |
| 3 ✓ | **Halvorsen (a)** | none (cyclic symmetry) | yes, but 26/80 random ICs escape | z, 0.53 (0.32) | [1.289, 1.593] (1.4) | 0.22 | 0.89, 2 windows | 1.0 | 6.7 % | 4 | Third: safe but narrow, no story |
| 4 ✓ | Moore–Spiegel (a) | astrophysics | yes | x, 0.37 (0.0*) | [5.17, 25] (10), 12 windows | 1.98 | 0.94 | 0.07 | 4.8 % | 3 | Great story, but needs an engine fix and its default pitch is IC-dependent |
| 5 ✓ | Forced Brusselator (f) | chemistry, forced | yes | y, 0.80 (0.64) | [0.048, 0.090] (0.05, u_default = 0.04) | 0.85 | 0.88 | 0.12 | 0 (flat) | 4 | Exactly an octave low; needs a drive-multiple field |
| 6 | Shimizu–Morioka (b) | mathematics | yes | z, 0.38 (0.30) | [0.181, 0.528] (0.5) | 0.69 | 0.94 | 0.33 | 8.3 % | 3 | Octave-low at the top end; Lorenz look-alike |
| 7 | Lü (LuChen, c) | Lorenz family | yes | z, 0.72 (0.12) | [12.6, 22.0] (18) | 0.52 | 1.00 | 0.15 | 4.5 % | 3 | Weakly chaotic default, no diversity |
| 8 | Hastings–Powell (a2) | ecology | yes | z, 0.74 (0.41) | [0.089, 0.105] (0.1) | 0.16 | 0.74 | 0.24 | 11.7 % | 3 | Good story; narrow, riddled with windows |
| 9 | Colpitts (d) | electronics | yes | y, 0.29 (0.20) | [0.042, 0.101] (0.08) | 0.74 | 1.00 | 0.40 | 2.9 % | 2.5 | Flat P(u), marginal pitch, duplicates Chua |
| 10 | Sprott D (own a) | computer search | escape at a ≥ 3.55 | y, 0.28 (0.16) | [2.05, 3.41] (3) | 0.45 | 1.00 | 0.51 | 0.3 % | 2.5 | Bursts near escape; not a dysts parameter |
| 11 | Hadley (g) | meteorology | yes | z, 0.34 (0.10) | [0.992, 1.082] (1) | 0.09 | 0.97 | 0.27 | 1.9 % | 2 | Narrow, Lorenz-84 again |
| 12 | Bouali (y0) | economics | yes | x, 0.26 | [3.43, 4.08] (4) | 0.16 | 0.71 | 0.05 | 0.9 % | 2 | Barely chaotic, narrow |
| 13 | Aizawa (e) | tori | yes | x, 0.70 | [0.24, 0.25] (0.25) | 0.04 | 1.00 | 0.16 | 0 | 2 | No chaotic range (forced oscillator in disguise) |
| 14 | Chen–Lee (c) | mechanics | yes | z, 0.74 (0.11) | [−0.60, −0.375] (−0.38) | 0.59 | 0.97 | 0.23 | 9.2 % | 2 | Pitched only next to a window |
| 15 | Chen (b) | Lorenz family | partly (a, c escape) | y, 0.21 | [2.58, 3.58] (3) | 0.33 | 0.97 | 0.61 | 3.1 % | 2 | Unpitched |
| 16 | Genesio–Tesi (a) | control | escapes 2–6 % from the default | y, 0.54 | [0.429, 0.488] (0.44) | 0.13 | 0.97 | 0.65 | 0.3 % | 1 | Fails criterion 1 |
| 17 | Arneodo (c) | Shil'nikov | escape at 0.583 | z, 0.25 | [0.617, 1.29] (1) | 0.67 | 0.82 | 0.50 | 6.5 % | 1 | Pitch −187…−3 c at the default (two competing peaks) |
| 18 | Burke–Shaw (e) | Lorenz-like | yes | z, 0.08 | [6.5, 17.5] (13) | 0.85 | 0.97 | 1.39 | 5.6 % | 1.5 | Unpitched |
| 19 | Dadras (o) | electronics | yes | y, 0.08 | [2.7, 3.15] (2.7) | 0.17 | 1.00 | 1.10 | 2.9 % | 1 | Unpitched |
| 20 | Sprott B (own c) | computer search | yes | z, 0.08 | [0.6, 1.5] (1) | 0.90 | 0.94 | 1.38 | 6.4 % | 1 | Unpitched |
| 21 | Lorenz-84 (f) | meteorology | yes | z, 0.15 | [4.83, 4.87] (4.83) | 0.01 | 1.00 | 0.43 | 3.8 % | 1 | No range, unpitched |
| 22 | Rabinovich–Fabrikant (g) | plasma waves | escapes 1.2 % above the default | z, 0.15 | [0.755, 0.870] (0.87) | 0.13 | 0.97 | 0.46 | 4.7 % | 1 | Fails criterion 1 |
| 23 | Hindmarsh–Rose (c) | neuroscience | yes | y, 0.17 | empty | 0 | 0.02 | 0.33 | — | 1 | No range |
| 24 | Forced van der Pol (a) | electronics | yes | x, 0.81 | none: the default is periodic | 0 | 0.004 | −0.20 | — | 1 | Not chaotic in the dysts parameterization |
| ref | *Thomas (catalog)* | symmetry | yes | x, 0.18 (0.00), return time | [1.783, 1.945] (1.85) | 0.087 | 0.73, 4 windows | 0.78 | 5.8 % | — | To be replaced |

\* An artifact: x's fundamental sits at the analysis cut-off f_min (engine issue 5).

Shipped systems at the same metrics, for comparison:

| System | Rel. width | Chaotic frac. | Prominence (min) | Max P step |
|---|---|---|---|---|
| Lorenz | 1.66 | 0.99 | 0.43 (0.28) | 1.2 % |
| Rössler | 0.58 | 0.85 | 0.85 (0.45) | 1.8 % |
| Chua | 0.28 | 0.91 | 0.60 (0.24) | 5.2 % |
| Duffing | 0.64 | 0.89 | 0.24 (0.23) | 0 |

### Table 2: re-run of the leaders (screener → my re-run)

For each quantity, the screener's value comes first and my re-run follows, at 121/33 unless
marked (241/129).

| Quantity | Rikitake (a) | Rikitake (μ), recommended | Rucklidge (b) | Halvorsen (a) |
|---|---|---|---|---|
| Range at 121/33 | [0.144, 4.0] → **same** | screener alt.: [0.527, 2.11] → same | [4.02, 9.99] → **same** | [1.272, 1.587] → **same** |
| Range at 241/129 | **[0.02, 4.0]**: the low-end trim disappears | [0.513, 1.8] (candidate (0.2, 1.8)) | [4.6, 8.5] (candidate) | [1.289, 1.593] |
| Chaotic fraction, windows | 1.00, 0 → same | 0.98, 3 one-point windows at μ ≈ 0.53–0.55, 0.57, 0.73 | 0.97 → same; 1.00 on [4.6, 8.5] | 0.94 → same; 0.89, 2 windows (241/129) |
| Prominence, default (min, median) | 0.54 → 0.54 (0.43, 0.49) | 0.54 (0.45, 0.61) | 0.44 → 0.44 (0.09, 0.40); (0.18, 0.43) on [4.6, 8.5] | 0.53 → 0.53 (0.32, 0.49) |
| P(u), span, max step | 3.27–7.07, 7.4 % → same, monotone | 3.79–7.02, 1068 c, 1.3 % | 2.62–6.13, 9.6 % → same; 2.95–4.81, 845 c, 1.2 % on [4.6, 8.5] | 128 c, 5.8 % → same; 199 c, 6.7 % (241/129) |
| Bounded: sweep / 80 random ICs | 118/118 / 80/80 | 194/194 / 80/80 | 242/242 / 80/80 | 53/53 / **54/80** |
| IC-to-IC period spread vs table | ≤ ±11 c for a ≥ 1; **3–6 of 80 ICs reach another state at a ≲ 0.63** | −4.9…+5.2 c; 2/80 ICs reach a near-equilibrium oscillation | −5.6…+8.6 c on [4.6, 8.5]; at b = 4.02, P 5.2–12.4 between ICs | −6.7…+11 c |
| Engine cents at the default (6 seeds) | −1.0…+7.7 → same | −1.0…+7.7 | −3.8…+0.1 → same | −8.8…−2.8 → same |
| Engine cents across u = 0…1 (4 seeds) | −5.6…+14.5; **+670 at u = 0 at 241/129** | **−4.5…+4.8** | 121/33 build: **−1215 at u = 0, −729…−966 at u = 1**; on [4.6, 8.5]: −4.0…+8.8 | −8.4…+13.1 |
| Resets / quiet runs (stress, 6 cases × 8 seeds) | 0 / **6–8 of 8 in the fast sweep** | 0 / 0 | 0 / 0 | 0 / 0 |
| Peak / target RMS | screener: "1.31 FS" = 5.2× → up to **6.7×** (6.9× in Table 3) | ≤ 4.0× (4.5× in Table 3) | ≤ 4.0× (5.0×) | ≤ 2.9× |
| RK4 sub-steps per sample at A3 | 2–3 | 2–3 | 2 | 2 |

Also re-run and reproduced:

- **Moore–Spiegel (a).** The screener's numbers reproduce: [5.17, 25], 0.94 chaotic, 12
  windows, prominence 0.37 at the default. Two findings are new:
  - The default pitch depends on the IC: the period spreads by −25…+27 c over 8 ICs, a
    Thomas-like flaw. The engine seeds give −4.2…+17.1 c.
  - The engine plays **−148/−150 c at u = 0**. The cause is the f_min bias of engine issue 5.
- **Forced Brusselator (f).** The screener's numbers reproduce exactly. All 80 IC runs land on
  P = 2·T_drive, and the engine plays −1200.0 c at every u.

### Table 3: how fast can the knob move? (A1, 8 seeds; quiet runs / mean fraction of quiet windows)

| LFO (cycles per period) | Rikitake a ∈ [0.5, 4] | Rikitake a ∈ [0.75, 3] | Rikitake μ ∈ [0.513, 2.125] | **Rikitake μ ∈ [0.513, 1.8]** | Rucklidge b ∈ [4.6, 8.5] | Halvorsen a | Lorenz (catalog) |
|---|---|---|---|---|---|---|---|
| sine, 7 | 8/8, 79 % | 7/8, 38 % | 0 | 0 | 0 | 0 | 0 |
| sine, 14 | 8/8, 25 % | 6/8, 3.4 % | 0 | 0 | 0 | 0 | 0 |
| sine, 28 | 5/8, 1.7 % | 0 | 0 | 0 | 0 | 0 | 0 |
| sine, 55–220 | 0 | 0 | 0 | 0 | 0 | 0 | ≤ 1/8, 0.3 % |
| square, 7 | 0 | 0 | 4/8, 3.4 % | **8/8, 7.4 %** | 0 | 0 | 0 |
| square, 14–28 | ≤ 3/8, ≤ 0.9 % | ≤ 6/8, ≤ 2.8 % | ≤ 1/8, 0.3 % | 0 | 0 | 0 | 0 |
| square, 55–220 | **≤ 8/8, ≤ 11 %** | ≤ 6/8, ≤ 8.5 % | ≤ 3/8, ≤ 0.9 % | 0 | 0 | 0 | 2/8, 1.7 % (at 55) |
| ramp, 7–220 | **≤ 8/8, ≤ 14 %** | ≤ 8/8, ≤ 13 % | ≤ 4/8, ≤ 1.7 % | ≤ 1/8, 0.6 % | 0 | 0 | 0 |
| hold at u = 1 (A3, stress test) | 0 | 0 | **8/8, up to 29 %** | 0 | 0 | 0 | — |

Across all of these cases:

- there were no safety resets for any candidate;
- Rössler, Duffing and Thomas were never quiet;
- Chua was never quiet, but took **10 safety resets** under square LFOs (engine issue 3);
- the largest peak was 6.9× target RMS for Rikitake a, 4.5× for μ, 5.0× for Rucklidge and 3.0×
  for Halvorsen.

### Why the Rikitake dynamo goes quiet

The equilibria are (±k, ±1/k, μk²), with μk⁴ − a k² − μ = 0. Their Jacobian has the
characteristic polynomial

  (λ + 2μ)(λ² + k² + k⁻²),

so they are **linear centres for every a and μ**. The eigenvalues are −2μ and
±i√(k² + k⁻²), which gives a period of 4.2 at the default.

Numerically the centre is a weakly repelling focus. Started 0.02 away at a = 1, the
peak-to-peak swing of z grows only from 0.039 to 0.040 over 20 000 time units (≈ 3900
cycles). An orbit left close to an equilibrium therefore sings a faint, nearly pure sine at
2π/√(k² + k⁻²) for many seconds before it spirals back onto the attractor.

At a fixed parameter the attractor never gets that close: all holds in the recommended ranges
were clean. A fast or abrupt change of the parameter moves the equilibria, though, and can leave
the state next to one. Modulating a does this far more often than modulating μ (Table 3); I
have not worked out why. At μ = 2.125 the attractor itself has quiet spells, which is why the
μ range ends at 1.8.

Random ICs that happen to start near an equilibrium stay there for the whole record:
5 of 384 probe runs, at a = 0.15, 0.25 and 0.95 (`rikitake_probe.json`). They show σ_z of
0.06–0.3, against 0.8–1.8 on the attractor, and P = 4.2–4.5, the linear period.

There is also a second effect at low a. As a → 0 the plane x = ±y becomes invariant and
attracting, and on it the flow is conservative, with H = (z − μ)²/2 + x²/2 − ln|x|. So chaos
must die there. The 241/129 build keeps that region, and the engine plays +670 c at u = 0
(engine issue 1).

Lorenz has a mild form of the same problem (2 of 8 runs, 1.7 %), probably for the same
reason: its range starts at ρ = 24.8, just above the Hopf point ρ_H ≈ 24.74, where its foci are
only weakly unstable. I did not check this.

## Conclusion and recommendations

1. **Replace Thomas with the Rikitake dynamo, modulating μ.** It is the only candidate that is
   strong on all four criteria:
   - **Robust.** Bounded everywhere, with no escapes or resets. It passed all 6 stress cases and
     every sine LFO with no quiet windows. The exception is a square LFO toggling every 3.5
     cycles (mean 7 % quiet windows), comparable to Lorenz.
   - **Pitched.** z has prominence 0.45–0.71 over the whole range (0.54 at the default).
   - **Wide and smooth.** Relative width 1.29, second only to Lorenz in the catalog. P(u) is
     monotone, 3.79 → 7.02 (1068 c), with a largest step of 1.3 %.
   - **Accurate tuning.** −1.0…+7.7 c at the default and −4.5…+4.8 c across u, against −9…+34
     for Thomas. Eight random ICs agree within ±5 c.
   - **Story and diversity.** T. Rikitake, "Oscillations of a system of disk dynamos", *Proc.
     Camb. Phil. Soc.* 54, 89 (1958): two coupled Faraday-disc dynamos as a toy geodynamo for
     the irregular reversals of Earth's magnetic field. Its chaos was analysed later (Cook &
     Roberts, *Proc. Camb. Phil. Soc.* 68, 547 (1970); citations from memory, please check).
     Geophysics is a new field for the set. The sign flips of x and y are the "field reversals",
     and they are audible if x is chosen as the observable (unpitched, prominence ≈ 0).

   **Configuration.**

   | Setting | Value |
   |---|---|
   | dysts parameters | (a, μ) = (1, 1) |
   | `modulated_param` | `"mu"` (the dissipation, i.e. coil resistance) |
   | `candidate_range` | (0.2, 1.8). The builder at 241/129 selects **μ ∈ [0.513, 1.8]**: the low end is a periodic window at 0.46 (chaos starts at μ ≈ 0.51); the high end is chosen by hand |
   | Default | μ = 1 at u_default = 0.378 |
   | Tuning observable | **z** |
   | Period method | **`peak_centroid`** |
   | `h_max` | 0.0148 (2–3 RK4 sub-steps per sample at A3) |

   Before adopting it:

   - add it with `/add-dynamical-system`;
   - run the slow tuning tests at A2, A3 and A4 with more seeds;
   - decide on the crest factor: peaks reach 4.5× RMS, i.e. 1.1 at full scale with amp = 1;
   - optionally start at μ ≈ 0.6 to skip the onset windows at 0.53–0.57.

   Knob a has the wider pitch span: chaos continues at least to a = 10, where λ·P reaches 1.4.
   It should not be used without an engine guard against quiet traps (issue 2), and its low end
   must be set by hand (a ≥ 0.75).

2. **Runner-up: Rucklidge, modulating b ∈ [4.6, 7.6]** (dysts default a = 2, b = 6.7; z,
   `peak_centroid`).
   - It is the most robust candidate: 0 resets and 0 quiet windows in every case, all ICs agree,
     and P(u) is monotone with a largest step of 1.2 %.
   - Prominence is 0.30–0.51 on this range. It falls below 0.3 at b ≈ 7.59 and to 0.2 at 8.5,
     so the screener's 8.5 is too high.
   - The relative width is 0.45, and the tuning is −4…+9 c.
   - Weak points:
     - below b ≈ 4.4 it is an octave off;
     - its story, A. M. Rucklidge, *J. Fluid Mech.* 237, 209 (1992) on double convection, is
       fluid convection again, close to Lorenz in field and in its butterfly shape.
3. **Third: Halvorsen, modulating a ∈ [1.29, 1.59]** (z, `peak_centroid`).
   - It is pitched (0.53), strongly chaotic, and robust in the engine (0 resets and 0 quiet in
     every case, peaks ≤ 3×).
   - It is narrow (0.22) and its P(u) is bumpy (6.7 % steps next to two windows).
   - Its attractor's basin is bounded: 26/80 random ICs escape. This is harmless in the engine,
     which starts on the attractor.
   - It has no physical story. It would fill Thomas's "symmetry" role with a better sound rather
     than add a field.
4. **Not now:**
   - Moore–Spiegel has the best story after Rikitake: D. W. Moore & E. A. Spiegel, *Astrophys.
     J.* 143, 871 (1966). It needs the f_min fix (issue 5), and its default pitch depends on the
     IC (±25 c).
   - The Forced Brusselator needs a drive-multiple field (issue 6).
   - The rest fail criterion 1, 2 or 3 (Table 1).
5. **Add a modulation-rate test** (Table 3: square, ramp and fast sine LFOs, counting resets and
   quiet windows) to the checks a new system must pass. The current tests would not have caught
   Rikitake's quiet traps or Chua's resets.

### Corrections to the screener rows

- **Rikitake.** The 121/33 numbers reproduce exactly, but:
  - at 241/129 the low-end trim vanishes and u = 0 plays +670 c;
  - chaos extends to a = 10, not only to the explored edge 4;
  - knob a goes quiet under fast or abrupt modulation;
  - peaks reach 5–7× RMS, not 5.2×.

  Prefer μ.
- **Rucklidge.** The engine is also badly off at u = 1 (b ≈ 9.99: −729…−966 c, prominence
  0.09–0.10). At b = 4.02 the period differs between ICs (5.2–12.4), so near the low end the
  problem is not only the estimator. Use b ∈ [4.6, 7.6].
- **Halvorsen.** At 241/129: [1.289, 1.593], chaotic fraction 0.89, largest step 6.7 %, span
  199 c.
- **Moore–Spiegel.** The engine plays −150 c at u = 0, and the default pitch spreads by ±25 c
  between ICs.

### Engine issues (seen, not fixed)

1. **Range trimming depends on resolution.** `max_period_jump` is tested on each step of the
   P(u) table, so a finer table accepts a steeper P(u). For Rikitake a:
   - at 121/33 the builder trims at a = 0.144 (a 16 % step);
   - at 241/129 it does not trim, and the range reaches a = 0.02, next to the conservative limit
     a = 0, where the engine plays +670 c;
   - with a wider candidate window (0.02, 10) the trim moves to 0.33.

   The window and escape tolerances are fractions of the candidate width, so they too depend on
   the window the author picks.
2. **No guard against amplitude collapse.** The safety reset checks only the bounds box. A voice
   left near a weakly unstable equilibrium stays quiet for seconds:
   - Rikitake a: up to 95 % of the windows in a run;
   - Lorenz: mildly, because its range starts just above the Hopf point.

   No catalog test exercises square, ramp or fast LFOs.
3. **Chua (shipped) takes safety resets under square LFOs:** 10 resets in 24 runs (A1, 14–55
   cycles per period), with peaks at 7–8× target RMS.
4. **Pitch clarity is checked only at the default.** The prominence threshold and the period
   method are decided once, at the default. Range selection has no pitch-clarity criterion. So
   the full Rucklidge build keeps ends where prominence is 0.09 and the engine is 7–12
   semitones off.
5. **`f_min = 0.25/P_ref` uses the fastest scale.** At Moore–Spiegel's low end, x's fundamental
   (P = 1.51) sits next to the cut-off (period 1.58). The table prominence reads 0.0 and the
   engine plays −150 c. This confirms batch B's issue 3 with a measured tuning error.
6. **`choose_period_method` picks `"drive"` without checking P_obs/T_drive.** The Forced
   Brusselator plays −1200.0 c at every u and for all 80 ICs (confirms batch B's issue 2).

### Uncertainties

- Counts come from 8 seeds or ICs per case. A quiet fraction of a few percent means one or two
  short dips, and "0/8" does not exclude rare events.
- The rate tests ran at A1 only. The dynamics depend on cycles per LFO period, but the 5 ms
  declick and the 5 Hz DC blocker are in seconds, so other notes can differ slightly.
- The Rikitake μ low end is uncertain by one sweep step (±0.007 at 241/129). The top ends of
  Rikitake μ (1.8) and Rucklidge b (7.6) were set by hand. The μ ≤ 1.8 limit was tested, not
  optimized: 1.9–2.0 may also be clean, while 2.125 is not.
- The Rikitake stability statement (centres for all a, μ) is exact for the linearization. That
  the centre is weakly repelling is numerical, tested at a = 0.25, 1 and 3.
- Citations not checked against the sources: Cook & Roberts (1970), and Tomita & Kai for the
  Forced Brusselator.

### Reproduce (from `lab/`)

```bash
export NUMBA_CACHE_DIR=<scratch dir>
caffeinate -is uv run python scripts/studies/screening/fifth_system_verify.py run        # Table 2, overview.png
caffeinate -is uv run python scripts/studies/screening/fifth_system_rikitake_probe.py    # equilibria, random ICs
caffeinate -is uv run python scripts/studies/screening/fifth_system_stress.py            # stress + pitch
caffeinate -is uv run python scripts/studies/screening/fifth_system_rate.py candidates   # Table 3
caffeinate -is uv run python scripts/studies/screening/fifth_system_rate.py catalog      # Table 3 baseline
```

Figures:

- `lab/outputs/studies/screening/fifth_system/overview.png`: P(u) and prominence vs u for the
  leaders and Thomas;
- `build_<job>.png`: the builder's four-panel diagnostic for each job.
