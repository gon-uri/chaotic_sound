# Review: decisions waiting for the owner

While you were away I made the reasonable choices needed to keep going and recorded them all
here. Each item gives my choice, the reason, and what to look at. Strike or edit freely:
nothing below is hard to change yet. Items are ordered by impact.

> How to listen: the demos are already rendered in `lab/outputs/demos/` (WAV + spectrogram
> PNG + `report.md`). To regenerate them: `cd lab && uv run python scripts/render_demos.py`.

## A. Decisions that need your call

1. **Engine language for the browser: TypeScript** (ADR 0002, still *Proposed*). You asked
   for a fuller pros/cons comparison; it is in the ADR. In short:
   - The UI must be TypeScript anyway, so a TypeScript engine adds no second language.
   - Speed is not a constraint: about 3–5 RK4 sub-steps per sample per box.
   - The math stays checkable in the Python reference, through cross-engine tests.
   - Rust/WASM remains possible later, behind the same kernel interface.

   Phase 2 is blocked only on this decision, and on installing Node (which needs your OK).
   `docs/design/engine-typescript.md` shows what the engine would look like, including the
   same RK4 code side by side in Python and TypeScript.
2. **Thomas as the 5th system.** At dysts' parameters it is the weak voice:
   - narrow chaotic band (a ∈ [1.78, 1.95]), only 73% chaotic;
   - no sharp spectral peak, so it is tuned on return times;
   - its pitch depends on the run (−9 … +34 cents) and wanders by up to ±1 semitone across
     its band.

   It still works and passes its (looser) tests. Options:
   - (a) keep it as the "noisy" voice;
   - (b) replace it (see the screening study, `docs/studies/fifth-system-screening.md`, and
     section D);
   - (c) keep it and add the best candidate as a 6th.

   My recommendation: (b) or (c). Evidence: `docs/math/tuning.md` §2, §4, §6 and
   `docs/figures/catalog_thomas.png`.
3. **What "chaos only" means.** Strictly windowless ranges are tiny: Rössler [5.6, 5.8],
   Duffing [0.342, 0.354]. I accepted narrow periodic windows (each ≤ 3% of the candidate
   range) inside the chaotic band. The knob ranges end up 73–99% chaotic (ADR 0010). Inside a
   window the sound simply turns periodic for a moment, and pitch lock still holds. Is this
   acceptable, or do you want stricter (narrower) ranges?
4. **Default knob positions sit near the bottom of the range** for Lorenz (u = 0.07),
   Rössler (0.06) and Duffing (0.035), because the dysts default values lie near the low end
   of their chaotic bands. Duffing's default γ = 0.35 even sits on a small chaotic island
   below the main band (0.375–0.565). Options:
   - keep the dysts defaults (current choice; "around the initial value", as you asked);
   - move the box defaults to mid-range (for example Duffing γ = 0.45). The lab would then
     recompute the initial condition on the new attractor.
5. **Lorenz range ρ ∈ [24.8, 71.3].** The low end is chosen above ρ ≈ 24.74 so a modulated
   box can never fall onto a silent fixed point. The period, and so the uncorrected pitch,
   changes by almost an octave across the range, so pitch lock matters most here.
   `03_lorenz_sweep_locked.wav` and `03_lorenz_sweep_free.wav` show the difference.
6. **One tuning period per system** (ADR 0010). It is measured on the most pitched variable
   (Lorenz z, Rössler x, Chua y, Duffing y; Thomas x by return time). Switching the heard
   variable changes the timbre, not the note. Lorenz x/y are tuned through z's loop, but they
   sound mostly like a rumble (lobe switching). Agree?
7. **Pitch estimator: the peak centroid** (power-weighted mean within ±10% of the highest
   bin). It is 2–4× more stable than the highest bin for chaotic peaks. Accuracy:
   - < 1 cent for Rössler and Duffing;
   - about 3–6 cents for Lorenz and Chua;
   - about ±15 cents for Thomas.

   Whether the measured pitch equals the *perceived* pitch needs your ears (section C).

## B. Choices I made that you may want to revisit (lower stakes)

