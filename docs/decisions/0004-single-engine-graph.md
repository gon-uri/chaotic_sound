# 0004. One engine runs the whole patch

- Status: Accepted (provisional, pending owner review)
- Date: 2026-10-25

## Context

There are two common ways to build a modular synth in the browser:

1. **One Web Audio node per box.** Each box is its own `AudioWorkletNode`, and cables are Web
   Audio `connect()` calls. The browser mixes the signals and routes modulation through
   `AudioParam`s.
2. **One engine for the whole patch.** A single `AudioWorkletNode` hosts our own engine. The
   engine holds the graph, orders the blocks topologically and processes them buffer by buffer.
   The UI sends patch edits to it as messages.

## Decision

Option 2. The engine is a plain library with no browser dependencies. The same code runs:
- inside the AudioWorklet (live sound);
- in a Web Worker or Node (offline WAV export, tests);
- under the Python reference implementation's tests (same patch JSON in, compare out).

## Consequences

- WAV export is exactly what you hear (same code), and renders are deterministic.
- The engine is reusable in other programs: it is just a library.
- We implement mixing, fan-in and parameter smoothing ourselves (simple).
- Block-size independence becomes our responsibility; it is a required test (spec §6).
- A future feedback cable (cycles) can be done with an explicit one-block or one-sample delay
  that we control, rather than Web Audio's fixed 128-sample delay.

## Alternatives considered

Option 1 uses more of the browser, but it ties the engine to Web Audio. It cannot run in Node
or tests unchanged, its cross-node modulation is harder to make sample-accurate, and every node
adds overhead.
