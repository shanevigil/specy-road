"""M21.44: a model whose profile records guidance bypass (composer-2.5) is kept out of the executor and reviewer roles
while ``policy.signed_reviews`` is on, unless its committed roster entry sets ``allow_guidance_bypass_model: true``.

Public CLI only: ``orchestrate plan``, ``worker delegate``, ``review delegate``, ``prompt``, ``handoff status``,
``review record``, ``validate``, ``doctor`` and ``models show``, on temp repos whose roster and profiles are committed
on the integration branch (``dev``). A fake harness touches ``HARNESS-RAN`` and the roster ``preflight`` touches
``PREFLIGHT-RAN``, so a refusal is shown to have launched nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.review_delegate_helpers import run_review_cli
from tests.helpers import REPO
from tests.review_repo_helpers import git, make_review_repo, review_text
from tests.worker_cli_helpers import run_worker_cli, wait_for_worker

from specy_road import cli
from specy_road.bundled_scripts import chore_cli, models_cli, orchestrate_cli, role_prompt
from specy_road.model_profiles import bundled_profiles_root

BUNDLED = bundled_profiles_root() / "model-profiles" / "cursor-composer"
COMPOSER = "model-profiles/cursor-composer/composer-2.5.md"
EXCLUDED = ("is excluded from executor and reviewer roles while policy.signed_reviews is on: its profile records "
            "guidance bypass observed (2026-11-06, cursor: ")
OPT_IN_HINT = "Set allow_guidance_bypass_model: true on its roster entry to use it at your own risk."
WARNED = ("opted in at its own risk: its profile records guidance bypass observed (2026-11-06, cursor)")
DUMMY_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDummyKeyForRosterRowsOnly0000000000000"

# Prints a stream-json turn and touches HARNESS-RAN next to the repo: the harness ran.
HARNESS = '''
import json, pathlib, sys
pathlib.Path(sys.argv[1]).touch()
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1", "model": "fake"}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "result": "done", "session_id": "s-1"}), flush=True)
'''


def roster(*, signed: bool = True, opt_in: bool = False, rid: str = "composer-2.5", extra: str = "",
           cli: str = "{harness}", roles: str = "[executor, reviewer]", key: str = DUMMY_KEY,
           harness: str = "generic") -> str:
    """human (coordinator, reviewer), the entry under test, and an unflagged executor and reviewer ``sol``."""
    opt = "\n    allow_guidance_bypass_model: true" if opt_in else ""
    return ("version: 1\nroster:\n"
            "  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - id: {rid}\n    family: cursor\n    roles: {roles}\n    harness: {harness}\n"
            f"    channels: {{cli: '{cli}'}}\n    preflight: 'touch ../PREFLIGHT-RAN'\n"
            f"    public_key: '{key}'{opt}{extra}\n"
            f"  - {{id: sol, family: openai, roles: [executor, reviewer], public_key: '{DUMMY_KEY}'}}\n"
            f"policy: {{reviewers_required: 1, signed_reviews: {'true' if signed else 'false'}}}\n")


def guidance_repo(tmp_path: Path, orchestration: str, *, profile: str | None = None) -> Path:
    """A claimed leaf M1.1 whose roster (and ``profile``, a text for ``COMPOSER``) is committed on ``dev``."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "harness.py").write_text(HARNESS)
    harness = f"{sys.executable} {tmp_path / 'harness.py'} {tmp_path / 'HARNESS-RAN'} {{prompt}}"
    repo = make_review_repo(tmp_path, orchestration=orchestration.replace("{harness}", harness))
    (repo / ".gitignore").write_text("work/\n")
    if profile is not None:
        (repo / COMPOSER).parent.mkdir(parents=True)
        (repo / COMPOSER).write_text(profile)
    on_dev(repo, "ignore work, profile")
    (repo / "work" / "reviews" / "M1.1").mkdir(parents=True)
    (repo / "work" / "reviews" / "M1.1" / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    return repo


def on_dev(repo: Path, msg: str) -> None:
    """Commit the working tree on the leaf branch and move ``dev`` (the integration branch) there."""
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)
    git(repo, "update-ref", "refs/heads/dev", "HEAD")


