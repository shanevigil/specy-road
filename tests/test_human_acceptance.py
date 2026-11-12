"""``human:`` acceptance items: reviewers skip them, ``finish-this-task`` waits for a person's decision (M11.9).

An item a person must satisfy (approve wording, supply a link) made both
reviewers spend full runs and then block. Marked ``human:`` it is ``n/a`` for a
review, and the leaf finishes only once a person has closed its
``decisions.yaml`` entry, committed on the leaf or integration branch (M22.69);
a planning-sheet ``A#:`` line no longer counts, since any agent can write it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import decisions_cli, finish_task, review_cli
from specy_road.bundled_scripts.role_prompt_rca import reviewer_preamble
from specy_road.decisions import read_decisions
from specy_road.bundled_scripts.finish_task import human_acceptance_ids, undecided_human_items
from specy_road.orchestration_role_env import ROLE_ENV
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo
from tests import test_gui_app_pm_decisions as gui

HUMAN_NODE = {**NODE, "acceptance": ["a.py exists", "human: the maintainer approves the wording"]}
SHEET = NODE["planning_dir"]
LEDGER = "roadmap/decisions.yaml"
CHUNK = "roadmap/phases/M1.json"


def _human_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path)
    commit_file(repo, CHUNK, json.dumps({"nodes": [HUMAN_NODE]}), "mark A2 human")
    return repo


def _entry(**extra) -> dict:
    return {**gui.question("H1", kind="human-action", criterion="A2"), **extra}


def _closed(**extra) -> dict:
    return _entry(status="closed", answer="A: approved", closed="2026-11-11T12:00:00+00:00",
                  decided_by="operator", channel="terminal", **extra)


def _ledger(*entries: dict) -> str:
    return yaml.safe_dump({"version": 1, "entries": list(entries)})


def _finish_err(repo: Path, capsys) -> str:
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
    assert e.value.code == 1
    return capsys.readouterr().err


def _status(repo: Path, capsys) -> tuple[int, list[str], str]:
    out = []
    for extra in (["--json"], []):
        capsys.readouterr()
        with pytest.raises(SystemExit) as e:
            review_cli.main(["handoff", "status", "M1.1", *extra, "--repo-root", str(repo)])
        out.append((e.value.code, capsys.readouterr().out))
    assert out[0][0] == out[1][0]
    return out[0][0], json.loads(out[0][1])["nodes"][0]["human_criteria_undecided"], out[1][1]


def test_marker_ids() -> None:
    assert human_acceptance_ids(HUMAN_NODE) == ["A2"]
    assert human_acceptance_ids(NODE) == []


def test_reviewer_is_told_to_skip_a_human_item() -> None:
    text = "\n".join(reviewer_preamble("M1.1", "r1"))
    assert "`human:`" in text and "mark it `n/a`" in text and "write `human` as its reason" in text


def test_finish_refuses_until_a_person_closes_the_ledger_entry(tmp_path: Path, capsys) -> None:
    repo = _human_repo(tmp_path)
    before = git(repo, "rev-parse", "HEAD")
    code, undecided, text = _status(repo, capsys)
    assert undecided == ["A2"] and "human criteria undecided: A2" in text

    err = _finish_err(repo, capsys)
    assert "error: M1.1 has human acceptance item(s) with no person's decision: A2." in err
    assert "A planning-sheet `A#:` line no longer counts." in err
    assert "decisions add M1.1 --kind human-action --criterion A2" in err
    assert "decisions close <ID>" in err and "PM GUI's Status window" in err
    assert "implementation review is required" not in err
    assert git(repo, "rev-parse", "HEAD") == before

    commit_file(repo, LEDGER, _ledger(_closed()), "a person decides A2")   # F8: on the leaf branch
    assert undecided_human_items(repo, HUMAN_NODE, "refs/heads/dev") == []
    err = _finish_err(repo, capsys)
    assert "no person's decision" not in err
    assert "implementation review is required" in err   # the next gate, as before
    code_after, undecided, text = _status(repo, capsys)
    assert (code_after, undecided) == (code, []) and "human criteria undecided" not in text


def _sheet_line(repo: Path) -> None:
    commit_file(repo, SHEET, (repo / SHEET).read_text() + "\n## Decisions and notes\n\n- [x] A2: approved\n", "sheet")


@pytest.mark.parametrize("setup", [
    lambda r: None,                                                                             # F1 no entry
    _sheet_line,                                                                                # F2 sheet line only
    lambda r: commit_file(r, LEDGER, _ledger(_entry()), "open"),                               # F3 open
    lambda r: commit_file(r, LEDGER, _ledger({k: v for k, v in _closed().items() if k != "channel"}), "x"),  # F4
    lambda r: commit_file(r, LEDGER, _ledger(_closed(node="M1.2")), "other node"),             # F5
    lambda r: commit_file(r, LEDGER, _ledger(_closed(criterion="A1")), "other criterion"),     # F5
    lambda r: (r / "roadmap" / "decisions.local.yaml").write_text(_ledger(_closed())),          # F6 local only
    lambda r: (r / LEDGER).write_text(_ledger(_closed())),                                      # F7 uncommitted
], ids=["no-entry", "sheet-line", "open", "no-channel", "other-node", "other-criterion", "local", "uncommitted"])
def test_only_a_committed_person_closed_entry_decides(tmp_path: Path, capsys, setup) -> None:
    repo = _human_repo(tmp_path)
    setup(repo)
    assert undecided_human_items(repo, HUMAN_NODE, "refs/heads/dev") == ["A2"]
    assert "no person's decision: A2." in _finish_err(repo, capsys)


def test_an_entry_committed_on_the_integration_branch_counts(tmp_path: Path) -> None:
    repo = _human_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, LEDGER, _ledger(_closed()), "decided on dev")
    git(repo, "checkout", "-q", "feature/rm-thing")
    assert undecided_human_items(repo, HUMAN_NODE, None) == ["A2"]   # no integration ref: the leaf HEAD alone
    assert undecided_human_items(repo, HUMAN_NODE, "refs/heads/dev") == []


def test_the_pm_gui_answer_decides_the_criterion(tmp_path: Path, monkeypatch, capsys) -> None:
    """F9: the GUI's own close path, committed and pushed on the integration branch only."""
    monkeypatch.delenv(ROLE_ENV, raising=False)   # the manual coordinator
    lay = gui.layout(tmp_path, monkeypatch)
    commit_file(lay.leaf, CHUNK, json.dumps({"nodes": [HUMAN_NODE]}), "mark A2 human")
    gui.with_questions(lay, _entry())
    assert gui.answer(gui.client(), "H1", "A", "wording approved").status_code == 200
    entry = gui.ledger_at(lay, "origin/dev")["H1"]
    assert (entry["decided_by"], entry["channel"]) == ("operator", "pm-gui")
    assert not (lay.leaf / LEDGER).exists()
    err = _finish_err(lay.leaf, capsys)
    assert "no person's decision" not in err and "implementation review is required" in err


