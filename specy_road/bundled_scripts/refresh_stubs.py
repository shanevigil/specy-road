#!/usr/bin/env python3
"""Refresh the specyrd-managed IDE stubs in a consumer repo from this version.

``specyrd init`` copies the command stubs once and then skips anything that
already exists, so after ``pip install -U specy-road`` a repo keeps stubs pinned
to whatever version scaffolded them, and never sees the ones that shipped since.
There was no command for this. ``specy-road update`` fast-forwards a git *clone*
of the toolkit and says so; ``refresh-schemas`` covers ``schemas/`` and nothing
else. That left ``init --force`` as the only apparent route, which is how a
consumer's hand-authored ``CLAUDE.md`` came to be destroyed.

This is the missing middle, and it is the same shape as ``refresh-schemas``: it
rewrites exactly the paths ``.specyrd/manifest.json`` records as managed, adds
stubs this version ships that the manifest predates, re-applies the managed
blocks in the consumer-owned files, and touches nothing else. Idempotent, so it
is safe to run on every upgrade.

Orphans are **reported, not deleted**. Re-running ``init`` with a narrower
``--role`` replaces the manifest's path list wholesale, leaving stubs on disk
that dropped out of it; those are the consumer's to remove, and quietly deleting
a file we no longer claim to manage is the mistake this command exists to undo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE, apply_guide_and_report
from specy_road.agents_md_block import apply_agents_and_report
from specy_road.agent_ignores import apply_and_report
from specy_road.runtime_paths import (
    add_repo_root_arg,
    git_root,
    prefix_within,
    recorded_project_root,
)
from specy_road.managed_block import REFUSED, UNCHANGED, resolves_outside
from specy_road.specyrd_skills import SKIPPED, ensure_link, is_link_path, render_skill, skill_rel
from specy_road.specyrd_init import (
    AGENT_REL_DEST,
    COMMAND_FILES,
    ROLE_COMMAND_FILES,
    _load_manifest,
    _read_dot_specyrd_readme,
    _read_template,
    _save_manifest,
    managed_paths,
)

MANIFEST_REL = Path(".specyrd") / "manifest.json"
README_REL = ".specyrd/README.md"


def _stub_set(role: str | None) -> tuple[str, ...]:
    """The stubs this version installs for ``role`` (``both``/unknown = all)."""
    if role in ROLE_COMMAND_FILES:
        return ROLE_COMMAND_FILES[role]
    return COMMAND_FILES


def _dest_dir(agent: str, recorded: list[str]) -> Path | None:
    """Where this pack's stubs live, from the manifest for a ``generic`` pack."""
    known = AGENT_REL_DEST.get(agent)
    if known is not None:
        return known
    for rel in recorded:
        if rel != README_REL and rel.endswith(".md"):
            return Path(rel).parent
    return None


def _content_for(rel: str) -> str | None:
    if rel == README_REL:
        return _read_dot_specyrd_readme()
    path = Path(rel)
    if path.name == "SKILL.md" and f"{path.parent.name}.md" in COMMAND_FILES:
        return render_skill(f"{path.parent.name}.md")
    if path.name in COMMAND_FILES:
        return _read_template(path.name)
    return None


def _write_if_changed(
    repo_root: Path, rel: str, *, dry_run: bool, written: list[str], agent: str = "generic",
    owned: bool = True,
) -> bool:
    """Rewrite one managed path. Returns whether the path is the pack's after this call.

    A path the manifest never owned that already exists on disk is the
    consumer's: it is left alone and reported, not adopted.
    """
    if is_link_path(rel):
        outcome = ensure_link(repo_root, agent, f"{Path(rel).name}.md", dry_run=dry_run, repair=owned, owned=owned)
        if outcome == SKIPPED:
            written.append(f"{rel} ({outcome})")
            return False
        if outcome != UNCHANGED:
            written.append(f"{rel} ({outcome})")
        return True
    content = _content_for(rel)
    if content is None:
        return True
    dest = repo_root / rel
    if resolves_outside(repo_root, dest):
        written.append(f"{rel} ({REFUSED})")
        return False
    if not owned and dest.exists():
        written.append(f"{rel} (skipped (not ours))")
        return False
    if dest.is_file() and dest.read_text(encoding="utf-8") == content:
        return True
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    written.append(rel)
    return True


def _refresh_pack(
    repo_root: Path, agent: str, current: list[str], all_recorded: set[str], *, dry_run: bool, written: list[str],
) -> list[str]:
    """Rewrite one pack's managed paths; return the ones that are the kit's afterwards.

    A link is only ever made to a canonical skill the kit owns: when the
    canonical ``SKILL.md`` is skipped as someone else's, its link is skipped
    too, rather than exposing (and recording) content the kit declined to own.
    """
    ours: list[str] = []
    declined: set[str] = set()
    for rel in current:
        if is_link_path(rel) and str(skill_rel(f"{Path(rel).name}.md")) in declined:
            written.append(f"{rel} ({SKIPPED})")
            continue
        owned = rel in all_recorded or rel.startswith(".specyrd/")
        if _write_if_changed(repo_root, rel, dry_run=dry_run, written=written, agent=agent, owned=owned):
            ours.append(rel)
        else:
            declined.add(rel)
    return ours


def _old_command_stub(rel: str) -> bool:
    """A pre-0.3.0 harness command stub (not a `generic` pack's own commands dir)."""
    return rel.startswith((".cursor/commands/", ".claude/commands/"))


