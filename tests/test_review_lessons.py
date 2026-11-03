"""``constraints/review-lessons.md``: init header, ``lessons add|list``, reviewer prompt section (M11.78)."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import lessons_cli, role_prompt
from specy_road.init_project import run_init_project
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_lessons import LESSONS_REL, read_lessons
from tests.review_repo_helpers import make_review_repo
from tests.test_models_and_prompt import ROSTER

HEADING = "## Project review lessons"


def _run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        lessons_cli.main(argv)
    return int(exc.value.code or 0)


def _add(root: Path, *extra: str) -> int:
    return _run(["lessons", "add", "--repo-root", str(root), *extra])


def _reviewer_prompt(repo: Path) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n", encoding="utf-8")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="human")
    assert err is None, err
    return text


def test_init_project_writes_an_empty_lessons_file_with_a_header(tmp_path: Path) -> None:
    assert run_init_project(tmp_path) == 0
    path = tmp_path / LESSONS_REL
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Review lessons") and "specy-road lessons add" in text and "## Lessons" in text
    assert read_lessons(path) == []


def test_add_appends_entries_and_list_prints_them(tmp_path: Path, capsys) -> None:
    assert run_init_project(tmp_path) == 0
    assert _add(tmp_path, "--rule", "A new CLI flag needs a test\nthat passes it",
                "--example", "--force shipped untested", "--from", "M11.3") == 0
    assert _add(tmp_path, "--rule", "Paths in a worktree resolve from the git root") == 0
    assert read_lessons(tmp_path / LESSONS_REL) == [
        {"rule": "A new CLI flag needs a test that passes it", "example": "--force shipped untested",
         "from": "M11.3"},
        {"rule": "Paths in a worktree resolve from the git root"},
    ]
    capsys.readouterr()
    assert _run(["lessons", "list", "--repo-root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "- A new CLI flag needs a test that passes it\n"
        "  - Example: --force shipped untested\n"
        "  - From: M11.3\n"
        "- Paths in a worktree resolve from the git root\n"
    )


def test_missing_file_lists_nothing_and_add_creates_it(tmp_path: Path, capsys) -> None:
    assert _run(["lessons", "list", "--repo-root", str(tmp_path)]) == 0
    assert "does not exist" in capsys.readouterr().out
    assert _add(tmp_path, "--rule", "Never drop a docstring to fit a line cap") == 0
    text = (tmp_path / LESSONS_REL).read_text(encoding="utf-8")
    assert text.startswith("# Review lessons")
    assert read_lessons(tmp_path / LESSONS_REL) == [{"rule": "Never drop a docstring to fit a line cap"}]


def test_add_lands_in_the_lessons_section_when_another_section_follows(tmp_path: Path) -> None:
    path = tmp_path / LESSONS_REL
    path.parent.mkdir(parents=True)
    path.write_text("# Review lessons\n\n## Lessons\n\n- first\n\n## Retired\n\n- old rule\n", encoding="utf-8")
    assert _add(tmp_path, "--rule", "second") == 0
    assert path.read_text(encoding="utf-8") == (
        "# Review lessons\n\n## Lessons\n\n- first\n- second\n\n## Retired\n\n- old rule\n"
    )


def test_add_refuses_a_from_that_is_not_a_node_id(tmp_path: Path, capsys) -> None:
    assert _add(tmp_path, "--rule", "r", "--from", "M1 and M2") == 1
    assert "--from must be a node id" in capsys.readouterr().err
    assert not (tmp_path / LESSONS_REL).exists()


def test_reviewer_prompt_carries_every_lesson(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    assert HEADING not in _reviewer_prompt(repo)
    assert _add(repo, "--rule", "A retry must not repeat a side effect", "--from", "M11.9") == 0
    assert _add(repo, "--rule", "A reviewer prompt names its commit") == 0
    text = _reviewer_prompt(repo)
    section = text[text.index(HEADING):text.index("\n---\n", text.index(HEADING))]
    assert "- A retry must not repeat a side effect\n  - From: M11.9\n" in section
    assert "- A reviewer prompt names its commit\n" in section
