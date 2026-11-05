"""Shared fixtures for file-limits baseline tests (M15.7)."""

from __future__ import annotations

from pathlib import Path

import yaml


def write_layout(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def cfg_yaml(**extra: object) -> str:
    base = {
        "max_lines_per_file": 10,
        "max_lines_per_function": 5,
        "applies_to_globs": ["**/*.py"],
    }
    base.update(extra)
    return yaml.safe_dump(base, sort_keys=False)


def policy_prefix() -> str:
    return 'max_lines_per_file: 2\napplies_to_globs:\n  - "**/*.py"\n'


def assert_only_inserted(before: str, after: str) -> None:
    prefix = 0
    while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < len(before) - prefix
        and suffix < len(after) - prefix
        and before[len(before) - 1 - suffix] == after[len(after) - 1 - suffix]
    ):
        suffix += 1
    assert before[:prefix] == after[:prefix]
    assert before[len(before) - suffix :] == after[len(after) - suffix :]
    assert len(after) > len(before)
