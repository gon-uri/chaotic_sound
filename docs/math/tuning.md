# Tuning chaos to a note

- Status: Phase 1 results (2026-10-25).
- Numbers come from `catalog/systems.json` and the lab scripts. Rerun them with
  `lab/scripts/build_catalog.py` and `lab/scripts/render_demos.py`.
- Decisions: ADR 0006 (time rescaling) and ADR 0010 (period estimation and range selection).

## 1. Tuning is a rescaling of time

A system is an autonomous ODE in its own time τ:

$$\frac{dx}{d\tau} = F(x;\,p).$$

Its main oscillation has a **characteristic period P**, in system-time units. To hear it at
the frequency f₀ (Hz), let the system's clock run k times faster than real time t (seconds):

$$\tau = k\,t,\qquad k = P\,f_0 \quad\Longrightarrow\quad \frac{dx}{dt} = k\,F(x;\,p).$$

One period P of system time now lasts 1/f₀ seconds. Three consequences:

- **The timbre does not depend on the pitch.** The trajectory, and so the waveform shape, is
  the same at every k. Only its speed changes. `08_rossler_A2_to_A5.wav` demonstrates this.
- **The integration step is independent of the sample rate.** Each audio sample at rate fs
  advances the system by Δτ = k/fs = P·f₀/fs. We take n = ⌈Δτ/h_max⌉ equal RK4 sub-steps.
  h_max is fixed in system time (h_max = P_min/N, with N = 256 steps per period and P_min the
  shortest period over the range). The cost is therefore about N·f₀/fs RK4 steps per sample
  for every system, which comes to 3–5 sub-steps at A4 and 48 kHz.
- **Moving a parameter is forcing.** When a modulator moves p(t), the system becomes
  non-autonomous, which is the owner's point that modulation is equivalent to forcing. For
  slow modulation the trajectory follows the attractor of the current p adiabatically.
  Faster modulation is genuine forcing (see `docs/studies/modulation.md`).

## 2. What is "the" period?

The owner proposed two definitions: the most prominent spectral frequency, or the period of
the most visited unstable periodic orbit (UPO). Two facts shaped the implementation.

**The period depends on which variable you look at.** dysts lists P = 1.50 for Lorenz.
Lorenz's z, however, loops with a period of 0.75, an octave higher. The x and y variables are
dominated by slow, random switching between the two lobes and are hardly pitched: their
spectral prominence is about 0.03, against 0.42 for z.

The spectral **prominence** is the fraction of the power within ±3% of the peak. It measures
how pitched a variable sounds. At the default parameters the most pitched variables are:

| System | Most pitched variable | Prominence |
|---|---|---|
| Rössler | x | 0.83 |
| Chua | y | 0.55 |
| Lorenz | z | 0.42 |
| Duffing | y | 0.28 |
| Thomas | all variables | about 0.1–0.25 |

**Estimators differ in stability.** For each system at its default parameter we ran 12
independent stretches of 2000 periods each and measured how much each estimator spread
between stretches (standard deviation in cents; 100 cents = 1 semitone):

| System | Highest bin of the peak | **Peak centroid (±10%)** | Return time between maxima |
|---|---|---|---|
| Lorenz (z) | 4.5 | **2.3** | 2.9 |
| Rössler (x) | 0.3 | **0.3** | 0.2 |
| Chua (y) | 11.0 | **3.1** | 3.6 |
| Thomas (x) | 24.7 | 17.0 | **6.3** |
| Duffing (y) | 0.1 | 0.4 | 15.0 (drive period used instead) |

Chaotic peaks are broad and have sub-structure. The highest bin jumps between sub-peaks,
while the power-weighted centroid of the peak averages over them.

**What the lab does (ADR 0010):**

1. **One period per system.** It is measured on the variable with the most prominent peak at
   the default parameter (the *tuning observable*), and used whatever variable is heard. x, y
   and z are views of the same oscillation, so the choice of variable changes the timbre,
   not the tuning.
2. **The method:**
   - Forced systems use the exact drive period 2π/ω.
   - A pitched tuning observable (prominence ≥ 0.25) uses the **peak centroid**.
   - A broadband one uses the **mean return time between maxima**. Only Thomas falls in this
     case.
3. UPO-based tuning is kept as a research item (roadmap). The return time is its cheap
   relative: for phase-coherent attractors it equals the mean period of the main loop.

## 3. Pitch lock

The lab tabulates P(u) on 129 points over the knob range u ∈ [0, 1], plus an exact node at
the default value. Engines interpolate it linearly. With pitch lock on (the default),
k(t) = P(u(t))·f₀, so the note stays fixed while the timbre changes. With it off, k uses P at
the default value, and the pitch drifts as the parameter moves.

| Lorenz ρ: 24.8 → 71.3 in 20 s at A3 | Pitch error, averaged over the sweep |
|---|---|
| pitch lock ON (`03_lorenz_sweep_locked.wav`) | −0.7 cents |
| pitch lock OFF (`03_lorenz_sweep_free.wav`) | +307 cents (rising to almost an octave at the end) |

![Lorenz sweep, pitch lock on](../figures/demo_lorenz_sweep_locked.png)
![Lorenz sweep, pitch lock off](../figures/demo_lorenz_sweep_free.png)

P(u) has real fine structure for some systems. Chua's period wiggles by ±20 cents over steps
of about 0.1 in α, near its periodic windows. A 33-point table missed this and caused 13-cent
errors. The 129-point table follows it.

## 4. Choosing the chaotic range of the knob

The owner asked for chaos only, with the route to chaos left for later (roadmap). For each
system the lab sweeps the modulated parameter over a wide **candidate range**: 241 values,
1000 periods each. It uses **continuation**: each value starts from the previous one's end
state, walking outward from the default. A slowly modulated box follows the same attractor
branch. The range then grows outward from the default while:

