"""`edit-node --add` / `--remove` change one list entry without restating the list (M11.10).

Widening a zone used to mean reading the whole list with show-node and passing
every entry back to --set. The claim row follows, as it does for --set (M10.14).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path

NK = "11111111-1111-5111-8111-111111111111"


def _crud(repo: Path, *argv: str) -> None:
    ns = build_parser().parse_args(["--repo-root", str(repo), *argv])
    ns.func(ns)


def _node(repo: Path, nid: str = "M1.1") -> dict:
    return next(n for n in load_roadmap(repo)["nodes"] if n["id"] == nid)


def _claim_zones(repo: Path) -> list[str]:
    return read_registry(registry_path(repo))["entries"][0]["touch_zones"]


def test_add_and_remove_a_zone_keep_the_rest_and_the_claim_follows(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "edit-node", "M1.1", "--add", "touch_zones=docs")
    assert _node(repo)["touch_zones"] == ["src", "docs"]
    assert _claim_zones(repo) == ["src", "docs"]
    _crud(repo, "edit-node", "M1.1", "--remove", "touch_zones=src")
    assert _node(repo)["touch_zones"] == ["docs"]
    assert _claim_zones(repo) == ["docs"]
    assert "touch_zones now match M1.1" in capsys.readouterr().err


def test_acceptance_entries_add_and_remove(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "edit-node", "M1.1", "--add", "acceptance=Works, offline too", "--remove", "acceptance=a.py exists")
    assert _node(repo)["acceptance"] == ["nothing else breaks", "Works, offline too"]


def test_dependencies_take_an_id_or_a_key(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "add-node", "--id", "M1.2", "--type", "task", "--title", "Other", "--parent-id", "null")
    _crud(repo, "edit-node", "M1.2", "--add", "dependencies=M1.1")
    assert _node(repo, "M1.2")["dependencies"] == [NK]
    _crud(repo, "edit-node", "M1.2", "--remove", f"dependencies={NK}")
    assert _node(repo, "M1.2")["dependencies"] == []


def test_duplicate_add_leaves_the_list_and_writes_nothing(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    before = chunk.read_bytes(), registry_path(repo).read_bytes()
    _crud(repo, "edit-node", "M1.1", "--add", "touch_zones=src")
    assert (chunk.read_bytes(), registry_path(repo).read_bytes()) == before
    out = capsys.readouterr()
    assert "[note] M1.1 already lists touch_zones entry 'src'; left as is" in out.err
    assert "[ok] M1.1 unchanged" in out.out


def test_removing_a_missing_entry_leaves_the_list(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "edit-node", "M1.1", "--remove", "touch_zones=lib", "--add", "touch_zones=docs")
    assert _node(repo)["touch_zones"] == ["src", "docs"]
    assert "[note] M1.1 does not list touch_zones entry 'lib'; left as is" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--add", "title=New"], "--add takes LIST_FIELD=ENTRY"),
        (["--remove", "touch_zones="], "--remove takes LIST_FIELD=ENTRY"),
        (["--set", "touch_zones=a", "--add", "touch_zones=b"], "use one or the other"),
        ([], "at least one --set, --add or --remove"),
    ],
)
def test_bad_list_edits_are_refused_before_writing(tmp_path: Path, capsys, argv, message) -> None:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    before = chunk.read_bytes()
    with pytest.raises(SystemExit):
        _crud(repo, "edit-node", "M1.1", *argv)
    assert chunk.read_bytes() == before
    assert message in capsys.readouterr().err
