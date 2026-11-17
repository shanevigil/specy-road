"""`specy-road refresh-stubs`: the safe path between `init` and `init --force`.

Without this command, a repo that upgraded specy-road had no way to pick up
stubs added since it was scaffolded except `init --force`, which is what led a
consumer to lose a hand-authored `CLAUDE.md`. So the contract is narrow on
purpose: exactly the paths `.specyrd/manifest.json` records, plus the managed
blocks, and nothing else.
"""

from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path

import pytest

from specy_road import __version__
from specy_road.bundled_scripts.refresh_stubs import (
    main,
    refresh_stubs,
    stubs_are_stale,
    warn_if_stubs_stale,
)
from specy_road.managed_block import HTML_COMMENT, render_block
import shutil
from specy_road.written_entry import Written
from specy_road.bundled_scripts.refresh_stubs import report
import os
from specy_road.bundled_scripts import refresh_stubs as rs
from specy_road.specyrd_init import run_init

MANIFEST = ".specyrd/manifest.json"
OLD_VERSION = "0.1.4"
OLD_DEV_STUBS = (
    "specyrd-validate",
    "specyrd-brief",
    "specyrd-claim",
    "specyrd-finish",
    "specyrd-do-next-task",
)
CONSUMER_CLAUDE_MD = "# My App\n\n## Rules\n\n- Never push to main.\n"


def _old_repo(tmp_path: Path, *, extra_recorded: list[str] | None = None) -> Path:
    """A repo scaffolded by an older specyrd: stale stubs, no context tools."""
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    recorded = []
    for name in OLD_DEV_STUBS:
        (commands / f"{name}.md").write_text("stale stub\n", encoding="utf-8")
        recorded.append(f".claude/commands/{name}.md")
    recorded.append(".specyrd/README.md")
    recorded.extend(extra_recorded or [])
    (tmp_path / "CLAUDE.md").write_text(CONSUMER_CLAUDE_MD, encoding="utf-8")
    manifest = tmp_path / ".specyrd" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "specyrd_version": OLD_VERSION,
                "agents": {"claude-code": recorded},
                "role": "dev",
                "project_root": ".",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return tmp_path


def _manifest(root: Path) -> dict:
    return json.loads(
        (root / ".specyrd" / "manifest.json").read_text(encoding="utf-8")
    )


def test_a_repo_without_a_stub_pack_still_gets_the_managed_blocks(tmp_path: Path) -> None:
    """The upgrade path for repos that never ran `specyrd init` (rc1 feedback)."""
    (tmp_path / "AGENTS.md").write_text("# Ours\n", encoding="utf-8")

    written, orphans = refresh_stubs(tmp_path)

    assert "AGENTS.md (updated)" in written
    assert any(w.startswith(".gitignore") for w in written)
    assert orphans == []
    assert "specy-road managed block" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ".specyrd/cache/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert not (tmp_path / ".specyrd" / "manifest.json").exists()
    assert not (tmp_path / "CLAUDE.md").exists()   # never created without the claude-code pack
    assert refresh_stubs(tmp_path) == ([], [])

    # One the consumer has gets the block (so the @ imports) whichever packs are installed.
    (tmp_path / "CLAUDE.md").write_text(CONSUMER_CLAUDE_MD, encoding="utf-8")
    assert refresh_stubs(tmp_path)[0] == ["CLAUDE.md (updated)"]
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith(CONSUMER_CLAUDE_MD) and "@.specyrd/AGENTS.md" in claude.splitlines()


def test_a_manifest_without_packs_reports_no_stub_skew(tmp_path: Path) -> None:
    """0.2.x `init project` recorded its version with no pack; validate nagged for refresh-stubs forever."""
    manifest = tmp_path / ".specyrd" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"specyrd_version": OLD_VERSION, "project_root": "."}), encoding="utf-8")

    assert stubs_are_stale(tmp_path) is None


def test_a_repo_without_a_stub_pack_uses_the_given_project_root(tmp_path: Path) -> None:
    """No manifest records the nested root, so the caller's project root places AGENTS.md."""
    (tmp_path / "sr").mkdir()

    written, _ = refresh_stubs(tmp_path, project=tmp_path / "sr")

    assert "sr/AGENTS.md (updated)" in written   # the H1 is written first, then the block
    assert not (tmp_path / "AGENTS.md").exists()


