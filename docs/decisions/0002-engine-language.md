# 0002. Real-time engine in TypeScript; the Python lab is the reference implementation

- Status: **Proposed**. The owner asked for a fuller explanation of the trade-offs before
  deciding. Nothing built so far depends on this choice.
- Date: 2026-10-25

## Context

ADR 0001 puts synthesis in the browser. Browsers run two kinds of code: **JavaScript** (and
TypeScript, which is JavaScript with type annotations and compiles to it) and **WebAssembly**
(WASM, a compact binary format that languages such as Rust and C++ compile to). The UI (the
patch editor, 3D views, pages) will be TypeScript whatever we choose here, because that is how
web UIs are built. So the question is only which language the audio engine (the code inside
the AudioWorklet) is written in.

Requirements: real-time safety (no glitches), modularity, reuse in other programs, code the
owner can read and review (fluent in Python, new to TypeScript), and a toolchain that is "good,
state of the art, but not overly complicated".

## Options

| | **A. TypeScript** | **B. Rust → WASM** | **C. C++ → WASM** |
|---|---|---|---|
| Runs in the audio thread | Natively | Yes, via a WASM module | Yes, via a WASM module |
| Speed for our loops | JIT-compiled; roughly 1.5–3× slower than native, still far more than we need (dozens of boxes) | Near native | Near native |
| Glitch risk | Garbage-collector pauses if the hot loop allocates memory. Avoided by preallocating typed arrays (standard practice). | None (no GC) | None (no GC) |
| Languages in the web project | 1 (TS everywhere) | 2 (Rust + TS) | 2 (C++ + TS) |
| Toolchain | Node + pnpm + Vite + Vitest, one ecosystem | Adds cargo, wasm-bindgen / wasm-pack, plus glue to load WASM in the worklet and share buffers (fiddly) | Adds Emscripten (heavier, older ergonomics) |
| Debugging | Browser devtools, breakpoints inside the worklet | Harder (WASM debugging is improving but limited) | Harder |
| Learning curve for the owner | Gentle: reads much like Python with type hints | Steep (ownership, lifetimes, borrow checker) | Moderate to steep, and memory-unsafe |
| Reuse outside the web | Node and any JS/TS app; not from Python or in audio plugins | Same core could become a Python package (PyO3) and native audio plugins (VST3/CLAP via nih-plug) | Same, plus JUCE for plugins |

## Decision (proposed)

**Option A: TypeScript**, with a deliberately narrow, numeric "kernel" interface. Each block
processes a buffer of samples using preallocated `Float64Array`s, with no allocation in the
audio thread. The **Python lab is the reference implementation** of the same spec
(`docs/spec-v1.md`). Cross-engine tests run the same patch JSON through both engines and
compare.

Why:
1. The UI must be TypeScript anyway, so A adds no language, while B or C add a second one.
2. Performance is not the bottleneck: at 440 Hz a box needs about 3 RK4 sub-steps per sample,
   which is a few hundred floating-point operations.
3. The owner can learn to read TypeScript quickly. The math can always be checked in the
   Python reference, in a language the owner knows well.
4. It is the simplest toolchain that is fully state of the art for web audio.

## Consequences

- Python users get the offline engine (`chaotic_sound` package) for scripts, notebooks and WAV
  rendering. The browser gets the TS engine. Each new block is written twice. Mitigations:
  - The spec is precise.
  - The system equations should eventually be generated from one symbolic source
    (equation → TS + Python + LaTeX; see the roadmap).
  - Cross-engine tests catch drift.
- If profiling ever shows a bottleneck, or the owner wants native plugins or Python bindings
  for the real-time engine, the kernel can be ported to Rust/WASM later without touching the
  graph code or the UI.

## Alternatives considered

B and C are in the table above. "Python everywhere" is ruled out by ADR 0001.
