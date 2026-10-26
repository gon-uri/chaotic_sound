# 0014. Live edits, click-free knobs and robustness guards (spec v0.4)

- Status: Proposed (made by Claude while the owner was away; listed in `docs/REVIEW.md` B5)
- Date: 2026-10-26

## Context

A multi-lens review of the TypeScript engine (parity, real-time safety, architecture, tests,
readability), with each finding checked by independent skeptics, found that:

- a rejected `load()` left the engine half-updated (old graph playing, blocks gone);
- `setParam` and `edit({op: "setParams"})` treated the same knob change differently: the
  first kept the oscillator running, the second restarted it;
- live changes of Sum/Control Sum `gain`, Output `volume` and the `amp_curve` toggle were
  applied as steps and clicked (a volume change from 0.8 to 0.1 jumped 0.32 in one sample);
- `process()` allocated a little on every 128-frame quantum;
- after a pitch cable was removed and another connected, the pitch glided from a stale value;
- a single non-finite sample (possible only with a malformed catalog) stayed in the DC
  blocker forever and reached the speakers;
- the two engines disagreed on a few patch documents (`{"foo": null}`, `"seed": 7.0`).

## Decision

1. **One live-edit path.** `setParam(id, name, v)` is `edit({op: "setParams", id, params:
   {name: v}})`. A setting the block can change live (knobs and pitch settings, spec §6)
   updates the running block, which keeps its state. Any other setting recreates the block.
   If one of several values is invalid, the changes already made are rolled back.
2. **Atomic loads and edits.** Everything is built and validated before anything is
   committed. An error leaves the running patch exactly as it was.
3. **Gliding knobs.** `gain`, `volume` and `amp_curve` glide with the 5 ms one-pole used for
   `amp`. The glide snaps to its target within 1e-9. A steady value is applied exactly, so
   static renders stay bit-identical to the Python reference, which has no live changes.
   `amp_curve` blends the two laws during the glide.
4. **No allocation in `process()`.** Per-block input arrays and the RK4 argument record are
   built once at compile time. Table lookups are hoisted out of the sample loop, and the
   slew coefficient is computed once per chunk when there is no pitch cable.
5. **Guards (both engines).**
   - The pitch smoother restarts from a new cable's first value.
   - A non-finite DC-blocker state is cleared and counted as a safety reset.
   - Output maps NaN to 0.
   - Catalog validation requires finite tables with σ, π and P > 0.
6. **Document rules (both engines).**
   - An unknown param is an error even when its value is `null`.
   - An integer setting may be written `7.0`. JavaScript's JSON parser cannot tell `7.0`
     from `7`, so Python follows it.

## Consequences

- The UI can send every knob move as `setParams` without caring which ones are live.
- A bad patch from the editor or a file never breaks what is playing.
- Golden vectors are unchanged (every change is either a live-only behavior or a guard that
  never fires on valid input).
- `pitch_lock`, `note` and `cents` still switch at the next chunk. They only change the
  ODE's speed, so they do not click; a pitch glide for them could be added later.

## Alternatives considered

- **Smooth `gain`/`volume` always** (a smoother on the static path too). Rejected: it would
  change static renders and break bit-parity with the reference for no audible benefit.
- **Recreate blocks on every knob change and crossfade.** Rejected: it doubles the cost
  during the fade and still restarts the attractor, which is audible.
- **Reject `7.0` in TypeScript.** Not possible with the standard JSON parser.