def test_stubs_shipped_since_the_repo_was_scaffolded_are_added(
    tmp_path: Path,
) -> None:
    """The 0.2.1 context tools were reachable only by force-overwriting."""
    root = _old_repo(tmp_path)

    written, _ = refresh_stubs(root)

    for name in ("specyrd-search", "specyrd-digest", "specyrd-history"):
        assert f".agents/skills/{name}/SKILL.md" in written
        assert (root / ".agents" / "skills" / name / "SKILL.md").is_file()


def test_stale_stubs_are_rewritten_and_the_version_is_bumped(
    tmp_path: Path,
) -> None:
    root = _old_repo(tmp_path)

    _, orphans = refresh_stubs(root)

    skill = root / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    assert f"Generated by specyrd {__version__}." in skill.read_text(encoding="utf-8")
    # The pre-0.3.0 command stub is superseded, reported, and left alone.
    old = root / ".claude" / "commands" / "specyrd-validate.md"
    assert old.read_text(encoding="utf-8") == "stale stub\n"
    assert ".claude/commands/specyrd-validate.md" in orphans
    assert _manifest(root)["specyrd_version"] == __version__


def test_a_second_run_changes_nothing(tmp_path: Path) -> None:
    root = _old_repo(tmp_path)
    refresh_stubs(root)

    written, orphans = refresh_stubs(root)

    assert written == []
    assert orphans == []


def test_the_consumer_half_of_claude_md_is_untouched(tmp_path: Path) -> None:
    root = _old_repo(tmp_path)

    refresh_stubs(root)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")

    assert text.startswith(CONSUMER_CLAUDE_MD)
    assert "specy-road managed block" in text


def test_orphaned_stubs_are_reported_not_deleted(tmp_path: Path) -> None:
    """A narrower --role drops paths from the manifest; the files stay ours to keep."""
    orphan_rel = ".claude/commands/specyrd-add-node.md"
    root = _old_repo(tmp_path, extra_recorded=[orphan_rel])
    (root / orphan_rel).write_text("pm-only stub\n", encoding="utf-8")

    _, orphans = refresh_stubs(root)

    assert orphan_rel in orphans
    assert (root / orphan_rel).read_text(encoding="utf-8") == "pm-only stub\n"
    assert orphan_rel not in _manifest(root)["agents"]["claude-code"]


def test_a_dry_run_reports_everything_once_and_writes_nothing(tmp_path: Path) -> None:
    root = _old_repo(tmp_path)
    manifest = _manifest(root)
    manifest["agents"]["codex"] = [".specyrd/README.md"]   # a second pack sharing the skills
    (root / ".specyrd" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    written, _ = refresh_stubs(root, dry_run=True)

    assert written.count(".agents/skills/specyrd-search/SKILL.md") == 1
    assert any(w.startswith("CLAUDE.md (") for w in written)
    assert not (root / ".agents").exists()
    assert not (root / ".claude" / "skills").exists()
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == CONSUMER_CLAUDE_MD
    assert _manifest(root)["specyrd_version"] == OLD_VERSION


def test_validate_warns_once_while_the_stubs_lag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _old_repo(tmp_path)
    assert stubs_are_stale(root) == OLD_VERSION

    warn_if_stubs_stale(root)
    assert "specy-road refresh-stubs" in capsys.readouterr().err

    refresh_stubs(root)
    assert stubs_are_stale(root) is None
    warn_if_stubs_stale(root)
    assert capsys.readouterr().err == ""


def test_a_repo_with_no_specyrd_stubs_never_warns(tmp_path: Path) -> None:
    assert stubs_are_stale(tmp_path) is None


def test_a_dry_run_summarises_the_migration_in_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _old_repo(tmp_path)

    main(["--dry-run", "--repo-root", str(root)])

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("migration:")]
    n = len(OLD_DEV_STUBS)
    assert lines == [f"migration: {n} command stubs (*/commands/) become {n} skills under .agents/skills/"]



def _diff_sections(out: str) -> dict[str, list[str]]:
    """``{path: hunk lines}`` from a run of unified diffs."""
    sections: dict[str, list[str]] = {}
    current: list[str] = []
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current = sections.setdefault(line[len("+++ b/"):], [])
        elif not line.startswith("--- "):
            current.append(line)
    return sections


