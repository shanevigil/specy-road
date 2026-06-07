"""Tests for yamllint-clean registry serialization (``specy_road.registry_yaml``)."""

from __future__ import annotations

import re

import yaml

from specy_road.registry_yaml import dump_registry_text, write_registry


def _sample_doc() -> dict:
    return {
        "version": 1,
        "entries": [
            {
                "codename": "vault-mcp-secrets",
                "node_id": "M10.2",
                "branch": "feature/rm-vault-mcp-secrets",
                "touch_zones": ["src/vault/", "docs/"],
                "started": "2026-06-07",
            },
            {
                "codename": "entry-api",
                "node_id": "M3.1",
                "branch": "feature/rm-entry-api",
                "touch_zones": [],
                "started": "2026-06-07",
                "implementation_review": "pending",
            },
        ],
    }


def test_round_trips_to_same_doc() -> None:
    doc = _sample_doc()
    text = dump_registry_text(doc)
    assert yaml.safe_load(text) == doc


def test_block_sequences_are_indented() -> None:
    """yamllint default ``indent-sequences: true`` requires the ``-`` to be indented."""
    text = dump_registry_text(_sample_doc())
    lines = text.splitlines()
    # The top-level ``entries:`` key exists, and no sequence item dash sits at
    # column 0 (which is what plain yaml.dump produces and yamllint rejects).
    assert "entries:" in text
    for line in lines:
        if line.startswith("- "):
            raise AssertionError(
                f"found indentless block sequence item (yamllint-unsafe): {line!r}"
            )
    # Entry items are indented two spaces under ``entries:``.
    assert any(line.startswith("  - ") for line in lines)
    # Nested touch_zones sequence is indented deeper than its mapping key.
    assert any(re.match(r"^\s{4,}- ", line) for line in lines)


def test_empty_entries_round_trip() -> None:
    doc = {"version": 1, "entries": []}
    text = dump_registry_text(doc)
    assert yaml.safe_load(text) == doc
    # ``entries: []`` flow-empty list is fine for yamllint (no block items).
    assert "entries: []" in text


def test_write_registry_writes_file(tmp_path) -> None:
    path = tmp_path / "registry.yaml"
    doc = _sample_doc()
    write_registry(path, doc)
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == doc
    # File ends with a trailing newline (yamllint new-line-at-end-of-file).
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_optional_yamllint_default_config_passes() -> None:
    """If yamllint is installed, the dumped registry must pass its default config."""
    yamllint_config = __import__("importlib").util.find_spec("yamllint")
    if yamllint_config is None:
        return
    from yamllint import linter
    from yamllint.config import YamlLintConfig

    conf = YamlLintConfig("extends: default")
    text = dump_registry_text(_sample_doc())
    problems = [
        p
        for p in linter.run(text, conf)
        if p.rule == "indentation" or p.level == "error"
    ]
    assert not problems, f"yamllint problems: {[str(p) for p in problems]}"
