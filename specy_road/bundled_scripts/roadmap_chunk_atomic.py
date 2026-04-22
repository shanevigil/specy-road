"""Atomic write planner for roadmap chunk + manifest mutations.

All on-disk roadmap mutations from the chunk router go through
:class:`AtomicWritePlan`. Original bytes for every affected path are
captured before we write any bytes, so a validation failure restores the
working tree to byte-for-byte its prior state. Net-new files are unlinked
on rollback.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from roadmap_chunk_utils import (
    discover_manifest_path,
    render_json_chunk,
    render_manifest,
)


@dataclass
class AtomicWritePlan:
    """Stage chunk + manifest writes; commit (validate) or rollback to original on disk."""

    root: Path
    pending: dict[Path, str] = field(default_factory=dict)  # abs_path -> new text
    snapshots: dict[Path, bytes | None] = field(default_factory=dict)
    new_paths: set[Path] = field(default_factory=set)
    _staged: bool = False

    def stage_chunk(self, abs_path: Path, nodes: list[dict]) -> None:
        """Stage a chunk write (renders canonical JSON, no disk IO yet)."""
        self.pending[abs_path] = render_json_chunk(nodes)

    def stage_manifest(self, doc: dict) -> None:
        """Stage a manifest write at the discovered manifest path."""
        manifest_abs = discover_manifest_path(self.root)
        self.pending[manifest_abs] = render_manifest(doc)

    def _snapshot(self) -> None:
        for path in self.pending:
            if path in self.snapshots:
                continue
            if path.is_file():
                self.snapshots[path] = path.read_bytes()
            else:
                self.snapshots[path] = None
                self.new_paths.add(path)

    def write(self) -> None:
        """Write all pending payloads atomically (per-file ``os.replace``)."""
        self._snapshot()
        for path, text in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        self._staged = True

    def rollback(self) -> None:
        """Restore every snapshotted file to its original bytes (or unlink if new)."""
        if not self._staged:
            return
        for path, original in self.snapshots.items():
            try:
                if original is None:
                    if path.is_file():
                        path.unlink()
                else:
                    path.write_bytes(original)
            except OSError:
                # Best-effort restore; keep going so other files revert.
                pass
        self._staged = False

    def commit(self, validate: Callable[[], None]) -> None:
        """Write, then run ``validate``; rollback and re-raise on any failure."""
        self.write()
        try:
            validate()
        except BaseException:
            self.rollback()
            raise
