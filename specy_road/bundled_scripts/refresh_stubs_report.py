"""What ``refresh-stubs`` (and ``upgrade``) print after a refresh.

Split out of ``refresh_stubs.py`` to keep that file under its line cap. A stub
directory that is a symlink (say ``.agents/skills`` → ``.claude/skills``) makes
one file reachable under two names; the report names its real path once and
notes the link, rather than listing the same skills twice.
"""

from __future__ import annotations

from pathlib import Path

NEXT_STEP = "Next: specy-road validate (specy-road upgrade runs the whole sequence)."


def old_command_stub(rel: str) -> bool:
    """A pre-0.3.0 harness command stub (not a `generic` pack's own commands dir)."""
    return rel.startswith((".cursor/commands/", ".claude/commands/"))


def _linked_dir(repo_root: Path, rel: Path) -> Path | None:
    """The shallowest directory above ``rel`` that is a symlink, if any."""
    for i in range(1, len(rel.parts)):
        if (repo_root / Path(*rel.parts[:i])).is_symlink():
            return Path(*rel.parts[:i])
    return None


def resolve_linked(written: list[str], repo_root: Path | None) -> list[str]:
    """``written`` with each entry under a symlinked directory named by its real path, once.

    Entries are ``"<rel>"`` or ``"<rel> (<outcome>)"``. Two entries whose parent
    directories resolve to the same place are one file: it is listed under its
    real path with ``(<link> → <target>)`` appended. A skill link that *is* the
    real directory of a file listed through the symlink (``.claude/skills/<name>``
    when ``.agents/skills`` links there) is that same skill, and is dropped: a
    real run reports it unchanged, so the dry run reports the same lines.
    """
    if repo_root is None:
        return list(written)
    root = repo_root.resolve()
    entries = []
    for entry in written:
        rel = entry.partition(" (")[0]
        link = _linked_dir(repo_root, Path(rel))
        entries.append((entry, (repo_root / rel).parent.resolve() / Path(rel).name, link))
    linked_dirs = {real.parent for _, real, link in entries if link is not None}
    lines: dict[Path, list[str]] = {}
    for entry, real, link in entries:
        _, sep, rest = entry.partition(" (")
        if link is None and real in linked_dirs:
            continue
        if link is None or not real.is_relative_to(root):
            lines.setdefault(real, [entry, ""])
            continue
        target = (repo_root / link).resolve().relative_to(root).as_posix()
        line = lines.setdefault(real, [f"{real.relative_to(root).as_posix()}{sep}{rest}", ""])
        line[1] = f" ({link.as_posix()} → {target})"
    return [base + note for base, note in lines.values()]


def report_orphans(orphans: list[str], *, dry_run: bool, pruned: bool) -> None:
    if pruned:
        verb = "would remove" if dry_run else "removed"
        print("")
        for rel in orphans:
            print(f"{verb} {rel} (no longer installed)")
        return
    print("\nNo longer installed for this role (or a .cursor/.codex copy of a skill), left on disk for you to remove:")
    for rel in orphans:
        print(f"  {rel}")
    if any(old_command_stub(rel) for rel in orphans):
        print(
            "\nThe */commands/ files are the pre-0.3.0 command stubs. The same commands are now\n"
            "skills under .agents/skills/ (one file read by Cursor, Codex, and Claude Code), so\n"
            "delete the old stubs to avoid two /specyrd-… entries:\n  rm "
            + " ".join(rel for rel in orphans if old_command_stub(rel))
        )
    print("Rerun with --prune to delete every path listed above.")


def report(written: list[str], orphans: list[str], *, dry_run: bool, pruned: bool = False,
           footer: bool = True, repo_root: Path | None = None) -> None:
    """Print a refresh's outcome; ``repo_root`` resolves symlinked stub directories (see :func:`resolve_linked`)."""
    verb = "would write" if dry_run else "wrote"
    old_stubs = [rel for rel in orphans if old_command_stub(rel)]
    if dry_run and old_stubs:
        skills = len({Path(rel).stem for rel in old_stubs})
        print(f"migration: {len(old_stubs)} command stubs (*/commands/) become {skills} skills under .agents/skills/")
    for rel in resolve_linked(written, repo_root):
        print(f"{verb} {rel}")
    if orphans:
        report_orphans(orphans, dry_run=dry_run, pruned=pruned)
    if not footer:
        return
    if dry_run:
        print("\n(dry-run; no files written)")
        return
    print(
        "\nStubs and managed blocks only. Your roadmap, planning sheets and "
        "anything outside a managed block were not touched."
        f"\n{NEXT_STEP}"
    )