def unflagged(text: str) -> str:
    """The bundled composer-2.5 profile without its ``guidance_bypass_observed`` block."""
    head, rest = text.split("guidance_bypass_observed:\n", 1)
    return head + rest[rest.index("role_fit:"):]


def launched(tmp_path: Path) -> tuple[bool, bool]:
    return (tmp_path / "PREFLIGHT-RAN").exists(), (tmp_path / "HARNESS-RAN").exists()


def main_exit(main, *args: str) -> int:
    try:
        main(list(args))
    except SystemExit as e:
        return e.code or 0
    return 0


def plan(tmp_path: Path, orchestration: str, capfd) -> dict:
    """``orchestrate plan --json``'s assignment for M1.1, unclaimed in a repo of its own (the planner skips claims)."""
    repo = guidance_repo(tmp_path / "plan", orchestration)
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(chunk.read_text().replace('"status": "In Progress"', '"status": "Not Started"'))
    on_dev(repo, "ready")
    capfd.readouterr()
    main_exit(orchestrate_cli.main, "orchestrate", "plan", "--json", "--repo-root", str(repo))
    return json.loads(capfd.readouterr().out)["batches"][0][0]


def prompt(repo: Path, role: str, *extra: str, model: str = "composer-2.5") -> int:
    return main_exit(role_prompt.main, "M1.1", "--model", model, "--role", role, *extra, "--repo-root", str(repo))


def worker_delegate(repo: Path, *extra: str) -> int:
    return run_worker_cli("worker", "delegate", "M1.1", "--model", "composer-2.5", *extra, "--repo-root", str(repo))


def review_delegate(repo: Path, *extra: str) -> int:
    return run_review_cli("review", "delegate", "M1.1", "--model", "composer-2.5", "--backoff", "0", *extra,
                          "--repo-root", str(repo)) or 0


