/**
 * Catalog validation (TS engine review, findings 36 and 51): `CatalogEntry.checkAgainst`
 * must reject the malformed tables that the Python reference rejects, instead of playing
 * NaN. Every table has the length of `u_grid`; the default observable has tables; mean, std
 * and peak are finite, std and peak positive; the period table is finite and positive.
 */

import { describe, expect, test } from "vitest";
import { Catalog, CatalogError, type EntryJson } from "../src/core/catalog.ts";
import { getSystem, SYSTEMS } from "../src/core/dsp/systems.ts";
import { Engine } from "../src/core/engine.ts";
import { catalog, single } from "./helpers.ts";
import { editedCatalog } from "./rules-helpers.ts";

const FS = 48_000;

test("the real catalog passes for every system", () => {
  const cat = new Catalog(catalog);
  for (const system of SYSTEMS)
    expect(() => cat.get(system.name).checkAgainst(system)).not.toThrow();
});

/**
 * Edits of the Lorenz entry: z is heard by default, x is not (both must be valid).
 * `void expr` evaluates `expr` and returns undefined, so each edit is a statement.
 * `describe.each(rows)` below runs its tests once per row, like `pytest.mark.parametrize`.
 */
const z = (e: EntryJson) => e.observables.z!;
const x = (e: EntryJson) => e.observables.x!;
const MALFORMED: [string, (e: EntryJson) => void][] = [
  ["a std table one entry short", (e) => void z(e).std.pop()],
  ["a peak table one entry short", (e) => void z(e).peak.pop()],
  ["a mean table one entry short", (e) => void x(e).mean.pop()],
  ["a prominence table one entry short", (e) => void x(e).prominence.pop()],
  ["a std table one entry long", (e) => void z(e).std.push(1)],
  ["a period table one entry short", (e) => void e.period.pop()],
  ["a default observable without tables", (e) => void (e.default_observable = "w")],
  ["a zero std", (e) => void (z(e).std[100] = 0)],
  ["a negative std", (e) => void (x(e).std[3] = -1)],
  ["a NaN std", (e) => void (z(e).std[0] = Number.NaN)],
  ["an infinite std", (e) => void (z(e).std[128] = Infinity)],
  ["a zero peak", (e) => void (x(e).peak[64] = 0)],
  ["a NaN peak", (e) => void (z(e).peak[5] = Number.NaN)],
  ["a NaN mean", (e) => void (z(e).mean[7] = Number.NaN)],
  ["an infinite mean", (e) => void (x(e).mean[7] = -Infinity)],
  ["a zero period", (e) => void (e.period[10] = 0)],
  ["a negative period", (e) => void (e.period[0] = -0.5)],
  ["a NaN period", (e) => void (e.period[128] = Number.NaN)],
  ["an infinite period", (e) => void (e.period[1] = Infinity)],
];

describe.each(MALFORMED)("a catalog with %s", (_, edit) => {
  test("is rejected by checkAgainst", () => {
    const entry = new Catalog(editedCatalog("lorenz", edit)).get("lorenz");
    expect(() => entry.checkAgainst(getSystem("lorenz"))).toThrow(CatalogError);
  });

  test("cannot be loaded, and the running patch is kept", () => {
    const e = new Engine({ maxFrames: 128 });
    e.load(single({ system: "rossler" }), catalog, FS);
    // An explicit observable, so only the validation can reject the entry.
    const doc = single({ system: "lorenz", observable: "x", param: 0.999 });
    expect(() => e.load(doc, editedCatalog("lorenz", edit), FS)).toThrow(/catalog entry lorenz/);
    expect(e.patch?.blocks[0]?.params).toEqual({ system: "rossler" });
  });
});
