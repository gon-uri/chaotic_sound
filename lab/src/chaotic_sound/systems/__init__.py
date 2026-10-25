"""Registry of the dynamical systems available to the engine.

Add a new system by writing a module like :mod:`chaotic_sound.systems.lorenz` and listing it
in ``_ALL`` below (see the project skill ``add-dynamical-system``).
"""

from chaotic_sound.systems.base import SystemDef
from chaotic_sound.systems.chua import CHUA
from chaotic_sound.systems.duffing import DUFFING
from chaotic_sound.systems.lorenz import LORENZ
from chaotic_sound.systems.rossler import ROSSLER
from chaotic_sound.systems.thomas import THOMAS

_ALL: tuple[SystemDef, ...] = (LORENZ, ROSSLER, CHUA, THOMAS, DUFFING)
SYSTEMS: dict[str, SystemDef] = {s.name: s for s in _ALL}


def get_system(name: str) -> SystemDef:
    """Return the system registered under ``name`` (e.g. ``"lorenz"``)."""
    try:
        return SYSTEMS[name]
    except KeyError:
        raise KeyError(f"unknown system {name!r}; available: {sorted(SYSTEMS)}") from None


def list_systems() -> list[str]:
    """Names of all registered systems, in display order."""
    return [s.name for s in _ALL]


__all__ = ["SYSTEMS", "SystemDef", "get_system", "list_systems"]
