"""Definition of a dynamical system as used by the engine (architecture layer 1).

A system is an autonomous ODE ``dx/dτ = F(x; p)`` in its own time units τ ("system time").
Forced systems are written autonomously with an explicit phase variable (e.g. Duffing's
drive phase ``z' = ω``), listed in :attr:`SystemDef.phase_indices` so engines can wrap it
modulo 2π.

The right-hand side is a numba ``@njit`` function with the uniform signature::

    rhs(x: float64[:], p: float64[:], out: float64[:]) -> None

which writes ``F(x; p)`` into ``out`` without allocating. ``p`` is ordered as
:attr:`SystemDef.param_names`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

RhsFunc = Callable[[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]], None]
"""Type of a system right-hand side; in practice a numba dispatcher."""


@dataclass(frozen=True)
class SystemDef:
    """Static description of one dynamical system.

    Parameters
    ----------
    name
        Registry key, lowercase ASCII (e.g. ``"rossler"``).
    display_name
        Human-readable name (e.g. ``"Rössler"``).
    variables
        Names of the state variables, in state-vector order.
    param_names
        Names of the parameters, in the order the RHS reads them from ``p``.
    default_params
        Default parameter values (from dysts), same order as ``param_names``.
    initial_condition
        A point on (or very near) the attractor at the default parameters (from dysts).
    modulated_param
        Name of the one parameter users can move in v1 (spec §7).
    candidate_range
        Wide interval ``(lo, hi)`` of the modulated parameter that the lab sweeps when
        searching for the chaotic range. Not used by the engine.
    rhs
        The numba-compiled right-hand side (see module docstring).
    dysts_name
        Class name of the same system in dysts, used by the tests and the catalog builder.
    phase_indices
        Indices of variables that are angles (wrapped modulo 2π, never heard).
    drive_frequency_param
        For forced systems, the parameter holding the angular drive frequency ω (in rad per
        unit of system time); the characteristic period is then exactly ``2π/ω``.
    equations_latex
        The equations in LaTeX (KaTeX-compatible), for documentation and the Learn-more page.
    """

    name: str
    display_name: str
    variables: tuple[str, ...]
    param_names: tuple[str, ...]
    default_params: tuple[float, ...]
    initial_condition: tuple[float, ...]
    modulated_param: str
    candidate_range: tuple[float, float]
    rhs: Any  # numba dispatcher implementing RhsFunc
    dysts_name: str
    phase_indices: tuple[int, ...] = ()
    drive_frequency_param: str | None = None
    equations_latex: str = ""
    notes: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if len(self.param_names) != len(self.default_params):
            raise ValueError(f"{self.name}: param_names and default_params differ in length")
        if len(self.variables) != len(self.initial_condition):
            raise ValueError(f"{self.name}: variables and initial_condition differ in length")
        if self.modulated_param not in self.param_names:
            raise ValueError(f"{self.name}: unknown modulated_param {self.modulated_param!r}")
        lo, hi = self.candidate_range
        if not lo < self.default_value < hi:
            raise ValueError(f"{self.name}: default value must lie inside candidate_range")

    @property
    def dim(self) -> int:
        """Number of state variables."""
        return len(self.variables)

    @property
    def modulated_index(self) -> int:
        """Index of the modulated parameter in the parameter vector."""
        return self.param_names.index(self.modulated_param)

    @property
    def default_value(self) -> float:
        """Default value of the modulated parameter."""
        return self.default_params[self.param_names.index(self.modulated_param)]

    @property
    def audio_variables(self) -> tuple[str, ...]:
        """Variables that can be heard (all except phase variables)."""
        return tuple(v for i, v in enumerate(self.variables) if i not in self.phase_indices)

    def variable_index(self, name: str) -> int:
        """Index of a state variable by name."""
        try:
            return self.variables.index(name)
        except ValueError:
            raise KeyError(f"{self.name} has no variable {name!r}") from None

    def params_array(self, **overrides: float) -> NDArray[np.float64]:
        """Parameter vector with optional overrides by name.

        Examples
        --------
        >>> from chaotic_sound.systems import get_system
        >>> get_system("lorenz").params_array(rho=35.0)
        array([10.   , 35.   ,  2.667])
        """
        values = dict(zip(self.param_names, self.default_params, strict=True))
        for key, value in overrides.items():
            if key not in values:
                raise KeyError(f"{self.name} has no parameter {key!r}")
            values[key] = float(value)
        return np.array([values[k] for k in self.param_names], dtype=np.float64)

    def initial_state(self) -> NDArray[np.float64]:
        """Return the initial condition as a fresh float64 array."""
        return np.array(self.initial_condition, dtype=np.float64)

    def wrap_mask(self) -> NDArray[np.bool_]:
        """Boolean mask of phase variables, for the integration kernels."""
        mask = np.zeros(self.dim, dtype=np.bool_)
        mask[list(self.phase_indices)] = True
        return mask

    def drive_period(self, params: NDArray[np.float64] | None = None) -> float | None:
        """Exact period ``2π/ω`` of the drive for forced systems, else ``None``."""
        if self.drive_frequency_param is None:
            return None
        p = self.params_array() if params is None else params
        omega = float(p[self.param_names.index(self.drive_frequency_param)])
        return 2.0 * np.pi / omega
