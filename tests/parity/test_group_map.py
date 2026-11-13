"""Each old milestone, planning and archive-node invocation and its new form, on the same repo.

``milestone start|status|pr`` run what ``start-milestone-session``, ``reconcile-milestone-status``
and ``open-milestone-pr`` ran; ``planning scaffold|approach`` what ``scaffold-planning`` and
``author-approach`` ran; ``archive --hard-remove NODE_ID`` what ``archive-node NODE_ID
--hard-remove`` ran. Each side runs on its own repo built the same way: the same exit, stdout and
files (the repo's path, its parent and wall-clock times written as placeholders); the old form, a
deprecated alias, adds only its one deprecation line on stderr.

The canonical command count (registered top-level names minus the ones command_map.yaml retires)
is printed and held to its bound.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from specy_road import cli
from specy_road.bundled_scripts import scaffold_planning
from specy_road.milestone_session import milestone_session_path, write_milestone_session
from tests.milestone_repo_helpers import make_milestone_repo
from tests.move_node_helpers import base_fixture
from tests.parity.command_map import command_map_rows, retired_top_level_names
from tests.scenarios.milestone.repos import (
    INTEGRATION,
    PARENT,
    REMOTE,
    landed_milestone,
    milestone_repo,
)

pytestmark = pytest.mark.parity


def _session_repo(tmp: Path) -> Path:
    root = make_milestone_repo(tmp, land=False)
    write_milestone_session(
        milestone_session_path(root / "work"),
        parent_node_id=PARENT,
        parent_codename="milestone-two",
        integration_branch=INTEGRATION,
        remote=REMOTE,
    )
    return root


def _roadmap(tmp: Path) -> Path:
    root = tmp / "r"
    base_fixture(root)
    return root


def _scaffolded(tmp: Path) -> Path:
    root = _roadmap(tmp)
    scaffold_planning.main(["M2.1", "--force", "--repo-root", str(root)])
    return root


def _rollup(tmp: Path) -> Path:
    return milestone_repo(tmp, land=False)


def _unsessioned(tmp: Path) -> Path:
    return make_milestone_repo(tmp, land=False)


def _active(tmp: Path) -> Path:
    return landed_milestone(tmp, state="active")


def _closed(tmp: Path) -> Path:
    return landed_milestone(tmp, state="closed")


START = [PARENT, "--base", INTEGRATION, "--remote", REMOTE]

#: ``(old argv, new argv, the repo both run on)``; ``--repo-root`` is appended to both.
ROWS: list[tuple[list[str], list[str], Callable[[Path], Path]]] = [
    (["start-milestone-session", *START], ["milestone", "start", *START], _rollup),
    (["start-milestone-session", "M2.1"], ["milestone", "start", "M2.1"], _rollup),
    (["reconcile-milestone-status"], ["milestone", "status"], _active),
    (["reconcile-milestone-status", "--apply"], ["milestone", "status", "--apply"], _closed),
    (["open-milestone-pr"], ["milestone", "pr"], _session_repo),
    (["open-milestone-pr"], ["milestone", "pr"], _unsessioned),
    (["scaffold-planning", "M2.1", "--force"], ["planning", "scaffold", "M2.1", "--force"],
     _roadmap),
    (["scaffold-planning", "M2.1"], ["planning", "scaffold", "M2.1"], _roadmap),
    (["scaffold-planning", "M9"], ["planning", "scaffold", "M9"], _roadmap),
    (["author-approach", "M2.1"], ["planning", "approach", "M2.1"], _scaffolded),
    (["author-approach", "M2.1", "-o"], ["planning", "approach", "M2.1", "-o"], _scaffolded),
    (["author-approach", "M2"], ["planning", "approach", "M2"], _scaffolded),
    (["archive-node", "M2.1", "--hard-remove"], ["archive", "--hard-remove", "M2.1"], _roadmap),
    (["archive-node", "M2", "--hard-remove"], ["archive", "--hard-remove", "M2"], _roadmap),
]
NEW_NAME = {
    "start-milestone-session": "milestone start",
    "reconcile-milestone-status": "milestone status",
    "open-milestone-pr": "milestone pr",
    "scaffold-planning": "planning scaffold",
    "author-approach": "planning approach",
    "archive-node": "archive --hard-remove",
}


#: A wall-clock time a command writes (``opened_at`` on a milestone): the two sides run seconds
#: apart, so it is compared as a placeholder.
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


def _placeholders(text: str, root: Path, tmp: Path) -> str:
    """``text`` with the repo's path, its parent and every ISO-8601 time written as placeholders."""
    text = text.replace(str(root), "<ROOT>").replace(str(tmp), "<TMP>")
    return _TIMESTAMP.sub("<TIME>", text)


