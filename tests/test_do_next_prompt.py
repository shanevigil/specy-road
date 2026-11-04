"""Tests for do_next_prompt."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import do_next_prompt as dnp
from specy_road.bundled_scripts import role_prompt
from tests.test_models_and_prompt import commit_profile, make_profile_repo


def test_write_agent_prompt_includes_leaf_execution_contract(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    brief_path = repo_root / "work" / "brief-M1.1.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# brief\n", encoding="utf-8")

    nodes = [
        {
            "id": "M1",
            "type": "phase",
            "title": "Parent",
            "status": "In Progress",
            "node_key": "11111111-1111-4111-8111-111111111111",
        },
        {
            "id": "M1.1",
            "type": "milestone",
            "title": "Leaf",
            "status": "Not Started",
            "parent_id": "M1",
            "codename": "leaf-node",
            "node_key": "22222222-2222-4222-8222-222222222222",
        },
    ]
    (repo_root / "roadmap").mkdir()
    (repo_root / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n"
        "require_implementation_review_before_finish: true\n",
        encoding="utf-8",
    )
    out = dnp.write_agent_prompt(
        nodes[1],
        nodes,
        brief_path,
        repo_root=repo_root,
        work_dir=repo_root / "work",
        on_complete="pr",
    )
    text = out.read_text(encoding="utf-8")
    assert "## Execution Target" in text
    assert "**Execution Target (leaf):** `M1.1`" in text
    assert "## Ancestor Context Chain" in text
    assert "## Derived Rollup Semantics" in text
    # Same rules as `prompt --role executor`; no unconditional hook claim.
    assert "ending with an `## Added` inventory" in text
    assert "`git commit --only <paths>`), never `-A`, `-a`" in text
    assert "If this repo has a pre-commit hook" in text
    assert "the pre-commit hook validates" not in text
    # M10.11: the harness-subagent paragraph, unconditionally (no model is known at pickup).
    assert "\n\n" + dnp.SUBAGENT_LINE + "\n" in text


def test_executor_prompt_has_the_subagent_paragraph_only_when_the_profile_says_yes(tmp_path: Path) -> None:
    """M10.11 A2: `prompt --role executor` repeats the pickup paragraph, gated on `access.subagents`."""
    repo = make_profile_repo(tmp_path)
    assert dnp.SUBAGENT_LINE in role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]   # "yes Vendor…"
    assert dnp.SUBAGENT_LINE not in role_prompt.build_prompt(repo, "M1.1", role="coordinator", model="opus")[0]
    prof_path = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    for value, expected in (("unknown No data found", False), ("yes", True), ("no", False)):   # bare yes/no: YAML bools
        text = prof_path.read_text()
        line = next(ln for ln in text.splitlines() if ln.startswith("  subagents:"))
        prof_path.write_text(text.replace(line, f"  subagents: {value}", 1))
        commit_profile(repo)
        assert (dnp.SUBAGENT_LINE in role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")[0]) is expected, value