def test_diff_previews_skills_and_managed_blocks_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _old_repo(tmp_path)

    main(["--diff", "--repo-root", str(root)])
    out = capsys.readouterr().out

    sections = _diff_sections(out)
    assert ".agents/skills/specyrd-search/SKILL.md" in sections
    assert {"CLAUDE.md", ".gitignore", ".cursorindexingignore", "AGENTS.md"} <= set(sections)
    assert "--- a/CLAUDE.md" in out and "--- /dev/null" in out
    assert "would write .claude/skills/specyrd-search (created)" in out   # a link has no text to diff
    assert "(dry-run; no files written)" in out
    assert not (root / ".agents").exists()
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == CONSUMER_CLAUDE_MD
    assert not (root / ".gitignore").exists()
    assert _manifest(root)["specyrd_version"] == OLD_VERSION


@pytest.mark.parametrize("agents_block", [None, "full", "minimal"])
def test_the_diff_is_what_a_refresh_then_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], agents_block: str | None
) -> None:
    root = _old_repo(tmp_path)
    if agents_block:
        (root / MANIFEST).write_text(json.dumps(_manifest(root) | {"agents_block": agents_block}), encoding="utf-8")
    main(["--diff", "--repo-root", str(root)])
    sections = _diff_sections(capsys.readouterr().out)

    refresh_stubs(root)

    def added(rel: str) -> list[str]:
        return [ln[1:] for ln in sections[rel] if ln.startswith("+")]

    skill = ".agents/skills/specyrd-search/SKILL.md"
    assert added(skill) == (root / skill).read_text(encoding="utf-8").splitlines()
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert added("CLAUDE.md") == claude[len(CONSUMER_CLAUDE_MD):].splitlines()
    assert added(".gitignore") == (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert added("AGENTS.md") == (root / "AGENTS.md").read_text(encoding="utf-8").splitlines()   # M13.3: same setting
    section = _between_markers((root / "AGENTS.md").read_text(encoding="utf-8"))
    assert (len(section) == 3) == (agents_block == "minimal")


def _between_markers(text: str) -> list[str]:
    lines = text.splitlines()
    return lines[lines.index(HTML_COMMENT.start):lines.index(HTML_COMMENT.end) + 1]


@pytest.mark.parametrize(("layout", "manifest", "agents"), [
    ("embedded", "minimal", "no-block"),
    ("embedded", "full", "stale"),
    ("embedded", "missing", "none"),
    ("embedded", "missing", "stale"),
    ("nested", "minimal", "stale"),
    ("nested", "minimal", "none"),
    ("nested", "full", "no-block"),
])
def test_the_agents_md_preview_is_what_a_refresh_then_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], layout: str, manifest: str, agents: str
) -> None:
    """M13.3 R2: --diff renders AGENTS.md with the real run's agents_block, nested project root included."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    prefix = "sr/" if layout == "nested" else ""
    project = tmp_path / prefix
    project.mkdir(parents=True, exist_ok=True)
    if manifest != "missing":
        (tmp_path / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / MANIFEST).write_text(json.dumps({
            "specyrd_version": __version__, "agents": {}, "project_root": prefix.rstrip("/") or ".",
            "agents_block": manifest}), encoding="utf-8")
    path = project / "AGENTS.md"
    if agents != "none":
        stale = render_block(["- an old rule"], style=HTML_COMMENT) if agents == "stale" else ""
        path.write_text(f"# Ours\n\n{stale}\nOur text.\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8") if path.is_file() else None

    main(["--diff", "--repo-root", str(project)])
    preview = _diff_sections(capsys.readouterr().out)[f"{prefix}AGENTS.md"]
    assert path.read_text(encoding="utf-8") == before if before is not None else not path.exists()
    main(["--repo-root", str(project)])
    after = path.read_text(encoding="utf-8")

    expected = "".join(difflib.unified_diff((before or "").splitlines(keepends=True), after.splitlines(keepends=True)))
    assert preview == [ln for ln in expected.splitlines() if not ln.startswith(("--- ", "+++ "))]
    assert (len(_between_markers(after)) == 3) == (manifest == "minimal")


def test_diff_on_a_current_repo_shows_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _old_repo(tmp_path)
    refresh_stubs(root)
    capsys.readouterr()

    main(["--diff", "--repo-root", str(root)])
    out = capsys.readouterr().out

    assert "+++" not in out
    assert "already match" in out


# M13.7: notices that were correct but misleading.
# A symlinked skills directory listed every skill twice; a new .gitignore
# rule silently matched files already in the tree. (The session end wording
# is pinned in test_session_presence.py.)

NOTE = "(.agents/skills → .claude/skills)"



def _linked_skills_repo(tmp_path: Path) -> Path:
    """``.agents/skills`` is a symlink to ``.claude/skills``, with a claude-code pack recorded."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "skills").symlink_to(Path("..") / ".claude" / "skills")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"claude-code": [".agents/skills/specyrd-brief/SKILL.md"]}}), encoding="utf-8")
    return tmp_path



