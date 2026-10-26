<!-- Study written by an AI agent (2026-10-25, revised 2026-10-26); numbers from lab/scripts/studies/cost.py. Needs owner review. -->

# Compute cost of a dynamical box

**Numbers from engine v0.3**, meaning the Python reference engine in `lab/` (its version string
still reads 0.1.0), and the catalog `catalog/systems.json` with `metadata.generated` =
2026-10-25T20:00:03+00:00. The systems are Lorenz, Rössler, Chua, Rikitake and Duffing. The
TypeScript engine package (`packages/engine`, in progress) was **not** benchmarked.

Scripts:

- `lab/scripts/studies/cost.py`. Run it from `lab/` with
  `caffeinate -is uv run python scripts/studies/cost.py --chrome` (602 s wall time). It uses
  `jsc` (ships with macOS) and node if installed. `--chrome` also starts the installed Google
  Chrome headless, with a throwaway profile, for one V8 run.
- `lab/scripts/studies/rk4_bench.js`, the JavaScript benchmark. `rk4_bench.html` runs it in any
  browser.

Numbers are in `lab/outputs/studies/cost/`: `results.json`, `summary.md` (every table, all
engines) and `js_<engine>.json`. The figures `cost_vs_substeps.png` and `breakdown.png` are in
the same folder; they are gitignored and the script regenerates them.

## Question

How expensive is one dynamical box? What does that mean for the planned real-time engine?
That engine is TypeScript in an AudioWorklet, with 128-sample render quanta at 48 kHz, so each
quantum has a budget of 2667 µs. How many boxes fit in 50 % of one core, and is WebAssembly
needed?

## Method

- **Machine.** Apple M1 Pro, macOS 14.3.1, Python 3.14.6, numba 0.68.0, numpy 2.5.4. Other jobs
  were running at the same time (load average 5–21 on 10 cores).
