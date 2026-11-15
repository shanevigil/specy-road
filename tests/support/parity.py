"""Shared parity-table helpers."""

from __future__ import annotations

from pathlib import Path


def golden_file(golden: Path, row) -> Path:
    """Where ``row``'s recorded output lives."""
    return golden / f"{row.name}.txt"