@pytest.mark.parametrize("dry_run", [True, False])
def test_a_symlinked_skills_dir_reports_each_skill_once_with_the_link(tmp_path: Path, capsys, dry_run: bool) -> None:
    repo = _linked_skills_repo(tmp_path)
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    brief = [ln for ln in capsys.readouterr().out.splitlines() if "specyrd-brief" in ln]
    verb = "would write" if dry_run else "wrote"
    assert brief == [f"{verb} .claude/skills/specyrd-brief/SKILL.md {NOTE}"]



def _reverse_linked_repo(tmp_path: Path) -> Path:
    """``.claude/skills`` is a symlink to ``.agents/skills`` (the other direction)."""
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").symlink_to(Path("..") / ".agents" / "skills")
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"claude-code": [".agents/skills/specyrd-brief/SKILL.md"]}}), encoding="utf-8")
    return tmp_path



def _skill_lines(out: str, verb: str) -> list[str]:
    return [ln.removeprefix(verb) for ln in out.splitlines() if "specyrd-" in ln and ln.startswith(verb)]



def test_a_reverse_symlinked_skills_dir_reports_each_skill_once_and_runs_agree(tmp_path: Path, capsys) -> None:
    repo = _reverse_linked_repo(tmp_path)
    main(["--repo-root", str(repo), "--dry-run"])
    dry = _skill_lines(capsys.readouterr().out, "would write ")
    main(["--repo-root", str(repo)])
    real = _skill_lines(capsys.readouterr().out, "wrote ")
    assert [ln for ln in dry if "specyrd-brief" in ln] == [".agents/skills/specyrd-brief/SKILL.md"]
    assert dry == real and len(dry) == len({ln.split("/")[2] for ln in dry})



def test_the_report_folds_two_names_for_one_file_into_its_real_path(tmp_path: Path, capsys) -> None:
    repo = _linked_skills_repo(tmp_path)
    written = [Written(".agents/skills/x/SKILL.md"), Written(".claude/skills/x/SKILL.md"),
               Written(".gitignore", "updated")]
    report(written, [], dry_run=True, footer=False, repo_root=repo)
    assert capsys.readouterr().out.splitlines() == [
        f"would write .claude/skills/x/SKILL.md {NOTE}",
        "would write .gitignore (updated)",
    ]



def _generic_repo(tmp_path: Path, rel_dir: str, *, link_to: str | None = None) -> Path:
    """A ``generic`` pack recorded under ``rel_dir``, optionally a symlink to ``link_to`` (repo-relative)."""
    stub_dir = tmp_path / rel_dir
    stub_dir.parent.mkdir(parents=True, exist_ok=True)
    if link_to:
        (tmp_path / link_to).mkdir(parents=True)
        stub_dir.symlink_to(Path(*[".."] * (len(Path(rel_dir).parts) - 1), link_to))
    else:
        stub_dir.mkdir()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        (stub_dir / name).write_text("stale\n", encoding="utf-8")
    (tmp_path / ".specyrd").mkdir()
    recorded = [f"{rel_dir}/specyrd-validate.md", f"{rel_dir}/specyrd-brief.md"]
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"agents": {"generic": recorded}}), encoding="utf-8")
    return tmp_path



