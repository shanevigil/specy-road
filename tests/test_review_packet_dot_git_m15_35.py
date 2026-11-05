"""M15.35: the review packet never treats `.git` as an uncommitted reference."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.review_packet_uncommitted_refs import UNCOMMITTED_REF_NOTE


def test_packet_skips_dot_git_paths_named_in_the_brief(tmp_path: Path, capsys) -> None:
    """A1: `.git` and paths under it are never uncommitted references."""
    repo = make_review_repo(tmp_path)
    git(repo, "rm", "docs/x.md")
    git(repo, "commit", "-qm", "drop docs x")
    sheet = repo / NODE["planning_dir"]
    commit_file(
        repo,
        NODE["planning_dir"],
        sheet.read_text()
        + "\nIgnore `.git` and `.git/hooks/pre-commit`; still track `docs/x.md`.\n",
        "cite git and missing doc",
    )
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    block = text.split("## Uncommitted references\n", 1)[1].split("\n## Changed paths\n", 1)[0]
    assert UNCOMMITTED_REF_NOTE in block and "- `docs/x.md`" in block
    assert ".git" not in block
    err = capsys.readouterr().err
    assert err.count("warning:") == 1
    assert "warning: `docs/x.md` is named in the packet but not at commit" in err
    assert ".git" not in err