- **JavaScript engines.**
  - JavaScriptCore (JSC, Safari's engine): the `jsc` shell, 3 runs.
  - V8, in two forms: node 24.22 (3 runs) and headless Chrome 155 (1 run).

  Each run is a separate process. Each configuration has a JIT warm-up of ≥ 2000 quanta, then
  3 timed repetitions of 4 s of audio, then 1 repetition timed per quantum.
- **Kernels compared.**
  - **A, specialized**: code generated per system, with the RHS inlined and the state held in
    scalar locals.
  - **B, literal port**: `rhs(x, p, out)` on `Float64Array`s plus a shared `rk4Step`. This is
    the structure of the Python kernel, and of `packages/engine/src/core/dsp/rk4.ts` as of
    this writing.
  - **C, full v0.3 box**: A plus everything `Dynamical.process` does per sample (spec §4.2
    steps 1–8):
    - pitch;
    - the smoothers, with the parameter slew max(5 ms, 2/f);
    - the perceptual amp curve g = a^1.661;
    - the u → p map;
    - the P/μ/σ/π table lookups (an exact `np.interp`);
    - the peak-limited level min(0.25/σ, 0.8/π);
    - the DC blocker, flush-to-zero and the safety check.

    C is called once per quantum, writes `Float32Array`s and allocates nothing.
  - **Native ceiling**: hand-written numba kernels with scalar locals for all five systems. This
    is LLVM-optimized machine code.
- **Box modes** (C, for each system × {A1, A3, A5, A7}):
  - `default`: knob at the default u.
  - `worst`: knob where P(u), and therefore n, is largest.
  - `lfo`: a 4 s full-range sine on `param`.
  - `pitch`: a cable on the pitch input.
  - `linear`: `amp_curve = "linear"`.

  Static knobs are passed as a `Float64Array` filled with the knob value.
- **Statistics.**
  - "Mean": the median over all timed repetitions (min–max in `summary.md`).
  - "p99" and "peak16": from the per-quantum repetition. peak16 is the largest moving average
    over 16 quanta (43 ms).
  - Box counts = 1333 µs ÷ mean, rounded down, which is **average-load capacity**. The saved
    `summary.md` rounds to the nearest box, so some of its counts are one higher (JSC, A7,
    worst knob: 12/22/10/11/11 there, 11/22/9/10/11 here). The script now rounds down.
- **Python engine.** `Dynamical.process` timed in 128- and 512-sample chunks, `render_tuned`
  timed alone, and an instrumented copy of `process` (bit-identical output) for the per-stage
  breakdown.
- **Checks.**
  - JS kernels A and B reproduce numba **bit for bit** for all five systems in JSC, node and
    Chrome. That includes Duffing's `cos`.
  - The JS box matches the Python block to ≤ 3·10⁻⁸ over 0.1 s, which is float32 rounding. Eight
    cases were checked, including a moving pitch cable, linear amp, and all five systems.
  - The scalar numba kernels are bit-identical to the engine kernel.
  - No safety resets occurred in any run.

## Results

### 1. Sub-steps per sample

n = ⌈Δτ/h_max⌉ = ⌈N·(P(u)/P_min)·f₀/fs⌉, with N = 256 (spec §4.2 step 6). The cells give the
default knob / worst knob / LFO mean (LFO min–max):

| System | P_def/P_min | P_max/P_min | A3 (220 Hz) | A5 (880 Hz) | A7 (3520 Hz) |
|---|---|---|---|---|---|
| Lorenz | 1.23 | 1.86 (u = 0) | 2 / 3 / 2.2 | 6 / 9 / 6.7 | 24 / 35 / 25.4 (19–35) |
| Rössler | 1.03 | 1.03 | 2 / 2 / 2.0 | 5 / 5 / 5.0 | 20 / 20 / 19.8 |
| Chua | 1.03 | 1.20 | 2 / 2 / 2.0 | 5 / 6 / 5.7 | 20 / 23 / 20.9 (19–23) |
| Rikitake | 1.45 | 1.85 (u = 1) | 2 / 3 / 2.3 | 7 / 9 / 7.3 | 28 / 35 / 27.6 (19–35) |
| Duffing | 1.00 | 1.00 | 2 / 2 / 2.0 | 5 / 5 / 5.0 | 19 / 19 / 19.0 |

At A1, n = 1 everywhere.

- **The new default knobs make Lorenz cheaper at the default, but not in the worst case.**
  - Lorenz's default moved from ρ = 28 to 48. That takes A7 from 33 sub-steps to 24.
  - Its worst knob (u = 0) still needs 35.
  - Rikitake (new) needs 28 at the default and 35 at the worst knob.

  So the worst knob costs up to 1.5× the default (measured at A3–A7: Lorenz 1.40–1.49×,
  Rikitake 1.25–1.45×), and budgets must use it (§3).
- **Rounding up adds cost below A5.** Taking n up to the next integer costs ×1.18–1.70 at A3,
  ×1.03–1.07 at A5 and ×1.01–1.04 at A7, relative to the continuous estimate
  N·(P/P_min)·f₀/fs. That estimate (cost ∝ f₀, independent of fs) is therefore good only from
  about A5 up.
- **44.1 kHz** (computed from n, not timed): the RK4 work per second of audio, against 48 kHz,
  is 0.92× at A1 and A3, 1.02–1.10× at A5 and 0.965–1.024× at A7. Over every note from A1 to
  C8 it is 0.92–1.84×. The top value occurs below A5, at notes where n is 1 at 48 kHz and 2 at
  44.1 kHz (for example Rössler at F3). From A5 up it stays within 0.92–1.10×.

### 2. Cost of one RK4 step (ns, minimum over runs)

| System | numba engine kernel | numba scalar | JSC A | V8 A (Chrome) | JSC B | V8 B | A, 2 states interleaved (per state), JSC / V8 |
|---|---|---|---|---|---|---|---|
| Lorenz | 59.7 | 24.8 | 25.8 | 24.4 | 62.1 | 57.2 | 13.1 / 12.5 |
| Rössler | 56.9 | 22.4 | 23.2 | 22.4 | 61.6 | 55.9 | 11.8 / 11.6 |
| Chua | 72.0 | 45.6 | 45.6 | 44.5 | 70.7 | 67.4 | 23.2 / 22.3 |
| Rikitake | 58.1 | 27.1 | 27.2 | 26.6 | 63.7 | 57.7 | 14.0 / 13.7 |
| Duffing | 157 | 31.2 | 46.2 | 39.0 | 82.7 | 95.6 | 29.7 / 32.0 |

- **Specialized JS matches native scalar code**, except for Duffing.
  - Lorenz, Rössler, Chua and Rikitake: JSC is within 4 % of numba, and V8 within 3 %.
  - Duffing is 1.25× native in V8 and 1.48× in JSC. The gap is probably the `cos` call (the JS
    engines' own implementation against libm); this was not tested further.
- **Structure matters more than language.** The literal port B costs 2.2–2.7× of A for Lorenz,
  Rössler and Rikitake, 1.5× for Chua and 1.8–2.5× for Duffing.
  - This holds in both JS engines and in numba: the numba engine kernel against scalar numba
    is 1.6–2.5×, and 5× for Duffing.
  - Megamorphic B, one copy shared by all systems, cost at most 3 % more than monomorphic B in
    the best run (≤ 0.5 % in V8). The exception is Duffing in JSC, at 22 % more.
- **The step is latency-bound.** Two independent states stepped in one loop cost 1.9–2.0×
  less per state for four systems, and 1.2–1.6× less for Duffing.
- **Absolute step costs are 12–18 % higher than in the first version of this study.** This is
  the same code (Lorenz numba scalar: 24.8 against 22.0 ns), so it reflects the machine state.
  Ratios between kernels were stable.

### 3. One box in JavaScript: default knob, worst knob, per-quantum tail

µs per 128-sample quantum, default knob / worst knob, then in brackets the boxes that fit in
50 % of one core at the worst knob. JSC first, V8 (Chrome) second:

| System | A1 | A3 | A5 | A7 |
|---|---|---|---|---|
| Lorenz | 5.0 / 4.6 (288) · 5.2 / 5.1 (259) | 7.9 / 11.2 (119) · 8.1 / 11.3 (117) | 20.6 / 30.6 (43) · 20.7 / 30.1 (44) | 78.3 / 114 (11) · 77.2 / 111 (11) |
| Rössler | 4.5 / 4.5 (297) · 5.1 / 5.1 (259) | 7.5 / 7.5 (177) · 7.8 / 7.8 (170) | 16.3 / 16.4 (81) · 16.5 / 16.5 (80) | 59.9 / 59.7 (22) · 59.9 / 59.6 (22) |
| Chua | 6.0 / 5.9 (224) · 6.8 / 6.9 (194) | 11.8 / 11.8 (113) · 12.6 / 12.5 (106) | 29.6 / 35.2 (37) · 29.9 / 35.7 (37) | 118 / 135 (9) · 116 / 133 (10) |
| Rikitake | 4.9 / 4.6 (288) · 5.3 / 5.8 (229) | 8.6 / 11.5 (116) · 8.7 / 12.6 (105) | 25.5 / 32.6 (40) · 25.8 / 33.1 (40) | 98.9 / 123 (10) · 97.3 / 122 (10) |
| Duffing | 8.8 / 8.5 (157) · 11.2 / 11.1 (119) | 14.1 / 14.0 (95) · 16.2 / 16.2 (82) | 32.1 / 32.1 (41) · 31.1 / 31.2 (42) | 117 / 117 (11) · 101 / 101 (13) |

- **JSC and V8 agree within 3 % from A5 up.** At A1–A3, where bookkeeping dominates, V8 is
  1–25 % slower. Duffing differs most: V8 is 15–31 % slower at A1–A3 and 13 % faster at A7.
- **An LFO peaks at the worst-knob cost.** Its 43 ms peak (peak16) is 1.00–1.07× the worst-knob
  mean at A7 and 1.08–1.21× at A5. The static worst-knob rows show 1.04–1.23× from jitter
  alone. The cycle average understates the load by 1.25–1.36× for Lorenz and Rikitake at A7
  (Lorenz: 84 against 114 µs).
- **Per-quantum tail** (JSC, timer 0.73 µs, A5–A7 rows):
  - p99 is 1.06–1.42× the mean.
  - The slowest single quantum of each configuration was 1.5× the mean or more, and up to
    5.5 ms. That is preemption by the other jobs on this machine.
  - Counted from p99 at the worst knob, A7 fits 8–17 boxes (instead of 9–22) and A5 fits 29–76
    (instead of 37–81).
  - The node runs were disturbed by that load: repetitions of the same configuration spread up
    to 4.6×. Node therefore enters only as minima. Chrome's 100 µs timer gives means only.
- **Per-sample model.** A fit of ns/sample = c₀ + c₁·n gives c₁ equal to the step cost, and c₀
  equal to the bookkeeping not hidden behind the RK4 dependency chain:
  - c₀ = 1–17 ns in JSC and 9–17 ns in V8, except Duffing in V8 (48 ns).
  - c₀ = 2–5 ns with the linear amp curve (V8: 0–3, Duffing 26). That bound covers every other
    per-sample stage, including the new peak table and min().

### 4. What the v0.3 controls cost (ns per sample, JSC / V8)

| Control | A1 | A3 | A5 | A7 |
|---|---|---|---|---|
| Perceptual amp curve (`Math.pow` per sample), versus linear | 0–10 / 8–25 | 0–13 / 9–26 | 0–13 / 9–25 | 0–16 / 12–15 |
| Pitch cable (per-sample `pow` for f and `exp` for the slew coefficient) | 26–32 / 19–40 | 21–36 / 14–39 | 6–19 / 12–36 | 1–15 / 17–33 |

- **Both costs matter only at low notes.** At A1 the JSC box costs 3.8–7.5 µs with linear amp,
  4.5–8.8 µs perceptual and 8.6–12.2 µs with a pitch cable. At A7 the pitch cable adds
  0.2–3 % to the box in JSC and 2–7 % in V8.
- **The slew is free without a pitch cable.** f is then constant, so its coefficient is
  computed once. The slew bounds how fast n can change, but not n_max.
- **The peak-limited level** is inside c₀ (linear), so it costs ≤ 5 ns.

### 5. Many boxes in one engine loop

All boxes are LFO-modulated and summed into one bus, timed over a full 4 s LFO cycle. Values
are µs per quantum, JSC (V8):

| Patch | Mean | Sum of single-box means | peak16 | p99 (JSC) | % of budget (mean / peak16) |
|---|---|---|---|---|---|
| 5 boxes, each system at A3 | 65 (65) | 55 (62) | 64 | 74 | 2 / 2 |
| 40 boxes, 8 of each system at A3 | 464 (504) | 438 (492) | 589 | 577 | 17 / 22 |
| 20 boxes, every system × {A1, A3, A5, A7} | 772 (711) | 703 (706) | 800 | 838 | 29 / 30 |
| 40 boxes, 2 × the previous | 1569 (1422) | 1406 (1412) | 1925 | 1913 | 59 / 72 |
| 16 boxes at A7 (3 of each system + 1 Lorenz) | 1553 (1481) | 1530 (1486) | 1609 | 1668 | 58 / 60 |

The cost is linear in the number of boxes. JSC adds 1.5–19 % over the sum of single boxes and V8
adds at most 6 %. The cause of the JSC excess is unexplained. It is probably not the catalog
tables leaving the L1 cache. The 5-box patch has the largest excess (+19 %), but its tables
take about 25 KB (5 tables of 129–130 doubles per box), well inside the 128 KB L1 data cache
of an M1 Pro performance core. V8 runs the same data layout on the same hardware with at most
6 % excess. A JSC code effect is possible, for example the bus loop calling every box through
one call site (`B.fn`) that sees five different functions (not tested).

### 6. Python engine (offline only, ADR 0001)

- **One box with a static knob runs at the following real-time factor (RTF):**

  | Chunk size | A1 | A3 | A7 |
  |---|---|---|---|
  | 512 samples | 71–111 | 47–84 | 7–16 |
  | 128 samples | 43–56 | 33–48 | 6–14 |

- **v0.3 is slower at low notes.** At A1, 128-sample chunks ran at 58–85 in v0.2.
  - The fixed cost per `process` call rose from 22.5 to 31 µs.
  - The "controls" stage is 17–22 % of a call at A1 (`breakdown.png`). It computes the slew
    coefficient with `np.exp` on every sample, even when the pitch is fixed, plus the
    `a**1.661`.
- **Whole patch.** LFO → Lorenz A3 → Output renders at RTF 64 with 512-sample blocks (v0.2: 80)
  and RTF 33 with 128-sample blocks (v0.2: 43).
- **The JS box is much faster.** It is 1.9–10.6× faster than `process()` in 128-sample chunks,
  and 1.6–3.3× faster than `render_tuned` alone.

## Conclusion

- **One box is cheap.**
  - At A3 it takes 0.3–0.6 % of an M1 Pro core (JSC 0.28–0.53 %, V8 0.29–0.61 %).
  - At A7 it takes 2.2–4.4 % at the default knob and up to 5.1 % at the worst knob.
  - ADR 0002 quotes "0.2–0.4 % at A3" from the first version of this study. It is now
    0.3–0.6 %. Part of the rise is the v0.3 per-sample controls (§4) and part is the slower
    machine state (§2). The ADR's conclusion stands.
- **Capacity in 50 % of one core**, average load, worst knob:

  | Note | JSC | V8 (Chrome) |
  |---|---|---|
  | A3 | 95–177 | 82–170 |
  | A5 | 37–81 | 37–80 |
  | A7 | 9–22 | 10–22 |

  - From the JSC p99, A7 fits 8–17 boxes.
  - The most expensive box is Chua at its worst knob (135 µs at A7). Thomas, the old worst
    case at 4 boxes at A7, is gone.
  - A v1-sized patch of 4–16 boxes at A3 uses 1–10 % of the core at the worst knob. At A5,
    16 boxes use 10–21 % (16 × 16.4–35.7 µs).
  - 16 boxes all at A7 (§5), with LFOs, use 56–58 % of the budget on average and 60 % at the
    JSC peak16. At the worst knob their single-box means add up to 1692–1758 µs, 63–66 % of
    the budget: more than 50 %, but within one core.
  - 40 boxes spread over all systems and A1–A7 use 53–59 % on average. In JSC the peak16 is
    72 % (1925 µs) and the p99 quantum 1913 µs.
- **WebAssembly is not needed for speed (JSC and V8, M1 only).**
  - Specialized JS is within 4 % of LLVM scalar code for four systems. Duffing is 1.25–1.5×
    native.
  - The one structural advantage WebAssembly keeps is f64x2 SIMD: stepping two boxes per
    instruction. SIMD was not measured. Its gain is probably of the same order as two-way
    interleaving (1.2–2.0× per state here, an estimate), and part of it is already available
    to plain JS through interleaving. It only applies to two boxes of the same system with the
    same n.
  - The factor that matters is code structure: B costs 1.5–2.7× of A.
- **v0.3 changes the numbers, not the conclusions.**
  - Removing Thomas raised the worst-case capacity at A7 from 4 to 9 boxes.
  - The worst knob, not the default, must size the budget.
  - The new controls add 0–40 ns per sample, which is visible only below A5.

## Recommendations

1. **Generate one specialized kernel per system, with scalar locals (variant A).**
   - Generate it from the planned symbolic equation source.
   - The current TS engine port uses variant B. At A7 and the worst knob, B would fit about
     4–8 boxes (Lorenz and Rikitake 4–5), against 9–22 with A. This is estimated from
     n_max·t_step(B); the full box was not timed with B.
   - B is fine while the engine is being made correct. Switch to A before relying on
     high-note polyphony.
   - Keep the state in a `Float64Array`, loaded into locals at the start of each quantum.
2. **Keep the hot code monomorphic.**
   - Use one function per system and no allocation in `process()`.
   - For a control input with no cable, pass either `null` or a `Float64Array` filled with the
     knob value, and keep to one convention. The array gives every call site one type, which
     is simpler. Speed does not decide it: in steady state `null` was not slower (Rössler A1,
     µs per quantum: JSC 3.8–4.1 for `null` against 3.7–4.5 for the array; node 4.2–4.5
     against 4.4–5.5).
   - The one effect of `null` seen here is transient and JSC-only. The first time any copy of
     the box code received `null` in a process, it ran at up to 4× its steady cost for
     6000–7500 quanta (16–20 s of audio), in either test order. Any other fresh copy needs
     about 3000 quanta (8 s); see Uncertainties.
   - An earlier version of this rule said that code that had only seen `null` ran 2.3× slower
     (10.3–10.6 against 4.5 µs per quantum in the saved `js_jsc.json`). That was a test
     artifact, not an effect of the input type. Each copy was warmed for only 38 quanta, and
     the `null` copy always ran first. With the order swapped, the other copy was the slow one.
     `rk4_bench.js` now times this from each copy's first call (§5 of the script).
3. **Use the cheap paths for the v0.3 controls.** Both give bit-identical output.
   - Without a pitch cable, compute f and the slew coefficient once per quantum.
   - Compute g = a^1.661 only when the smoothed a changes. With a static amp knob it stops
     changing shortly after the fade-in.
4. **Give the engine a CPU budget model sized on the worst case.**
   - Cost per box per quantum ≈ 128·(c₀ + n_max·t_step), with
     n_max = ⌈N·(P_max/P_min)·f_max/fs⌉.
   - f_max is the note, or `pitch_max` when a pitch cable is connected.
   - On this machine t_step ≈ 25, 23, 45, 27 and 40–46 ns (Lorenz, Rössler, Chua, Rikitake,
     Duffing). c₀ ≈ 10–17 ns (Duffing in V8: 48 ns), plus up to 40 ns with a pitch cable
     (19–40 ns at A1, where it is not hidden behind the RK4 chain; 1–36 ns from A5 up, §4).
   - Keep about 1.4× headroom for per-quantum jitter (p99 of JSC here). A newly added box can
     cost up to 4× the model for 8–20 s while the JIT warms up (Uncertainties). Show the load
     as a CPU meter.
5. **Do not plan WebAssembly for speed in v1.** If the slowest target hardware ever needs more,
   these levers come first:
   1. Variant A, if B is still in use: 1.5–2.7×.
   2. N = 128 for systems where `resolution.md` (being redone for v0.3) supports it: this halves
      high-note cost.
   3. h_max = P(u)/N per sample instead of P_min/N: this makes the cost flat in u, at
      ⌈N·f₀/fs⌉ sub-steps. Against the worst-knob budget it needs up to 1.84× fewer sub-steps
      for Lorenz and Rikitake (19 against 35 at A7, 5 against 9 at A5), 1.21× fewer for Chua
      at A7 and at most 1.05× fewer for Rössler and Duffing. That is an accuracy decision for
      you.
   4. Interleaving two same-system boxes with the same n: 1.2–2.0× measured in JS. SIMD was
      not measured.

   Switching to 44.1 kHz does not help. The RK4 work changes by −8 % to +10 % from A5 up, and
   by up to +84 % at some lower notes (§1). If top-octave oversampling is adopted
   (`aliasing.md`), the RK4 work barely changes, because n ≥ 19 already. The added cost is the
   decimation filter, which this study did not measure.
6. **Cross-engine tests.** V8 and JSC both reproduced numba bit for bit over about 10 periods,
   including Duffing's `cos`. Nothing guarantees that for transcendental functions, so keep
   comparing short horizons and statistics (golden vectors), not long chaotic trajectories.
7. **Run `rk4_bench.html` on the slowest device you care about** before relying on these box
   counts there. It takes about 70 s once `cost.py` has written its config.
8. **Optional: offline Python speed.**
   - Render with large blocks (≥ 512).
   - Compute the slew coefficient once when there is no pitch cable.
   - A scalar numba kernel would be 1.6–2.5× faster at high notes (5× for Duffing), with
     bit-identical output (verified for all five systems).

## Uncertainties

- **Hardware.** Only an M1 Pro, a fast core, was measured. Mid-range laptops or phones may be
  2–4× slower per core (an estimate). Divide the box counts accordingly.
- **Load.**
  - Other jobs ran throughout (load 5–21).
  - Node was disturbed (spread up to 4.6×), so it is used only for minima.
  - V8 means come from one Chrome run with tight repetitions (spread ≤ 6 %).
  - Absolute numbers shifted by 12–18 % against the first version, with the same code.
- **Not a real AudioWorklet.** The browser's per-quantum overhead, the priority of the audio
  thread and GC from other code are not included. The single-quantum outliers (up to 5.5 ms;
  12.5 ms in the multi-box runs) came from a shell process on a loaded machine. A real-time
  audio thread is scheduled differently.
- **JIT warm-up.** A new copy of box code runs slower until the JIT reaches its top tier.
  - Saved runs (`js_jsc.json`): after the ≥ 2000-quantum warm-up, the first timed repetition
    of each new code copy at A1 still ran up to 1.6× slower than the next ones. The medians
    used here are not affected, since only 3 of the 9 repetitions are first ones. In the old
    `deopt` test, the first copy to receive `null` ran
    at 10.3–10.6 µs per quantum in its best 4 s repetition, against 4.5 µs for later copies.
  - Re-check (Rössler A1, timed in blocks of 1500 quanta from each copy's first call; 8 test
    orders × 3 runs in JSC and 3 × 3 in node, plus one full benchmark run each; the outputs
    are not in `lab/outputs/`): in JSC a fresh copy ran 2.4–3.0× slower than its steady cost
    for the first 1500 quanta and 1.4–2.0× for the next 1500, so about 8 s of audio in all.
    The first copy to receive `null` in a process ran up to 4× slower for 16–20 s. In node only
    the first block was clearly slow, by up to 1.9×.
  - The next full run of `cost.py` saves this test (`deopt` in `js_<engine>.json`).
  - So a newly added box may cost up to 4× the model for 8–20 s. For Rössler at A1 that
    peaked at 15 µs per quantum, 0.6 % of a core. Other systems and higher notes were not
    measured.
- **Sample rate.** 44.1 kHz was computed from n, not timed.

## Changes after review

Each review issue, then the change:

1. **The LFO mean hides the worst quantum (medium).**
   - Added the `worst` knob mode (n_max) and peak16.
   - Box counts and Rec. 4 now use the worst knob.
   - "The LFO makes A7 cheaper" was dropped. The LFO peak equals the worst-knob cost (§3).
2. **No per-quantum tail (medium).**
   - Added p50, p99, p99.9, max and peak16 per quantum.
   - Counts are labeled average-load, and p99-based counts are added.
   - The "minima are pessimistic" sentence was removed. The study now reports medians.
3. **Native ceiling for two systems only.** Scalar numba kernels now cover all five systems.
   The JS-to-native claim is qualified per system, including Duffing's gap.
4. **JSC only, SIMD not mentioned.** V8 was measured (node 24, Chrome 155), the headline
   carries "M1 only", and SIMD is named as WebAssembly's remaining advantage.
5. **The multi-box window mismatched the single-box window.** The multi-box test now covers the
   full 4 s LFO cycle, the same window as the single-box runs, and reports peak16 and p99.
6. **Run-to-run spread understated.** Min, median and max over runs are now in `summary.md`,
   and the spread is stated per engine.
7. **Unsaved JIT-hazard evidence.** §6 was replaced by the saved `deopt` test (Rec. 2), and the
   1.4–2.8× figure was dropped.
8. **ceil() left out of the cost scaling.** §1 gives the rounding factors and the 44.1 kHz
   ratios per note, and the budget model has the per-sample term c₀.
9. **Interleaving gain overstated.** It is now quoted as 1.2–2.0×, with the same-system,
   same-n condition.
10. **Reproducibility.** There was one end-to-end run with the final scripts. Afterwards only
    comments changed (spec step numbers, the run time in the docstring). The `--js-only` merge
    path was removed.

Also updated for engine v0.3:

- Rikitake replaces Thomas.
- The new knob ranges and defaults are used.
- The JS box implements the pitch input, the slew, the perceptual amp curve and the
  peak-limited level, with `pitch` and `linear` modes.
- The script uses the v0.3 API (`BlockContext`).

## Changes after the second review (2026-10-26)

No benchmark was re-run for the report; the tables are unchanged. The saved outputs in
`lab/outputs/studies/cost/` come from the scripts before this revision. In `rk4_bench.js` only
the last section (the JIT test) and one comment changed, so its other timings are still those
of the current script. `cost.py` changed in how it merges and prints results.

1. **Rec. 2's "null is 2.3× slower" was a JIT warm-up and test-order artifact (medium).** The
   test was re-run with both orders and longer timing. The claim and "never pass `null`" were
   dropped; Rec. 2, Rec. 4's headroom note and the JIT warm-up uncertainty now give the
   re-check. `rk4_bench.js` times each copy from its first call, and `cost.py` summarizes the
   new test.
2. **Rec. 5 lever 3 understated the gain.** Against the worst-knob budget it is up to 1.84×
   (35 against 19 sub-steps), not 1.45×.
3. **The Conclusion quoted mean loads only.** It now gives peak16, p99 and worst-knob sums,
   and limits "a few percent" to A3.
4. **Pitch-cable cost in Rec. 4.** "15–40 ns" became "up to 40 ns", with the per-note ranges.
5. **The L1 hypothesis for the multi-box excess** did not fit the 5-box patch (about 25 KB of
   tables). The excess is now called unexplained.
6. **Box-count rounding.** The report rounds down and `summary.md` rounded to nearest. The
   script now rounds down, and Method states the difference.
7. **Smaller fixes.** 44.1 kHz ratios at A5 and A7, and their full range over all notes; the
   worst-to-default ratio (up to 1.5×, not 1.45×); the multi-box excess (JSC 2–19 %, V8 at
   most 6 %); SIMD's gain is no longer said to be bounded by the interleaving test; a new
   engine observation on the `MAX_SUBSTEPS` comment.

## Engine observations (not changed)

- **ADR 0006 point 4 overstates how uniform the cost is.** It says the cost is ⌈N·f₀/fs⌉ steps
  "whatever the system". With h_max = P_min/N it is ⌈N·(P(u)/P_min)·f₀/fs⌉. That is up to
  1.84× more for Lorenz and Rikitake (35 against 19 sub-steps at A7).
- **The `MAX_SUBSTEPS` comment in `packages/engine/src/core/dsp/rk4.ts`** says "about 23 are
  needed at C8". That holds for P(u) = P_min. At the worst knob, Lorenz and Rikitake need 42
  at C8 (28 and 33 at the default knob). The cap itself, 4096, is far above both, so this is
  only the same non-uniformity as the ADR 0006 point.
- **ADR 0002's "about 3 sub-steps per sample at 440 Hz"** holds at the default knob for four
  systems; Rikitake needs 4. At the worst knob, Lorenz and Rikitake need 5.
- **`Dynamical.process` computes the slew coefficient with `np.exp` for every sample**, even
  with a fixed pitch. It also runs the DC blocker twice in mono. Both are minor; the result is
  correct.
