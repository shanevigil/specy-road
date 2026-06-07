"""yamllint-clean serialization for ``roadmap/registry.yaml``.

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
