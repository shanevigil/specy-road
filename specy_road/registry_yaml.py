"""Reading and yamllint-clean writing of ``roadmap/registry.yaml``.

Default ``yaml.dump`` emits block sequences *indentless* (the ``-`` sits at the
parent key's column), which violates yamllint's default
``indentation: {indent-sequences: true}`` rule and breaks unattended task pickup
on repos that run yamllint as a pre-commit hook.

``_IndentedDumper`` forces sequence indentation so the registry written by
``do-next-available-task`` / ``finish-this-task`` / ``abort-task-pickup`` passes
the default yamllint config out of the box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _IndentedDumper(yaml.Dumper):
    """Dumper that indents block sequences under mapping keys (yamllint-safe)."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):  # noqa: ANN201
        # Never emit indentless block sequences; yamllint's default
        # ``indent-sequences: true`` expects the ``-`` to be indented.
        return super().increase_indent(flow, False)


#: The registry's location, relative to the project root.
REGISTRY_REL = Path("roadmap") / "registry.yaml"


def registry_path(root: Path) -> Path:
    """``roadmap/registry.yaml`` under ``root``."""
    return root / REGISTRY_REL


def read_registry(path: Path, *, missing_ok: bool = True) -> dict[str, Any]:
    """Parse a registry document, defaulting an absent or empty file to empty.

    This module owned the write side but not the read side, so eight callers
    hand-rolled the parse and drifted: half treated a missing registry as empty
    and half raised ``FileNotFoundError`` at the user. Empty is the useful
    answer -- a repo with no claims yet is not an error -- and callers that
    genuinely require the file pass ``missing_ok=False``.
    """
    if not path.is_file():
        if not missing_ok:
            raise FileNotFoundError(path)
        return {"version": 1, "entries": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def dump_registry_text(doc: dict[str, Any]) -> str:
    """Serialize a registry document to yamllint-clean YAML text."""
    return yaml.dump(
        doc,
        Dumper=_IndentedDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def write_registry(path: Path, doc: dict[str, Any]) -> None:
    """Write ``doc`` to ``path`` (``roadmap/registry.yaml``) as yamllint-clean YAML."""
    path.write_text(dump_registry_text(doc), encoding="utf-8")
