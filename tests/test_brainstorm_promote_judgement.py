"""M4.1: promote carries the converge judgement into sheets and writes an authoring prompt."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts import brainstorm_promote
from specy_road.bundled_scripts.brainstorm_close import close_session, closed_dir
from specy_road.bundled_scripts.brainstorm_promote import promote_session
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    add_idea,
    prompt_path,
    write_session,
)
from specy_road.bundled_scripts.planning_sheet_bootstrap import placeholder_sheet, promote_placeholder
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _judged_session(**kw) -> BrainstormSession:
    s = BrainstormSession(slug="pay", topic="Expand payments", under="M1", **kw)
    idea = add_idea(s, title="Stored payment vault", rationale="Cuts PCI scope")
    idea.status = "accepted"
    idea.overlap = [{"node_id": "M0.1", "relation": "adjacent"},
                    {"node_id": "M0.2", "relation": "prerequisite"}]
    idea.critic = {"feasibility": "needs the token service first",
                   "value": "only large merchants gain"}
    idea.recommendation = "strong"
    idea.verdict_why = "Principle 3; overlap with M0.1 is adjacent only"
    return s


def _sheet(root: Path, node_id: str) -> str:
    node = next(n for n in load_roadmap(root)["nodes"] if n["id"] == node_id)
    return (root / node["planning_dir"]).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    body = text.split(f"## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


def test_references_list_overlaps_by_id_and_relation(repo: Path) -> None:
    node_id = promote_session(repo, _judged_session())[0].node_id

    refs = _section(_sheet(repo, node_id), "References")

    assert "- Overlaps existing node M0.1 (adjacent)" in refs
    assert "- Overlaps existing node M0.2 (prerequisite)" in refs
    assert f"Roadmap chunk for `{node_id}`" in refs


def test_approach_lists_critics_and_verdict_as_constraints(repo: Path) -> None:
    node_id = promote_session(repo, _judged_session())[0].node_id

    approach = _section(_sheet(repo, node_id), "Approach")

    assert "Constraints from the brainstorm's converge pass:" in approach
    assert "- feasibility critic: needs the token service first" in approach
    assert "- value critic: only large merchants gain" in approach
    assert "- Verdict (strong): Principle 3; overlap with M0.1 is adjacent only" in approach
    assert approach.strip().endswith(promote_placeholder(node_id))


def test_approach_is_only_the_placeholder_without_critics_or_verdict(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    add_idea(s, title="Plain idea", rationale="r").status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    approach = _section(_sheet(repo, node_id), "Approach")
    assert "converge pass" not in approach
    assert approach.strip() == promote_placeholder(node_id)


def test_the_seeded_sheet_still_counts_as_unauthored(repo: Path) -> None:
    """The judgement is input for the author; pickup must still skip the leaf."""
    node_id = promote_session(repo, _judged_session(), node_type="task")[0].node_id

    node = next(n for n in load_roadmap(repo)["nodes"] if n["id"] == node_id)
    assert placeholder_sheet(repo, node) is not None


def test_the_anchor_sheet_gains_the_recorded_frame(repo: Path) -> None:
    s = _judged_session(frame={"problem": "checkout drops", "who": "returning buyers"})

    promote_session(repo, s)

    frame = _section(_sheet(repo, "M1"), "Brainstorm frame")
    assert "brainstorm session `pay`" in frame
    assert "- **problem:** checkout drops" in frame
    assert "- **who:** returning buyers" in frame


def test_a_second_promote_replaces_the_frame_section(repo: Path) -> None:
    s = _judged_session(frame={"problem": "checkout drops"})
    promote_session(repo, s)
    s.frame = {"problem": "refunds are slow"}
    add_idea(s, title="Second idea", rationale="r").status = "accepted"

    promote_session(repo, s)

    text = _sheet(repo, "M1")
    assert text.count("## Brainstorm frame") == 1
    assert "refunds are slow" in text and "checkout drops" not in text
    assert text.endswith("\n")


def test_no_frame_leaves_the_anchor_sheet_alone(repo: Path) -> None:
    before = _sheet(repo, "M1")

    promote_session(repo, _judged_session())

    assert _sheet(repo, "M1") == before


def test_a_dry_run_writes_no_frame(repo: Path) -> None:
    before = _sheet(repo, "M1")

    promote_session(repo, _judged_session(frame={"problem": "x"}), dry_run=True)

    assert _sheet(repo, "M1") == before


def test_promote_writes_the_authoring_prompt(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = _judged_session(frame={"problem": "checkout drops"})
    add_idea(s, title="Second idea", rationale="Another bet").status = "accepted"

    results = promote_session(repo, s)

    path = prompt_path(repo, "pay", "authoring")
    assert path.name == "brainstorm-pay-authoring-prompt.md"
    text = path.read_text(encoding="utf-8")
    nodes = {n["id"]: n for n in load_roadmap(repo)["nodes"]}
    for r in results:
        assert f"`{r.node_id}` {r.title} (from {r.idea_id}" in text
        assert nodes[r.node_id]["planning_dir"] in text
    for asked in ("**Approach:**", "**Tasks / checklist:**", "**Acceptance:**",
                  "**Touch zones:**", "**References:**"):
        assert asked in text
    assert "- feasibility critic: needs the token service first" in text
    assert "- Overlaps existing node M0.1 (adjacent)" in text
    assert "- **problem:** checkout drops" in text
    assert "work/brainstorm-pay.yaml" in text
    assert "authoring prompt: work/brainstorm-pay-authoring-prompt.md" in capsys.readouterr().err


def test_a_dry_run_writes_no_authoring_prompt(repo: Path) -> None:
    promote_session(repo, _judged_session(), dry_run=True)

    assert not prompt_path(repo, "pay", "authoring").exists()


def test_a_failed_validation_writes_no_authoring_prompt_or_frame(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _sheet(repo, "M1")

    def boom(_root: Path) -> None:
        raise RuntimeError("validate failed")

    monkeypatch.setattr(brainstorm_promote, "run_validate_raise", boom)
    with pytest.raises(RuntimeError):
        promote_session(repo, _judged_session(frame={"problem": "x"}))

    assert not prompt_path(repo, "pay", "authoring").exists()
    assert _sheet(repo, "M1") == before


def test_close_archives_the_authoring_prompt_with_its_session(repo: Path) -> None:
    root = repo.resolve()
    s = _judged_session()
    promote_session(root, s)
    write_session(root, s)

    close_session(root, "pay")

    assert not prompt_path(root, "pay", "authoring").exists()
    assert (closed_dir(root) / "brainstorm-pay-authoring-prompt.md").is_file()
    assert (closed_dir(root) / "brainstorm-pay.yaml").is_file()
