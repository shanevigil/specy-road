"""Read/write ``roadmap/archive/index.json`` — the ledger of archived subtrees.

The index is the only durable record that an archived subtree ever existed. It
carries every archived ``node_key`` so
:func:`validate_roadmap_checks.validate_dependency_ids` can treat a live node's
dependency on archived work as satisfied instead of dangling, which is what lets
live nodes keep their ``dependencies`` untouched and makes restore lossless.

It validates against the schema **bundled in this package**, not against
``<repo_root>/schemas/``. Consumer-owned schemas use
``additionalProperties: false``, so a toolkit that added fields to a
consumer-owned schema would break every adopter's ``validate`` until they
hand-edited a JSON file. Keeping this one in the wheel means adopters pick up
new archive fields by upgrading the package.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jsonschema import Draft202012Validator

from specy_road.roadmap_json import render_canonical_json
from specy_road.runtime_paths import specy_road_package_dir

INDEX_VERSION = 1
ARCHIVE_DIRNAME = "archive"
INDEX_FILENAME = "index.json"


def archive_dir(root: Path) -> Path:
    return (root / "roadmap" / ARCHIVE_DIRNAME).resolve()


def archive_index_path(root: Path) -> Path:
    return archive_dir(root) / INDEX_FILENAME


def archive_chunks_dir(root: Path) -> Path:
    return archive_dir(root) / "chunks"


def archive_deep_dir(root: Path) -> Path:
    return archive_dir(root) / "deep"


def archive_refs_dir(root: Path) -> Path:
    return archive_dir(root) / "refs"


def archive_planning_dir(root: Path, archive_id: str) -> Path:
    """Where an archive's planning sheets are parked.

    Deliberately **not** ``planning/archive/``: ``validate`` rejects any
    subdirectory or nested ``.md`` under ``planning/`` (flat-only rule in
    ``planning_artifacts._append_orphan_planning_files``), so parking sheets
    there would break every subsequent validate. Keeping them under
    ``roadmap/archive/`` also makes the deep-archive bundle a single subtree.
    """
    return archive_dir(root) / "planning" / archive_id


def empty_index() -> dict[str, Any]:
    return {"version": INDEX_VERSION, "records": []}


def bundled_archive_schema_path() -> Path:
    return specy_road_package_dir() / "schemas" / "archive.schema.json"


def bundled_archive_schema() -> dict[str, Any]:
    path = bundled_archive_schema_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"missing bundled archive schema at {path} (broken install). "
            "Reinstall specy-road."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@cache
def _archive_validator() -> "Draft202012Validator":
    """The compiled archive-index validator.

    Cached because it was rebuilt -- schema read from the wheel, parsed,
    validator compiled -- on every load *and* every write of the index, which
    ``specy-road archive`` does four times in one run.
    """
    from jsonschema import Draft202012Validator

    return Draft202012Validator(bundled_archive_schema())


def validate_archive_index(doc: dict[str, Any]) -> None:
    """Schema-validate an in-memory index; raise ``ValueError`` on the first error."""
    validator = _archive_validator()
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if not errors:
        return
    first = errors[0]
    loc = "/".join(str(p) for p in first.path) or "."
    raise ValueError(f"archive index invalid at {loc}: {first.message}")


def load_archive_index(root: Path) -> dict[str, Any]:
    """Load the index, or an empty one when the repo has never archived anything.

    A malformed index raises rather than being silently replaced: it is the
    dependency ledger, and quietly starting over would turn every live
    dependency on archived work into a validation failure.
    """
    path = archive_index_path(root)
    if not path.is_file():
        return empty_index()
    try:
        with path.open(encoding="utf-8") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: not valid JSON ({e})") from e
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: must be a JSON object")
    validate_archive_index(doc)
    return doc


def render_archive_index(doc: dict[str, Any]) -> str:
    """Canonical index text."""
    return render_canonical_json(doc)


def records_or_empty(root: Path) -> list[dict[str, Any]]:
    """Ledger records, or ``[]`` if the ledger is missing or unreadable.

    :func:`load_archive_index` raises, which is right for ``validate`` and wrong
    for everyone else: a digest, a brief, a search index and a history walk all
    have to render without the ledger rather than fail. Four callers wrapped it
    in the same ``try/except Exception`` to say so; this says it once.
    """
    try:
        return index_records(load_archive_index(root))
    except Exception:  # noqa: BLE001 - a broken ledger is validate's to report
        return []


def iter_archived_summaries(root: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """``(record, node summary)`` for every archived node, best-effort.

    The nested walk into ``nodes_summary`` was written out at four call sites,
    each projecting it differently -- by key, by id, as pairs. The traversal is
    shared here; the projection stays with the caller that needs it.
    """
    return [
        (record, summary)
        for record in records_or_empty(root)
        for summary in record.get("nodes_summary") or []
        if isinstance(summary, dict)
    ]


def write_archive_index(root: Path, doc: dict[str, Any]) -> Path:
    """Validate then write the index, creating ``roadmap/archive/`` if needed."""
    validate_archive_index(doc)
    path = archive_index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_archive_index(doc), encoding="utf-8")
    return path


def index_records(doc: dict[str, Any]) -> list[dict[str, Any]]:
    recs = doc.get("records")
    return [r for r in recs if isinstance(r, dict)] if isinstance(recs, list) else []


def find_record(doc: dict[str, Any], archive_id: str) -> dict[str, Any] | None:
    for rec in index_records(doc):
        if rec.get("archive_id") == archive_id:
            return rec
    return None


def archived_node_keys(root: Path) -> set[str]:
    """Every ``node_key`` currently held in the archive, at any depth.

    Returns the empty set when no index exists. A *malformed* index still
    raises — see :func:`load_archive_index`.
    """
    out: set[str] = set()
    for rec in index_records(load_archive_index(root)):
        keys = rec.get("node_keys")
        if isinstance(keys, list):
            out.update(k for k in keys if isinstance(k, str))
    return out


def node_summary(node: dict[str, Any]) -> dict[str, Any]:
    """The identity fields the GUI needs without unpacking a deep bundle."""
    out: dict[str, Any] = {
        "id": node.get("id"),
        "node_key": node.get("node_key"),
        "title": node.get("title") or "",
        "type": node.get("type"),
    }
    status = node.get("status")
    if isinstance(status, str) and status:
        out["status"] = status
    return out