| # | Choice | Where |
|---|---|---|
| 8 | Loudness: each box normalized to RMS 0.25 (−12 dBFS) at amp = 1; amp is linear; Output soft-clips above 0.9; 5 Hz DC blocker | ADR 0005, spec §3–4 |
| 9 | Modulation: a cable *replaces* its knob; several cables are summed then clipped to [0, 1]; every control is smoothed (5 ms); amp fades in from 0 at start (no click) | ADR 0005, spec §3, §4.2 |
| 10 | Modulator shapes start at 0 (sine = (1 − cos)/2, triangle) except square and ramp-down, which start at 1; `period_s` is both the loop period and the envelope length; `once` holds the final value | spec §4.1 |
| 11 | Box defaults: note A3 (220 Hz), A4 = 440 Hz, 12-TET, cents ±100; pitch lock on; mono (stereo = two variables, optional) | spec §4.2 |
| 12 | Each box's initial condition = the dysts IC plus a 10⁻⁶σ perturbation seeded from the block id, so identical boxes drift apart (`07_twins.wav`) but renders are reproducible | spec §4.2 step 9 |
| 13 | The Output accepts one cable (use a Sum box to mix); no feedback cables in v1 | spec §3 |
| 14 | WAV export: 16-bit PCM by default, 32-bit float optional, 48 kHz | spec §4.4 |
| 15 | Integration: classical RK4, 256 steps per characteristic period (see the resolution study for whether that is overkill) | ADR 0006 |
| 16 | Catalog tables: 129 points + exact default node; ranges chosen by continuation sweeps; criteria in ADR 0010 | ADR 0010 |

## C. What to listen to (`lab/outputs/demos/`)

| File | Listen for |
|---|---|
| `01_voice_<system>.wav` | The five voices at A3. Is each one heard as A3? Which sound musical? |
| `02_owner_example.wav` | Your original example: an LFO on a Rössler parameter, an LFO on the Lorenz amplitude, summed |
| `03_lorenz_sweep_locked.wav` / `_free.wav` | Pitch lock on vs off during a 20 s sweep of ρ (near the end you pass a narrow periodic window) |
| `04_chua_square.wav` | Chua flipping between both ends of its range (single vs double scroll) |
| `05_duffing_drive.wav` | The drive amplitude γ moving slowly; the pitch is exactly the drive |
| `06_chaotic_chord.wav` | A major chord from four different systems |
| `07_twins.wav` | Two identical Rössler boxes: unison at first, then chaos pulls them apart |
| `08_rossler_A2_to_A5.wav` | Same timbre at four octaves (tuning = time rescaling) |

## D. Results of the background studies (partial: the usage limit was reached)

- **Fifth-system screening.** The top candidate to replace Thomas is the **Rikitake dynamo** (1958,
  geophysics: Earth's magnetic-field reversals). It modulates `a`, is chaotic across a wide range
  with no windows, has a smooth P(u), tunes on z (prominence ≈0.5) within a few cents, and had 0
  resets. Its caveat is a high crest factor (peaks up to 1.3 at RMS 0.25). Runners-up: Rucklidge
  (convection, close to Lorenz) and Moore–Spiegel (1966 astrophysics; weakly chaotic). Raw
  results: `lab/outputs/review/studies-result.txt`. The synthesis report may be in `docs/studies/`.
- **Aliasing, resolution, cost and modulation studies**: drafts in `docs/studies/` and
  `lab/scripts/studies/`. Each was reviewed ("minor issues"), but the final revision step did not
  run because of the usage limit. Treat the numbers as unrevised drafts.
- **Code review** of the engine: done, with adversarially verified findings, but **not yet
  fixed**. Raw results: `lab/outputs/review/engine-review-result.txt` (local, not committed).
  Examples: the spec should pin the modulator's floating-point phase formula (low severity), and
  patch JSON writes `null` for defaulted params, which spec §5 does not define (medium).

## E. Setup choices

- **uv** was installed into `~/.local/share/uv-bootstrap` (linked from `~/.local/bin/uv`),
  because Homebrew has no prebuilt packages for macOS 14 and failed to build from source.
  Removable at any time.
- Python 3.14 (uv-managed) with numba 0.68; dysts is pinned to commit `2a03f1ae7b06` as a dev
  dependency.
- Claude Code configuration:
  - `.claude/settings.json`: narrow allow rules for `uv run pytest/ruff/mypy/python scripts/*`,
    plus a hook that runs `ruff format` on edited Python files;
  - a nested `lab/CLAUDE.md`;
  - the project skill `/add-dynamical-system`.
- Generated figures (`docs/figures/`) and demo patches (`examples/patches/`) are committed.
  WAVs are not.
- **License**: none yet (private repo). dysts' GitHub says Apache-2.0 while its package
  metadata says MIT. Settle this before publishing (`NOTICE.md`).

## F. System pages ("Learn more" drafts)

`docs/systems/*.md` were written by agents and then fact-checked by two independent agents
per page (history/citations and math). The remaining doubts are listed at the end of this
file once the pages are final. They need your review before anything is published.
