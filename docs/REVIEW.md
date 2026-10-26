# Review: decisions waiting for the owner

- Last updated: 2026-10-26, after the owner's third round of answers (section A3).
- Section A records how those answers were applied.
- Section B lists the new choices I made that need a look. Each has a recommendation; edit or
  strike freely.

> **How to listen:** `cd lab && uv run python scripts/render_demos.py`, then open
> `lab/outputs/demos/` (WAVs, spectrograms and `report.md`). There is also an interactive
> tour in `lab/notebooks/01_tour.ipynb`.

## A. Your answers, applied (engine v0.3, catalog v2)

| # | Your answer | What I did |
|---|---|---|
| 1 | Synthesis in the browser: OK | ADR 0001 accepted |
| 2 | TypeScript first, modular and hexagonal so that C++ later is easy | ADR 0002 accepted; **ADR 0011**: core, ports and adapters, a narrow data-only `EnginePort`, a C-style DSP kernel, and golden tests as the language-neutral contract |
| 3 | Lab → JSON catalog: OK | ADR 0003 accepted; catalog format v2 |
| 4 | One engine runs the patch: OK | ADR 0004 accepted |
| 5a | One cable per control input; use an "additive" block to combine | New **Control Sum** box: clip(gain · Σ in, 0, 1). A second cable is rejected with a hint (ADR 0013) |
| 5b | dB amp curve toggle, on by default, 0.5 = half the volume | `amp_curve = "perceptual"` (default): g = a^1.661, −10 dB per halving, i.e. half as loud. `"linear"` is available |
| 6–7 | OK | ADR 0006, 0007 accepted |
| 8 | Pitch input on dynamical boxes, overriding the note | `pitch` input: q ∈ [0, 1] maps linearly in semitones from `pitch_min` to `pitch_max` (default A1 … A5, so 0.5 = A3) |
| 9 | OK | |
| 10 | No need for chaos-only ranges; stability and musicality first; the default may move to mid-band; replace Thomas if needed | New range rules (**ADR 0012**): hysteresis test, a musicality criterion, chaos ≥ 60%, windows allowed, default at mid-range. **Thomas replaced by the Rikitake dynamo**, the screening's top pick |

The code review (55 confirmed findings, none high severity) is fixed. The spec now pins every
formula exactly (spec v0.3): the smoothers, the DC blocker, the modulator phase, portable
seeding, null and unknown-key handling, and the note grammar. The test suite went from 132
to 215 tests.

## A3. Your third round of answers, applied (spec v0.5)

| # | Your answer | What I did |
|---|---|---|
| B1–B8 | "I agree with all the recommendations" | Kept: the parameter slew, the peak-limited level, mid-range defaults (classic values kept as `p_reference`), absolute pitch mapping, Rikitake's top set by hand, notes C0–C8, the TypeScript tooling |
| B5 | Output volume perceptual, Sum gain linear | **Output volume now uses the amp curve**: v^1.661, so halving the knob is −10 dB. The default 0.8 is a gain of 0.69, so patches are about 1.3 dB quieter than before. Sum gain stays a linear mixing coefficient (spec §4.4) |
| Tonality | Design D, also as an input, default 0.3 | **Implemented** as the `tonality` knob and input of every dynamical box (spec §4.2 step 7, ADR 0015). Choices to check by ear: **B6** |

Still open from that list: **B3**, whether the Learn-more pages should offer a "classic
value" button that sets the knob to the dysts value (ρ = 28, c = 5.7, …). *My
recommendation: yes; it is one button and a nice bridge to the literature.*

## B2. Phase 2 (TypeScript engine), new and ready to try

```bash
npm install          # once
npm run playground   # then open http://localhost:5173, pick a patch, press Play
```

- **What exists:**
  - `packages/engine`: a hexagonal core, ports and adapters (ADR 0011);
  - `apps/playground`: a developer page that plays every example patch live in the browser,
    with live knobs and WAV export.
