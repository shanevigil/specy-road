"""M11.75: the reviewer prompt asks for independent probes; `review record` refuses an approve that excuses a defect."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import git, make_review_repo, review_text
from tests.test_models_and_prompt import make_profile_repo
from tests.test_review_cli import ONE_AI

from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.review_files import PACKET_NAME, review_path, reviews_dir
from specy_road.review_record_rules import defect_word, unexplained_defects


def test_reviewer_prompt_carries_the_four_probe_rules(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert ("1. Run the tests that import each changed module, not only the executor's selection or the READY's "
            "verifiers") in text
    assert ("2. For each changed public function, try at least one input that the diff's tests do not use, and "
            "report it, with what it returned, under `commands_rerun`.") in text
    assert ("3. Fail an acceptance item whose observed behaviour differs from its text, even when the difference "
            "looks minor") in text
    assert ("4. List every defect your notes or findings describe under `required_changes` (and block), or "
            "explain on that same line why it is not one, starting `not a defect because`.") in text
    executor, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None and "Run the tests that import each changed module" not in executor


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _record(repo: Path, verdict: str = "approve", findings: dict | None = None, notes: str = "notes\n",
            required: list[str] | None = None) -> int:
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict=verdict)
    data = yaml.safe_load(text.split("---")[1])
    data["findings"].update(findings or {})
    if required is not None:
        data["required_changes"] = required
    p = repo.parent / "notes-opus.md"
    p.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n" + notes)
    return _run("review", "record", "M1.1", "--model", "opus", "--verdict", verdict, "--file", str(p),
                "--repo-root", str(repo))


def test_record_refuses_an_approve_whose_finding_names_a_defect(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"correctness": ["Checked the lock order.", "Advisory: x drops an empty y"]}) == 1
    err = capsys.readouterr().err
    assert 'findings.correctness[1] says "Advisory"' in err and "findings.correctness[0]" not in err
    assert "no required_changes entry and no 'not a defect because' line" in err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_record_refuses_an_approve_whose_notes_name_a_defect(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes="A1 pass.\n\nNon-blocking nit: the comment is stale.\n") == 1
    assert 'notes line 3 says "Non-blocking"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_record_refuses_an_approve_whose_finding_describes_a_crash(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    finding = "The command crashes on empty input and drops the review."
    assert _record(repo, findings={"correctness": [finding]}) == 1
    assert 'findings.correctness[0] says "crashes"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_record_refuses_an_approve_where_no_workaround_does_not_negate_the_bug(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes="A1 pass.\nThere is no workaround for this bug: empty input loses the review.\n") == 1
    assert 'notes line 2 says "bug"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_record_names_every_offending_finding_and_line(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    findings = {"correctness": ["Checked the lock order.", "A queued message is lost when the wrapper dies."],
                "regression": ["The sync silently drops unreadable events."]}
    notes = "No other correctness defect proved.\nIt hangs on a closed pipe.\nNo crash on empty input.\n"
    assert _record(repo, findings=findings, notes=notes) == 1
    err = capsys.readouterr().err
    for where in ('findings.correctness[1] says "is lost"', 'findings.regression[0] says "silently drops"',
                  'notes line 2 says "hangs"'):
        assert where in err
    assert "findings.correctness[0]" not in err and "notes line 1" not in err and "notes line 3" not in err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_files_an_approve_with_no_findings(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes="No defect found; no bugs.\n") == 0
    assert review_path(repo, "M1.1", "opus").is_file()


def test_record_files_an_approve_that_says_why_it_is_not_a_defect(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    finding = "Advisory: y is dropped; not a defect because no caller passes an empty y."
    assert _record(repo, findings={"regression": [finding]}) == 0
    assert review_path(repo, "M1.1", "opus").is_file()


def test_record_files_a_block_that_lists_the_defect(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, verdict="block", findings={"correctness": ["bug: y is dropped"]},
                   required=["keep an empty y"]) == 0


@pytest.mark.parametrize("line, word", [
    ("Weak assertion (not blocking): foo", "Weak assertion"),
    ("Two traces that look like bugs do not fail an item.", "bugs"),
    ("Minor; delivery re-checks anyway.", "Minor"),
    ("No other correctness defect proved.", None),
    ("None blocking. Nothing minor.", None),
    ("`test_minor_bug` passes", None),
    ("> refuses an approve whose notes name a defect", None),
    ("## Defects", None),
    ("Advisory: x. Not a defect because no caller reaches it.", None),
    ("The command crashes on empty input and drops the review.", "crashes"),
    ("There is no workaround for this bug.", "bug"),
    ("There is no test for this bug.", "bug"),
    ("It overwrites the user's edits.", "overwrites the user's edits"),
    ("`ops.delegate` returns the wrong commit.", "returns the wrong"),
    ("It no longer crashes; it doesn't drop data; no known bug.", None),
    ("Malformed values are treated as missing rather than crashing the gate.", None),
    ("Default drops a leaf that still has a placeholder; one parametrize case dropped.", None),
    ("The test fails without the fix and raises ReviewTargetError on an unknown node.", None),
])
def test_defect_word(line: str, word: str | None) -> None:
    assert defect_word(line) == word


def test_fenced_code_in_the_notes_is_not_checked() -> None:
    body = "Ran it:\n```\nFAILED test_bug - minor\n```\nadvisory: z\n"
    assert unexplained_defects({"findings": {}}, body) == ['notes line 5 says "advisory"']
