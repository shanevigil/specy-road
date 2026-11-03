"""finish-this-task archive of a committed implementation summary."""

from __future__ import annotations

import pytest

from tests.helpers import REPO
from tests.review_repo_helpers import git, make_review_repo, review_text

from specy_road.bundled_scripts import finish_task
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.review_files import reviews_dir


def test_finish_still_commits_when_work_done_is_gitignored(
    tmp_path, monkeypatch, capsys,
) -> None:
    """A tracked summary whose archive path is ignored is deleted, not moved."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    repo = make_review_repo(tmp_path)
    (repo / ".gitignore").write_text(
        "/work/*\n!/work/implementation-summary-*.md\n", encoding="utf-8"
    )
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "implementation-summary-M1.1.md").write_text(
        "## Summary\n\nShipped.\n", encoding="utf-8"
    )
    git(repo, "add", ".gitignore", "work/implementation-summary-M1.1.md")
    git(repo, "commit", "-qm", "executor: summary")
    head = git(repo, "rev-parse", "HEAD")
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "REVIEW-human.md").write_text(review_text(head))
    with pytest.raises(SystemExit) as e:
        mir.main(["--yes", "--repo-root", str(repo)])
        raise SystemExit(0)
    assert (e.value.code or 0) == 0
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
        raise SystemExit(0)
    err = capsys.readouterr().err
    assert (e.value.code or 0) == 0, err
    committed = git(repo, "show", "--name-only", "--format=%s", "HEAD")
    assert committed.startswith("chore(rm-thing): complete, deregister")
    assert not (repo / "work" / "implementation-summary-M1.1.md").exists()
    assert not (repo / "work" / "done" / "implementation-summary-M1.1.md").exists()
    assert "work/done/implementation-summary-M1.1.md" not in committed.splitlines()
    assert "!work/done/" in err
