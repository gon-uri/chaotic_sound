# Screening a 5th voice: Halvorsen, Aizawa, Dadras, Sprott B/D, Shimizu–Morioka, Lorenz-84, Burke–Shaw

Study date: 2026-10-25. Scripts: `lab/scripts/studies/screening/halvorsen_set_*.py`. Outputs and
figures: `lab/outputs/studies/screening/halvorsen_set/` (one figure per candidate,
`overview.png`, `listen_<name>.wav`). Compute: about 5 minutes of wall time in all.

## Question

Can one of these eight dysts flows replace Thomas as the 5th voice? Thomas has a narrow band,
no sharp spectral peak, and a pitch that depends on the realization. The criteria, in order:

1. Robust: bounded at the default and over a usable range, with no escape.
2. Pitched: prominence of at least 0.3.
3. A wide chaotic range with a smooth P(u).
4. A good story, and diversity with Lorenz, Rössler, Chua and Duffing.

## Method

- **Wrapping.** Each dysts `_rhs` is wrapped as a numba `rhs(x, p, out)`, with the parameters in
  dysts' sorted-key order. Sprott B and Sprott D have no parameters in dysts, so one coefficient
  became a parameter:
  - Sprott B: `z' = c − xy`, with c = 1.
  - Sprott D: `z' = xz + a·y²`, with a = 3.

  At 50 random points the RHS matches `model.rhs` exactly (error 0) for every candidate.
- **Coarse exploration** (`halvorsen_set_explore.py`). I ran 20 (system, parameter) options.
  Each one swept ×0.5…×1.5 of the default over 41 points with `QUICK_SETTINGS`. For each system I
  kept the parameter with the widest chaotic run around the default. Two systems kept two.
- **Full pipeline** (`halvorsen_set_screen.py`). I ran `build_system` with
  `BuildSettings(sweep_points=121, table_points=33)`. This is coarser than production (241/129),
  so a range end is uncertain by one sweep step. Halvorsen a: 0.012. Shimizu–Morioka b: 0.005.
  Sprott D a: 0.025.
- **Tuning test.** I used the engine's `Dynamical` block with each system registered in-process
  only. Settings:
  - A3, at least 2000 cycles, with the estimator from `tests/test_dynamical.py`.
  - 4 seeds at the default, plus 2 seeds at u = 0.1, 0.5 and 0.9.
  - For the leaders, also 2 seeds at u = 0, 0.25, 0.75, 0.95 and 1.
