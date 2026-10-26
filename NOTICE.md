# chaotic_sound: copyright and license notices

Copyright (C) 2026 Gonzalo Uribarri. Source: <https://github.com/gon-uri/chaotic_sound>.

## Software: GNU AGPL v3 or later, with an attribution term

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU Affero General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version (see `LICENSE`).

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
the GNU Affero General Public License for more details.

### Additional terms (section 7 of the GNU AGPL)

Under section 7(b), the following author attribution must be preserved in all copies of this
software, in whole or in part, and in all modified versions:

> Based on chaotic_sound by Gonzalo Uribarri (https://github.com/gon-uri/chaotic_sound)

It must appear:

- in the source, next to the copyright notice;
- in the Appropriate Legal Notices of every interactive user interface (for example, an
  About screen or a footer), as the editor in `apps/web` does.

Section 7(b) allows requiring "preservation of specified reasonable legal notices or author
attributions". All other terms are those of the GNU AGPL.

## Documentation and educational text: CC BY-SA 4.0

The texts and figures in `docs/`, including the system pages shown in the editor's
"Learn more", are licensed under the Creative Commons Attribution-ShareAlike 4.0 International
License (<https://creativecommons.org/licenses/by-sa/4.0/>), unless a file says otherwise.
Credit: "chaotic_sound by Gonzalo Uribarri", with a link to the repository.

## What you make with it is yours

Sounds, music, WAV files and patches you create with chaotic_sound belong to you. You may use,
publish and sell them for any purpose. The licenses above cover the software and its
documentation, not their output. Credit is appreciated but not required.

## Commercial licenses

The author holds the copyright and can offer the software under other terms, for example to
include it in a closed-source product. Contact: <https://github.com/gon-uri>.

Contributions are welcome. Because the author may offer the software under other licenses, a
contribution can be accepted only if its author agrees that it may be used under both the
AGPL and such other terms (a contributor license agreement).

# Third-party notices

## dysts

This project uses data (system definitions, parameter values, initial conditions and estimated
properties) from **dysts**:

- Repository: <https://github.com/GilpinLab/dysts>, snapshot at commit
  `2a03f1ae7b0680b0470458783dcb4664660e131a` (2026-04-15).
- Paper: W. Gilpin, "Chaos as an interpretable benchmark for forecasting and data-driven
  modelling", NeurIPS Datasets and Benchmarks (2021). arXiv:2110.05266.
- License: the GitHub repository declares **Apache-2.0** (LICENSE file), while the package
  metadata in `pyproject.toml` lists MIT. Both are permissive and compatible with the AGPL v3.
  We follow the stricter one (Apache-2.0): this notice gives attribution and states what we use.
  dysts code is not redistributed; it is a development dependency used as a test oracle.

The equations in `lab/src/chaotic_sound/systems/` are written independently for this project
and are checked numerically against the dysts implementations in the test suite.

## Libraries

The editor and engines depend on open-source libraries under their own licenses, all permissive
(MIT, BSD, ISC or Apache-2.0). They include React, React Flow (@xyflow/react), Zustand,
three.js with @react-three/fiber and drei, KaTeX, react-markdown, NumPy, SciPy and numba. The
full lists, with versions, are in `package-lock.json` and `lab/uv.lock`. Each library's license
ships with it in `node_modules/` or the Python environment.