# --- decisions add --criterion and the person-only close ----------------------


def _cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as e:
        decisions_cli.main(list(argv))
    return int(e.value.code or 0)


def _add(repo: Path, *extra: str, kind: str = "human-action", criterion: str = "A2") -> int:
    return _cli("decisions", "add", "M1.1", "--kind", kind, "--criterion", criterion, "--summary", "Wording ok?",
                "--why", "A2 needs a person", "--option", "yes|ships", "--recommendation", "yes",
                "--recommendation-reason", "reviewed", "--default", "no", *extra, "--repo-root", str(repo))


def _criterion_repo(tmp_path: Path) -> Path:
    repo = _human_repo(tmp_path)
    assert _add(repo, "--id", "H1") == 0
    assert read_decisions(repo / LEDGER)["entries"][0]["criterion"] == "A2"
    return repo


@pytest.mark.parametrize("kind, criterion, local", [
    ("decision", "A2", None), ("human-action", "A1", None),
    ("human-action", "A2", None),                                   # the second open A2
    ("human-action", "A2", "version: 1\nentries:\n- {id: P1, kind: preference, summary: s, status: open}\n"),
])
def test_add_criterion_refusals_write_nothing(tmp_path: Path, capsys, kind: str, criterion: str,
                                              local: str | None) -> None:
    """The last row: a schema-invalid local ledger (``asked`` missing) hides nothing; the add still refuses."""
    repo = _criterion_repo(tmp_path)   # an open A2 entry already
    if local:
        (repo / "roadmap" / "decisions.local.yaml").write_text(local)
    before = (repo / LEDGER).read_bytes()
    assert _add(repo, kind=kind, criterion=criterion) == 1
    assert (repo / LEDGER).read_bytes() == before


def _close(repo: Path) -> int:
    return _cli("decisions", "close", "H1", "--answer", "approved", "--repo-root", str(repo))


def _unset_identity(repo: Path, monkeypatch) -> None:
    empty = repo.parent / "empty.gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    git(repo, "config", "--unset", "user.email")


@pytest.mark.parametrize("tty, role, reply, identity", [
    (False, None, "y", True),                     # C1 not a terminal
    *[(True, role, "y", True) for role in ("executor", "reviewer", "rca", "", " coordinator", "Coordinator")],  # C2
    (True, None, "y", False),                     # C3 identity unset
    (True, None, "n", True),                      # C4
    (True, "coordinator", "", True),              # C4
])
def test_a_criterion_close_refused_writes_nothing(tmp_path: Path, monkeypatch, capsys, tty, role, reply,
                                                  identity) -> None:
    repo = _criterion_repo(tmp_path)
    before = (repo / LEDGER).read_bytes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: tty)
    monkeypatch.setattr("builtins.input", lambda _p="": reply)
    if role is None:
        monkeypatch.delenv(ROLE_ENV, raising=False)
    else:
        monkeypatch.setenv(ROLE_ENV, role)
    if not identity:
        _unset_identity(repo, monkeypatch)
    assert _close(repo) == 1
    assert (repo / LEDGER).read_bytes() == before


def test_a_person_at_a_terminal_closes_the_criterion(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _criterion_repo(tmp_path)
    monkeypatch.delenv(ROLE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _p="": "y")
    capsys.readouterr()
    assert _close(repo) == 0
    shown = capsys.readouterr().out
    assert "M1.1" in shown and "A2: human: the maintainer approves the wording" in shown and "approved" in shown
    e = read_decisions(repo / LEDGER)["entries"][0]
    assert (e["status"], e["decided_by"], e["channel"]) == ("closed", "operator", "terminal")
    assert e["answer"] == "approved (recorded by T <t@e.com>)"
    git(repo, "add", LEDGER)
    git(repo, "commit", "-qm", "a person decides A2")
    assert undecided_human_items(repo, HUMAN_NODE, None) == []
