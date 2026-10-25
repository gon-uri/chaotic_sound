"""Shared fixtures. Block and patch tests use the committed catalog (catalog/systems.json)."""

import pytest

from chaotic_sound.catalog import Catalog, load_default_catalog

FS = 48_000


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return load_default_catalog()