def _files(root: Path, tmp: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): _placeholders(p.read_text(encoding="utf-8"), root, tmp)
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }


def _cli(
    argv: list[str], tmp: Path, setup: Callable[[Path], Path], capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, list[str], dict[str, str]]:
    tmp.mkdir()
    root = setup(tmp)
    capsys.readouterr()
    code = cli.run([*argv, "--repo-root", str(root)])
    out, err = (_placeholders(t, root, tmp) for t in capsys.readouterr())
    return code, out, err.splitlines(), _files(root, tmp)


@pytest.mark.parametrize(
    ("old", "new", "setup"), ROWS, ids=[f"{' '.join(o)}-{i}" for i, (o, _n, _s) in enumerate(ROWS)]
)
def test_new_form_gives_the_old_files_and_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    old: list[str],
    new: list[str],
    setup: Callable[[Path], Path],
) -> None:
    """The new form's exit, stdout and files are the old one's; the old adds its deprecation."""
    old_code, old_out, old_err, old_files = _cli(old, tmp_path / "old", setup, capsys)
    new_code, new_out, new_err, new_files = _cli(new, tmp_path / "new", setup, capsys)
    assert (new_code, new_out, new_files) == (old_code, old_out, old_files)
    assert old_err[0] == (
        f"warning: `specy-road {old[0]}` is deprecated and is removed in the release after "
        f"0.3.1; use `specy-road {NEW_NAME[old[0]]}`."
    )
    assert new_err == old_err[1:]


USAGE_ERROR = 2


@pytest.mark.parametrize(
    "extra", [["M2.1", "--dry-run"], ["M2.1", "--force"], ["M2.1", "--deep"], ["--auto"], []]
)
def test_hard_remove_refuses_an_archive_option_or_a_missing_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    """``--hard-remove`` beside an archive option, or without a node, exits 2 and writes nothing."""
    root = _roadmap(tmp_path)
    before = _files(root, tmp_path)
    code = cli.run(["archive", "--hard-remove", *extra, "--repo-root", str(root)])
    assert code == USAGE_ERROR
    assert "error: --hard-remove takes one NODE_ID" in capsys.readouterr().err
    assert _files(root, tmp_path) == before


#: A3's retired names: M16.4.1-M16.4.4's fourteen, and ``update`` (renamed, net zero).
RETIRED = {
    "registry-prune", "branches", "refresh-stubs", "refresh-schemas", "refresh-profiles",
    "update", "handoff", "review-packet", "lessons", "start-milestone-session",
    "reconcile-milestone-status", "open-milestone-pr", "scaffold-planning", "author-approach",
    "archive-node",
}
NEW_GROUPS = {"milestone", "planning"}
#: A3's formula on the coordinator's recount (2026-11-07: the bound is the current count minus
#: this leaf's removals): the names registered before this leaf, not A3's planning-time 68.
REGISTERED_BEFORE_THIS_LEAF = 74
CANONICAL_BOUND = REGISTERED_BEFORE_THIS_LEAF + len(NEW_GROUPS) - len(RETIRED)


@pytest.mark.parametrize(
    ("row", "retired"),
    [
        ({"old": "specy-road a", "new": "specy-road b c"}, {"a"}),  # a top-level row
        ({"old": "specy-road a x", "new": "specy-road b"}, set()),  # a subcommand row
        ({"old": "specy-road a --j", "new": "specy-road b"}, set()),  # a flag row
        ({"old": "specy-road a", "new": "specy-road a x"}, set()),  # moved under itself
        ({"old": "", "new": "specy-road a"}, set()),  # an addition
    ],
)
def test_only_a_top_level_row_retires_a_name(row: dict, retired: set[str]) -> None:
    """A name counts as retired only when a row with no options moves it outside itself."""
    assert retired_top_level_names([row]) == retired


def test_canonical_command_count_is_at_most_its_bound() -> None:
    """The map retires A3's names; the canonical names, printed, fit A3's formula."""
    registered = cli.registered_agent_command_names()["specy-road"] - {"version"}
    retired = retired_top_level_names(command_map_rows())
    canonical = sorted(registered - retired)
    print(f"canonical commands ({len(canonical)}): {' '.join(canonical)}")
    assert retired == RETIRED
    assert NEW_GROUPS <= registered
    assert len(canonical) <= CANONICAL_BOUND, canonical