def checks(repo: Path, capfd, monkeypatch) -> tuple[str, str]:
    """``validate`` and ``doctor`` stderr (``validate`` runs as a subprocess of this checkout)."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    capfd.readouterr()
    main_exit(cli.main, "validate", "--repo-root", str(repo))
    v = capfd.readouterr().err
    main_exit(cli.main, "doctor", "--repo-root", str(repo))
    return v, capfd.readouterr().err


# ---- the decision table: flag x signed_reviews x opt-in, per role ----

@pytest.mark.parametrize("flagged, signed", [(False, False), (False, True), (True, False)])
def test_unchanged_unless_a_flagged_model_meets_signed_reviews(tmp_path: Path, capfd, monkeypatch, flagged: bool,
                                                                 signed: bool) -> None:
    rid = "composer-2.5" if flagged else "composer-2"
    orchestration = roster(signed=signed, rid=rid)
    repo = guidance_repo(tmp_path, orchestration)
    a = plan(tmp_path, orchestration, capfd)
    assert a["executor"] == rid and not any("guidance bypass" in n for n in a["notes"])
    assert prompt(repo, "reviewer", model=rid) == 0
    assert "guidance bypass" not in capfd.readouterr().err
    v, d = checks(repo, capfd, monkeypatch)
    assert "allow_guidance_bypass_model" not in v + d and "opted in" not in v + d
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", rid, "--json", "--repo-root", str(repo)) == 0
    out, err = capfd.readouterr()
    wait_for_worker(repo, json.loads(out)["worker_id"])
    assert "guidance bypass" not in err and launched(tmp_path) == (True, True)


def test_flagged_model_is_refused_as_executor_and_reviewer_under_signed_reviews(tmp_path: Path, capfd, monkeypatch) -> None:
    repo = guidance_repo(tmp_path, roster())
    a = plan(tmp_path, roster(), capfd)
    assert a["executor"] == "sol" and "composer-2.5" not in a["reviewers"]
    assert any(EXCLUDED in n and OPT_IN_HINT in n for n in a["notes"])
    for role in ("executor", "reviewer", "rca"):
        assert prompt(repo, role) == 1
        err = capfd.readouterr().err
        assert "composer-2.5 (model composer-2.5) " + EXCLUDED in err and OPT_IN_HINT in err
    assert prompt(repo, "executor", "--channel", "cli", "--run") == 1
    assert EXCLUDED in capfd.readouterr().err
    assert worker_delegate(repo) == 1
    assert EXCLUDED in capfd.readouterr().err
    assert review_delegate(repo) == 1
    assert EXCLUDED in capfd.readouterr().err
    assert launched(tmp_path) == (False, False)
    v, d = checks(repo, capfd, monkeypatch)
    line = ("warning: composer-2.5 (model composer-2.5) is excluded: set allow_guidance_bypass_model: true on its "
            "roster entry to use it at your own risk")
    assert v.count(line) == 1 and d.count(line) == 1


def test_opted_in_flagged_model_is_used_and_warns_once_per_launch(tmp_path: Path, capfd, monkeypatch) -> None:
    repo = guidance_repo(tmp_path, roster(opt_in=True))
    a = plan(tmp_path, roster(opt_in=True), capfd)
    assert a["executor"] == "composer-2.5" and any(WARNED in n for n in a["notes"])
    assert prompt(repo, "reviewer") == 0
    assert "guidance bypass" not in capfd.readouterr().err   # writing a prompt launches nothing
    assert worker_delegate(repo, "--json") == 0
    out, err = capfd.readouterr()
    wait_for_worker(repo, json.loads(out)["worker_id"])
    assert err.count("warning: composer-2.5 (model composer-2.5) " + WARNED) == 1
    assert launched(tmp_path) == (True, True)
    v, d = checks(repo, capfd, monkeypatch)
    line = "warning: composer-2.5 (model composer-2.5) opted in at its own risk"
    assert v.count(line) == 1 and d.count(line) == 1


def test_opted_in_reviewer_and_prompt_run_warn_once_per_launch(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster(opt_in=True))
    review_delegate(repo)
    assert capfd.readouterr().err.count(WARNED) == 1
    assert launched(tmp_path) == (True, True)
    prompt(repo, "executor", "--channel", "cli", "--run")
    assert capfd.readouterr().err.count(WARNED) == 1


def test_multi_role_entry_stays_coordinator_without_a_warning(tmp_path: Path, capfd) -> None:
    orchestration = roster(roles="[coordinator, executor, reviewer]").replace(
        "{id: human, family: human, roles: [coordinator, reviewer]}", "{id: human, family: human, roles: [reviewer]}")
    repo = guidance_repo(tmp_path, orchestration)
    a = plan(tmp_path, orchestration, capfd)
    assert a["coordinator"] == "composer-2.5" and a["executor"] == "sol"
    assert prompt(repo, "coordinator") == 0
    assert "guidance bypass" not in capfd.readouterr().err
    repo2 = guidance_repo(tmp_path / "in", roster(roles="[coordinator, executor, reviewer]", opt_in=True))
    assert prompt(repo2, "coordinator", "--channel", "cli", "--run") == 0
    assert "guidance bypass" not in capfd.readouterr().err


# ---- which copy of the profile flags, and which model an entry launches ----

def test_flag_only_on_the_bundled_profile_still_flags(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster(), profile=unflagged((BUNDLED / "composer-2.5.md").read_text()))
    assert prompt(repo, "executor") == 1
    assert EXCLUDED in capfd.readouterr().err


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not available")
@pytest.mark.parametrize("how", ["feature branch", "working tree"])
@pytest.mark.parametrize("change", ["removed", "malformed"])
def test_a_branch_or_drifted_copy_never_clears_a_committed_flag(tmp_path: Path, capfd, how: str,
                                                                 change: str) -> None:
    """A model no bundled profile names, flagged only in the profile committed on ``dev``."""
    key, pub = make_key(tmp_path, "my-model")
    text = (BUNDLED / "composer-2.5.md").read_text().replace("composer-2.5", "my-model")
    repo = guidance_repo(tmp_path, roster(rid="my-model", key=pub), profile=text)
    git(repo, "mv", COMPOSER, "model-profiles/cursor-composer/my-model.md")
    on_dev(repo, "rename the profile")
    copy = unflagged(text) if change == "removed" else text.replace("  harness: cursor\n", "  harness: vscode\n")
    (repo / "model-profiles" / "cursor-composer" / "my-model.md").write_text(copy)
    if how == "feature branch":
        git(repo, "commit", "-qam", "drop the flag on the leaf branch")
    sign_approval(repo, key, "my-model")
    node = status(repo, capfd)
    assert not [r for r in node["reviews"] if r["model"] == "my-model"] and not node["policy_met"]
    row = next(r for r in node["reviewer_eligibility"] if r["model"] == "my-model")
    assert not row["eligible"] and "my-model (model my-model) " + EXCLUDED in row["reason"]


@pytest.mark.parametrize("extra, cli, rid", [
    ("\n    harness_model: composer-2.5", "{harness}", "my-cursor"),
    ("", "agent -p --model composer-2.5 {prompt}", "my-cursor"),
    ("", "{harness}", "composer-2.5-fast"),
])
def test_every_model_an_entry_launches_is_matched(tmp_path: Path, capfd, extra: str, cli: str, rid: str) -> None:
    profile = unflagged((BUNDLED / "composer-2.5.md").read_text()).replace("composer-2.5", "my-cursor")
    repo = guidance_repo(tmp_path, roster(rid=rid, extra=extra, cli=cli), profile=profile)
    assert prompt(repo, "executor", model=rid) == 1
    err = capfd.readouterr().err
    assert EXCLUDED in err and f"{rid} (model composer-2.5" in err


def test_composer_2_is_not_flagged(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster(rid="composer-2"))
    assert prompt(repo, "executor", model="composer-2") == 0
    assert "guidance bypass" not in capfd.readouterr().err


# ---- chores, resume, local roster ----

@pytest.mark.parametrize("review", [False, True])
def test_chore_executor_and_reviewer_are_refused_before_preflight_and_harness(tmp_path: Path, capfd,
                                                                               review: bool) -> None:
    repo = guidance_repo(tmp_path, roster())
    start = ["chore", "start", "fix-env", "--task", "Repair the env", "--zone", "src", "--model", "composer-2.5",
             "--harness", "generic", *(["--review"] if review else []), "--repo-root", str(repo)]
    assert main_exit(chore_cli.main, *start) == 0
    capfd.readouterr()
    if review:
        code = run_review_cli("review", "delegate", "fix-env", "--model", "composer-2.5", "--repo-root", str(repo))
    else:
        code = run_worker_cli("worker", "delegate", "fix-env", "--repo-root", str(repo))
    assert code == 1 and EXCLUDED in capfd.readouterr().err
    assert launched(tmp_path) == (False, False)


def test_worker_and_review_resume_are_refused(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster(signed=False, harness="claude-code"))   # generic cannot resume
    assert worker_delegate(repo, "--json") == 0
    wid = json.loads(capfd.readouterr().out)["worker_id"]
    wait_for_worker(repo, wid)
    roster_file = repo / "roadmap" / "orchestration.yaml"
    roster_file.write_text(roster_file.read_text().replace("signed_reviews: false", "signed_reviews: true"))
    on_dev(repo, "signed reviews on")
    (tmp_path / "PREFLIGHT-RAN").unlink()
    (tmp_path / "HARNESS-RAN").unlink()
    capfd.readouterr()
    assert run_worker_cli("worker", "resume", wid, "--repo-root", str(repo)) == 1
    assert EXCLUDED in capfd.readouterr().err
    assert review_delegate(repo, "--resume") == 1
    assert EXCLUDED in capfd.readouterr().err
    assert launched(tmp_path) == (False, False)


def test_local_roster_add_may_not_opt_in(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster())
    (repo / "roadmap" / "orchestration.local.yaml").write_text(
        "roster_add:\n  - {id: composer-2.5-fast, family: cursor, roles: [executor], "
        "allow_guidance_bypass_model: true}\n")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "composer-2.5-fast",
                          "--repo-root", str(repo)) == 1
    assert "sets allow_guidance_bypass_model, which counts only on the committed roster" in capfd.readouterr().err
    assert launched(tmp_path) == (False, False)


# ---- the gate and handoff status ----

def make_key(tmp_path: Path, name: str) -> tuple[Path, str]:
    key = tmp_path / f"{name}_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    return key, Path(f"{key}.pub").read_text().strip()


def sign_approval(repo: Path, key: Path, model: str = "composer-2.5") -> None:
    """A valid approval at HEAD, signed with the roster entry's key."""
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))
    assert run_review_cli("review", "record", "M1.1", "--model", model, "--verdict", "approve",
                          "--file", str(notes), "--sign-key", str(key), "--repo-root", str(repo)) in (0, None)


