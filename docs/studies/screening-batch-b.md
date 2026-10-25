# Screening batch B: a 5th voice to replace Thomas

Candidates: HindmarshRose, HastingsPowell, ForcedVanDerPol, ForcedBrusselator,
RabinovichFabrikant, Hadley, ChenLee, Bouali (plus Bouali2). All exist in the pinned dysts.

## Question

Which of these dysts flows is a better 5th voice than Thomas? The criteria, in order:

1. Robust: bounded at the default and over a usable range of one parameter.
2. Pitched: spectral prominence ≥ 0.3.
3. A wide chaotic range around the default with a smooth P(u).
4. Story and diversity next to Lorenz, Rössler, Chua and Duffing.

## Method

- **Wrapper** (`lab/scripts/studies/screening/dysts_adapter_b.py`). It generates an `@njit rhs(x, p, out)` that calls
  the dysts kernel `Model._rhs`, with `p` in `sorted(params)` order, which is the order dysts
  uses. It agrees with `model.rhs(X, 0)` to 0.0 relative error at 50 random points for every
  candidate. The forced systems keep dysts' phase variable `z' = w` (wrapped, `drive_frequency_param="w"`).
- **Step 1** (`probe_defaults_b.py`): `reference_scale` + `analyze_point` at the dysts default.
- **Step 2** (`scan_params_b.py`): every parameter of every candidate, 41 values over d ± 0.75·|d|.
  Uses continuation and `QUICK_SETTINGS`, then `select_chaotic_range` with the builder's tolerances.
- **Step 3** (`wide_scan_b.py`): wider scans of ChenLee c (including the c = −3.8 variant) and Brusselator f.
- **Step 4** (`build_candidates_b.py`): the full `build_system` with
  `BuildSettings(sweep_points=121, table_points=33)` for the best parameter of each candidate.
  Then an engine check: a `Dynamical` box (registered only inside the process) at A3. It renders
  4 s at 48 kHz for 6 seeds at u = 0.1, u_default and 0.9. The pitch is the spectral-peak
  centroid of the audio: Welch, 128 note periods per segment, f_min = f₀/4.
- **Step 5** (`followups_b.py`): forced van der Pol on a 20 × 27 (a, w) grid, and a
  wide-initial-condition basin check for the Brusselator (8 ICs × 3 values of f).
- Outputs are in `lab/outputs/studies/screening/batch_b/`: logs, `param_scan.json`,
  `builds/*.json|png`, `summary.md` and `forcedvanderpol_a_w_plane.png`. Total compute was about
  4 min.

λ is the largest Lyapunov exponent, in nats per P_ref (the builder's convention; for forced
systems P_ref is the drive period). "Prominence" is the fraction of power within ±3 % of the peak.

## Results

### Overview (one row per candidate)

| Candidate (param) | Bounded | Best variable, prominence (default / table median) | Chaotic range (default) | Width / default | Chaotic | λ·P @def | Max P step | Score |
|---|---|---|---|---|---|---|---|---|
| **ForcedBrusselator (f)** | yes, 100 % of all scans | y, 0.80 / 0.69 (min 0.64) | [0.0482, 0.0904] (0.05) | 0.85 | 88 %, 2 one-point windows | 0.118 | 0 (drive) | **4** |
| HastingsPowell (a2; b1) | yes, 100 % | z, 0.74 / 0.73 (min 0.41) | a2: [0.0888, 0.105] (0.1); b1: [2.98, 3.19] (3) | 0.16; 0.07 | 74 %; 79 % | 0.243 | 11.7 %; 3.1 % | 3 |
| ChenLee (c; b) | yes, but b > −4.4 escapes | z, 0.74 at default / 0.27 median | c: [−0.60, −0.375] (−0.38) | 0.59 | 97 % | 0.233 | 9.2 % (4 outliers) | 2 |
| Hadley (g) | yes | z, 0.34 / 0.19 | [0.992, 1.082] (1) | 0.09 | 97 % | 0.273 | 1.9 % | 2 |
| Bouali (y0) | yes | y, 0.25 / 0.28 (x 0.26 / 0.22) | [3.425, 4.075] (4) | 0.16 | 71 %, 5 windows | 0.046 | 0.9 % | 2 |
| RabinovichFabrikant (g) | **no**: escapes at g = 0.881, +1.2 % from the default; 48–56 % of the ±75 % scans unbounded | z, 0.15 / 0.26 (return-time method) | [0.755, 0.87] (0.87, at the edge) | 0.13 | 97 % | 0.456 | 4.7 % | 1 |
| HindmarshRose (c) | yes | y, 0.17 (return-time method) | empty: P jumps of 26–42 % within ±3 % of the default on every parameter | 0 | 2–7 % of scans | 0.334 | — | 1 |
| ForcedVanDerPol (a) | yes | x, 0.81, but at 1.6 × T_drive | **default is periodic** (λ·T = −0.20); chaotic at 2 of 540 (a, w) points | 0 | 0.4 % of the plane | −0.20 | — | 1 |

Bouali2 is not chaotic at its dysts default under the builder's criterion (λ·P = 0.027), and
its prominence is 0.10–0.14. It is rejected.

### Engine pitch check (A3, 6 seeds, cents from the note)

| Job | u = u_default | u = 0.1 | u = 0.9 |
|---|---|---|---|
| forcedbrusselator_f | −1200 (spread 0.0) | −1200 (0.0) | −1200 (0.0) |
| hastingspowell_a2 | −6…+3 | 0 (periodic window) | −18…−2 |
| hastingspowell_b1 | −6…+3 | +27 (periodic) | −52…−29 |
| chenlee_c | −3…+1 | −33…+243 | +32…+58 |
| chenlee_b | −3…+1 | +5…+25 | −53…+241 |
| hadley_g | −3…+1 | −2…+5 | −2…+8 |
| bouali_y0 | +1…+3 | −4…+2 | +2 |
| rabinovichfabrikant_g (return time) | −22…+9 | −3…0 | −55…+5 |

For comparison, Thomas measures −9…+34 cents.

### Per-candidate findings

- **ForcedBrusselator.** Brusselator: Prigogine & Lefever, *J. Chem. Phys.* 48, 1695 (1968).
  Periodically forced, it gave one of the first chemical "strange attractors" (Tomita & Kai,
  *Phys. Lett. A* 66, 91 (1978); *Prog. Theor. Phys.* 61, 54 (1979)).
  - It is robust. It stays bounded on every scan (f ∈ [0.0125, 0.25], and a, b, w at ±75 %).
    8 random ICs per value of f all reach the same attractor, with P = 15.514 = 2T and the
    same λ and prominence.
  - The response is period-doubled and phase-locked. The observable's period is 2.0000 T_drive
    (ratio 1.99996–2.00003) across the whole range. Pitch is therefore rock-steady: 0.0 cent
    spread between seeds.
  - It sounds exactly one octave below the selected note (engine issue 2). The knob changes
    chaos and timbre only, not pitch: λ·T goes from 0.1 to 0.25, and σ rises to 1.4× the
    value at u = 0.
  - Weak points:
    - The chaos is mild (λ ≈ 0.12–0.25 nats per drive period).
    - The default sits at the lower edge of the band (u_default = 0.04).
    - The story overlaps with Rössler (chemistry), and the forcing mechanism with Duffing.
  - Cost is 2 RK4 sub-steps per sample at A3.
- **HastingsPowell.** Hastings & Powell, "Chaos in a three-species food chain", *Ecology* 72,
  896 (1991). This is the "teacup" attractor, in a new field (ecology) with a strong story.
  - z is very pitched on the slow cycle (P ≈ 120–137). x and y carry the fast predator–prey
    oscillation at ≈ 3.7× f₀, an inharmonic partial.
  - The chaotic band is riddled with periodic windows wider than 3 % of the candidate range,
    and P(u) has steps of 10–12 % at the ends. The usable range is therefore only 7–16 % of
    the default.
  - Chaos continues for a2 ≈ 0.11–0.20, but P(z) falls in steps from 135 to 95 there.
- **ChenLee.** Chen & Lee, "Anti-control of chaos in rigid body motion", *Chaos Solitons
  Fractals* 21, 957 (2004). These are Euler's rigid-body equations with feedback (mechanics,
  like Duffing).
  - The dysts default (c = −0.38) sits next to a periodic window. That is why z is pitched
    there (0.74).
  - Inside the chaotic band, prominence falls to 0.1–0.3, the P(u) table needs 4 outlier
    corrections, and seeds spread up to +243 c.
  - The c = −3.8 variant, also found in the literature, behaves the same way. It is pitched
    (x: 0.76) only next to the window at c ≈ −4. Over c ∈ [−3.4, −0.3] prominence is 0.03–0.1.
- **Hadley.** This is Lorenz's 1984 general-circulation model (*Tellus A* 36, 98). dysts cites
  Hadley (1735), which is the phenomenon, not the model.
  - Chaos is confined to narrow bands (g ∈ [0.99, 1.08]; f ≈ 8.7–10.4), with prominence ≈ 0.2–0.34.
  - It is meteorology again, the same story area as Lorenz.
- **Bouali.** dysts cites Bouali, *IJBC* 9, 745 (1999), an economic model of cycles. The
  parameter set appears to be the "stretched loop" attractor of Bouali (2012).
  - It would add a new field (economics).
  - Chaos is weak (λ·P = 0.046 at the default, below the builder's 0.05 threshold with the
    table settings) and prominence is ≈ 0.25. The band is narrow and has 5 windows.
- **RabinovichFabrikant.** Rabinovich & Fabrikant, *Sov. Phys. JETP* 50, 311 (1979), on wave
  self-modulation in plasmas. It escapes 1.2 % above the default and is broadband. It fails
  criterion 1.
- **HindmarshRose.** Hindmarsh & Rose, *Proc. R. Soc. B* 221, 87 (1984), on bursting neurons.
  dysts uses a rescaled form (Marhl & Perc, 2005). The default is a chaotic sliver between
  periodic bursting regimes, so no range can be built.
- **ForcedVanDerPol.** van der Pol & van der Mark, "Frequency demultiplication", *Nature* 120,
  363 (1927). They heard "irregular noise" in the telephone receiver, arguably the first chaos
  ever heard, which is a superb story.
  - At μ = 8.53 the dynamics are mode-locked almost everywhere. The response ratio
    P_obs/T_drive jumps between 0.69 and 3 (a devil's staircase).

## Conclusion and recommendations

1. **ForcedBrusselator, modulating f, is the best voice in this batch** and on criteria 1–3 is
   clearly better than Thomas:
   - robust;
   - prominence 0.64–0.80 everywhere in the range;
   - range 0.85× the default;
   - pitch exact, with zero realization spread.

   It needs one change before adoption: the tuning period must be 2·2π/ω, not 2π/ω (issue 2).
   Without it every note sounds an octave low. A catalog field such as `drive_multiple = 2`,
   measured and checked to be constant over the range, would do this. On criterion 4 it is
   weaker: it is chemistry plus forcing.
2. **HastingsPowell is the runner-up** for its story (ecology) and its pitch.
   - Its range is narrow (a2: 16 %, 2 windows) and P(u) steps by up to 12 %.
   - It is worth a closer look only if diversity outweighs range.
   - If tried, the tuning cut-off f_min should be checked first (issue 3).
3. Reject ChenLee, Hadley, Bouali/Bouali2, RabinovichFabrikant, HindmarshRose and
   ForcedVanDerPol (dysts parameterization) as v1 voices.
4. Uncertainties:
   - Ranges come from 121-point sweeps and 33-point tables, coarser than the catalog's 241/129.
     Narrow windows can be missed, and the ends can move by about one grid step.
   - The pitch check uses 4 s renders at A3 only.
   - Citations for the forced Brusselator and Bouali (2012) are from memory and should be
     checked.

## Engine issues found (not fixed)

1. **numba cache and first-class `rhs`.** The `@njit(cache=True)` kernels in `integrate.py`
   take `rhs` as a dispatcher argument. The shared index in `lab/src/chaotic_sound/__pycache__`
   already holds at least 18 `integrate_sampled` overloads. Compiling any new `rhs` signature
   then crashed in `save_overload` with `ReferenceError: underlying object has vanished`. It
   works with a fresh `NUMBA_CACHE_DIR`, including across processes. The cause is probably a
   stale entry written by other studies' generated RHS. A new module-level system could hit
   the same error until the cache is cleared. I did not clear it, and used private cache dirs.
2. **`choose_period_method` uses `"drive"` for every forced system without checking** that the
   observable's peak is at the drive period. For the Brusselator the response is at exactly 2T,
   so the box is −1200 c off. For forced van der Pol the ratio varies from 0.69 to 3. Duffing
   should be checked the same way.
3. **`f_min = 0.25 / P_ref` uses the fastest time scale.** In slow–fast systems
   (HastingsPowell: P_ref = 35.6, tuning peak 120–137) the cut-off (periods > 142) sits just
   above the tuning peak. When the slow cycle lengthens past it, the estimator silently drops
   the peak. The scans show prominence 0 and NaN centroids, with a `RuntimeWarning` at
   `spectrum.py:98`.

## Reproduce (from `lab/`)

```bash
export NUMBA_CACHE_DIR=<private dir>   # see issue 1
uv run python scripts/studies/screening/probe_defaults_b.py
uv run python scripts/studies/screening/scan_params_b.py
uv run python scripts/studies/screening/wide_scan_b.py
uv run python scripts/studies/screening/build_candidates_b.py forcedbrusselator_f   # one job per process
uv run python scripts/studies/screening/followups_b.py
uv run python scripts/studies/screening/summarize_b.py
```
