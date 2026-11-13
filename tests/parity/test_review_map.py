"""Each old review command and its new form, run on the same leaf (M16.4.3).

``review status`` prints every line ``handoff status`` and ``review list`` printed, with handoff's exit.

One row per old invocation (``handoff status`` with no node, one node, ``--json`` and ``--ref``; ``review list``
with one node, ``--json`` and ``--ref``), run against each review state of one leaf: waiting, a READY in review,
approved, blocked, stale after a later commit, and records with no claim. The old command, a deprecated alias,
prints its one deprecation line on stderr; ``review status`` with the same words after the command exits as
``handoff status`` does and prints every stdout line the old one printed (compared without leading and trailing
blanks: ``review list`` prints a line ``handoff status`` already printed indented, and ``review status`` keeps
it once). With ``--json`` the handoff payload is kept key for key and ``review list``'s is its ``records``.

``review-packet`` and ``review packet``, and ``lessons add|list`` and ``decisions add|list --kind lesson``, each
run on their own copy of a leaf: the same exit, stdout and files (``PACKET.md``, ``constraints/review-lessons.md``);
the old form adds only its deprecation line on stderr.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from specy_road import cli
from specy_road.bundled_scripts import review_cli
from specy_road.review_files import reviews_dir
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text

pytestmark = pytest.mark.parity

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""
NODE = "M1.1"
BRANCH = "feature/rm-thing"


def _ready(repo: Path) -> None:
    d = reviews_dir(repo, NODE)
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-composer.md").write_text(
        f"---\nnode_id: {NODE}\nagent: composer\nbranch: {BRANCH}\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n")


def _record(repo: Path, verdict: str) -> None:
    notes = repo.parent / "notes-opus.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict=verdict,
                                 a1="pass" if verdict == "approve" else "fail"))
    assert _run(["review", "record", NODE, "--model", "opus", "--verdict", verdict, "--file", str(notes),
                 "--repo-root", str(repo)])[0] == 0


def _waiting(repo: Path) -> None:
    reviews_dir(repo, NODE).mkdir(parents=True)


def _in_review(repo: Path) -> None:
    _ready(repo)


def _approved(repo: Path) -> None:
    _ready(repo)
    _record(repo, "approve")


def _blocked(repo: Path) -> None:
    _ready(repo)
    _record(repo, "block")


def _stale(repo: Path) -> None:
    _approved(repo)
    commit_file(repo, "src/b.py", "x\n", "fix")


def _unclaimed(repo: Path) -> None:
    _approved(repo)
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")


STATES: dict[str, Callable[[Path], None]] = {
    "waiting": _waiting, "in-review": _in_review, "approved": _approved, "blocked": _blocked,
    "stale": _stale, "unclaimed": _unclaimed,
}

#: ``(old command, words after it)``; ``review status`` runs with the same words.
ROWS = [
    (["handoff", "status"], []),
    (["handoff", "status"], [NODE]),
    (["handoff", "status"], [NODE, "--json"]),
    (["handoff", "status"], [NODE, "--ref", BRANCH]),
    (["review", "list"], [NODE]),
    (["review", "list"], [NODE, "--json"]),
    (["review", "list"], [NODE, "--ref", BRANCH]),
]


def _run(argv: list[str], capsys: pytest.CaptureFixture[str] | None = None) -> tuple[int, str, str]:
    if capsys:
        capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        review_cli.main(argv)
    out, err = capsys.readouterr() if capsys else ("", "")
    return e.value.code, out, err


@pytest.fixture(params=sorted(STATES))
def state_repo(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    STATES[request.param](repo)
    return repo


@pytest.mark.parametrize(("old", "tail"), ROWS, ids=[" ".join(o + t).replace(NODE, "N") for o, t in ROWS])
def test_review_status_keeps_every_old_line_and_handoff_exit(
    state_repo: Path, capsys: pytest.CaptureFixture[str], old: list[str], tail: list[str]
) -> None:
    words = [*tail, "--repo-root", str(state_repo)]
    _old_code, old_out, old_err = _run([*old, *words], capsys)
    handoff_code = _run(["handoff", "status", *words], capsys)[0]
    new_code, new_out, new_err = _run(["review", "status", *words], capsys)
    assert old_err.splitlines()[0] == (f"warning: `specy-road {' '.join(old)}` is deprecated and is removed in "
                                       "the release after 0.3.1; use `specy-road review status`.")
    assert "deprecated" not in new_err
    assert new_code == handoff_code
    if "--json" not in tail:
        new_lines = {line.strip() for line in new_out.splitlines()}
        assert [line for line in old_out.splitlines() if line.strip() not in new_lines] == []
    elif old[0] == "handoff":
        new_payload = json.loads(new_out)
        assert {k: new_payload[k] for k in json.loads(old_out)} == json.loads(old_out)
    else:
        assert json.loads(new_out)["records"] == json.loads(old_out)


LESSON_FILE = "constraints/review-lessons.md"

#: ``(old argv, new argv, set-up)``; ``--repo-root`` is appended to both.
SAME_OUTPUT_ROWS = [
    (["review-packet", NODE], ["review", "packet", NODE], _approved),
    (["review-packet", NODE, "--full", "--max-diff-lines", "1"],
     ["review", "packet", NODE, "--full", "--max-diff-lines", "1"], _in_review),
    (["lessons", "add", "--rule", "R", "--example", "E", "--from", NODE],
     ["decisions", "add", NODE, "--kind", "lesson", "--summary", "R", "--example", "E"], _waiting),
    (["lessons", "list"], ["decisions", "list", "--kind", "lesson"], _waiting),
    (["lessons", "list"], ["decisions", "list", "--kind", "lesson"],
     lambda repo: (repo / LESSON_FILE).parent.mkdir() or (repo / LESSON_FILE).write_text("## Lessons\n\n- R\n")),
]
DEPRECATION = {"review-packet": "review packet", "lessons add": "decisions add --kind lesson",
               "lessons list": "decisions list --kind lesson"}


def _files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` but ``.git``, with ``root`` itself (the packet names it) as ``<ROOT>``."""
    return {p.relative_to(root).as_posix(): p.read_bytes().replace(str(root).encode(), b"<ROOT>")
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


def _cli(argv: list[str], repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str, dict]:
    capsys.readouterr()
    code = cli.run([*argv, "--repo-root", str(repo)])
    out, err = capsys.readouterr()
    return code, out.replace(str(repo), "<ROOT>"), err, _files(repo)


@pytest.mark.parametrize(("old", "new", "setup"), SAME_OUTPUT_ROWS,
                         ids=[f"{' '.join(o)}-{i}".replace(NODE, "N") for i, (o, _n, _s) in enumerate(SAME_OUTPUT_ROWS)])
def test_new_form_gives_the_old_files_and_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], old: list[str], new: list[str], setup: Callable
) -> None:
    base = make_review_repo(tmp_path / "base", orchestration=ROSTER)
    setup(base)
    repos = {}
    for side in ("old", "new"):
        repos[side] = tmp_path / side / "r"
        shutil.copytree(base.parent, repos[side].parent)
    old_code, old_out, old_err, old_files = _cli(old, repos["old"], capsys)
    new_code, new_out, new_err, new_files = _cli(new, repos["new"], capsys)
    assert (new_code, new_out, new_files) == (old_code, old_out, old_files)
    name = old[0] if old[0] == "review-packet" else " ".join(old[:2])
    assert old_err.splitlines()[0] == (f"warning: `specy-road {name}` is deprecated and is removed in the release "
                                       f"after 0.3.1; use `specy-road {DEPRECATION[name]}`.")
    assert new_err.splitlines() == old_err.splitlines()[1:]
