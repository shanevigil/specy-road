"""M11.24: a worktree executor can reach the main checkout's ``work/reviews/<ID>`` (default ``--add-dir``, ``{reviews_dir}``)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_worker_m310_reconcile_status import nested_project

from specy_road import worker_adapters as wa
from specy_road.review_files import reviews_dir


@pytest.fixture
def linked(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """``(git root, project root, linked worktree, prompt file)``."""
    top, project = nested_project(tmp_path)
    git(top, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(top, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    prompt = project / "work" / "prompt-M1.1-executor-x.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("x\n")
    return top, project, wt, prompt


def _added(argv: list[str]) -> str | None:
    return argv[argv.index("--add-dir") + 1] if "--add-dir" in argv else None


@pytest.mark.parametrize("harness", ["claude-code", "codex", "cursor"])
def test_default_launch_adds_the_handoff_dir_only_in_a_linked_worktree(linked, harness: str) -> None:
    top, project, wt, prompt = linked
    a = wa.adapter_for(harness)
    assert _added(a.launch(prompt, wt, "m", None, node_id="M1.1", repo_root=project).argv) == str(
        reviews_dir(project, "M1.1"))
    assert _added(a.launch(prompt, top, "m", None, node_id="M1.1", repo_root=project).argv) is None


@pytest.mark.parametrize("harness, expected", [("claude-code", True), ("cursor", True), ("codex", False)])
def test_default_resume_adds_the_handoff_dir_where_the_harness_documents_it(linked, harness: str, expected: bool) -> None:
    _top, project, wt, prompt = linked
    argv = wa.adapter_for(harness).resume("abc", prompt, wt, "m", None, node_id="M1.1", repo_root=project).argv
    assert _added(argv) == (str(reviews_dir(project, "M1.1")) if expected else None)


def test_claude_add_dir_does_not_swallow_the_stdin_instruction(linked) -> None:
    """``--add-dir`` takes several values in Claude Code: an option must follow it, not the instruction."""
    _top, project, wt, prompt = linked
    a = wa.adapter_for("claude-code")
    for argv in (a.launch(prompt, wt, "m", None, node_id="M1.1", repo_root=project).argv,
                 a.resume("abc", prompt, wt, "m", None, node_id="M1.1", repo_root=project).argv):
        assert argv[argv.index("--add-dir") + 2].startswith("--")
        assert argv[-1] == wa.STDIN_INSTRUCTION


@pytest.mark.parametrize("harness", ["claude-code", "codex", "cursor", "generic"])
@pytest.mark.parametrize("word", ["{reviews_dir}", '"{reviews_dir}"', "'{reviews_dir}'"])
def test_custom_cli_receives_the_handoff_dir_as_one_argument(linked, harness: str, word: str) -> None:
    _top, project, wt, prompt = linked
    cli = f"printf '%s\\n' --add-dir {word} {{prompt}}"
    launch = wa.adapter_for(harness).launch(prompt, wt, "m", cli, node_id="M1.1", repo_root=project)
    out = subprocess.run(launch.argv, capture_output=True, text=True, check=True).stdout.splitlines()
    assert out == ["--add-dir", str(reviews_dir(project, "M1.1")), str(prompt)]


def test_custom_cli_resume_receives_the_handoff_dir(linked) -> None:
    _top, project, wt, prompt = linked
    cli = "printf '%s\\n' {session_flag} --add-dir {reviews_dir} {prompt}"
    launch = wa.adapter_for("claude-code").resume("abc", prompt, wt, "m", cli, node_id="M1.1", repo_root=project)
    out = subprocess.run(launch.argv, capture_output=True, text=True, check=True).stdout.splitlines()
    assert out == ["--resume", "abc", "--add-dir", str(reviews_dir(project, "M1.1")), str(prompt)]


@pytest.mark.parametrize("cli, node_id", [
    ("run --add-dir={reviews_dir} {prompt}", "M1.1"),   # part of a larger word: its quoting would land inside it
    ("run --add-dir {reviews_dir} {prompt}", None),     # no leaf to resolve the directory for
])
def test_custom_cli_reviews_dir_is_refused_when_it_cannot_be_substituted(linked, cli: str, node_id: str | None) -> None:
    _top, project, wt, prompt = linked
    with pytest.raises(wa.Unsupported, match=r"\{reviews_dir\}"):
        wa.adapter_for("codex").launch(prompt, wt, "m", cli, node_id=node_id, repo_root=project)