def _orphans(recorded: list[str], current: list[str], repo_root: Path) -> list[str]:
    """Stubs still on disk that this version no longer installs for the pack."""
    wanted = set(current)
    return sorted(
        rel
        for rel in recorded
        if rel not in wanted and _on_disk(repo_root / rel)
    )


def _on_disk(path: Path) -> bool:
    """A file, a directory, or a symlink — dangling included: a skill link whose target went is still an orphan."""
    return path.is_file() or path.is_dir() or path.is_symlink()


def refresh_stubs(
    repo_root: Path, *, dry_run: bool = False
) -> tuple[list[str], list[str]]:
    """Rewrite the managed stubs and blocks. Returns ``(written, orphans)``."""
    manifest = _load_manifest(repo_root)
    agents: dict[str, list[str]] = manifest.get("agents") or {}
    if not agents:
        raise ValueError(
            "no specyrd packs recorded in .specyrd/manifest.json — "
            "run: specyrd init --ai cursor|claude-code|generic"
        )

    project = recorded_project_root(repo_root)
    prefix = prefix_within(repo_root, project or repo_root)

    written: list[str] = []
    orphans: list[str] = []
    role = manifest.get("role")

    # Ownership is the kit's, not one pack's: a skill file another recorded
    # pack wrote is ours to refresh and to link.
    all_recorded = {p for paths in agents.values() for p in paths if isinstance(p, str)}
    for agent in sorted(agents):
        recorded = [p for p in agents[agent] if isinstance(p, str)]
        rel_dest = _dest_dir(agent, recorded)
        if rel_dest is None:
            continue
        current = _refresh_pack(repo_root, agent, managed_paths(rel_dest, _stub_set(role), agent=agent),
                                all_recorded, dry_run=dry_run, written=written)
        all_recorded.update(current)   # what this pack just wrote is the kit's for the packs after it
        orphans.extend(_orphans(recorded, current, repo_root))
        # Refresh the block in a CLAUDE.md the consumer has; never create the
        # file (`specyrd init` does that only with --write-claude-md).
        if (repo_root / AGENT_GUIDE).is_file():
            apply_guide_and_report(
                repo_root, prefix, written, agent=agent, dry_run=dry_run
            )
        if not dry_run:
            agents[agent] = current

    apply_and_report(repo_root, prefix, written, dry_run=dry_run)
    apply_agents_and_report(repo_root / prefix if prefix else repo_root, written, dry_run=dry_run, prefix=prefix)

    if not dry_run:
        manifest["agents"] = agents
        _save_manifest(repo_root, manifest)
    # A dry run writes nothing, so every pack sharing a skill reports it again.
    return list(dict.fromkeys(written)), sorted(set(orphans))


def stubs_are_stale(start: Path) -> str | None:
    """The recorded specyrd version when it lags the installed one, else None.

    ``start`` may be the project root; ``.specyrd/`` lives at the git root, which
    is a different directory under the nested layout.
    """
    checkout = git_root(start) or start
    if not (checkout / MANIFEST_REL).is_file():
        return None
    recorded = str(_load_manifest(checkout).get("specyrd_version") or "")
    return recorded if recorded and recorded != __version__ else None


def warn_if_stubs_stale(start: Path) -> None:
    """One non-fatal line when the installed stubs predate this version."""
    recorded = stubs_are_stale(start)
    if recorded is None:
        return
    print(
        f"specyrd: warning — IDE stubs were installed by specyrd {recorded} "
        f"but specy-road {__version__} is running, so commands added since "
        "then have no stub. Run: specy-road refresh-stubs",
        file=sys.stderr,
    )


def _resolve_root(explicit: Path | None) -> Path:
    """The **git** root: `.claude/`, `.cursor/` and `.specyrd/` are checkout-level.

    ``--repo-root`` means the *project* root everywhere else in the CLI, and in
    the nested layout that is a subdirectory of the checkout — so accept either
    and resolve upward, rather than reporting an uninitialized repo to someone
    who passed the same path that works for every other command.
    """
    start = (explicit or Path.cwd()).resolve()
    if (start / MANIFEST_REL).is_file():
        return start
    return (git_root(start) or start).resolve()


def _report(written: list[str], orphans: list[str], *, dry_run: bool) -> None:
    verb = "would write" if dry_run else "wrote"
    for rel in written:
        print(f"{verb} {rel}")
    if orphans:
        print("\nNo longer installed for this role, left on disk for you to remove:")
        for rel in orphans:
            print(f"  {rel}")
        if any(_old_command_stub(rel) for rel in orphans):
            print(
                "\nThe */commands/ files are the pre-0.3.0 command stubs. The same commands are now\n"
                "skills under .agents/skills/ (one file read by Cursor, Codex, and Claude Code), so\n"
                "delete the old stubs to avoid two /specyrd-… entries:\n  rm "
                + " ".join(rel for rel in orphans if _old_command_stub(rel))
            )
    if dry_run:
        print("\n(dry-run; no files written)")
        return
    print(
        "\nStubs and managed blocks only. Your roadmap, planning sheets and "
        "anything outside a managed block were not touched."
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road refresh-stubs",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written; do not modify files.",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = _resolve_root(args.repo_root)
    try:
        written, orphans = refresh_stubs(root, dry_run=args.dry_run)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    if not written and not orphans:
        print(f"stubs already match specy-road {__version__} ({root})")
        return
    _report(written, orphans, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
