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
from specy_road.review_record_rules import clause_problem, defect_word, explained, note_problem, unexplained_defects


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
    assert 'findings.correctness[1] says "Advisory"' in err and 'findings.correctness[0] is a finding' in err
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
    assert 'findings.correctness[0] is a finding' in err
    # negated lines name no defect word, but they are still observations without a reason (round 5)
    assert "notes line 1 is an observation" in err and "notes line 3 is an observation" in err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


SOL_WORDING = "Valid input raises ValueError, so the command exits 1 instead of filing the review."


def test_record_refuses_an_approve_whose_finding_says_valid_input_raises(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"correctness": [SOL_WORDING]}) == 1
    err = capsys.readouterr().err
    assert 'findings.correctness[0] says "Valid input raises"' in err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_refuses_an_approve_with_any_finding_that_does_not_say_why_it_is_not_a_defect(
        tmp_path: Path, capsys) -> None:
    """A word list cannot catch every way of describing a defect, so on an approve every finding needs the line."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"boundary": ["The cache key ignores the branch name."]}) == 1
    err = capsys.readouterr().err
    assert "findings.boundary[0] is a finding" in err
    assert "on an approve every findings entry and every observation line of the notes needs that line" in err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_refuses_an_approve_whose_notes_say_valid_input_raises(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes=f"A1 pass.\n{SOL_WORDING}\n") == 1
    assert 'notes line 2 says "Valid input raises"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


ORDER_WORDING = "The second call reads the registry before the first writes it."


def test_record_refuses_an_approve_whose_notes_describe_a_write_order_race(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes=f"A1 pass.\n\n{ORDER_WORDING}\n") == 1
    assert 'notes line 3 says "reads the registry before the first writes"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_files_an_approve_whose_notes_explain_the_order_on_the_same_line(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    notes = f"{ORDER_WORDING} Not a defect because both calls hold the registry lock.\n"
    assert _record(repo, notes=notes) == 0
    assert review_path(repo, "M1.1", "opus").is_file()


MALFORMED_WORDING = "The parser accepts malformed input, so invalid configuration reaches execution."


def test_record_refuses_an_approve_whose_notes_carry_an_unclassified_observation(tmp_path: Path, capsys) -> None:
    """No word in the sentence names a defect: every observation line of approve notes needs a reason (round 5)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert defect_word(MALFORMED_WORDING) is None
    assert _record(repo, notes=f"## Acceptance\n\n- **A1:** pass\n\n{MALFORMED_WORDING}\n") == 1
    err = capsys.readouterr().err
    assert "notes line 5 is an observation" in err
    assert "every observation line of the notes needs that line" in err
    assert "notes line 1" not in err and "notes line 3" not in err   # the heading and the bare result
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


@pytest.mark.parametrize("line, why", [
    (MALFORMED_WORDING, "is an observation"),
    ("The cache key ignores the branch name.", "is an observation"),
    ("No defect found.", "is an observation"),
    ("- A2 — pass. The prompt renders all four rules.", "is an observation"),
    ("Crashes.", 'says "Crashes"'),
    (f"{MALFORMED_WORDING} Not a defect because the parser is outside this leaf.", None),
    ("notes", None),
    ("- **A1:** pass", None),
    ("| A1 | pass |", None),
    ("|---|---|", None),
    ("## Acceptance", None),
    ("> The parser accepts malformed input.", None),
    ("`pytest -q` -> 41", None),
    ("No internal imports, mock assertions or defensive branches were added; not a defect because the change uses "
     "the existing exclusion mechanism.", None),
    ("The test drives the CLI and checks both the pass case and the fail case, which is not a defect because it is "
     "the exact scenario A2 describes.", None),
    ("X fails and Y crashes; not a defect because the fallback handles both.",
     'says "crashes", two observations joined by "and": "X fails" and "Y crashes"'),
    ("X fails, Y crashes; not a defect because the fallback handles both.",
     'says "crashes", two observations joined by ",": "X fails", "Y crashes"'),
])
def test_note_problem(line: str, why: str | None) -> None:
    assert note_problem(line) == why


BOUNDARY_WORDING = "The parser accepts malformed input; xnot a defect becausey is only a marker."


def test_record_refuses_an_approve_whose_marker_is_only_a_substring(tmp_path: Path, capsys) -> None:
    """The marker must stand on its own with a reason after it; a substring inside other words is not one (round 6)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"correctness": [BOUNDARY_WORDING]}) == 1
    assert "findings.correctness[0] " in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


MULTILINE_WORDING = "The parser accepts malformed input; not a defect because\nthe parser is unreachable."


def test_record_refuses_an_approve_whose_reason_is_on_the_next_line(tmp_path: Path, capsys) -> None:
    """The reason must follow the marker on the same line; a line break after 'because' is not one (round 7)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"correctness": [MULTILINE_WORDING]}) == 1
    assert "findings.correctness[0] " in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


@pytest.mark.parametrize("text, ok", [
    (BOUNDARY_WORDING, False),
    (MULTILINE_WORDING, False),
    ("x; not a defect because \r\ny", False),
    ("x; not a\ndefect because y", False),
    ("x; not a defect because\u2028y", False),
    ("x; not a defect because - \ny", False),
    ("x; not a defect because\ty", True),
    ("x; not a defect because \u2014 y", True),
    ("x; anot a defect because y", False),
    ("x; not a defect becausey", False),
    ("x; not-a defect because y", False),
    ("x; not a defect because", False),
    ("x; not a defect because.", False),
    ("x; `not a defect because y`", False),
    ("x; not a defect because y.", True),
    ("x (not a defect because y)", True),
    ("x;not a defect because y", True),
    ("x. Not  a defect because the CLI never passes it", True),
    ("x; NOT A DEFECT BECAUSE it is intended", True),
])
def test_explained(text: str, ok: bool) -> None:
    assert explained(text) is ok


