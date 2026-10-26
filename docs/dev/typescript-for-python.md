# TypeScript for a Python programmer

A short guide to reading `packages/engine` and `apps/web` if you know Python well. It covers
only the TypeScript syntax that appears in this repository.

## Running things

| Python habit | Here |
|---|---|
| `python script.py` | `node script.ts`. Node 24 runs TypeScript directly: it removes the types and runs the JavaScript. |
| `pytest` | `npm test` (Vitest) at the repository root |
| `mypy` | `npm run check` runs `tsc`, the type checker, on three configs, then Biome |
| `ruff` | Biome (`npx biome check --write .` fixes formatting and import order) |
| `pyproject.toml` | `package.json` (dependencies, scripts) and `tsconfig*.json` (type-checker settings) |
| `uv sync` | `npm install` (packages go to `node_modules/`, versions locked in `package-lock.json`) |

Imports carry the `.ts` extension (`import { Engine } from "./engine.ts"`) because Node loads
the files as written, with no build step. Because types are only removed, never translated,
the code uses only "erasable" syntax: no `enum` and no `namespace` (see
`packages/engine/CLAUDE.md`).

## Types are annotations, like mypy

```ts
function interp(x: number, xp: Float64Array, fp: Float64Array): number { … }
```

is `def interp(x: float, xp: NDArray[float64], fp: NDArray[float64]) -> float`. As in Python,
types are not checked at run time: `tsc` checks them before the code runs, like mypy. `number`
is a float64. JavaScript has no separate int type, so `3` and `3.0` are the same value.

| TypeScript | Python equivalent |
|---|---|
| `let x = 1` / `const x = 1` | `x = 1`. `const` cannot be reassigned (the object it points to can still change). |
| `string`, `number`, `boolean` | `str`, `float`, `bool` |
| `string \| null` | `str \| None` (`Optional[str]`) |
| `x === y`, `x !== y` | `x == y`, `x != y`. Always the triple form: `==` in JS converts types first. |
| `undefined` | Roughly `None` for "missing": a missing dict key or array index gives `undefined`, not a `KeyError`. |
| `Float64Array` | a 1-D `np.ndarray` of float64 (fixed length, preallocated) |
| `Map<string, Block>` | `dict[str, Block]` (`m.get(k)`, `m.set(k, v)`, `m.has(k)`) |
| `Set<string>` | `set[str]` |
| `Record<string, number>` | `dict[str, float]` written as a plain object `{ a: 1 }` |
| `interface Foo { readonly a: number; b?: string }` | a `TypedDict` / frozen dataclass shape; `b?` means "may be absent" |
| `type Kind = "audio" \| "control"` | `Literal["audio", "control"]` |
| `class Engine implements EnginePort` | a class that satisfies a `Protocol` (`EnginePort` in `src/ports.ts`) |

## Small symbols that look strange

- **`x!` (non-null assertion).** It means "I know this is not `undefined` here". The configs
  enable `noUncheckedIndexedAccess`, so `arr[i]` has type `number | undefined` even inside a
  loop over a valid range. In hot loops we write `arr[i]!` instead of checking. It does nothing
  at run time.
- **`a ?? b`.** `a` unless it is `null`/`undefined`, else `b`. Like `a if a is not None else b`.
  Unlike Python's `a or b`, it keeps `0` and `""`.
- **`obj?.field`, `f?.()`.** Optional chaining: gives `undefined` instead of raising when
  `obj` or `f` is missing. `block.setParam?.(name, v)` calls `setParam` only if the block has
  one.
- **`import type { X }`.** Imports a name used only as a type. It is removed entirely when the
  code runs, like `if TYPE_CHECKING:` imports.
- **`readonly`.** The field cannot be reassigned after construction, like a frozen dataclass
  field. `ReadonlyArray<T>` / `readonly T[]` is a tuple-like view you may not modify.
- **`as const`.** Freezes a literal and keeps its exact values as types:
  `["sine", "triangle"] as const` has type `readonly ["sine", "triangle"]`.
- **`x as Foo`.** A cast for the type checker only (`typing.cast`). It does no conversion.
- **`private`.** Like a leading underscore, but enforced by `tsc`.
- **Arrow functions `(a, b) => a + b`.** `lambda a, b: a + b`, but they can also contain a
  block `{ … }` with statements.
- **`` `text ${x}` ``.** An f-string: `f"text {x}"`.
- **`...spread`.** `{ ...d, a: 1 }` is `{**d, "a": 1}`; `[...xs, y]` is `[*xs, y]`.
- **`for (const x of xs)`** iterates values, like `for x in xs`. Avoid `for … in`, which
  iterates keys.
- **`(...args)`** in a parameter list collects the remaining arguments into an array, like
  `*args`. In a call, `f(...xs)` spreads an array into arguments, like `f(*xs)`.
- **`void expr`** evaluates `expr` and discards the result. It is used to mark a promise that
  is deliberately not awaited (`void play()`).
- **`test.each(cases)(name, fn)` / `describe.each`** (Vitest) are `@pytest.mark.parametrize`:
  `%s` and `%i` in the name are replaced by the case's values.
- **`>>> 0`, `Math.imul`, `| 0`.** 32-bit integer arithmetic for the random number generator
  and CRC-32 (`src/core/dsp/rng.ts`). JavaScript numbers are float64, so these operators force
  unsigned or signed 32-bit wrap-around, like `& 0xFFFFFFFF` in Python.

## Classes and errors

```ts
class Smoother {
  private y = 0;                     // instance attribute with a default
  readonly a: number;
  constructor(a: number) {           // __init__
    this.a = a;
  }
  step(x: number): number {          // a method; `this` is `self`
    this.y += this.a * (x - this.y);
    return this.y;
  }
}
```

`this` must always be written out (there is no implicit attribute access). Errors are `throw new RangeError("…")`
and `try { … } catch (e) { … }`. The engine uses `PatchError` (in `src/core/patch.ts`) for
invalid patches, like `PatchError` in the Python lab.

## Modules and the package

- `export` marks what a file makes public. There is no `__all__`: anything not exported is
  private to the file.
- `packages/engine/src/index.ts` is the package's `__init__.py`: it re-exports the public API.
  The web app imports it as `@chaotic-sound/engine` (an npm workspace, like an editable
  install).

## React, in two lines (apps/web only)

A component is a function that returns markup (`.tsx` files mix HTML-like tags into code).
`useState`/`useMemo`/`useEffect` are "hooks" that keep state between redraws. The patch itself
lives in a store (`apps/web/src/store/patchStore.ts`, Zustand): a single object plus functions
that change it, and every change goes through the engine's validation.
