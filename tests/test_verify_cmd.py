"""``verify_cmd``: the bounded test command executor briefs and reviewer prompts give (M11.80)."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import git
from tests.test_models_and_prompt import make_profile_repo

from specy_road.bundled_scripts import role_prompt
from specy_road.git_workflow_config import validate_git_workflow_dict
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.verify_cmd_config import resolve_verify_cmd

CMD = "python -m pytest -n 4 -p no:cacheprovider"
CAP = "cap parallel test workers"


def _set_verify_cmd(repo: Path, cmd: str) -> None:
    gw = repo / "roadmap" / "git-workflow.yaml"
    gw.write_text(gw.read_text(encoding="utf-8") + f"verify_cmd: {cmd}\n", encoding="utf-8")


def _reviewer_prompt(repo: Path) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n\n- **Commit under review:** `abc`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    return text


def test_schema_accepts_verify_cmd() -> None:
    data = {"version": 1, "integration_branch": "main", "remote": "origin", "verify_cmd": CMD}
    assert validate_git_workflow_dict(data) is None


def test_unset_or_blank_verify_cmd_resolves_to_none(tmp_path: Path) -> None:
    assert resolve_verify_cmd(tmp_path) is None
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\nverify_cmd: '  '\n", encoding="utf-8")
    assert resolve_verify_cmd(tmp_path) is None


def test_prompts_without_verify_cmd_say_to_cap_test_workers(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    executor = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]
    reviewer = _reviewer_prompt(repo)
    for text in (executor, reviewer):
        assert CAP in text and "when other workers share this machine" in text
        assert "followed by the test paths" not in text


def test_prompts_with_verify_cmd_give_it_as_the_leaf_test_command(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    _set_verify_cmd(repo, CMD)
    git(repo, "commit", "-qam", "verify_cmd")
    executor = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]
    reviewer = _reviewer_prompt(repo)
    for text in (executor, reviewer):
        assert f"run this leaf's tests with `{CMD}` followed by the test paths" in text
        assert CAP not in text
    # the executor reads it in the brief; the reviewer, whose packet has no brief, in its preamble
    brief = executor.split("# Work-packet brief", 1)[1]
    assert f"`{CMD}`" in brief.split("## 8. Rollup semantics", 1)[0]
