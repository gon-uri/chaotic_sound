# Design sketch: the TypeScript real-time engine (Phase 2)

- Status: **design sketch**, waiting on ADR 0002 (engine language). Nothing is implemented.
- Purpose:
  1. Show concretely what the proposed TypeScript engine would look like, to help decide ADR
     0002.
  2. Let Phase 2 start quickly once the decision is made.

## 1. Goals and constraints

- Implement `docs/spec-v1.md` exactly, reading `catalog/systems.json`; never hard-code system
  numbers.
- Run in an **AudioWorklet**, the browser's audio thread:
  - the browser asks for 128 samples ("a render quantum") about 375 times per second at
    48 kHz;
  - missing a deadline means an audible glitch;
  - so the hot path must never allocate memory or block.
- The same code renders offline in a **Web Worker** (WAV export) and in **Node** (tests).
- It must be checkable against the Python reference with the same patch JSON.

## 2. What TypeScript looks like (for a Python reader)

The RK4 step in both languages. TypeScript is JavaScript plus type annotations. A
`Float64Array` is like a 1-D float64 NumPy array of fixed length.

```python
# Python (lab/src/chaotic_sound/integrate.py)
@njit
def rk4_step(rhs, x, p, h, k1, k2, k3, k4, tmp):
    n = x.shape[0]
    rhs(x, p, k1)
    for i in range(n):
        tmp[i] = x[i] + 0.5 * h * k1[i]
    rhs(tmp, p, k2)
    ...
    for i in range(n):
        x[i] += (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
```

```ts
// TypeScript (packages/engine/src/integrate.ts)
export type Rhs = (x: Float64Array, p: Float64Array, out: Float64Array) => void;

export function rk4Step(rhs: Rhs, x: Float64Array, p: Float64Array, h: number,
                        s: Scratch): void {
  const n = x.length;
  rhs(x, p, s.k1);
  for (let i = 0; i < n; i++) s.tmp[i] = x[i] + 0.5 * h * s.k1[i];
  rhs(s.tmp, p, s.k2);
  // ...
  for (let i = 0; i < n; i++) {
    x[i] += (h / 6) * (s.k1[i] + 2 * s.k2[i] + 2 * s.k3[i] + s.k4[i]);
  }
}
```

The differences are mostly syntax:
- `const`/`let` declare variables;
- `: Float64Array` is a type annotation, checked when compiling, like mypy;
- loops are C-style.

## 3. Package layout

```
packages/engine/            npm package "@chaotic-sound/engine" (no browser/DOM dependencies)
  src/systems/              one file per system: rhs + metadata (mirrors lab/src/chaotic_sound/systems)
  src/integrate.ts          rk4Step, renderTuned (same signature as the Python kernel)
  src/dsp.ts                onePole, dcBlock, softClip
  src/pitch.ts              noteToHz, …
  src/catalog.ts            types for catalog/systems.json, interpolation
  src/blocks/               Modulator, Dynamical, Sum, Output (same ports/params as the spec)
  src/patch.ts              graph, validation, topological order, fan-in, process(n)
  src/render.ts             offline render → Float32Array per channel
  src/wav.ts                WAV encoder (16-bit PCM / 32-bit float)
  src/worklet/processor.ts  AudioWorkletProcessor wrapper (thin)
  test/                     unit tests + cross-engine tests (Vitest)
```

## 4. Key interfaces

```ts
interface Block {
  readonly id: string;
  readonly type: "modulator" | "dynamical" | "sum" | "output";
  reset(sampleRate: number): void;
  // Writes into preallocated output buffers; inputs are views into upstream buffers.
  process(n: number, inputs: Record<string, Float64Array | null>): void;
  outputs: Record<string, Float64Array>;      // audio: interleaved stereo, length 2·maxN
}
```

- Every buffer is allocated once, when the patch is built, sized to the maximum chunk (128
  in the worklet, larger offline).
- Fan-in sums go into a preallocated scratch buffer.
- These follow the Python design, except that Python allocates per chunk, which is fine
  offline.

## 5. Real-time protocol (UI ↔ worklet)

- The UI owns the patch JSON (spec §5) and sends **edit messages** over the worklet's
  `MessagePort`: `addBlock`, `removeBlock`, `connect`, `disconnect`, `setParam`, `loadPatch`,
  `play`, `stop`.
- The worklet applies edits **between** render quanta. Structural edits (add/remove/connect)
  rebuild the processing order. The allocations this needs happen outside `process()`, in a
  message handler, or are prepared by the UI thread and transferred.
- Knob moves are `setParam` messages. The engine's 5 ms smoothers (spec §3) remove zipper
  noise, so no `AudioParam` automation is needed.
- The catalog is fetched once by the UI and passed to the worklet in `processorOptions`.
- Meters and debug data (RMS per box, safety resets) are posted back at about 20 Hz.

## 6. Cross-engine testing

The Python lab would export "golden" data for every patch in `examples/patches/`, through a
new script `lab/scripts/export_golden.py` that writes to `examples/golden/`:

1. **The first 2048 samples.** JS and Python both use IEEE float64, so they should agree to
   about 1e-9 at first. Chaos then amplifies differences in the last bits of `Math.sin`/`exp`,
   so only a short prefix can be compared exactly.
2. **Statistics** over the whole render: RMS per channel, measured pitch in cents, spectral
   envelope in octave bands, peak level and safety resets. These must agree within the
   estimator tolerances of `docs/math/tuning.md` §6.
3. **Modulator output** exactly (it has no chaos), plus block-size independence (128 vs 4096).

## 7. Performance budget

- Target: 16 dynamical boxes at 48 kHz using under 50% of one core in the worklet.
- Measured numbers will come from `docs/studies/cost.md`.
- Each box costs about N·f₀/fs RK4 steps per sample (3–5 at A4), plus about 10 flops per
  sample of DSP.
- Rules:
  - no allocation in `process()`;
  - no closures or object creation in inner loops;
  - typed arrays only;
  - each system's `rhs` is a plain function (monomorphic call sites keep the JIT fast).

## 8. Tooling (proposed)

| Concern | Choice |
|---|---|
| Runtime | Node 24 LTS |
| Packages | pnpm workspaces (`packages/engine`, later `apps/web`) |
| Language | TypeScript, `strict` mode |
| Tests | Vitest |
| Lint and format | Biome (one fast tool, like ruff for Python) |
| Web app (Phase 3) | Vite + React + React Flow |

Installing Node: Homebrew has no prebuilt packages for macOS 14 (it failed to build uv from
source the same way). Options:
- the official installer or tarball from nodejs.org;
- a version manager such as `fnm`.

**This needs the owner's OK** (ADR 0002 and the install itself), so it has not been done.

## 9. Order of work once approved

1. Scaffold the pnpm workspace, the engine package, Vitest and Biome.
2. Port the pure parts first: `pitch`, `dsp`, `systems`, `integrate`. Unit tests mirror the
   Python ones.
3. `catalog`, `blocks`, `patch` and `render`.
4. Golden exporter in the lab, then cross-engine tests over `examples/patches/`.
5. The AudioWorklet wrapper and a minimal HTML test page (play/stop one patch) to hear it live.
6. Then Phase 3 (the UI).