def status(repo: Path, capfd) -> dict:
    capfd.readouterr()
    run_review_cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capfd.readouterr().out)["nodes"][0]


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not available")
@pytest.mark.parametrize("opt_in", [False, True])
def test_gate_counts_a_signed_approval_only_from_an_opted_in_entry(tmp_path: Path, capfd, opt_in: bool) -> None:
    key, pub = make_key(tmp_path, "composer")
    repo = guidance_repo(tmp_path, roster(key=pub, opt_in=opt_in))
    sign_approval(repo, key)
    node = status(repo, capfd)
    counted = [r["model"] for r in node["reviews"]]
    assert (counted, node["policy_met"]) == ((["composer-2.5"], True) if opt_in else ([], False))
    assert (EXCLUDED in json.dumps(node["problems"])) is not opt_in


def test_handoff_status_row_and_next_step_never_offer_the_excluded_id(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster().replace("signed_reviews: true", "signed_reviews: true, max_fix_rounds: 1"))
    node = status(repo, capfd)
    row = next(r for r in node["reviewer_eligibility"] if r["model"] == "composer-2.5")
    assert not row["eligible"] and EXCLUDED in row["reason"] and OPT_IN_HINT in row["reason"]
    assert "composer-2.5" not in json.dumps(node.get("fix_round_budget") or {})


