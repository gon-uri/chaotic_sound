# Roadmap

## Phase 0: project setup ✅ (2026-10-25)

Repo, docs, decision records, Python lab environment, agent configuration, private GitHub repo.

## Phase 1: Python reference engine and analysis ✅ (2026-10-26, engine v0.3)

Goal: prove that "tuned chaos" works and sounds interesting before building any UI.

- [x] Five system definitions, checked against dysts.
- [x] RK4 kernels with per-sample time scale and parameter; tests of accuracy and convergence.
- [x] Frequency estimation per observable (spectral peak, return times), compared with dysts.
- [x] Parameter sweeps: boundedness, Lyapunov exponent, P(u), μ(u), σ(u). Choose chaotic
      ranges and default observables (`docs/math/tuning.md`, ADR 0010).
- [x] `catalog/systems.json` generated.
- [x] Blocks (Modulator, Dynamical, Sum, Output), the patch graph and JSON, offline render, WAV.
- [x] Demo patches rendered to WAV, with spectrograms and a written report of what works.
- [x] Studies: aliasing, steps-per-period convergence, cost, modulation rate, fifth-system
      screening (`docs/studies/`).
- [x] Owner's review, round 1: single-cable inputs + Control Sum, perceptual amp, pitch input,
      playable ranges, Thomas → Rikitake (ADRs 0011–0013).
- [x] Code review: 55 findings fixed, spec v0.3 pins every formula.
- [x] Owner's review, rounds 2–3: tonality knob and input (harmonic resynthesis, default 0.3,
      ADR 0015) and perceptual Output volume (spec v0.5).
- [ ] Listening tests by the owner (does the measured pitch match the perceived one?).

## Phase 2: TypeScript engine ✅ (2026-10-26)

- [x] `packages/engine`: hexagonal core (ADR 0011) implementing spec v0.3, reading the catalog.
- [x] Golden vectors from the Python lab (`examples/golden/`) and cross-engine tests. All
      fixtures match: initial states are bit-identical and the first 2048 samples agree to
      ≤ 3e-13.
- [x] Adapters: Node CLI renderer + WAV, AudioWorklet processor, offline renderer.
- [x] A developer playground (`apps/playground`) to hear the patches live in the browser.
- [x] Independent review of the TS engine; fixes in spec v0.4 (ADR 0014). Follow-up tests,
      golden contract, shared document rules and per-system kernels (ADR 0016).
- [ ] A data-only probe on `EnginePort` for the last two golden checks (before a C++ core).
- [x] Offline rendering in a Web Worker (`adapters/worker/`): WAV export off the UI thread,
      10 s in about 0.3 s in the browser.
- [x] CI workflow (`.github/workflows/ci.yml`): both test suites, on pull requests and on
      demand.

## Phase 3: web app MVP (in progress)

- [x] Patch editor (React Flow): add, move and delete boxes; draw typed cables (checked by
      the engine's rules); edit knobs and settings; undo/redo; automatic layout.
- [x] Play/stop through the AudioWorklet, live knob changes, WAV export in a Web Worker.
- [x] Save/load: JSON files, the examples menu, autosave to the browser's storage.
- [x] Learn-more pages: a 3D attractor computed by the engine core, the knob's parameter,
      and the system pages (Markdown + KaTeX) from `docs/systems/`.
- [ ] Owner's design review: visual style, page structure, default patch (see
      `docs/design/web-app.md` §5).
- [ ] Level meters and live scopes on the boxes; a mobile layout; an end-to-end browser test.
- [x] Static build that runs from any sub-path; a manual GitHub Pages deploy workflow
      (`.github/workflows/pages.yml`).
- [ ] First public deployment (the owner enables Pages and decides on visibility).

## Phase 4: Learn-more pages

- [ ] 3D attractor view (precomputed trajectories from the lab, or live from the engine).
- [ ] Equations (KaTeX), highlighted modulated parameter, properties, history (from
      `docs/systems/`, reviewed by the owner).

## Future ideas (recorded at the owner's request)

- **Brightness knob** for the tonality resynthesis (re-weight the harmonics); see
  `docs/ideas/tonal-knob.md`. The tonality knob itself is done (ADR 0015).
- **Standalone "Harmonizer" box**: the tonality DSP as an effect for any audio, with its own
  note setting.
- **Route to chaos**: let the parameter range include periodic regimes and period-doubling
  cascades. Open question: how to tune there. A likely answer is to lock to the mean loop time
  (return time to a Poincaré section). That stays continuous through period doubling, so the
  note holds and sub-octaves appear as extra lower partials.
- **Chaotic modulators**: slow chaotic systems used as LFOs.
- **Relative pitch input mode** (± N semitones around the note, for vibrato), with the
  modulator min/max properties.
- **Quiet-trap guard**: detect a voice stuck near a weakly unstable equilibrium and nudge it
  back onto the attractor.
- **Oversampling** for notes above about F#6 (`docs/studies/aliasing.md`).
- **Per-system resolution** (128 steps per period for most systems saves 33–50% CPU;
  `docs/studies/resolution.md`).
- **Moore–Spiegel** (1966, astrophysics) as a sixth system, after fixing the f_min issue in
  the analysis (screening study).
- **Modulator properties**: duty cycle, min/max, phase, retrigger, tempo sync.
- **More boxes**: noise generators (white, pink, brown, …), filters, classic effects (delay,
  reverb, distortion), multiply / ring modulation.
- **More systems** from dysts, eventually generated from one symbolic source (sympy →
  TS + Python + LaTeX).
- **Unstable-periodic-orbit-based tuning**: tune to the most visited UPO.
- **Feedback cables** (cycles with an explicit delay).
- **Languages**: Spanish and others (i18n).
- **MIDI / keyboard** input for playing notes.
- **Open-sourcing**: pick a license, and settle the dysts license note (`NOTICE.md`).