TWO_OBSERVATIONS = ("The cache miss is expected; not a defect because the cache fallback handles that miss. "
                    "Separately, valid input crashes and loses the review.")


def test_record_refuses_an_approve_whose_explanation_covers_only_one_observation(tmp_path: Path, capsys) -> None:
    """One explanation covers one observation; a second defect on the same line needs its own (round 8)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes=f"## Acceptance\n\n- **A1:** pass\n\n{TWO_OBSERVATIONS}\n") == 1
    err = capsys.readouterr().err
    assert 'notes line 5 says "valid input crashes"' in err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_files_an_approve_with_one_explanation_per_observation(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    notes = ("The cache miss is expected; not a defect because the cache fallback handles that miss. "
             "Empty input is refused; not a defect because the brief asks for that.\n")
    assert _record(repo, notes=notes) == 0
    assert review_path(repo, "M1.1", "opus").is_file()


CONJUNCTION_WORDING = ("The cache miss is expected and valid input crashes, not a defect because the fallback "
                       "handles the cache miss.")


def test_record_refuses_an_approve_whose_explained_clause_joins_a_second_defect(tmp_path: Path, capsys) -> None:
    """The text one explanation covers may not join a second observation with a conjunction (round 9)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes=f"## Acceptance\n\n- **A1:** pass\n\n{CONJUNCTION_WORDING}\n") == 1
    assert 'notes line 5 says "valid input crashes"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


def test_record_refuses_an_approve_whose_explained_finding_joins_a_second_defect(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, findings={"correctness": [CONJUNCTION_WORDING]}) == 1
    assert 'findings.correctness[0] says "valid input crashes"' in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()
    assert not (reviews_dir(repo, "M1.1") / "history").exists()


@pytest.mark.parametrize("text, why", [
    (CONJUNCTION_WORDING, 'says "valid input crashes", two observations joined by "and": '
     '"The cache miss is expected" and "valid input crashes"'),
    ("The cache miss is expected and valid input crashes; not a defect because the fallback handles it.",
     'says "valid input crashes", two observations joined by "and": "The cache miss is expected" and '
     '"valid input crashes"'),
    ("The cache miss is expected, valid input crashes, not a defect because the fallback handles it.",
     'says "valid input crashes", two observations joined by ",": "The cache miss is expected", '
     '"valid input crashes"'),
    ("The cache miss is expected and the cache key ignores the branch name, not a defect because it is handled.",
     None),
    ("The cache key ignores the branch and valid input crashes, not a defect because it is handled.",
     'says "valid input crashes", two observations joined by "and": "The cache key ignores the branch" and '
     '"valid input crashes"'),
    ("x y; not a defect because the fallback handles it, so the message is lost.", 'says "is lost" in its reason'),
    ("The parser accepts malformed input, so invalid configuration reaches execution. Not a defect because the "
     "parser is outside this leaf.", None),
    ("The lock and the registry are both held, not a defect because both calls take the lock.", None),
    ("It returns 0, 1 or 2; not a defect because the brief lists them.", None),
    ("Malformed values are treated as missing, rather than crashing the gate; not a defect because the brief asks "
     "for it.", None),
    (TWO_OBSERVATIONS, 'says "valid input crashes"'),
    ("Valid input crashes. The cache miss is expected, not a defect because the fallback handles it.",
     'says "Valid input crashes"'),
    ("The cache miss is expected; not a defect because the fallback handles it, and valid input crashes.",
     'says "valid input crashes" in its reason'),
    ("The lock is held; the cache is cold; not a defect because both are expected.", "is an observation"),
    ("The cache miss is expected; not a defect because the fallback handles it.", None),
    ("The cache miss is expected, not a defect because the fallback handles it.", None),
    ("Advisory: x. Not a defect because no caller reaches it.", None),
    ("x y; not a defect because e.g. the lock is held.", None),
    ("- **A1:** pass; the prompt renders; not a defect because it matches.", None),
    ("The cache miss is expected; not a defect because it is handled. Empty input is refused; not a defect "
     "because the brief asks for that.", None),
])
def test_clause_problem(text: str, why: str | None) -> None:
    assert clause_problem(text) == why


def test_record_files_an_approve_with_no_findings(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    notes = ("## Acceptance\n\n- **A1:** pass\n- **A2:** pass\n\n"
             "Re-ran the record tests; not a defect because all of them passed.\n")
    assert _record(repo, notes=notes) == 0
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
    (SOL_WORDING, "Valid input raises"),
    ("`decisions list` rejects a valid ledger.", "rejects a valid"),
    ("It fails on valid input.", "fails on valid"),
    ("It exits non-zero instead of writing the record.", "exits non-zero"),
    ("It no longer rejects a valid ledger; it exits 1 on an unknown node.", None),
    (ORDER_WORDING, "reads the registry before the first writes"),
    ("A stale read of the claim; events arrive out of order.", "stale read"),
    ("It reads the config before running git; no stale reads.", None),
])
def test_defect_word(line: str, word: str | None) -> None:
    assert defect_word(line) == word


def test_fenced_code_in_the_notes_is_not_checked() -> None:
    body = "Ran it:\n```\nFAILED test_bug - minor\n```\nadvisory: z\n"
    assert unexplained_defects({"findings": {}}, body) == ["notes line 1 is an observation",
                                                           'notes line 5 says "advisory"']