- **Parity with Python:** on all 15 fixtures, the initial states are bit-identical and the
  first 2048 samples agree to ≤ 3e-13 (usually exactly). The long-run statistics match.
- **Speed:** in Node, 20 s of your two-voice example renders in 0.7 s. In the browser, the
  worklet renders in real time with no errors.
- **Choices to check:**
  - (a) No build step: Node runs the TypeScript directly; Vite bundles it for the browser.
  - (b) The playground is a developer tool, not the Phase 3 editor.
  - (c) Live edits:
    - Knobs and the pitch settings change inside the running box, which keeps playing
      without a restart.
    - Structural settings (system, observable, seed, modulator settings) recreate that box.
    - Boxes that are not edited are never reset.

    See spec §6.
  - (d) An independent multi-lens review of the TS engine found 55 issues (one high: a test
    that could not detect a broken live knob); 36 were confirmed by skeptics, none refuted
    as harmful. The fixes and the decisions they needed are in **B5**.
  - (e) **CI** (`.github/workflows/ci.yml`) runs both test suites, but only on pull requests
    and on demand, to save Actions minutes on the private repo. Running it on every push is a
    one-line change. Do you want that?

## B3. Phase 3 (editor MVP), new and ready to try

```bash
npm run web   # then open http://localhost:5174
```

- **What it does:** add boxes from the toolbar, drag cables from an output (right) to an
  input (left), turn knobs, press Play, open "Learn more" on any dynamical box, load an
  example, save or open a JSON patch, undo with Cmd+Z.
- **Choices I made for you to judge:**
  - (a) A clean diagram look in dark and light themes: orange for audio, blue (dashed) for
    control.
  - (b) Patches without saved positions are laid out left to right by signal flow.
  - (c) Learn more = the 3D attractor at the box's current parameter + the knob's range +
    the system page. The pages are drafts and say so.
  - (d) Every edit is validated by the engine itself, so the editor cannot build a patch the
    engine would reject.
  - (e) All UI strings are in `apps/web/src/strings.ts`, ready for translation.
- Open questions are in `docs/design/web-app.md` §5: visual style, page order, default
  patch, mobile.

## B5. Engine review fixes (spec v0.4, ADR 0014: Proposed)

Decisions I made while fixing the review's findings. Each has a recommendation; nothing
changes the sound of a patch played without live changes (the golden vectors are unchanged).

1. **Every knob move is the same kind of edit.** `setParam` and an `edit` of `setParams`
   behave identically. Knobs and pitch settings change inside the running box, other
   settings recreate it, and invalid values roll back. *Recommendation: keep.*
2. **Loads and edits are atomic.** A bad patch (from a file or the editor) raises an error
   and the old patch keeps playing untouched. *Keep.*
3. **Sum/Control Sum gain, Output volume and the amp-curve toggle now glide over 5 ms** after
   a live change, instead of clicking. A steady value is applied exactly. *Keep.*
4. **Guards in both engines.** The pitch smoother restarts from a new cable's first value. A
   non-finite DC-blocker state is cleared and counted as a safety reset. The Output turns NaN
   into silence. The catalog check now requires finite tables with σ, π, P > 0. *Keep.*
5. **Patch files.** `{"foo": null}` is now an error in Python too (a typo stays a typo).
   `"seed": 7.0` is accepted as 7 in Python too: JavaScript cannot tell them apart. *Keep.*
6. **No allocation on the audio thread**, and a much stricter purity test for the core.
7. **The unused `DiagnosticsSink` port was removed.** The adapters poll diagnostics instead
   (ADR 0011 implementation notes).
8. **Still open:** two golden checks (initial states, modulator outputs) read TypeScript
   internals. A C++ core would need a small data-only probe on `EnginePort` for them. I would
   add it when the C++ work starts.
9. **Done**, see **B7**: tests that catch the review's surviving mutations, more golden
   fixtures, the Python edge cases of the patch format, and per-system integration kernels.

New for you: `docs/dev/typescript-for-python.md`, a short guide to the TypeScript idioms used
in the code, written for a Python programmer.

