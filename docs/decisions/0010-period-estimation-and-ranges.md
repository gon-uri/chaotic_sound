# 0010. Measuring the characteristic period and choosing the chaotic range

- Status: Accepted (provisional, pending owner review). Refines ADR 0006.
- Date: 2026-10-25
- Evidence: `docs/math/tuning.md` §2–4 and `docs/figures/catalog_*.png`.

## Context

ADR 0006 defined P as the dominant spectral peak of the heard variable. Phase 1 measurements
showed four problems with that definition.

1. P depends strongly on the variable. Lorenz x and y are dominated by slow lobe switching,
   and Chua x jumps between scroll and loop scales.
2. The highest bin of a chaotic peak is unstable: 11 cents of spread for Chua over 2000
   periods.
3. Some systems have no sharp peak at all (Thomas: prominence 0.1–0.25, with the spectral
   estimate spreading 17–25 cents).
4. Chaotic bands are riddled with periodic windows, so a strictly chaos-only range around the
   dysts default is tiny for Rössler ([5.6, 5.8]) and Duffing ([0.342, 0.354]).

## Decision

1. **One characteristic period per system.** It is measured on the *tuning observable*, the
   variable with the most prominent peak at the default parameter, and used whatever
   variable the box plays. The catalog stores P(u) per system, and μ(u), σ(u) per variable.
2. **The estimator:**
   - forced systems use the exact drive period 2π/ω;
   - a tuning observable with prominence ≥ 0.25 uses the **peak centroid**, the
     power-weighted mean frequency within ±10% of the highest bin (2–4× more stable than the
     highest bin);
   - otherwise the **mean return time** between maxima above the mean.
3. **Range selection** uses a sweep with continuation from the default. The range keeps
   growing while points are:
   - bounded, keeping a 3% margin from escape;
   - stationary on the tuning observable;
   - chaotic (λ·P > 0.05);
   - free of P jumps over 15%.

   Interior periodic windows up to 3% of the candidate width are accepted and recorded. A
   final 129-point pass trims the range at any unsafe point or jump it reveals.
4. **Tables** have 129 uniform points plus an exact node at the default. P(u) outliers over
   5% from a 5-point running median are replaced and logged.
5. **Lorenz's candidate range starts at ρ = 24.8**, above the subcritical Hopf point ρ ≈ 24.74
   where the fixed points become unstable. A modulated box can then never settle on a silent
   fixed point.

## Consequences

- The tuning accuracy is set by the dynamics, not by the code:
  - < 1 cent for Rössler and Duffing;
  - about 3–6 cents for Lorenz and Chua;
  - about ±15 cents for Thomas, depending on the run.
- "Chaos only" now means "predominantly chaotic, with narrow periodic windows" (73–99% of
  grid points are chaotic). The owner should confirm this reading.
- Thomas, at dysts' parameters, only just meets the criteria. Its replacement is an open
  question (`docs/REVIEW.md`).

## Alternatives considered

- **Return time everywhere.** It fails for Duffing (15 cents) and for variables that switch
  lobes.
- **One period per variable.** Switching variables would retune the box, and the tables were
  erratic for x of Lorenz and Chua.
- **Strictly windowless ranges.** Musically useless for Rössler and Duffing.
- **Moving the default parameter** to the middle of a wider band (for example Duffing
  γ = 0.45). Rejected for now to stay "around the dysts value" as the owner asked; it is easy
  to revisit.
