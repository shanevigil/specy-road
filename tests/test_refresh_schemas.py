"""``refresh-schemas`` is the safe way to update a consumer's ``schemas/``.

Regression cover for the v0.1.4-rc2 report: ``init project`` copies the JSON
schemas once and never revisits them, so a repo scaffolded before ``type: gate``
or ``implementation_review`` existed rejected output the current CLI produces.
The only command that looked like a fix, ``init project --force``, overwrites
every template file — including the roadmap it was meant to repair.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts.refresh_schemas import (
    bundled_schemas_dir,
    refresh_schemas,
    stale_schema_names,
    warn_if_schemas_stale,
)
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    shutil.copytree(bundled_schemas_dir(), tmp_path / "schemas")
    return tmp_path


def _degrade_roadmap_schema(root: Path) -> None:
    """Drop ``gate`` from the node type enum, as a pre-gate scaffold would have."""
    path = root / "schemas" / "roadmap.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["type"]["enum"] = [
        "vision",
        "phase",
        "milestone",
        "task",
    ]
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def test_current_schemas_are_not_reported_as_stale(repo: Path) -> None:
    assert stale_schema_names(repo) == []


def test_structural_drift_is_reported(repo: Path) -> None:
    _degrade_roadmap_schema(repo)
    assert stale_schema_names(repo) == ["roadmap.schema.json"]


def test_description_only_edits_are_not_drift(repo: Path) -> None:
    """Prose differs between the dogfood fixture and the bundled schema by design."""
    path = repo / "schemas" / "roadmap.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["title"]["description"] = "Reworded."
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    assert stale_schema_names(repo) == []


def test_dogfood_fixture_schemas_are_current() -> None:
    """Guards the repo's own sample data against silently going stale."""
    assert stale_schema_names(DOGFOOD) == []


def test_a_schema_the_consumer_never_had_is_not_drift(repo: Path) -> None:
    (repo / "schemas" / "git-workflow.schema.json").unlink()
    assert stale_schema_names(repo) == []


def test_refresh_rewrites_only_the_stale_schema(repo: Path) -> None:
    _degrade_roadmap_schema(repo)
    assert refresh_schemas(repo) == ["schemas/roadmap.schema.json"]
    assert stale_schema_names(repo) == []
    bundled = (bundled_schemas_dir() / "roadmap.schema.json").read_text(
        encoding="utf-8"
    )
    assert (repo / "schemas" / "roadmap.schema.json").read_text(
        encoding="utf-8"
    ) == bundled


def test_refresh_touches_nothing_outside_schemas(repo: Path) -> None:
    (repo / "roadmap").mkdir()
    manifest = repo / "roadmap" / "manifest.json"
    manifest.write_text('{"version": 1, "includes": ["phases/M1.json"]}\n', encoding="utf-8")
    before = manifest.read_text(encoding="utf-8")
    _degrade_roadmap_schema(repo)
    refresh_schemas(repo)
    assert manifest.read_text(encoding="utf-8") == before


def test_dry_run_writes_nothing(repo: Path) -> None:
    _degrade_roadmap_schema(repo)
    degraded = (repo / "schemas" / "roadmap.schema.json").read_text(encoding="utf-8")
    assert refresh_schemas(repo, dry_run=True) == ["schemas/roadmap.schema.json"]
    assert (repo / "schemas" / "roadmap.schema.json").read_text(
        encoding="utf-8"
    ) == degraded


def test_warning_names_the_command_that_fixes_it(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _degrade_roadmap_schema(repo)
    warn_if_schemas_stale(repo)
    err = capsys.readouterr().err
    assert "roadmap.schema.json" in err
    assert "specy-road refresh-schemas" in err