## B6. Tonality: choices to check by ear (ADR 0015)

Try it in the editor (`npm run web`, the **Tonality** knob on each dynamical box) or in the
demos. All demos now play at the default 0.3.

1. **Phase tracking instead of fixed-phase partials.** The prototype's partials beat against
   the raw sound at intermediate settings (a 2–4 dB tremolo at 0.3). Each partial now follows
   its band's slowly smoothed phase. *Recommendation: keep.*
2. **At 1 the tone is steady but alive**, not a static stack of sines: the partials keep the
   attractor's slow phase wander (90–100% harmonic).
3. **Mix law** (1 − τ)^0.75 / τ^0.75: level within about ±1.2 dB across systems and settings.
4. **Lorenz at intermediate settings reads about 8–10 cents sharp**, because of its broad
   spectrum. The other systems stay within about 6 cents (10 seeds). I found no variant that fixes this without
   bringing the beating back.
5. **8 harmonics** (over 99.9% of the power for all five systems over the whole knob
   range). Cost: about 0.9% of a core per voice.
6. **An independent verification found and I fixed** an overshoot after fast pitch drops
   (the band filter is now modulation-safe), a click when turning tonality to 0, sporadic
   ticks at the default setting (a coherence floor), and stale state when switching it on
   again. Details: ADR 0015, "Fixes after the independent verification".
7. **Open:** a second "brightness" knob (idea note, question 2).

## B7. Engine hardening (ADR 0016: Proposed)

Five pieces of work, each checked by an independent mutation-testing agent, then merged on
top of the tonality work.

1. **Tests.** The TypeScript engine has 610 tests (161 before) and the Python lab 450 (259).
   Almost all the plausible bugs the verifiers injected are now caught.
2. **Golden contract** (how the two engines must agree; spec §6). Choices to check:
   - The first 2048 samples within 1e-12 for TypeScript (17 of 23 goldens are bit-exact).
   - Long-run statistics within 10 standard deviations of a 13-seed ensemble.
   - Eight new golden-only fixtures.
   *Recommendation: keep.*
3. **Per-system kernels.** One hand-written integration kernel per system, bit-identical to
   the generic one. A voice is 1.4–2.8× faster, so at A7 one core runs 22–46 voices (about 10
   before). Adding a system now also needs a kernel; the add-system skill says so.