- **Stress test** (`halvorsen_set_robustness.py`). Each leader ran with 8 seeds in four cases, 20 s each:
  - held at u = 0 at A3;
  - held at u = 1 at A3;
  - a slow sweep, T = 4 s, at A3;
  - a fast sweep, T = 0.25 s, at A1 (about 14 cycles per sweep, far from adiabatic).

  I counted safety resets, collapses (the last second's RMS below 0.1) and the largest excursion in
  units of the target RMS.
- **λ·P** below is per tuning period, λ·P(u_default). Prominence is that of the tuning variable at
  the default, with `DEFAULT_SETTINGS`. In brackets: its minimum and median over the table.

## Results

### Table 1: catalog pipeline and tuning

| Candidate (param) | Default | Range [p_min, p_max] | Rel. width | Chaotic frac. | Tuning var / method | Prominence at default (min, median) | λ·P | P(u) span (cents) | Max P step | Cents at default (4 seeds) | Cents across u |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Halvorsen (a)** | 1.4 | [1.272, 1.587] | 0.225 | 0.94 | z / peak | **0.53** (0.36, 0.50) | 1.08 | 128 | 5.8 % | −8.8…−2.8 | −8.8…+14.3 |
| Halvorsen (b) | 4 | [3.533, 4.367] | 0.208 | 0.85 | z / peak | 0.53 (0.38, 0.49) | 1.08 | 435 | 7.6 % | −8.8…−2.8 | −17.0…+8.9 |
| **Shimizu–Morioka (b)** | 0.5 | [0.181, 0.528] | **0.693** | 0.94 | z / peak | 0.38 (0.30, 0.47) | 0.33 | 792 | 8.3 % | −6.8…−3.5 | −21…+2.3; **−1220 at u = 1** |
| Shimizu–Morioka (a) | 0.85 | [0.675, 0.961] | 0.336 | 1.00 | z / peak | 0.38 (0.23, 0.40) | 0.33 | 720 | 3.1 % | −6.8…−3.5 | **−1216 at u = 0.9** |
| Sprott D (a)* | 3 | [2.05, 3.406] | 0.452 | 1.00 | y / peak | 0.28 (0.16, 0.38) | 0.51 | **14** | 0.3 % | −0.6…+0.9 | −4.2…+1.8 |
| Aizawa (e) | 0.25 | [0.24, 0.25] | 0.040 | 1.00 | x / peak | 0.70 (0.66, 0.68) | 0.16 | 0 | 0 | 0.0 | 0.0 |
| Dadras (o) | 2.7 | [2.7, 3.15] | 0.167 | 1.00 | y / return | 0.08 | 1.10 | 137 | 2.9 % | +14…+38 | +8…+47 |
| Sprott B (c)* | 1 | [0.6, 1.5] | 0.900 | 0.94 | z / return | 0.08 | 1.38 | 644 | 6.4 % | +6…+21 | −201…+26 |
| Lorenz-84 (f) | 4.83 | [4.83, 4.87] | 0.008 | 1.00 | z / return | 0.15 | 0.43 | 174 | 3.8 % | −60…−31 | −60…+23 |
| Burke–Shaw (e) | 13 | [6.5, 17.52] | 0.848 | 0.97 | z / return | 0.08 | 1.39 | 759 | 5.6 % | +22…+39 | +2…+39 |
| *Lorenz (catalog)* | 28 | [24.8, 71.26] | 1.659 | 0.99 | z / peak | 0.43 | 0.69 | 1102 | 1.2 % | ≈ ±3 | |
| *Rössler (catalog)* | 5.7 | [5.51, 8.82] | 0.580 | 0.85 | x / peak | 0.85 | 0.46 | 60 | 1.8 % | < 1 | |
| *Chua (catalog)* | 15.6 | [13.7, 18.05] | 0.279 | 0.91 | y / peak | 0.60 | 0.65 | 311 | 5.2 % | ≈ ±3 | |
| *Thomas (catalog)* | 1.85 | [1.78, 1.95] | 0.087 | 0.73 | x / return | 0.18 | 0.74 | 349 | 5.8 % | −9…+34 | |

\* The parameter is my addition: dysts has none for Sprott B or Sprott D.

### Table 2: stress test of the leaders (8 seeds per case; resets / collapses / largest excursion in RMS units)

| Candidate | Hold u = 0 | Hold u = 1 | Sweep T = 4 s (A3) | Sweep T = 0.25 s (A1) |
|---|---|---|---|---|
| Halvorsen (a) | 0 / 0 / 2.5 | 0 / 0 / 2.3 | 0 / 0 / 2.5 | 0 / 0 / 2.6 |
| Halvorsen (b) | 0 / 0 / 2.3 | 0 / 0 / 2.5 | 0 / 0 / 2.5 | 0 / 0 / 2.5 |
| Shimizu–Morioka (a) | 0 / 0 / 3.0 | 0 / 0 / 2.4 | 0 / 0 / 3.0 | 0 / 0 / 3.2 |
| Shimizu–Morioka (b) | 0 / 0 / 2.5 | 0 / 0 / 2.5 | 0 / 0 / 3.4 | 0 / 0 / 3.7 |
| Sprott D (a) | 0 / 0 / 2.4 | 0 / 0 / **5.1** | 0 / 0 / **5.1** | **76 / 1 / 9.6** |
| Aizawa (e) | 0 / 0 / 2.7 | 0 / 0 / 2.6 | 0 / 0 / 2.7 | 0 / 0 / 2.7 |

The excursion is `max|audio| / 0.25`, the peak in units of the target RMS, so a peak of 2.5 is
0.62 at full scale. The listening renders (`listen_<name>.wav`: 3 s at the default, then a 6 s
sweep 0 → 1 → 0) all have an RMS of 0.249–0.251.

### Table 3: story and diversity

| System | Who, when, why | Diversity |
|---|---|---|
| Halvorsen | Credited to (A. D.) Halvorsen in J. C. Sprott's catalog (*Elegant Chaos*, World Scientific, 2010). As far as I could find, it was never published as a paper and has no physical model. | It is a 3-fold cyclically symmetric attractor, a mathematical object like Thomas: a better-sounding stand-in for Thomas, not a new field. |
| Shimizu–Morioka | T. Shimizu and N. Morioka, *Phys. Lett. A* 76, 201 (1980), studying how a symmetric limit cycle bifurcates into an asymmetric one. A. L. Shil'nikov, *Physica D* 62, 338 (1993), proved Lorenz-attractor bifurcations in it. It is one of the two classic normal forms for Lorenz-like attractors (Shil'nikov, Shil'nikov and Turaev, 1993). | It is a Lorenz-type butterfly with the same symmetry and z as the pitched variable. A good mathematics story, but it duplicates Lorenz in sound and in shape. |
| Sprott D (and B) | J. C. Sprott, *Phys. Rev. E* 50, R647 (1994): a systematic computer search for the algebraically simplest 3-D quadratic chaotic flows found 19 cases, A–S. | "Chaos found by computer search": a new kind of story, though not a physical field. |
| Aizawa | Y. Aizawa and T. Uezu, *Prog. Theor. Phys.* 67, 982 (1982); W. F. Langford (1984): torus bifurcations. | Torus breakdown. See the finding below. |
| Dadras | S. Dadras and H. R. Momeni, *Phys. Lett. A* (2009): a multi-scroll circuit. | Electronics, like Chua. Recent and little known. |
| Lorenz-84 | E. N. Lorenz, *Tellus A* 36, 98 (1984): a low-order model of the general circulation. | Meteorology again. |
| Burke–Shaw | R. Shaw, *Z. Naturforsch.* 36a, 80 (1981), from the Santa Cruz "Dynamical Systems Collective". | A good story, but the system is Lorenz-like. |

### Findings by candidate

- **Halvorsen.**
  - **Pitch.** By symmetry all three variables are equally pitched (0.52–0.53). The prominence stays
    at 0.36 or above across the range.
  - **Chaos.** It is the most strongly chaotic of the pitched candidates (λ·P ≈ 1.1), so expect a
    rough, buzzy timbre.
  - **Range.** The relative width is 0.225: 2.6 × Thomas, slightly below Chua.
  - **Escape.** The attractor escapes to infinity for a ≤ 1.225 (a crisis). The range's low end,
    1.272, keeps the builder's 3 % margin. Even so, no seed reset or escaped in any stress case.
  - **P(u).** The curve is bumpy: ±4 % spikes near a ≈ 1.42 and 1.51 next to periodic windows, and
    two outliers corrected. The span is small (128 cents).
  - **Tuning.** About −5 cents at the default, so in the Lorenz/Chua class. One seed reached +14
    cents at the crisis end (u = 0).
  - **Parameter b** behaves similarly. Its P(u) moves more (435 cents) and the escape is at the top
    (b ≥ 4.5).
- **Shimizu–Morioka.**
  - **Parameter b** gives the widest pitched range here (0.69), a smooth, monotonic P(u) from 14 to
    9 system-time units, and full robustness.
  - **The problem.** Near the top of both ranges, z has a competing spectral peak at 2P. The pitch
    measured on the audio there is **an octave low**: −1216 cents at a, u = 0.9, and −1220 at b,
    u = 1. The P(u) table follows the fundamental, because `robust_period_curve` replaced the 2P
    point as an outlier.
  - **The default** b = 0.5 sits at u = 0.92, only 0.03 below where the sweep's period estimate
    doubles. A usable b range would end near 0.51.
- **Sprott D.**
  - **Pitch.** P(u) is flat to 14 cents over the whole range, and the tuning is within ±4 cents
    everywhere. The knob changes only the "noisiness" at a fixed pitch.
  - **Prominence** falls from 0.6 at a ≈ 2.1 to 0.15 at a ≈ 3.4, and is 0.28 at the default.
  - **Escape** at a ≥ 3.55. Close to it there are intermittent bursts of 5 × RMS, and the fast sweep
    gave 76 resets and 1 collapse. The top would have to be trimmed to a ≲ 3.2.
  - **Parameter.** Its parameter is not a dysts parameter, which conflicts with
    `test_defaults_match_dysts` and ADR 0007.
- **Aizawa.**
  - **Hidden rotation.** In polar coordinates, `r' = r(z − b)` and `θ' = d` exactly. So x is a
    carrier at exactly d/2π with a chaotic envelope r(t), and the (r, z) subsystem is forced by
    f·cos³(dt). The system is a forced 2-D oscillator in disguise.
  - **Pitch.** Hence the tuning is exact (0.0 cents) and the prominence is 0.70. The sound is an
    amplitude-modulated sine.
  - **Chaos.** Around the dysts default, the dynamics is mostly quasi-periodic (a torus, λ ≈ 0). The
    chaotic range is e ∈ [0.24, 0.25] (relative width 0.04). Parameters a, b and d are no better.
- **Dadras, Sprott B, Burke–Shaw.** They are robust and widely chaotic, but unpitched (prominence
  ≤ 0.08). Their pitch depends on the realization (+6…+47 cents), which is worse than Thomas.
- **Lorenz-84.** At the dysts parameters it is chaotic only in a 1 % sliver around f = 4.83, and
  unpitched.

Uncertainties:
- Range ends are uncertain by one sweep step (above).
- Prominence depends on the Welch segment length: Halvorsen z reads 0.42 with `QUICK_SETTINGS` and
  0.53 with `DEFAULT_SETTINGS`. Compare candidates only at the same settings.
- Each cents figure comes from 2–4 seeds. The spreads are lower bounds on realization dependence.
- I did not test notes other than A1 and A3. Time rescaling makes the dynamics independent of the
  note.

## Conclusion and recommendations

1. **The best 5th voice in this set is Halvorsen, modulating a** (dysts default 1.4, range ≈
   [1.27, 1.59]). It beats Thomas on every criterion:
   - pitched: 0.53 against 0.18;
   - range: 2.6 × wider, chaotic fraction 0.94 against 0.73;
   - robust under fast modulation;
   - tuning about −5 ± 3 cents at the default and −9…+14 cents across the range, against Thomas's
     −9…+34 cents at the default alone.

   Its weaknesses are the story (an obscure, unpublished origin) and diversity (another abstract,
   cyclically symmetric attractor). It is best presented as "symmetry" rather than as a physical
   model. **Score 4/5.**
2. **Shimizu–Morioka (b) is the runner-up**, with the widest pitched range and the best mathematics
   story (Shil'nikov). It sounds and looks like Lorenz, though, and its top end needs trimming (to
   b ≲ 0.51) because of the octave ambiguity. **Score 3/5.**
3. **Sprott D is attractive as a "constant pitch, variable noise" voice** with a good
   computer-search story. It needs two things: an owner decision to allow a parameter that dysts
   does not have, and a trimmed top end. Its prominence is borderline. **Score 2.5/5.**
4. **Reject Aizawa for v1**, since it has almost no chaotic range at the dysts default. Its hidden
   exact rotation is a nice teaching example for a later "torus" page. **Reject Dadras, Sprott B,
   Burke–Shaw and Lorenz-84**, which are unpitched.
5. **Before adopting Halvorsen:**
   - rebuild it at production resolution (241/129);
   - run the slow tuning tests at A2, A3 and A4 with more seeds;
   - decide whether the P(u) bumps near the periodic windows at a ≈ 1.42 and 1.51 are acceptable.
     They are real period changes, and pitch lock follows them.

### Engine issues seen (not fixed)

- **numba cache misses on every run (already fixed).** When this study started, the `integrate`
  kernels that take the RHS dispatcher were `cache=True`. numba keyed the cached specialization
  on that dispatcher's per-process identity, so the cache never hit across processes and the
  index kept growing. `rk4_step`'s index had 131 entries, including 26 for `thomas_rhs`, and
  `lab/src/chaotic_sound/__pycache__` held 366 files (27 MB). With an `exec`-generated RHS,
  saving the index even crashed (`ReferenceError: underlying object has vanished`).
  `integrate.py` was changed during this study (17:04) to stop caching those kernels. My results
  are identical before and after the change. The scripts' in-process uncached swap
  (`halvorsen_set_adapter.use_uncached_kernels`) is now redundant but harmless, and they wrote
  nothing to `src/`.
- **Octave errors after the outlier filter.** `robust_period_curve` can hide a real spectral
  change. Where the strongest peak is at 2P (Shimizu–Morioka's top end), the table keeps P, and the
  pitch heard or measured is an octave lower than the note. The range check
  (`max_period_jump`) did not catch it because the table itself is smooth.
- **Parameter-free dysts flows.** `test_defaults_match_dysts` requires the same parameter set as
  dysts. So no flow without dysts parameters (Sprott A–E, J, N, S and others) can get a modulated
  parameter without an exception to ADR 0007.
