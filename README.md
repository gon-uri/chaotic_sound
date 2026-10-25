# chaotic_sound

**Make music with strange attractors.** A modular synthesizer in the browser. Each box solves a
chaotic differential equation (Lorenz, Rössler, Chua, …) and is tuned to a musical note.
Patching boxes together lets you hear chaos, and each box opens a page on the math and the
history behind its system.

> Status: Phase 1 (Python reference engine and analysis) is implemented: 5 tuned systems, modulators,
> mixing, offline WAV rendering, catalog of chaotic ranges and tuning tables, 132 tests. The browser
> engine and UI (Phases 2–3) have not started. Private repository. Open decisions: [`docs/REVIEW.md`](docs/REVIEW.md).

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
| [`docs/`](docs/) | Vision, v1 spec, architecture, decision records, math notes, studies, system pages |
| [`examples/patches/`](examples/patches/) | Demo patches in the patch JSON format (also cross-engine test fixtures) |

## Quick start (Python lab)

You need [uv](https://docs.astral.sh/uv/). It installs the right Python version for you.

```bash
cd lab
uv sync                                   # create the environment
uv run pytest -q                          # run the tests
uv run python scripts/render_demos.py     # render demo WAVs into lab/outputs/demos/
```

## Credits

The systems, parameter values and initial conditions come from **dysts** by William Gilpin and
the GilpinLab ([github.com/GilpinLab/dysts](https://github.com/GilpinLab/dysts)). See
[`NOTICE.md`](NOTICE.md).

## License

Not decided yet. The repository is private for now.