4. **Patch-file rules shared by both engines** (`examples/documents.json`, 146 cases):
   - standard JSON;
   - `version` 0 (`0.0` accepted);
   - `blocks`/`cables` may be null;
   - ids need a UTF-8 encoding;
   - names such as `toString` are unknown params;
   - writers (the editor's Save too) leave out default values;
   - the patch's own `ui` object is kept.
   *Recommendation: keep.*
5. **Real-time budget.** The audio loop now allocates almost nothing. The test allows 32 bytes
   per audio block, because exactly zero depends on V8's JIT and would make the test flaky.
6. **Two live-edit details:**
   - A pitch cable swapped for another between two audio blocks glides from the old pitch
     (5 ms) instead of jumping.
   - An edit whose values depend on each other (`pitch_min` and `pitch_max` moved past each
     other) rebuilds the box.
   *Recommendation: keep both.*
7. **Other fixes found by the review:**
   - rollback order;
   - glides on boxes with nothing connected;
   - Play after the audio engine crashed now restarts it;
   - an added box with a NaN param is rejected;
   - the purity test's tokenizer handles a regex after `=>` and `return`;
   - phase wrapping gives +0 like Python.
8. **Still open:**
   - a data-only probe on `EnginePort` for the two golden checks that read TypeScript
     internals (needed for a C++ core);
   - `test_golden.py` does not yet detect stale golden metadata or re-check the statistics on
     the Python side;
   - on Linux CI the TypeScript prefix check uses the 1e-12 bound instead of the exact records.

## B8. Hosting

- **Deploy workflow added**, manual only (`.github/workflows/pages.yml`). Steps: checkout, Node
  24, `npm ci`, checks and tests, build, deploy to GitHub Pages.
- **Your steps:**
  1. Settings → Pages → Source: "GitHub Actions";
  2. decide on visibility (on a private repository Pages needs a paid plan, and the site is
     public to anyone with the link);
  3. Actions → "Deploy to GitHub Pages" → Run workflow.
- **Tested locally under `/chaotic_sound/`** (the Pages sub-path): the editor loads, plays and
  opens Learn-more pages. Before sharing widely: the system pages are marked as unreviewed
  drafts, and the project has no license yet (section E).

## C. What to listen to (`lab/outputs/demos/`)

| File | Listen for |
|---|---|
| `01_voice_<system>.wav` | The five voices at A3. Is each one heard as A3? |
| `02_owner_example.wav` | Your example: an LFO on a Rössler parameter, an LFO on the Lorenz amplitude, summed |
| `03_lorenz_sweep_locked.wav` / `_free.wav` | Pitch lock on vs off while ρ sweeps the whole range |
| `04_chua_square.wav` | Chua flipping between both ends of its range (now with no resets) |
| `05_duffing_drive.wav` | The drive amplitude moving slowly; the pitch is exactly the drive |
| `06_chaotic_chord.wav` | All five systems in an A-major chord |
| `07_twins.wav` | Two identical Rössler boxes drifting apart |
| `08_rossler_A2_to_A5.wav` | Same timbre at four octaves |
| `09_pitch_glide.wav` | **New:** the pitch input gliding Rikitake A1 → A5 → A1 |
| `10_control_sum.wav` | **New:** a slow plus a fast modulator combined in a Control Sum box |
| `11_amp_envelope.wav` | **New:** the perceptual amp curve fading Lorenz out evenly |

## D. Studies (`docs/studies/`)

| Study | Main result |
|---|---|
| Fifth-system screening | 24 dysts flows evaluated; the Rikitake dynamo (μ) is recommended, then Rucklidge and Halvorsen |
| Aliasing | Below −110 dB up to A5; −80 dB is crossed above about F#6–E7 depending on the system. Oversampling only matters in the top octave |
| Resolution | 256 RK4 steps per period is sufficient and about 2× more than needed; 128 would do for most systems |
| Cost | One box costs 0.2–0.4% of a core at A3 in JavaScript, so more than 100 boxes run in real time. WebAssembly is not needed for speed |
| Modulation | Adiabatic for sweeps slower than about 100 oscillation periods; faster is real forcing (FM-like). Recommended the system-time slew, now implemented |

The four Phase-1 studies are being revised for engine v0.3 (Rikitake instead of Thomas, and
the reviewers' points addressed). Each report says which engine version its numbers come
from.

## E. Setup

- **uv** is in `~/.local/share/uv-bootstrap` (linked from `~/.local/bin/uv`); delete that
  folder to remove it. **Node** goes in `~/.local/node` (same idea).
- Python 3.14 with numba 0.68; dysts pinned at commit `2a03f1ae7b06` (a dev dependency).
- **License** (decided, round 4): code under AGPL-3.0-or-later, plus a section 7(b) term that
  keeps the attribution "Based on chaotic_sound by Gonzalo Uribarri" in copies, modified
  versions and the app's About dialog. Docs under CC BY-SA 4.0. Users' sounds and music are
  theirs. `CITATION.cff` added. dysts is Apache-2.0 or MIT; both are compatible, and
  `NOTICE.md` follows the stricter one. The repository is public.

## F. System pages (`docs/systems/`)

- The Lorenz, Rössler, Chua and Duffing pages were written, fact-checked by two independent
  agents (history and citations, and math), and revised.
- They are now being refreshed for catalog v2, and a new Rikitake page is being written and
  checked the same way.
- Thomas's page is archived in `docs/systems/archive/`.
- Each page's remaining doubts are in the agents' reports, summarized here when final.
  Everything needs your review before publishing.
