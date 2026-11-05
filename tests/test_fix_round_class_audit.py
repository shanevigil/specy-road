"""M14.11: the rework section and ``worker message --fix-round`` ask for a class audit and a ``## Probes`` list."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import git
from tests.test_models_and_prompt import make_profile_repo
from tests.test_rework_findings_in_prompt import executor_prompt, file_review, stopped_worker
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import make_worker_repo

from specy_road.bundled_scripts.role_prompt_rework import CLASS_AUDIT_LINES

AUDIT = CLASS_AUDIT_LINES[0]


def test_class_audit_wording() -> None:
    for words in ("name its class (the kind of input, path or state that failed)",
                  "check every other place in the change that class can reach",
                  "prefer a design change that removes the class over patching the one instance",
                  "list what you checked under `## Probes` in the implementation summary, one line each: "
                  "what was checked, and the result"):
        assert words in AUDIT


def test_rework_section_carries_the_class_audit_after_the_findings(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "block", ["Reject a path with `..`"])
    text = executor_prompt(repo)
    rework = text[text.index("## Rework"):text.index("\n---\n", text.index("## Rework"))]
    assert rework.index("- Reject a path with `..`") < rework.index(AUDIT)


def test_no_blocking_review_means_no_class_audit(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    stopped_worker(repo, "grok", "terminated", "half done")
    text = executor_prompt(repo)
    assert "## Rework" in text and AUDIT not in text and "## Probes" not in text


def _sent(repo: Path) -> str:
    (prompt,) = sorted((repo / "work").glob("prompt-w-0001-message-*.md"))
    return prompt.read_text(encoding="utf-8")


def test_fix_round_sends_findings_audit_and_text(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    tip = git(repo, "rev-parse", "HEAD")
    file_review(repo, "sol", tip, "block", ["Cover the empty roster"])
    assert run_worker_cli("worker", "message", "w-0001", "--fix-round", "--text", "Also rerun the gate.",
                          "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    sent = _sent(repo)
    assert sent.startswith("## Fix round\n")
    assert f"### `sol` blocks `{tip}` (the branch tip)" in sent
    assert sent.index("- Cover the empty roster") < sent.index(AUDIT) < sent.index("Also rerun the gate.")
    assert sent.endswith("Also rerun the gate.\n")


def test_fix_round_without_text_and_its_refusal(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    assert run_worker_cli("worker", "message", "w-0001", "--fix-round", "--repo-root", str(repo)) == 1
    assert "no blocking review on M1.1" in capsys.readouterr().err
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "block", ["Cover the empty roster"])
    assert run_worker_cli("worker", "message", "w-0001", "--fix-round", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert _sent(repo).endswith(AUDIT + "\n")


def test_plain_message_is_sent_unchanged(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "block", ["Cover the empty roster"])
    for extra in ([], ["--no-queue"], ["--offline"]):   # argparse's own refusal, as before --fix-round existed
        assert run_worker_cli("worker", "message", "w-0001", *extra, "--repo-root", str(repo)) == 2
        err = capsys.readouterr().err
        assert err.startswith("usage: specy-road worker message") and "(--file PATH | --text TEXT)" in err
        assert err.endswith("specy-road worker message: error: one of the arguments --file --text is required\n")
    assert not list((repo / "work").glob("prompt-w-0001-message-*.md"))
    assert run_worker_cli("worker", "message", "w-0001", "--text", "also update docs", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert _sent(repo) == "also update docs"
