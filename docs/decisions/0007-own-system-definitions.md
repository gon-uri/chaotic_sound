# 0007. Own system definitions, with dysts as data source and test oracle

- Status: Accepted (owner, 2026-10-26)
- Date: 2026-10-25

## Context

dysts provides about 135 chaotic systems, each with parameters, initial conditions on the
attractor, an estimated period, an integration step, means and standard deviations, Lyapunov
estimates, descriptions and citations. The PyPI release (0.96) pulls in heavy dependencies
(gluonts, scikit-learn, …), and its right-hand-side functions are numba functions with a
dysts-specific signature. Our engines need fast fixed-step kernels with a per-sample
parameter, which dysts does not provide.

## Decision

- We write each system's right-hand side ourselves (`lab/src/chaotic_sound/systems/`), in a
  uniform signature suited to our kernels.
- dysts is used only as:
  - a **data source**: parameter values and initial conditions are copied into our system
    modules from a pinned commit (`2a03f1ae7b06`), and tests check they still match. The
    catalog builder also records dysts' metadata (citation, description, period, Lyapunov
    estimate);
  - a **test oracle**: tests check that our RHS equals dysts' RHS at random points.
- dysts is a dev dependency installed from that git commit (which needs only numpy, scipy and
  tqdm), never a runtime dependency.

## Consequences

- The runtime package stays lean: numpy, scipy, numba.
- Adding a dysts system is mechanical: copy the equations, add a test against dysts, run the
  catalog build. A project skill (`.claude/skills/add-dynamical-system`) documents the steps.
- If dysts changes upstream, our snapshot is unaffected until we deliberately bump the pin.
