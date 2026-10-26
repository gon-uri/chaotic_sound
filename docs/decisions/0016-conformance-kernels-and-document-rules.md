# 0016. Engine conformance: golden contract, per-system kernels, shared document rules

- Status: Proposed (made by Claude while hardening the engines; listed in `docs/REVIEW.md` B7)
- Date: 2026-10-26

## Context

An adversarial review of the TypeScript engine found that the tests could not catch many
plausible bugs. For example, all ten mutations of the live knob path survived. Five parallel
work items closed the gaps, each checked by an independent mutation-testing verifier. This
ADR records the decisions they needed.

## Decision

1. **Golden contract** (`lab/scripts/export_golden.py`, `packages/engine/test/golden.test.ts`):
   - **Fixtures.** Besides the demo patches, eight golden-only fixtures in
     `examples/golden/patches/` exercise what the demos did not: defaults, stereo,
     44.1/96 kHz, an explicit seed, a pitch cable that starts high, a short `once` envelope
     and the soft clip.
   - **Modulators** are compared in windows around every cycle edge and every once end.
   - **Prefix tier.** The first 2048 samples must agree within 1e-9 (the spec bound for any
     engine). For the TypeScript engine the bound is 1e-12. On the platform where it was
     recorded (darwin-arm64), the error may also never exceed the recorded value; 17 of 23
     goldens are bit-exact. `GOLDEN_RECORD=1` re-records after an intended change.
   - **Statistical tier.** Over 8 s, the level, the level per 2 s segment and the
     octave-band spectrum, of the patch and of each voice alone, must lie within 10 standard
     deviations of a 13-seed ensemble of the reference. This replaces fixed tolerances that
     one-ulp differences could break (07_twins failed half the time).
2. **Per-system integration kernels** (`packages/engine/src/core/dsp/kernels.ts`).
   - One hand-written RK4 kernel per system, with scalar locals. Each is bit-identical to
     the generic `renderTuned`, which stays as the reference and the fallback; a bitwise
     differential test guards this.
   - Integrator 1.5–3.4× faster; a whole voice 1.4–2.8× faster.
   - A new system now needs a kernel; the add-system skill says so.
3. **Shared document rules** (`examples/documents.json`). 146 edge-case patch documents,
   each with its expected outcome, read by both test suites. New rules (spec §3, §5):
   - standard JSON only;
   - `version` 0 (`0.0` accepted, since JSON cannot tell them apart);
   - `blocks`/`cables` null or omitted mean `[]`;
   - ids need a UTF-8 encoding;
   - unknown params of any name are errors;
   - writers omit defaults;
   - the top-level `ui` is preserved.
4. **Real-time budget.**
   - `process()` must not allocate per sample. The test measures allocations with V8's
     sampling heap profiler and allows 32 bytes per quantum.
   - What remains, a few bytes per quantum, comes from V8 sometimes boxing a number passed
     to a call it did not inline: about 1.5 KB per second per voice, far below what a
     garbage collector notices.
   - Table lookups are batched per chunk, the modulator picks its shape per chunk, and
     glides keep their state in typed arrays.
5. **Live-edit details** (spec §4.2 step 1, §6):
   - A `setParams` edit whose values depend on each other and fail live (`pitch_min` and
     `pitch_max` moved past each other) rebuilds the block from the final settings.
   - A pitch cable swapped between two chunks glides from the old value (5 ms) instead of
     jumping; the restart from the new cable's first value applies after a chunk without a
     cable.
   - Knob glides on boxes with nothing connected still advance.

## Consequences

- The TypeScript engine has 610 tests (161 before), and the Python suite has 450 (259). The
  verifiers' surviving mutations are now killed.
- A C++ or WebAssembly engine can be held to the same contract, except two checks that still
  read TypeScript internals (initial states, modulator taps). Those need a data-only probe on
  `EnginePort`; this is an open item.
- The exact prefix records are platform-specific. On Linux CI the test falls back to the
  1e-12 bound by design.

## Alternatives considered

- **Generating the kernels from the symbolic RHS** (cost study recommendation 1). Hand-written
  kernels from one template were simpler to review, and the differential test makes them as
  safe as generated ones. Generation is worth it if many systems are added.
- **Exactly zero allocation in tests**: flaky, because V8's inlining decides it. The budget is
  stable and still catches any per-sample allocation (≥ 2 KB per quantum).
- **Restarting the pitch smoother on every cable swap**: the box would jump in pitch with no
  declick. Gliding from the current pitch is consistent with how control signals are smoothed.
