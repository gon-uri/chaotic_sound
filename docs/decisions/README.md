# Architecture decision records (ADRs)

Each file records one decision: its context, the options considered, the choice made and its
consequences. ADRs are never rewritten once accepted. To change one, write a new ADR that
*supersedes* it and update the status of the old one.

**Status values**
- **Proposed**: drafted, but the owner hasn't approved it yet.
- **Accepted**: approved; follow it.
- **Superseded by NNNN**: replaced by a newer ADR.

When Claude makes a decision while the owner is away, it is written as *Proposed* (or
*Accepted (provisional)* when work had to build on it) and listed in `../REVIEW.md`.

| # | Decision | Status |
|---|---|---|
| [0001](0001-client-side-audio.md) | All sound is generated in the browser; the site is static | Accepted (provisional) |
| [0002](0002-engine-language.md) | Real-time engine in TypeScript; Python lab as the reference | Proposed |
| [0003](0003-python-lab-and-catalog.md) | Python lab generates a JSON catalog that engines consume | Accepted (provisional) |
| [0004](0004-single-engine-graph.md) | One engine runs the whole patch (not one Web Audio node per box) | Accepted (provisional) |
| [0005](0005-signal-conventions.md) | Signal ranges, normalization and modulation semantics | Accepted (provisional) |
| [0006](0006-tuning-by-time-rescaling.md) | Tuning by time rescaling; period from the spectral peak; pitch lock | Accepted (provisional) |
| [0007](0007-own-system-definitions.md) | Own system definitions, dysts as data source and test oracle | Accepted (provisional) |
| [0008](0008-modulators-v1.md) | v1 modulators: separate entity, 5 shapes, loop/once | Accepted (owner's answers) |
| [0009](0009-python-tooling.md) | Python tooling: uv, Python 3.14, numba, ruff, mypy, pytest | Accepted (provisional) |

Template:

```markdown
# NNNN. Title
- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD
## Context
## Decision
## Consequences
## Alternatives considered
```