# ---- models show and malformed shapes ----

def test_models_show_prints_the_record(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster(), profile=(BUNDLED / "composer-2.5.md").read_text())
    capfd.readouterr()
    assert main_exit(models_cli.main, "models", "show", "composer-2.5", "--repo-root", str(repo)) == 0
    out = capfd.readouterr().out
    assert "- guidance bypass observed: 2026-11-06, cursor: specy-road's §9 context-regression replay" in out
    assert main_exit(models_cli.main, "models", "show", "composer-2.5", "--json", "--repo-root", str(repo)) == 0
    record = json.loads(capfd.readouterr().out)["front_matter"]["guidance_bypass_observed"]
    assert record["harness"] == "cursor" and str(record["date"]) == "2026-11-06" and "CR1" in record["evidence"]


@pytest.mark.parametrize("value", [
    "null", "[]", "{date: 2026-11-06, harness: cursor}",
    "{date: 2026-11-06, harness: cursor, evidence: x, extra: y}", "{date: '2026-02-30', harness: cursor, evidence: x}",
    "{date: 2026-11-06, harness: vscode, evidence: x}", "{date: 2026-11-06, harness: cursor, evidence: '  '}",
    "{date: 2026-11-06, harness: cursor, evidence: 3}",
])
def test_a_malformed_record_makes_the_profile_invalid(tmp_path: Path, capfd, value: str) -> None:
    text = unflagged((BUNDLED / "composer-2.5.md").read_text())   # signed_reviews off: no refusal comes first
    repo = guidance_repo(tmp_path, roster(signed=False), profile=text.replace("role_fit:", f"guidance_bypass_observed: {value}\n"
                                                                              "role_fit:", 1))
    capfd.readouterr()
    assert prompt(repo, "executor") == 1
    err = capfd.readouterr().err
    assert "profile for 'composer-2.5'" in err and "`guidance_bypass_observed`" in err and "Traceback" not in err


def test_a_non_boolean_opt_in_is_a_schema_error(tmp_path: Path, capfd) -> None:
    repo = guidance_repo(tmp_path, roster().replace("public_key:", "allow_guidance_bypass_model: 'yes'\n    public_key:", 1))
    capfd.readouterr()
    assert prompt(repo, "executor") == 1
    assert "allow_guidance_bypass_model" in capfd.readouterr().err
