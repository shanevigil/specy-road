"""registry-prune reports orphaned claims and removes only the ones you name.

The safety property under test: a claim held by another clone is
indistinguishable from an orphan here, because pickup pushes the registry and
keeps the feature branch local. So reporting must never imply removal, and
removal must never be inferred from branch absence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import registry_prune as rp


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _reg(*entries: dict) -> dict:
    return {"version": 1, "entries": list(entries)}


def _entry(codename: str, node_id: str) -> dict:
    return {
        "codename": codename,
        "node_id": node_id,
        "branch": f"feature/rm-{codename}",
        "touch_zones": [],
        "started": "2026-09-07",
    }


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    (root / "roadmap").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    (root / "README.md").write_text("# r\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


# --- reporting -------------------------------------------------------------


def test_report_is_quiet_when_every_branch_exists(repo: Path, capsys) -> None:
    _git(repo, "branch", "feature/rm-alpha")

    code = rp._report(repo, _reg(_entry("alpha", "M1.1")), "origin", "dev")

    assert code == 0
    assert "every branch accounted for" in capsys.readouterr().out


def test_report_lists_the_orphan_and_exits_1(repo: Path, capsys) -> None:
    code = rp._report(repo, _reg(_entry("alpha", "M1.1")), "origin", "dev")

    err = capsys.readouterr().err
    assert code == 1
    assert "alpha" in err and "M1.1" in err


def test_report_warns_that_another_clone_looks_the_same(repo: Path, capsys) -> None:
    """The whole reason this command does not auto-prune."""
    rp._report(repo, _reg(_entry("alpha", "M1.1")), "origin", "dev")

    err = capsys.readouterr().err
    assert "another clone" in err
    assert "--remove" in err
    assert "abort-task-pickup" in err


def test_report_counts_only_missing_branches(repo: Path, capsys) -> None:
    _git(repo, "branch", "feature/rm-alpha")

    rp._report(repo, _reg(_entry("alpha", "M1.1"), _entry("beta", "M1.2")), "origin", "dev")

    err = capsys.readouterr().err
    assert "1 of 2 registry claim(s)" in err
    assert "beta" in err


# --- resolving what to remove ---------------------------------------------


def test_unknown_codename_is_refused(repo: Path, capsys) -> None:
    with pytest.raises(SystemExit) as e:
        rp._resolve_removals(repo, _reg(_entry("alpha", "M1.1")), ["nope"])

    assert e.value.code == 1
    assert "no registry claim with codename 'nope'" in capsys.readouterr().err


def test_a_claim_whose_branch_is_here_is_refused(repo: Path, capsys) -> None:
    """That is not an orphan, and removing the row would orphan the work."""
    _git(repo, "branch", "feature/rm-alpha")

    with pytest.raises(SystemExit) as e:
        rp._resolve_removals(repo, _reg(_entry("alpha", "M1.1")), ["alpha"])

    err = capsys.readouterr().err
    assert e.value.code == 1
    assert "still exists in this clone" in err
    assert "abort-task-pickup" in err


def test_named_orphans_resolve_in_order(repo: Path) -> None:
    reg = _reg(_entry("alpha", "M1.1"), _entry("beta", "M1.2"))

    rows = rp._resolve_removals(repo, reg, ["beta", "alpha"])

    assert [r["codename"] for r in rows] == ["beta", "alpha"]


# --- removal ---------------------------------------------------------------


def test_removal_drops_only_named_rows_and_pushes(repo: Path, monkeypatch) -> None:
    reg = _reg(_entry("alpha", "M1.1"), _entry("beta", "M1.2"))
    calls: list[tuple] = []
    monkeypatch.setattr(rp, "git_run", lambda root, *a: calls.append(a))
    written: dict = {}
    monkeypatch.setattr(
        rp, "write_registry", lambda path, doc: written.update(doc)
    )

    code = rp._remove_and_push(repo, reg, [reg["entries"][0]], "origin", "dev")

    assert code == 0
    assert [e["codename"] for e in written["entries"]] == ["beta"]
    assert ("push", "origin", "dev") in calls
    assert any(a[0] == "commit" for a in calls)


def test_removal_commit_message_names_the_claims(repo: Path, monkeypatch) -> None:
    reg = _reg(_entry("alpha", "M1.1"), _entry("beta", "M1.2"))
    calls: list[tuple] = []
    monkeypatch.setattr(rp, "git_run", lambda root, *a: calls.append(a))
    monkeypatch.setattr(rp, "write_registry", lambda path, doc: None)

    rp._remove_and_push(repo, reg, list(reg["entries"]), "origin", "dev")

    commit = next(a for a in calls if a[0] == "commit")
    assert "alpha, beta" in commit[-1]
