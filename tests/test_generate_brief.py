"""Tests for generate_brief."""

from __future__ import annotations

import subprocess
import sys

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

from specy_road.bundled_scripts import generate_brief as gb


def test_render_brief_m02_contains_title() -> None:
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.2", by_id)
    assert "Roadmap validator in CI" in text
    assert "M0.2" in text
    assert "## 1. Execution target" in text
    assert "## 2. Ancestor context chain" in text
    # New section 6 inserted between deps and touch zones; rollup is now 8.
    assert "## 6. Dependency context (intent of upstream work)" in text
    assert "## 7. Touch zones — implementing agent instruction" in text
    assert "## 8. Rollup semantics (reference)" in text


def test_render_brief_dependencies_use_display_ids_not_raw_node_keys() -> None:
    """dependencies[] holds node_key UUIDs; brief must show peer display id + title."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M1", by_id)
    assert "## 5. Dependencies (must complete first)" in text
    assert "M0.1" in text
    assert "Establish shared contracts and ADR skeleton" in text
    assert "- **44ef4a9d-" not in text


def test_render_brief_inlines_planning_sheet_body() -> None:
    """F-004: brief inlines the planning sheet content, not just paths."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert "## 3. Planning context (inlined)" in text
    # The dogfood M0.3 planning template contains the literal text "Intent".
    assert "## Intent" in text


def test_render_brief_inlines_cited_shared_contracts() -> None:
    """A contract named in the chain's ``## References`` is inlined bodily."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert "## 4. Shared contracts (cited)" in text
    # M0.3's sheet cites shared/api-contract.md; its body must be present.
    assert "### `shared/api-contract.md`" in text
    assert "Error codes (enum)" in text  # a heading from inside that contract


def test_render_brief_lists_uncited_contracts_without_inlining_them() -> None:
    """The fix for the 436 KB brief: uncited contracts cost a path, not a body.

    M0.2 is about CI and cites no contract, so the api-contract body must not
    appear — but its path must, or the brief would silently hide it.
    """
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.2", by_id, repo_root=DOGFOOD)
    assert "### `shared/api-contract.md`" not in text
    assert "Error codes (enum)" not in text
    assert "`shared/api-contract.md`" in text
    assert "**Not inlined**" in text
    assert "--kind shared" in text


def test_render_brief_always_inlines_the_shared_readme() -> None:
    """AGENTS.md's load order: the index, then cited contracts only."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.2", by_id, repo_root=DOGFOOD)
    assert "### `shared/README.md`" in text


def test_render_brief_all_contracts_restores_inlining_everything() -> None:
    """The escape hatch has to be a real restoration, not an approximation."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    scoped = gb.render_brief("M0.2", by_id, repo_root=DOGFOOD)
    every = gb.render_brief("M0.2", by_id, repo_root=DOGFOOD, all_contracts=True)
    assert "### `shared/api-contract.md`" in every
    assert "**Not inlined**" not in every
    assert len(every) > len(scoped)


def test_render_brief_finds_contracts_in_shared_subdirectories(tmp_path) -> None:
    """The opposite bug: a flat glob never saw shared/<dir>/*.md at all."""
    import shutil

    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    nested = dest / "shared" / "contracts" / "auth-model.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# Auth model\n", encoding="utf-8")

    by_id = gb.index(gb.load_nodes(dest))
    text = gb.render_brief("M0.2", by_id, repo_root=dest)

    assert "`shared/contracts/auth-model.md`" in text


def test_render_brief_includes_touch_zone_instruction() -> None:
    """F-009: brief tells the implementer to derive/confirm touch zones."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    # Renumbered to 7 after the new ## 6. Dependency context section landed.
    assert "## 7. Touch zones — implementing agent instruction" in text
    assert "TODO (DEV agent)" in text


def test_render_brief_dependency_context_inlines_dep_intent() -> None:
    """New ## 6 inlines each effective dependency's ## Intent block.

    M1 in the dogfood fixture depends on M0.1 (whose planning sheet ships
    with a canonical '## Intent' section). The brief must surface that
    Intent body verbatim under '## 6. Dependency context …'.
    """
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M1", by_id, repo_root=DOGFOOD)
    assert "## 6. Dependency context (intent of upstream work)" in text
    # The dep is identified by display id + title under a level-3 heading.
    assert "### `M0.1` — Establish shared contracts and ADR skeleton" in text
    assert "**Intent (from this dependency's planning sheet):**" in text
    # Body of M0.1's Intent block (from the dogfood scaffold).
    assert "What problem this slice solves" in text


def test_render_brief_dependency_context_empty_when_no_deps() -> None:
    """Section is always present; body explicitly notes 'no effective dependencies'."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    # M0 is a phase root with no dependencies (and no inherited deps).
    text = gb.render_brief("M0", by_id, repo_root=DOGFOOD)
    assert "## 6. Dependency context (intent of upstream work)" in text
    assert "_no effective dependencies_" in text


def test_render_brief_is_deterministic() -> None:
    """F-004: same inputs => byte-identical output."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    a = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    b = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert a == b


def test_unknown_node_exits() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "generate_brief.py"),
            "M999.9",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )
    assert proc.returncode != 0


# --- ## 9. History (derived from git) ---------------------------------------


def test_render_brief_includes_the_history_section() -> None:
    """The section header is a stable landmark even with nothing to report."""
    from specy_road.bundled_scripts import generate_brief as gb

    by_id = gb.index(gb.load_nodes(DOGFOOD))
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)

    assert "## 9. History (derived from git)" in text


def test_render_brief_no_history_omits_the_section() -> None:
    from specy_road.bundled_scripts import generate_brief as gb

    by_id = gb.index(gb.load_nodes(DOGFOOD))
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD, include_history=False)

    assert "## 9. History" not in text
    assert "## 8. Rollup semantics (reference)" in text  # still complete


def test_render_brief_history_degrades_outside_a_git_worktree(tmp_path) -> None:
    """A brief must still render where git cannot answer."""
    import shutil

    from specy_road.bundled_scripts import generate_brief as gb

    dest = tmp_path / "no-git"
    shutil.copytree(DOGFOOD, dest)
    by_id = gb.index(gb.load_nodes(dest))

    text = gb.render_brief("M0.3", by_id, repo_root=dest)

    assert "## 9. History (derived from git)" in text
    assert "no git history available" in text


def test_render_brief_history_reports_archived_work_in_the_subtree(tmp_path) -> None:
    """The signal that is invisible any other way: this phase used to be bigger."""
    from specy_road.bundled_scripts import generate_brief as gb
    from specy_road.archive_ops import archive_node
    from specy_road.history_index import clear_memo
    from tests.test_history_walk import commit, git

    dest = tmp_path / "repo"
    import shutil

    shutil.copytree(DOGFOOD, dest)
    git(dest, "init", "-q", "-b", "main")
    commit(dest, "baseline")
    archive_node(dest, "M0.1")  # already Complete in the fixture
    commit(dest, "archive M0.1")
    clear_memo()

    by_id = gb.index(gb.load_nodes(dest))
    text = gb.render_brief("M0", by_id, repo_root=dest)

    assert "Related work that left the live roadmap" in text
    assert "M0.1 archived" in text
    assert "specy-road show-archive M0.1-" in text
