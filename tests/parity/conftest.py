"""Registers the ``parity`` marker, so ``pytest -m parity`` runs the harness alone."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "parity: the M16 parity harness (tests/parity/README.md)")
