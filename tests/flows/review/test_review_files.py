"""Tests for work/reviews/<NODE_ID>/ READY and REVIEW file parsing, and how a reviewer is launched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import fake_reviewer_run
from tests.support.review import claude_code_reviewer_repo

from specy_road import review_files as rf
from specy_road.planning_artifacts import split_frontmatter
from specy_road.bundled_scripts import review_packet as rp
from specy_road.review_files import latest_ready, reviews_dir
from specy_road.review_target import resolve_target
from tests.support.review import make_review_repo, git
from specy_road.review_files import reviews_root
from specy_road.bundled_scripts import review_cli

READY = """---
node_id: M1.1
agent: composer-2.5
branch: feature/rm-thing
commit: abc1234
base: def5678
changed_paths: [src/a.py]
verify:
  - {cmd: pytest, exit: 0, tail: "3 passed"}
---
Implementation done.
"""

REVIEW = """---
node_id: M1.1
model: claude-opus-5.5
date: 2026-10-26
verdict: approve
commit: abc1234
acceptance: {A1: pass, A2: n/a}
findings: {correctness: [], regression: [], boundary: [], test_integrity: []}
commands_rerun: [pytest]
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
---
Looks right.
"""


def _put(root: Path, name: str, text: str) -> Path:
    d = rf.reviews_dir(root, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_ready_and_review_parse(tmp_path: Path) -> None:
    ready = rf.load_ready(_put(tmp_path, "READY-composer-2.5.md", READY))
    assert ready.ok, ready.errors
    assert ready.data["verify"][0]["exit"] == 0
    review = rf.load_review(_put(tmp_path, "REVIEW-claude-opus-5.5.md", REVIEW), ["A1", "A2"])
    assert review.ok, review.errors
    assert review.data["date"] == "2026-10-26"
    assert review.body.strip() == "Looks right."


def test_all_digit_short_sha_is_kept_as_string(tmp_path: Path) -> None:
    text = READY.replace("commit: abc1234", "commit: 1234567")
    ready = rf.load_ready(_put(tmp_path, "READY-x.md", text))
    assert ready.ok, ready.errors
    assert ready.data["commit"] == "1234567"


def test_missing_front_matter(tmp_path: Path) -> None:
    r = rf.load_ready(_put(tmp_path, "READY-x.md", "just prose\n"))
    assert not r.ok
    assert "front matter" in r.errors[0]


def test_ready_schema_error_names_field(tmp_path: Path) -> None:
    r = rf.load_ready(_put(tmp_path, "READY-x.md", READY.replace("base: def5678\n", "")))
    assert any("base" in e for e in r.errors)


@pytest.mark.parametrize(
    "old, new, fragment",
    [
        ("authored_fix: false", "authored_fix: true", "authored_fix"),
        ("is_coordinator: false", "is_coordinator: true", "is_coordinator"),
        ("A1: pass", "A1: fail", "failing acceptance A1"),
        ("required_changes: []", "required_changes: [fix x]", "required_changes"),
        ("verdict: approve", "verdict: maybe", "verdict"),
        ("A1: pass", "B1: pass", "acceptance"),
    ],
)
def test_review_rejections(tmp_path: Path, old: str, new: str, fragment: str) -> None:
    r = rf.load_review(_put(tmp_path, "REVIEW-m.md", REVIEW.replace(old, new)), ["A1", "A2"])
    assert not r.ok
    assert any(fragment in e for e in r.errors), r.errors


def test_block_may_list_failures_and_changes(tmp_path: Path) -> None:
    text = (
        REVIEW.replace("verdict: approve", "verdict: block")
        .replace("A1: pass", "A1: fail")
        .replace("required_changes: []", "required_changes: [fix x]")
    )
    assert rf.load_review(_put(tmp_path, "REVIEW-m.md", text), ["A1", "A2"]).ok


def test_acceptance_ids_must_match_the_brief(tmp_path: Path) -> None:
    p = _put(tmp_path, "REVIEW-m.md", REVIEW)
    missing = rf.load_review(p, ["A1", "A2", "A3"])
    assert any("no result for A3" in e for e in missing.errors)
    # A2 is graded n/a: no judgment on an id the brief lacks, so it is not an error.
    assert rf.load_review(p, ["A1"]).ok
    graded = _put(tmp_path, "REVIEW-g.md", REVIEW.replace("A2: n/a", "A2: pass"))
    extra = rf.load_review(graded, ["A1"])
    assert any("A2 not in the brief" in e for e in extra.errors)
    assert rf.load_review(p, None).ok


def test_listing_and_latest_ready(tmp_path: Path) -> None:
    import os

    a = _put(tmp_path, "READY-a.md", READY)
    b = _put(tmp_path, "READY-b.md", READY.replace("abc1234", "fff0000"))
    _put(tmp_path, "READY-broken.md", "nope\n")
    os.utime(a, (1, 1))
    os.utime(b, (2, 2))
    assert [r.path.name for r in rf.list_ready(tmp_path, "M1.1")] == [
        "READY-a.md", "READY-b.md", "READY-broken.md"
    ]
    assert rf.latest_ready(tmp_path, "M1.1").data["commit"] == "fff0000"
    assert rf.node_ids_with_reviews(tmp_path) == ["M1.1"]
    assert rf.latest_ready(tmp_path, "M9") is None


def test_render_front_matter_round_trips(tmp_path: Path) -> None:
    src = rf.load_review(_put(tmp_path, "REVIEW-m.md", REVIEW))
    out = _put(tmp_path, "REVIEW-n.md", rf.render_front_matter(src.data, src.body))
    again = rf.load_review(out)
    assert again.ok and again.data == src.data


def test_trailing_non_ascii_space_round_trips(tmp_path: Path) -> None:
    data = {"0": "\xa0"}
    text = rf.render_front_matter(data)
    assert split_frontmatter(text)[0] == data
    path = tmp_path / "READY-nbsp.md"
    path.write_text(text, encoding="utf-8")
    assert rf.load_ready(path).data == data


@pytest.mark.parametrize("token, want", [
    ("0123456", "0123456"),      # YAML 1.1 octal
    ("0x1234567", "0x1234567"),  # hex: must not become a different valid SHA
    ("'0123456'", "0123456"),
    ('"abc1234"  # quoted, with comment', "abc1234"),
])
def test_sha_tokens_are_kept_as_written(tmp_path: Path, token: str, want: str) -> None:
    r = rf.load_ready(_put(tmp_path, "READY-x.md", READY.replace("commit: abc1234", f"commit: {token}")))
    assert r.data["commit"] == want
    assert r.ok == (want != "0x1234567"), r.errors


def test_only_human_may_attest_coordinator(tmp_path: Path) -> None:
    text = REVIEW.replace("is_coordinator: false", "is_coordinator: true")
    assert not rf.load_review(_put(tmp_path, "REVIEW-a.md", text), ["A1", "A2"]).ok
    human = text.replace("model: claude-opus-5.5", "model: human")
    assert rf.load_review(_put(tmp_path, "REVIEW-human.md", human), ["A1", "A2"]).ok


def test_ready_blocked_on_accepts_known_acceptance_ids(tmp_path: Path) -> None:
    insert = (
        "blocked_on:\n  - {acceptance: A1, reason: cannot without weakening a test}\n"
    )
    text = READY.replace(
        '  - {cmd: pytest, exit: 0, tail: "3 passed"}\n---',
        '  - {cmd: pytest, exit: 0, tail: "3 passed"}\n' + insert + "---",
    )
    ready = rf.load_ready(_put(tmp_path, "READY-x.md", text), "M1.1", acceptance_ids=["A1", "A2"])
    assert ready.ok, ready.errors
    assert ready.data["blocked_on"][0]["acceptance"] == "A1"


def test_ready_blocked_on_rejects_unknown_acceptance_id(tmp_path: Path) -> None:
    insert = "blocked_on:\n  - {acceptance: A9, reason: stuck}\n"
    text = READY.replace(
        '  - {cmd: pytest, exit: 0, tail: "3 passed"}\n---',
        '  - {cmd: pytest, exit: 0, tail: "3 passed"}\n' + insert + "---",
    )
    ready = rf.load_ready(_put(tmp_path, "READY-x.md", text), "M1.1", acceptance_ids=["A1", "A2"])
    assert not ready.ok
    assert any("blocked_on: A9 not in the brief" in e for e in ready.errors)


@pytest.mark.parametrize("mode", [*rf.REVIEW_LAUNCH_MODES, None])
def test_review_launch_mode_is_optional_and_one_of_three(tmp_path: Path, mode: str | None) -> None:
    text = REVIEW.replace("is_coordinator: false\n", f"is_coordinator: false\nlaunch_mode: {mode}\n") if mode else REVIEW
    r = rf.load_review(_put(tmp_path, "REVIEW-m.md", text), ["A1", "A2"])
    assert r.ok, r.errors
    assert r.data.get("launch_mode") == mode
    bad = REVIEW.replace("is_coordinator: false\n", "is_coordinator: false\nlaunch_mode: trusted\n")
    assert any("launch_mode" in e for e in rf.load_review(_put(tmp_path, "REVIEW-b.md", bad)).errors)


def test_review_record_stores_launch_mode_and_status_prints_it(tmp_path: Path, capsys) -> None:
    import json

    from specy_road.bundled_scripts import review_cli
    from tests.support.review import make_review_repo, review_text, git

    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: opus, family: anthropic, roles: [reviewer]}\n"))
    notes = tmp_path / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))

    def run(*args: str) -> int:
        with pytest.raises(SystemExit) as e:
            review_cli.main([*args, "--repo-root", str(repo)])
        return e.value.code

    assert run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve", "--file", str(notes),
               "--launch-mode", "bare") == 0
    assert rf.load_review(rf.review_path(repo, "M1.1", "opus")).data["launch_mode"] == "bare"
    capsys.readouterr()
    run("handoff", "status", "M1.1")
    assert "REVIEW-opus.md: approve by opus (anthropic), launch mode bare" in capsys.readouterr().out
    run("handoff", "status", "M1.1", "--json")
    assert json.loads(capsys.readouterr().out)["nodes"][0]["reviews"][0]["launch_mode"] == "bare"
    with pytest.raises(SystemExit):   # argparse: only the three modes
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                         "--file", str(notes), "--launch-mode", "trusted"])


def test_claude_code_reviewer_without_channels_cli_runs_bare(tmp_path: Path, capsys, monkeypatch) -> None:
    from specy_road.bundled_scripts import role_prompt
    from specy_road.orchestration.workers.worker_adapters import STDIN_INSTRUCTION
    from tests.support.review import review_output, git
    from tests.support.cli import run_main

    repo = claude_code_reviewer_repo(tmp_path)
    secret = "sk-ant-m15-2-do-not-print"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)   # bare only with a key; isolate from the developer environment
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-claude-config"))
    answer = review_output(git(repo, "rev-parse", "HEAD"), model="opus")
    calls = fake_reviewer_run(monkeypatch, [json.dumps({"type": "result", "subtype": "success", "result": "done",
                                                "structured_output": answer})])
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 0
    call = next(c for c in calls if list(c["cmd"][:2]) == ["claude", "-p"])   # the reviewer launch, by its argv
    argv = call["cmd"]
    assert argv[:2] == ["claude", "-p"] and "--bare" in argv
    assert argv[argv.index("--add-dir") + 1] == str(rf.reviews_dir(repo, "M1.1"))
    level = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")[1].effort("reviewer")
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5" and argv[argv.index("--effort") + 1] == level
    # Nothing re-enables the repository's settings, hooks or MCP servers that --bare turns off.
    assert not {"--settings", "--setting-sources", "--mcp-config", "--plugin-dir"} & set(argv)
    # M8.3 A2/A4: no file-writing tool; bare fires no hook, so the deny list sits beside the allowed tools; argv pinned.
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["title"] == "specy-road reviewer output" and "notes" in schema["required"]
    assert argv == ["claude", "-p", STDIN_INSTRUCTION, "--bare", "--session-id", argv[5], "--output-format",
                    "stream-json", "--verbose", "--model", "claude-opus-5-5", "--effort", level,
                    "--allowedTools", "Read,Glob,Grep,Bash", "--disallowedTools", "Write", "Edit", "NotebookEdit",
                    "Bash(git commit *)", "Bash(git push *)", "Bash(gh *)",
                    "--json-schema", argv[argv.index("--json-schema") + 1],
                    "--add-dir", str(rf.reviews_dir(repo, "M1.1"))]
    prompt = repo / "work" / "prompt-M1.1-reviewer-opus.md"
    assert call["input"] == prompt.read_text() and call["cwd"] == repo
    assert "**specy-road files your record.**" in call["input"]
    captured = capsys.readouterr()
    err = captured.err
    assert "--bare" in err and "ANTHROPIC_API_KEY" in err and "recorded: " in err
    assert secret not in err and secret not in captured.out
    assert secret not in " ".join(call["cmd"]) and secret not in (call.get("input") or "")
    run = json.loads((rf.reviews_dir(repo, "M1.1") / "RUN-opus.json").read_text())
    assert run["launch_mode"] == "bare" and secret not in json.dumps(run)
    log = (rf.reviews_dir(repo, "M1.1") / "RUN-opus.log").read_text()
    assert secret not in log
    # M8.3 A1: specy-road filed the record from the structured output, launch mode included.
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["launch_mode"] == "bare" and rec.data["family"] == "anthropic"
    assert "## Findings" in rec.body and len(rf.list_review_history(repo, "M1.1")) == 1


def test_claude_code_reviewer_with_channels_cli_runs_it_as_written(tmp_path: Path, capsys, monkeypatch) -> None:
    from specy_road.bundled_scripts import role_prompt
    from tests.support.cli import run_main

    repo = claude_code_reviewer_repo(tmp_path, '    channels: {cli: "cat {prompt} | head -1"}\n')
    calls = fake_reviewer_run(monkeypatch)
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 1   # M8.3: captured, and `cat | head` prints no verdict
    call = next(c for c in calls if list(c["cmd"][:2]) == ["sh", "-c"])     # the reviewer launch, by its argv
    assert call["cmd"][2].startswith("cat ") and "--bare" not in call["cmd"][2]
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" not in err and "rerun: rerun requested" in err


def test_reviewer_prompt_asks_for_launch_mode(tmp_path: Path) -> None:
    from specy_road.bundled_scripts import role_prompt

    repo = claude_code_reviewer_repo(tmp_path)
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None and "Add `--launch-mode full|bare|explicit` to that `review record` command" in text
    assert "--launch-mode" not in role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]



# --- F6 -------------------------------------------------------------------

def _ready(repo: Path, name: str, *, node_id: str = "M1.1", branch: str = "feature/rm-thing") -> Path:
    t = resolve_target(repo, "M1.1")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(f"---\nnode_id: {node_id}\nagent: x\nbranch: {branch}\ncommit: '{t.commit}'\n"
                 f"base: '{t.base}'\nchanged_paths: [src/a.py]\nverify:\n  - {{cmd: 'echo hi', exit: 0, tail: hi}}\n---\n")
    return p



# Evidence the gate, the packet and reconcile rely on.
# A rename or copy into a touch zone is also a change outside it, in `worker reconcile`, the
# review packet and the finish-time check.
# A READY under `work/reviews/<node>/` naming another node or branch never feeds `handoff status`,
# the packet or completion.
# The Markdown notes are bound to the signed front matter (`notes_sha256`); `verify` rejects a
# mismatched identity on its own; the packet labels committed, working-tree and missing summaries
# distinctly.
# A wrong `--sign-key` on the interactive human approval writes nothing and the reason is printed.

def test_a_ready_for_another_node_or_branch_is_invalid_here(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _ready(repo, "READY-wrong.md", node_id="M9.9", branch="feature/other")
    assert latest_ready(repo, "M1.1") is None
    st = review_cli._node_status(repo, "M1.1")
    assert st["state"] == "waiting"
    assert any("node_id is 'M9.9', not 'M1.1'" in e for r in st["ready"] for e in r["errors"])
    assert "READY-wrong.md" not in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    # Right node, wrong branch: still not this node's hand-off.
    _ready(repo, "READY-wrong.md", branch="feature/other")
    assert latest_ready(repo, "M1.1", "feature/rm-thing") is None
    assert "branch is 'feature/other', not the registered 'feature/rm-thing'" in review_cli._node_status(repo, "M1.1")["ready"][0]["errors"][0]
    _ready(repo, "READY-right.md")
    assert latest_ready(repo, "M1.1", "feature/rm-thing").path.name == "READY-right.md"
    assert review_cli._node_status(repo, "M1.1")["state"] == "in-review"



# One test per finding: a prompt containing `<prompt>` cannot break out of the shell quoting; the
# session id chosen up front survives the spawn; a completed worker can take a review `block` as a
# message and a turn's READY is judged against that turn; a linked worktree gets the brief; the
# guard scopes tree-only commands to this worktree and sees `checkout -f`, `restore <path>`, brace
# groups, `eval` and `$(…)`; an op id is bound to its target; handoff refuses a closed worker;
# hook prompts are attributed by line, not by second; adopt refuses a duplicate; reconcile treats
# an unbuildable prompt as a contract change; Codex resume keeps its sandbox; reviews_root stays
# inside a nested project; the CGNAT range is off-host.

def test_reviews_root_stays_inside_a_nested_project(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    nested = repo / "sr"
    nested.mkdir()
    assert reviews_root(nested) == nested / "work" / "reviews"
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    assert reviews_root(wt) == repo.resolve() / "work" / "reviews"
    (wt / "sr").mkdir()
    assert reviews_root(wt / "sr") == repo.resolve() / "sr" / "work" / "reviews"
