"""The system catalog: generated tables that engines need to tune and normalize a system.

The catalog (``catalog/systems.json``, ADR 0003) is the contract between the lab and every
engine. Per system it holds:

- the modulated parameter's range ``[p_min, p_max]`` (the knob u ∈ [0, 1] maps onto it);
- on a grid of u values: the system's characteristic period P(u) (system time), and for each
  audible variable its mean μ(u), standard deviation σ(u) and robust peak π(u) (the 99.9th
  percentile of |x − μ|);
- the integration resolution ``h_max``, a safety bounding box and the initial condition.

This module only reads, writes and interpolates catalogs; producing one is the job of
:mod:`chaotic_sound.analysis.catalog_builder`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

CATALOG_FORMAT = "chaotic-sound-catalog"
CATALOG_VERSION = 2
CATALOG_ENV_VAR = "CHAOTIC_SOUND_CATALOG"

PeriodMethod = str
"""How P was obtained: ``"peak_centroid"``, ``"return_time"`` or ``"drive"`` (ADR 0010)."""


def _arr(values: ArrayLike) -> NDArray[np.float64]:
    return np.asarray(values, dtype=np.float64)


@dataclass(frozen=True)
class ObservableTable:
    """Normalization tables of one audible variable, on the entry's u grid.

    Attributes
    ----------
    mean, std
        Mean μ(u) and standard deviation σ(u) of the variable.
    peak
        Robust peak π(u): the 99.9th percentile of ``|x − μ|``. Used to keep spiky signals
        (high crest factor) below the clipper (spec §4.2 step 6).
    prominence
        Fraction of the variable's power in its own spectral peak (informative: how pitched
        it sounds; e.g. Lorenz z ≈ 0.4 but Lorenz x ≈ 0.03).
    """

    mean: NDArray[np.float64]
    std: NDArray[np.float64]
    peak: NDArray[np.float64]
    prominence: NDArray[np.float64]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation."""
        return {
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "peak": self.peak.tolist(),
            "prominence": self.prominence.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservableTable:
        """Inverse of :meth:`to_dict`."""
        return cls(
            mean=_arr(d["mean"]),
            std=_arr(d["std"]),
            peak=_arr(d["peak"]),
            prominence=_arr(d["prominence"]),
        )


@dataclass(frozen=True)
class CatalogEntry:
    """Everything an engine needs to run one system (spec §4.2)."""

    name: str
    param: str
    p_min: float
    p_max: float
    p_default: float
    """Default parameter value (the knob's default position); may differ from dysts' value."""
    p_reference: float
    """The dysts parameter value the analysis started from (informative)."""
    u_grid: NDArray[np.float64]
    period_table: NDArray[np.float64]
    """Characteristic period P(u) of the system on ``u_grid`` (system time)."""
    period_method: PeriodMethod
    period_observable: str
    """Variable on which P was measured (the most pitched one)."""
    observables: dict[str, ObservableTable]
    default_observable: str
    h_max: float
    steps_per_period: int
    bounds_lo: NDArray[np.float64]
    bounds_hi: NDArray[np.float64]
    initial_condition: NDArray[np.float64]
    info: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def u_default(self) -> float:
        """Knob position of the default parameter value."""
        return (self.p_default - self.p_min) / (self.p_max - self.p_min)

    def param_value(self, u: ArrayLike) -> NDArray[np.float64]:
        """Map knob values u ∈ [0, 1] linearly onto [p_min, p_max] (spec §4.2 step 2)."""
        return self.p_min + np.clip(_arr(u), 0.0, 1.0) * (self.p_max - self.p_min)

    def _interp(self, u: ArrayLike, table: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.interp(np.clip(_arr(u), 0.0, 1.0), self.u_grid, table)

    def period(self, u: ArrayLike) -> NDArray[np.float64]:
        """P(u), linearly interpolated in u (system time). Used whatever variable is heard."""
        return self._interp(u, self.period_table)

    def mean(self, observable: str, u: ArrayLike) -> NDArray[np.float64]:
        """μ(u) of ``observable``."""
        return self._interp(u, self.observables[observable].mean)

    def std(self, observable: str, u: ArrayLike) -> NDArray[np.float64]:
        """σ(u) of ``observable``."""
        return self._interp(u, self.observables[observable].std)

    def peak(self, observable: str, u: ArrayLike) -> NDArray[np.float64]:
        """π(u) of ``observable`` (99.9th percentile of |x − μ|)."""
        return self._interp(u, self.observables[observable].peak)

    def check_against(self, system: Any) -> None:
        """Raise ``ValueError`` if this entry does not fit ``system`` (a ``SystemDef``)."""
        problems = []
        dim = len(system.variables)
        for name, arr in (("bounds_lo", self.bounds_lo), ("bounds_hi", self.bounds_hi),
                          ("initial_condition", self.initial_condition)):  # fmt: skip
            if arr.shape != (dim,):
                problems.append(f"{name} has shape {arr.shape}, expected ({dim},)")
        if self.param != system.modulated_param:
            problems.append(f"param {self.param!r} != {system.modulated_param!r}")
        if set(self.observables) != set(system.audio_variables):
            problems.append(f"observables {sorted(self.observables)} != {system.audio_variables}")
        if self.default_observable not in self.observables:
            problems.append(f"default observable {self.default_observable!r} has no table")
        g = self.u_grid
        if g.size < 2 or g[0] != 0.0 or g[-1] != 1.0 or np.any(np.diff(g) <= 0):
            problems.append("u_grid must increase strictly from 0 to 1")
        tables = [self.period_table] + [
            a for t in self.observables.values() for a in (t.mean, t.std, t.peak, t.prominence)
        ]
        if any(t.shape != g.shape for t in tables):
            problems.append("a table does not match u_grid")
        # Level normalization divides by σ and π: they must be finite and positive.
        for name, t in self.observables.items():
            if not (
                np.all(np.isfinite(t.mean))
                and np.all(np.isfinite(t.std) & (t.std > 0))
                and np.all(np.isfinite(t.peak) & (t.peak > 0))
            ):
                problems.append(f"tables of {name} must be finite, with std and peak > 0")
        if not np.all(np.isfinite(self.period_table) & (self.period_table > 0)):
            problems.append("period table must be finite and positive")
        if not (self.p_min < self.p_max and self.p_min <= self.p_default <= self.p_max):
            problems.append("p_min < p_max and p_min ≤ p_default ≤ p_max are required")
        if problems:
            raise ValueError(f"catalog entry {self.name!r}: " + "; ".join(problems))

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation."""
        return {
            "param": self.param,
            "p_min": self.p_min,
            "p_max": self.p_max,
            "p_default": self.p_default,
            "p_reference": self.p_reference,
            "u_default": self.u_default,
            "u_grid": self.u_grid.tolist(),
            "period": self.period_table.tolist(),
            "period_method": self.period_method,
            "period_observable": self.period_observable,
            "default_observable": self.default_observable,
            "observables": {k: v.to_dict() for k, v in self.observables.items()},
            "h_max": self.h_max,
            "steps_per_period": self.steps_per_period,
            "bounds": {"lo": self.bounds_lo.tolist(), "hi": self.bounds_hi.tolist()},
            "initial_condition": self.initial_condition.tolist(),
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> CatalogEntry:
        """Inverse of :meth:`to_dict`."""
        return cls(
            name=name,
            param=str(d["param"]),
            p_min=float(d["p_min"]),
            p_max=float(d["p_max"]),
            p_default=float(d["p_default"]),
            p_reference=float(d["p_reference"]),
            u_grid=_arr(d["u_grid"]),
            period_table=_arr(d["period"]),
            period_method=str(d["period_method"]),
            period_observable=str(d["period_observable"]),
            observables={k: ObservableTable.from_dict(v) for k, v in d["observables"].items()},
            default_observable=str(d["default_observable"]),
            h_max=float(d["h_max"]),
            steps_per_period=int(d["steps_per_period"]),
            bounds_lo=_arr(d["bounds"]["lo"]),
            bounds_hi=_arr(d["bounds"]["hi"]),
            initial_condition=_arr(d["initial_condition"]),
            info=dict(d.get("info", {})),
        )


@dataclass(frozen=True)
class Catalog:
    """A set of catalog entries plus provenance metadata."""

    entries: dict[str, CatalogEntry]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> CatalogEntry:
        try:
            return self.entries[name]
        except KeyError:
            raise KeyError(f"system {name!r} is not in the catalog") from None

    def __contains__(self, name: object) -> bool:
        return name in self.entries

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation (with format and version headers)."""
        return {
            "format": CATALOG_FORMAT,
            "catalog_version": CATALOG_VERSION,
            "metadata": self.metadata,
            "systems": {k: v.to_dict() for k, v in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Catalog:
        """Inverse of :meth:`to_dict`; checks the format and version."""
        if d.get("format") != CATALOG_FORMAT:
            raise ValueError("not a chaotic_sound catalog")
        if d.get("catalog_version") != CATALOG_VERSION:
            raise ValueError(
                f"catalog version {d.get('catalog_version')} unsupported "
                f"(expected {CATALOG_VERSION}); rebuild it with scripts/build_catalog.py"
            )
        entries = {k: CatalogEntry.from_dict(k, v) for k, v in d["systems"].items()}
        return cls(entries=entries, metadata=dict(d.get("metadata", {})))

    def save(self, path: str | Path) -> None:
        """Write the catalog as indented JSON."""
        text = json.dumps(self.to_dict(), indent=1, ensure_ascii=False) + "\n"
        Path(path).write_text(text, encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Catalog:
        """Read a catalog JSON file."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def default_catalog_path() -> Path:
    """Location of the catalog: ``$CHAOTIC_SOUND_CATALOG`` or ``<repo>/catalog/systems.json``."""
    env = os.environ.get(CATALOG_ENV_VAR)
    if env:
        return Path(env)
    # lab/src/chaotic_sound/catalog.py → repo root is three levels above the package.
    return Path(__file__).resolve().parents[3] / "catalog" / "systems.json"


@cache
def load_default_catalog() -> Catalog:
    """Load (once) the catalog at :func:`default_catalog_path`."""
    path = default_catalog_path()
    if not path.exists():
        raise FileNotFoundError(
            f"catalog not found at {path}; build it with `uv run python scripts/build_catalog.py`"
            f" or set {CATALOG_ENV_VAR}"
        )
    return Catalog.load(path)
