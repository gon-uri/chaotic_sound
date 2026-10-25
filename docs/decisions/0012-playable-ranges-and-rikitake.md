# 0012. Playable knob ranges (stability and musicality first) and Rikitake replaces Thomas

- Status: Accepted (from the owner's answers, 2026-10-26). Supersedes ADR 0010 point 3
  (range selection), and point 5 for the default position.
- Date: 2026-10-26
- Evidence: `docs/math/tuning.md` §4, `docs/figures/catalog_*.png`,
  `docs/studies/fifth-system-screening.md`.

## Context

The owner's answers:
- "There is no need for a chaos-only region." Use regions that of course present chaos but
  may contain periodic windows, and choose them prioritizing **stability and musicality**.
- Moving the default parameter to the middle of a wider band is fine. The dysts value acts as
  a reference, as long as the region is checked to be good.
- If Thomas is still problematic, pick a more straightforward attractor.

## Decision

**Range selection** (`analysis/sweep.py: select_playable_range`). A continuation sweep runs
over the candidate range, starting from the dysts value.

1. **Stability.**
   - A point is unsafe if it is unbounded, drifts (non-stationary tuning variable), or has no
     defined period.
   - Points within 3% of the candidate width of an unbounded or drifting value are also
     unsafe (the escape margin).
   - **Hysteresis test**: the range is swept up and down with continuation, the way a
     modulator moves the knob. Where the two directions disagree (σ by > 10%, or the period by
     > 3%), the attractor depends on history, and that stretch is excluded.
2. **Musicality.**
   - The tuning variable's spectral prominence must be ≥ 0.15 everywhere in the range.
   - P(u) must not jump by more than 15% between neighbors (pitch lock would glitch).
3. **Chaos present.** Both ends must be chaotic, and at least 60% of the points chaotic.
   Periodic windows of any width may lie inside. The periodic tails at either end are
   trimmed off.
4. **Choice.** The qualifying stretch containing the dysts value is used; otherwise the
   widest one.
5. **Default.** The chaotic point nearest the middle of the range, with its two neighbors on
   each side also chaotic, so it never sits at a window edge. The initial condition is the
   state on the attractor branch there.
6. **A table pass** (129 points + the default node, by continuation from the default) applies
   the same selection again and shrinks the range if it reveals new problems.

**Rikitake replaces Thomas** in v1. Thomas at dysts' parameters has several problems:
- its chaotic band is narrow and riddled with windows;
- it has no sharp spectral peak;
- its pitch depends on the run (−9…+34 cents).

The screening of 24 dysts flows recommends the Rikitake dynamo (T. Rikitake, 1958: two coupled
disc dynamos as a toy geodynamo for the reversals of Earth's magnetic field), modulating μ:
- robust;
- pitched (z, prominence ≥ 0.44);
- a wide and smooth range;
- a new field (geophysics).

Thomas's code and page are kept in the git history and `docs/systems/archive/`.

## Result (catalog v2)

| System | Range | Default (dysts) | Chaotic | Windows | Notes |
|---|---|---|---|---|---|
| Lorenz | ρ ∈ [24.8, 69.4] | 48.0 (28) | 100% | 0 | end at the ρ ≈ 69.8 window (period jump) |
| Rössler | c ∈ [4.24, 8.82] | 6.56 (5.7) | 78% | 11 | from chaos onset to the funnel regime |
| Chua | α ∈ [13.7, 18.05] | 15.8 (15.6) | 91% | 7 | margin from escape at 18.45 |
| Rikitake | μ ∈ [0.513, 1.8] | 1.15 (1) | 98% | 2 | top set by hand (quiet spells above ≈2.1) |
| Duffing | γ ∈ [0.386, 0.508] | 0.447 (0.35) | 98% | 2 | hysteresis found at 0.381 and 0.514 |

## Consequences

- Every default knob sits near the middle (u ≈ 0.5), so users can move both ways.
- The classic textbook values (Lorenz ρ = 28, Rössler c = 5.7) are no longer the defaults.
  They are still inside the ranges and recorded as `p_reference`. The "Learn more" pages can
  show the classic attractor.
- The hysteresis test makes the build slower (about 2 minutes for five systems) but catches
  multistability, which the old criteria missed.
