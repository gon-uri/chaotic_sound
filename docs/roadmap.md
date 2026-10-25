# Roadmap

## Phase 0: project setup ✅ (2026-10-25)

Repo, docs, decision records, Python lab environment, agent configuration, private GitHub repo.

## Phase 1: Python reference engine and analysis (implemented 2026-10-25; studies and review in progress)

Goal: prove that "tuned chaos" works and sounds interesting before building any UI.

- [x] Five system definitions, checked against dysts.
- [x] RK4 kernels with per-sample time scale and parameter; tests of accuracy and convergence.
- [x] Frequency estimation per observable (spectral peak, return times), compared with dysts.
- [x] Parameter sweeps: boundedness, Lyapunov exponent, P(u), μ(u), σ(u). Choose chaotic
      ranges and default observables (`docs/math/tuning.md`, ADR 0010).
- [x] `catalog/systems.json` generated.
- [x] Blocks (Modulator, Dynamical, Sum, Output), the patch graph and JSON, offline render, WAV.
- [x] Demo patches rendered to WAV, with spectrograms and a written report of what works.
- [ ] Studies: pitch-lock accuracy under modulation, aliasing vs. note (is oversampling
      needed?), steps-per-period convergence, cost per sample (`docs/studies/`).
- [ ] Decide on Thomas (replace or keep): see `docs/studies/fifth-system-screening.md`.
- [ ] Listening tests by the owner (does the measured pitch match the perceived one?).

## Phase 2: real-time engine (after ADR 0002 is accepted)

- [ ] `packages/engine` (TypeScript) implementing spec v1 and reading the catalog.
- [ ] Cross-engine tests: the same patch JSON through Python and TS, with matching statistics.
- [ ] AudioWorklet wrapper; Web Worker offline render plus WAV encoder.

## Phase 3: web app MVP

- [ ] Patch editor (React Flow): add, move and delete boxes; draw cables; edit knobs.
- [ ] Play/stop, master volume, WAV export.
- [ ] Save/load patches (JSON file, and local storage).

## Phase 4: Learn-more pages

- [ ] 3D attractor view (precomputed trajectories from the lab, or live from the engine).
- [ ] Equations (KaTeX), highlighted modulated parameter, properties, history (from
      `docs/systems/`, reviewed by the owner).

## Future ideas (recorded at the owner's request)

- **Route to chaos**: let the parameter range include periodic regimes and period-doubling
  cascades. Open question: how to tune there. A likely answer is to lock to the mean loop time
  (return time to a Poincaré section). That stays continuous through period doubling, so the
  note holds and sub-octaves appear as extra lower partials.
- **Chaotic modulators**: slow chaotic systems used as LFOs.
- **Pitch input** on dynamical boxes (glides, vibrato, sequencing).
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