- the motion stays **bounded**, with a margin of 3% of the candidate width kept from any
  value where trajectories escape;
- the tuning observable stays **stationary** (no drift between the two halves of a record);
- it is **chaotic**: λ_max·P > 0.05 nats per period, using the largest Lyapunov exponent from
  the two-trajectory (Benettin) method;
- P does not **jump** by more than 15% between neighbors, since pitch lock would glitch there.

**Narrow periodic windows** (each up to 3% of the candidate width) are accepted inside the
range. Chaotic bands are full of them: a strictly windowless range would be [5.6, 5.8] for
Rössler and [0.342, 0.354] for Duffing. Inside a window the sound simply becomes periodic
for a moment. A final 129-point pass trims the range again if it reveals an unsafe point or
a jump the coarse sweep missed.

| System | Param | Range (knob 0 → 1) | Knob at default | Tuning on | Method | P across range | Chaotic | Windows | RK4 sub-steps @A4 |
|---|---|---|---|---|---|---|---|---|---|
| Lorenz | ρ | [24.8, 71.26] | 0.069 | z | peak centroid | 0.440–0.832 | 99% | 0 | 5 |
| Rössler | c | [5.512, 8.818] | 0.057 | x | peak centroid | 5.738–5.941 | 85% | 7 | 3 |
| Chua | α | [13.7, 18.05] | 0.437 | y | peak centroid | 1.409–1.686 | 91% | 6 | 3 |
| Thomas | a | [1.783, 1.945] | 0.412 | x | return time | 1.389–1.700 | 73% | 4 | 3 |
| Duffing | γ | [0.3421, 0.5667] | 0.035 | y | drive 2π/ω | 4.488 (exact) | 89% | 3 | 3 |

Why each range ends where it does:

- **Lorenz.** The low end is set by hand at 24.8, just above ρ ≈ 24.74. Below that value the
  fixed points are stable alongside the chaotic attractor, so a modulated box could fall
  silent. At the high end a periodic window near 71.5 makes the period jump by 32%.
- **Rössler.** A periodic window at c ≈ 5.21 ends the low side. At the high side the range was
  trimmed at c ≈ 8.82, where the attractor changes to the funnel type and the period jumps.
- **Chua.** A periodic window at α ≈ 13.3 ends the low side. Trajectories escape to infinity
  from α ≈ 18.45, so the range stops at 18.05. The single-scroll to double-scroll transition
  near α ≈ 14.4–14.6 lies inside the range, and there x's standard deviation doubles.
- **Thomas.** A wide periodic region lies below a ≈ 1.72, and the final pass found a drifting
  point at a ≈ 1.947.
- **Duffing.** The system is periodic below γ ≈ 0.32 and from γ ≈ 0.59. The dysts default of
  0.35 sits on a small chaotic island, linked to the main band (0.375–0.565) across the
  window 0.357–0.374.

Diagnostic figures (Lyapunov exponent, tuning curve, levels and attractor) are in
`docs/figures/catalog_<system>.png`.

## 5. Loudness

Audio is y = a · 0.25 · (x_obs − μ(u))/σ(u). The table values μ(u) and σ(u) are the mean and
standard deviation of the heard variable, so every box has an RMS of 0.25 (about −12 dBFS) at
amp = 1, whatever the system, variable or parameter. A 5 Hz DC blocker removes what is left
of the offset. Measured on the demos: RMS 0.249–0.252, peaks 0.53–0.72 per box, and no
safety resets in any demo.

## 6. Accuracy achieved

Tuning error of a single box, measured on the rendered audio with the catalog's own method
(tests: `lab/tests/test_dynamical.py`):

| System | Error at A3 (6 s demo) | Test tolerance (A2, A3, A4; ≥ 2000 cycles) | Why that tolerance |
|---|---|---|---|
| Rössler | +0.1 cents | 5 cents | estimator spread < 1 cent |
| Duffing | −0.9 cents | 5 cents | drive period is exact |
| Lorenz | −6.2 cents | 12 cents | spread ≈ 3 cents per 2000 cycles |
| Chua | −5.1 cents | 12 cents | spread ≈ 3 cents |
| Thomas | −2.2 cents | 35 cents | depends on the run: −9 … +34 cents across seeds |

About 5–10 cents is close to the smallest pitch difference listeners can notice. For
chaotic signals the pitch is inherently a little blurred: it is the centre of a broad peak.

## 7. Limits and open questions

- **Thomas is a weak voice** at dysts' parameters. Its chaotic band is narrow and full of
  windows, its spectrum has no sharp peak, and its pitch depends on the run. A screening of
  replacement candidates is in `docs/studies/fifth-system-screening.md`; the decision is in
  `docs/REVIEW.md`.
- **Multistability and hysteresis.** The tables follow one attractor branch, walking outward
  from the default. A box modulated back and forth could land on another branch, where the
  pitch or level tables do not apply.
- **Aliasing at high notes** is quantified in `docs/studies/aliasing.md`.
- **Integration resolution** (is N = 256 needed?) is covered in `docs/studies/resolution.md`.
- **Perception.** All the pitch numbers above are signal measures. Listening tests are still
  needed, especially for Thomas and Lorenz x.
- **Route to chaos** (future). Lock to the mean loop time (the return time). It stays
  continuous through period doubling, so the note holds while sub-octaves appear.

## 8. Reproduce

```bash
cd lab
caffeinate -is uv run python scripts/build_catalog.py   # ≈ 2 min: catalog + figures
uv run python scripts/render_demos.py                   # WAVs + spectrograms + report
uv run pytest -q                                        # 132 tests, incl. tuning accuracy
```