@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("rel_dir", ["docs/team (commands)", "docs/équipe #1 !x"])
def test_a_generic_dir_with_parentheses_or_odd_characters_is_reported_whole(
        tmp_path: Path, capsys, dry_run: bool, rel_dir: str) -> None:
    repo = _generic_repo(tmp_path, rel_dir)
    main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])
    verb = "would write" if dry_run else "wrote"
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"{verb} {rel_dir}/{name}" in out



def _generic_linked_parent(tmp_path: Path, self_loop: bool) -> tuple[Path, Path]:
    """A stub under a linked directory that is not an agent skills directory (to ``actual``, or to itself)."""
    repo = _generic_repo(tmp_path, "docs/team (commands)", link_to=None if self_loop else "actual")
    link = repo / "docs" / "team (commands)"
    if self_loop:
        shutil.rmtree(link)
        link.symlink_to(link.name)
    return repo, link



@pytest.mark.parametrize("self_loop", [False, True], ids=["to-actual", "self-loop"])
@pytest.mark.parametrize("dry_run", [True, False])
def test_a_stub_under_a_linked_directory_that_is_not_a_skills_directory_is_refused(
        tmp_path: Path, capsys, dry_run: bool, self_loop: bool) -> None:
    """M21.37: only an agent skills directory may be a link; skills-link shapes are in test_setup_writers_refuse_links.
    A link loop is refused like any link, without a traceback."""
    repo, link = _generic_linked_parent(tmp_path, self_loop)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    with pytest.raises(SystemExit) as e:
        main(["--repo-root", str(repo), *(["--dry-run"] if dry_run else [])])

    err = capsys.readouterr().err
    assert e.value.code == 1 and f"error: {link} is a symlink" in err, err
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".specyrd" not in p.parts
            and p.name not in (".gitignore", ".cursorindexingignore", "AGENTS.md")} == {
        p: b for p, b in before.items() if ".specyrd" not in p.parts}



def test_diff_shows_stubs_under_a_parenthesised_dir(tmp_path: Path, capsys) -> None:
    repo = _generic_repo(tmp_path, "docs/team (commands)")
    main(["--repo-root", str(repo), "--diff"])
    out = capsys.readouterr().out.splitlines()
    for name in ("specyrd-validate.md", "specyrd-brief.md"):
        assert f"+++ b/docs/team (commands)/{name}" in out
        assert f"would write docs/team (commands)/{name}" not in out   # diffed, not left as a bare line



def test_refresh_stubs_lists_a_dangling_skill_link_as_an_orphan(tmp_path: Path) -> None:
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    manifest = tmp_path / ".specyrd" / "manifest.json"
    data = manifest.read_text()
    link = ".claude/skills/specyrd-gone"
    os.symlink("../../.agents/skills/specyrd-gone", tmp_path / link)
    manifest.write_text(data.replace('".claude/skills/specyrd-validate"', f'".claude/skills/specyrd-validate", "{link}"'))
    _w, orphans = rs.refresh_stubs(tmp_path)
    assert link in orphans and (tmp_path / link).is_symlink()



def test_refresh_stubs_does_not_create_claude_md(tmp_path: Path) -> None:
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, write_claude_md=False)
    assert not (tmp_path / "CLAUDE.md").exists()
    rs.refresh_stubs(tmp_path)
    assert not (tmp_path / "CLAUDE.md").exists()



def test_the_commands_hint_is_only_for_old_harness_stubs() -> None:
    assert rs.old_command_stub(".cursor/commands/specyrd-x.md")
    assert not rs.old_command_stub("docs/commands/specyrd-x.md")



# --- B7, F4 -------------------------------------------------------------------

def test_a_skipped_canonical_skill_is_never_adopted_or_overwritten(tmp_path: Path) -> None:
    mine = tmp_path / ".agents" / "skills" / "specyrd-validate" / "SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("CUSTOM USER SKILL\n")
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False, ai_commands_dir=None, role="dev")
    manifest = json.loads((tmp_path / ".specyrd" / "manifest.json").read_text())
    assert ".agents/skills/specyrd-validate/SKILL.md" not in manifest["agents"]["claude-code"]
    written, _o = rs.refresh_stubs(tmp_path)
    assert mine.read_text() == "CUSTOM USER SKILL\n"
    assert ".agents/skills/specyrd-validate/SKILL.md (skipped (not ours))" in written
