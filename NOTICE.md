# Third-party notices

## dysts

This project uses data (system definitions, parameter values, initial conditions and estimated
properties) from **dysts**:

- Repository: <https://github.com/GilpinLab/dysts>, snapshot at commit
  `2a03f1ae7b0680b0470458783dcb4664660e131a` (2026-04-15).
- Paper: W. Gilpin, "Chaos as an interpretable benchmark for forecasting and data-driven
  modelling", NeurIPS Datasets and Benchmarks (2021). arXiv:2110.05266.
- License: the GitHub repository declares **Apache-2.0** (LICENSE file), while the package
  metadata in `pyproject.toml` lists MIT. Both are permissive. We give attribution either way,
  and the question should be settled before this repository becomes public (see
  `docs/REVIEW.md`).

The equations in `lab/src/chaotic_sound/systems/` are written independently for this project
and are checked numerically against the dysts implementations in the test suite.
