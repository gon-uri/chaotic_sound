# 0009. Python tooling: uv, Python 3.14, numba, ruff, mypy, pytest

- Status: Accepted (provisional, pending owner review)
- Date: 2026-10-25

## Decision

| Concern | Choice | Why |
|---|---|---|
| Environments and dependencies | **uv**, with a committed `uv.lock` | Fast, reproducible, manages the Python version itself; the current standard |
| Python | **3.14** (`lab/.python-version`), `requires-python >= 3.12` | Current stable; numba 0.68 supports it |
| Hot loops | **numba** `@njit` | Per-sample RK4 in pure Python would be about 100× too slow |
| Core dependencies | numpy, scipy, numba only | A lean, reusable package. Plotting (matplotlib) is dev-only. |
| Lint and format | **ruff** (pydocstyle numpy convention) | One fast tool. A Claude Code hook formats files on edit. |
| Types | **mypy** on `src/` | Catches interface errors in the reusable package |
| Tests | **pytest**, with a `slow` marker for long numerical tests | Standard |
| Docstrings | numpy style, with **units and array shapes** stated | Numerical code is unreadable without units |
| Layout | `src/` layout, build backend `uv_build` | Prevents accidentally importing the source tree in tests |

## Notes

- uv was installed into `~/.local/share/uv-bootstrap` (linked from `~/.local/bin/uv`) because
  Homebrew no longer ships prebuilt packages for macOS 14 and building from source failed. To
  remove it: delete that folder and the link.
