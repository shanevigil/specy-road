"""``constraints/review-lessons.md``: init header, ``decisions add|list --kind lesson``, reviewer prompt section (M11.78)."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import decisions_cli, role_prompt
from specy_road.init_project import run_init_project
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_lessons import LESSONS_REL, read_lessons
from tests.review_repo_helpers import make_review_repo
from tests.test_models_and_prompt import ROSTER

HEADING = "## Project review lessons"


def _run(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc:
        decisions_cli.main(argv)
    return int(exc.value.code or 0)


def _add(root: Path, rule: str, *extra: str, node: str | None = None) -> int:
    return _run(["decisions", "add", *([node] if node else []), "--kind", "lesson", "--summary", rule,
                 "--repo-root", str(root), *extra])


def _list(root: Path) -> int:
    return _run(["decisions", "list", "--kind", "lesson", "--repo-root", str(root)])


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
    assert text.startswith("# Review lessons") and "## Lessons" in text
    assert "specy-road decisions add [<NODE_ID>] --kind lesson" in text
    assert read_lessons(path) == []


def test_add_appends_entries_and_list_prints_them(tmp_path: Path, capsys) -> None:
    assert run_init_project(tmp_path) == 0
    assert _add(tmp_path, "A new CLI flag needs a test\nthat passes it",
                "--example", "--force shipped untested", node="M11.3") == 0
    assert _add(tmp_path, "Paths in a worktree resolve from the git root") == 0
    assert read_lessons(tmp_path / LESSONS_REL) == [
        {"rule": "A new CLI flag needs a test that passes it", "example": "--force shipped untested",
         "from": "M11.3"},
        {"rule": "Paths in a worktree resolve from the git root"},
    ]
    capsys.readouterr()
    assert _list(tmp_path) == 0
    assert capsys.readouterr().out == (
        "- A new CLI flag needs a test that passes it\n"
        "  - Example: --force shipped untested\n"
        "  - From: M11.3\n"
        "- Paths in a worktree resolve from the git root\n"
    )


def test_missing_file_lists_nothing_and_add_creates_it(tmp_path: Path, capsys) -> None:
    assert _list(tmp_path) == 0
    assert "does not exist" in capsys.readouterr().out
    assert _add(tmp_path, "Never drop a docstring to fit a line cap") == 0
    text = (tmp_path / LESSONS_REL).read_text(encoding="utf-8")
    assert text.startswith("# Review lessons")
    assert read_lessons(tmp_path / LESSONS_REL) == [{"rule": "Never drop a docstring to fit a line cap"}]


def test_add_lands_in_the_lessons_section_when_another_section_follows(tmp_path: Path) -> None:
    path = tmp_path / LESSONS_REL
    path.parent.mkdir(parents=True)
    path.write_text("# Review lessons\n\n## Lessons\n\n- first\n\n## Retired\n\n- old rule\n", encoding="utf-8")
    assert _add(tmp_path, "second") == 0
    assert path.read_text(encoding="utf-8") == (
        "# Review lessons\n\n## Lessons\n\n- first\n- second\n\n## Retired\n\n- old rule\n"
    )


def test_add_refuses_a_from_that_is_not_a_node_id(tmp_path: Path, capsys) -> None:
    assert _add(tmp_path, "r", node="M1 and M2") == 1
    assert "--from must be a node id" in capsys.readouterr().err
    assert not (tmp_path / LESSONS_REL).exists()


@pytest.mark.parametrize(("argv", "error"), [
    (["add", "--kind", "lesson", "--summary", "r", "--option", "a|b", "--local"],
     "--kind lesson does not take --option, --local"),
    (["add", "M1.1", "--kind", "decision", "--summary", "s", "--example", "e"],
     "--example applies only to --kind lesson"),
    (["list", "--kind", "lesson", "--json"], "--kind lesson has no --json output"),
])
def test_lesson_flags_are_refused_where_they_do_not_apply(
    tmp_path: Path, capsys, argv: list[str], error: str
) -> None:
    assert _run(["decisions", *argv, "--repo-root", str(tmp_path)]) == 1
    assert capsys.readouterr().err == f"error: {error}\n"
    assert not (tmp_path / LESSONS_REL).exists()


def test_reviewer_prompt_carries_every_lesson(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    assert HEADING not in _reviewer_prompt(repo)
    assert _add(repo, "A retry must not repeat a side effect", node="M11.9") == 0
    assert _add(repo, "A reviewer prompt names its commit") == 0
    text = _reviewer_prompt(repo)
    section = text[text.index(HEADING):text.index("\n---\n", text.index(HEADING))]
    assert "- A retry must not repeat a side effect\n  - From: M11.9\n" in section
    assert "- A reviewer prompt names its commit\n" in section
