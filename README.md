# chaotic_sound

<p align="center">
  <a href="https://gon-uri.github.io/chaotic_sound/">
    <img src="docs/figures/open-app-button.svg" alt="Open the chaotic_sound app in your browser" width="440">
  </a>
</p>

**Make music with strange attractors.** A modular synthesizer in the browser. Each box solves a
chaotic differential equation (Lorenz, Rössler, Chua, …) and is tuned to a musical note.
Patching boxes together lets you hear chaos, and each box opens a page on the math and the
history behind its system.

> Status (2026-10-26):
> - **Phase 1**, the Python reference engine and analysis, is done: five tuned systems,
>   modulators, mixing, WAV export, and a catalog of playable ranges.
> - **Phase 2**, the TypeScript engine, runs live in the browser through an AudioWorklet and
>   matches the Python reference (golden tests). There is a developer playground to hear it.
> - **Phase 3** has started: a first patch editor (`apps/web`) lets you add boxes, draw cables,
>   turn knobs, play live, export WAV and open the Learn-more pages (3D attractor, equations,
>   history).
>
> Open decisions: [`docs/REVIEW.md`](docs/REVIEW.md).

## Why

- For people coming from **math, physics or engineering**: a playful way into sound and music.
- For people coming from **music**: a hands-on way into dynamical systems, chaos theory and its
  history.

## How it works (in one paragraph)

A chaotic system like Lorenz's oscillates irregularly but has a characteristic period *P* in its
own time units. If we run the system's clock *P·f₀* times faster than real time, that period
becomes 1/*f₀* seconds, and the system "sings" at the note *f₀* (for example A4 = 440 Hz). The
shape of the waveform, and so the timbre, does not change with pitch. Slow **modulator** boxes
can then move a parameter of the system (which turns it into a forced, non-autonomous system)
or its loudness. Sum boxes mix the signals, and an output box plays the result or exports it as
WAV. See [`docs/math/tuning.md`](docs/math/tuning.md).

## Repository layout

| Path | What it is |
|---|---|
| [`lab/`](lab/) | Python package `chaotic_sound`: reference engine, analysis tools, catalog generator |
| [`catalog/`](catalog/) | Generated data: systems, parameter ranges, tuning tables (the lab → engine contract) |
| [`packages/engine/`](packages/engine/) | TypeScript engine: pure core + ports + adapters (AudioWorklet, offline, CLI) |
| [`apps/web/`](apps/web/) | The app: patch editor (React + React Flow) and Learn-more pages |
| [`apps/playground/`](apps/playground/) | Developer page that plays the example patches live in the browser |
| [`docs/`](docs/) | Vision, v1 spec, architecture, decision records, math notes, studies, system pages |
| [`examples/patches/`](examples/patches/) | Demo patches in the patch JSON format (also cross-engine test fixtures) |
| [`examples/golden/`](examples/golden/) | Reference vectors from the Python engine for cross-engine tests |

## Quick start (Python lab)

You need [uv](https://docs.astral.sh/uv/). It installs the right Python version for you.

```bash
cd lab
uv sync                                   # create the environment
uv run pytest -q                          # run the tests
uv run python scripts/render_demos.py     # render demo WAVs into lab/outputs/demos/
```

## Quick start (TypeScript engine)

You need Node 24 or later. Install the dependencies once with `npm install`, then:

```bash
npm test                                  # all TypeScript tests, incl. cross-engine golden tests
npm run web                               # the editor: open http://localhost:5174
npm run playground                        # developer page: http://localhost:5173
npm run render -- examples/patches/06_chaotic_chord.json chord.wav --seconds 20
```

## Hosting the editor

`npm run build:web` writes a static site to `apps/web/dist/` (about 3.3 MB). All synthesis runs
in the visitor's browser, so any static host works. Asset paths are relative, so it also
works under a sub-path.

GitHub Pages: set the repository's Settings → Pages → Source to "GitHub Actions". Then run
the **Deploy to GitHub Pages** workflow from the Actions tab (`.github/workflows/pages.yml`,
manual only). It runs the checks and tests, builds the editor and publishes it at
`https://<owner>.github.io/<repository>/`. The site is public to anyone with the link, and on a
private repository Pages needs a paid GitHub plan. To try the built site locally, use the
`web-dist` launch configuration (`vite preview` under `/chaotic_sound/`).

## Credits

The systems, parameter values and initial conditions come from **dysts** by William Gilpin and
the GilpinLab ([github.com/GilpinLab/dysts](https://github.com/GilpinLab/dysts)). See
[`NOTICE.md`](NOTICE.md).

## License

Copyright (C) 2026 Gonzalo Uribarri.

- **Code:** [GNU AGPL v3 or later](LICENSE), with one additional term (section 7(b)). Copies
  and modified versions must keep the attribution *"Based on chaotic_sound by Gonzalo Uribarri
  (https://github.com/gon-uri/chaotic_sound)"*, in the source and in the app's legal notices.
  See [`NOTICE.md`](NOTICE.md).
- **Documentation and system pages** (`docs/`): [CC BY-SA 4.0](docs/LICENSE.md).
- **What you make with it is yours:** sounds, music and patches you create may be used and
  sold for any purpose. Credit is appreciated but not required.
- **Commercial licenses** for closed-source use are available from the author.
- **Citing:** see [`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository").
