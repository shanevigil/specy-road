"""M13.7 A2: the dry-run estimate treats a symlinked ``.gitignore`` as git does (it does not read one).

Split from ``test_m13_7_notices.py`` for the file-size cap; the helpers are that file's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.agent_ignores import GITIGNORE, apply_and_report
from specy_road.ignore_report import HIDDEN_NOTE
from tests.test_m13_7_notices import _listed, _repo_with_prompts, _shown, _write


def _case_symlinked_nested(repo: Path) -> None:
    _write(repo, "elsewhere.txt", "!prompt-keep.md\n")
    (repo / "work" / GITIGNORE).symlink_to("../elsewhere.txt")   # git does not read a symlinked .gitignore
    _write(repo, "work/prompt-keep.md")
    _write(repo, "work/prompt-hide.md")


def _case_symlinked_top(repo: Path) -> None:
    _write(repo, "real-ignore", "node_modules\n")
    (repo / GITIGNORE).symlink_to("real-ignore")                   # the update writes through it; git reads neither
    _write(repo, "work/prompt-hide.md")


def _case_dangling_top(repo: Path) -> None:
    (repo / GITIGNORE).symlink_to("missing-ignore")
    _write(repo, "work/prompt-hide.md")


#: name -> (setup, expected now-hidden): ``.gitignore`` symlinks the estimate must keep as symlinks.
SYMLINK_CASES = {
    "nested symlink": (_case_symlinked_nested, {"work/prompt-hide.md", "work/prompt-keep.md"}),
    "top-level symlink": (_case_symlinked_top, set()),
    "dangling top-level symlink": (_case_dangling_top, set()),
}


@pytest.mark.parametrize("case", list(SYMLINK_CASES))
def test_the_dry_run_estimate_treats_a_symlinked_gitignore_as_git_does(tmp_path: Path, capsys, case: str) -> None:
    setup, hidden = SYMLINK_CASES[case]
    repo = _repo_with_prompts(tmp_path, untracked=0)
    setup(repo)
    files = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    apply_and_report(repo, "", [], dry_run=True)
    dry = capsys.readouterr().out
    assert {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts} == files
    shown = _shown(repo)
    apply_and_report(repo, "", [])
    real = capsys.readouterr().out
    assert _listed(dry, HIDDEN_NOTE) == _listed(real, HIDDEN_NOTE) == shown - _shown(repo) == hidden
    assert dry.splitlines()[1:] == real.splitlines()[1:]
