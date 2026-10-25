# Review: decisions waiting for the owner

- Last updated: 2026-10-26, after the owner's answers to the first round.
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

## B. New choices for you to check

1. **The parameter slew** in system time: the parameter smoother is at least
   max(5 ms, 2 oscillation periods). It came from the modulation study and fixed Chua's
   safety resets under square modulators. The side effect: at low notes, a square LFO's jump
   takes longer (about 36 ms at A1). *Recommendation: keep.*
2. **Peak-limited level**: min(RMS 0.25, robust peak 0.8). Spiky voices are slightly quieter
   rather than clipped. *Recommendation: keep.*
3. **Classic values are no longer the defaults.** With the default at mid-range, Lorenz starts
   at ρ = 48 (not 28) and Rössler at c = 6.56 (not 5.7). The classic values are still inside
   the ranges and stored as `p_reference`. Do you want the Learn-more pages to offer a
   "classic value" button?
4. **Pitch input mapping**: absolute and linear in semitones between two note settings.
   Alternative: relative to the note (± N semitones, for vibrato). *Recommendation: keep
   absolute for v1; add a relative mode with the future modulator min/max properties.*
5. **The Sum gain and the Output volume are still linear.** Should they use the perceptual
   curve too, for consistency? *Recommendation: yes for Output volume, no for Sum gain (a
   mixing coefficient).*
6. **Rikitake's range top is set by hand at μ = 1.8**, because of quiet spells on the
   attractor above about 2.1 (screening study).
7. **Notes are limited to C0 … C8.** Aliasing becomes measurable above about F#6
   (`docs/studies/aliasing.md`). Oversampling is on the roadmap.
8. **TypeScript tooling**:
   - Node 24 LTS, installed from the official nodejs.org tarball into `~/.local/node`
     (Homebrew can't build on macOS 14);
   - npm workspaces (no extra package manager);
   - TypeScript in strict mode, run directly by Node (no build step for the engine);
   - Vitest;
   - Biome (one tool for lint and format, like ruff).

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
- **License**: none yet (private repo). dysts' GitHub says Apache-2.0 while its package
  metadata says MIT. Settle this before publishing.

## F. System pages (`docs/systems/`)

- The Lorenz, Rössler, Chua and Duffing pages were written, fact-checked by two independent
  agents (history and citations, and math), and revised.
- They are now being refreshed for catalog v2, and a new Rikitake page is being written and
  checked the same way.
- Thomas's page is archived in `docs/systems/archive/`.
- Each page's remaining doubts are in the agents' reports, summarized here when final.
  Everything needs your review before publishing.
