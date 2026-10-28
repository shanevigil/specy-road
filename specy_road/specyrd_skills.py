"""One skill directory for every harness: ``.agents/skills/<name>/SKILL.md``.

Each ``specyrd`` command is **one file**. Cursor and Codex read
``.agents/skills/`` natively (both follow symlinked skill folders); Claude
Code reads ``.claude/skills/<name>/SKILL.md`` and loads a skill directory
that is a symlink, so its pack adds one symlink per skill pointing at the
same file (all three verified against the harnesses' docs, 2026-10; see
``docs/optional-ai-tooling-patterns.md``). The ``generic`` pack keeps
writing flat ``.md`` files into the directory the user names.

Where a symlink cannot be created — Windows without the privilege — the
file is copied into place instead and the manifest records the copy, so
``refresh-stubs`` keeps it current like any other managed path.

The ``SKILL.md`` text is the command stub with ``name:`` added to its
frontmatter: Cursor requires ``name`` to match the folder, Codex requires
``name`` and ``description``, and Claude Code defaults ``name`` to the folder.
"""

from __future__ import annotations

import os
import re
import shutil
from importlib import resources
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE, GUIDE_AGENTS
from specy_road.doc_links import link_toolkit_docs
from specy_road.managed_block import CREATED, REFUSED, UNCHANGED, UPDATED, resolves_outside

SKILLS_REL = Path(".agents/skills")
#: Packs that read ``.agents/skills`` through a symlink elsewhere.
LINK_DEST: dict[str, Path] = {"claude-code": Path(".claude/skills")}
SKILL_AGENTS = frozenset({"cursor", "claude-code", "codex"})
COPIED = "copied"
SKIPPED = "skipped (not ours)"


def _package_templates_dir() -> Path:
    """Package directory for templates/specyrd/..."""
    return Path(__file__).resolve().parent / "templates" / "specyrd"


def _commands_traversable():
    """Traversable for packaged command templates (filesystem fallback)."""
    return resources.files("specy_road").joinpath("templates", "specyrd", "commands")


def _read_template(name: str) -> str:
    """Load a command template; substitute version placeholder."""
    path = _package_templates_dir() / "commands" / name
    text = path.read_text(encoding="utf-8") if path.is_file() else (_commands_traversable() / name).read_text(encoding="utf-8")
    return link_toolkit_docs(text.replace("{{SPECYRD_VERSION}}", __version__))


def stem(name: str) -> str:
    return name[:-3] if name.endswith(".md") else name


def skill_rel(name: str) -> Path:
    return SKILLS_REL / stem(name) / "SKILL.md"


def link_rel(agent: str, name: str) -> Path | None:
    dest = LINK_DEST.get(agent)
    return dest / stem(name) if dest else None


def link_target(agent: str, name: str) -> str:
    """The symlink's relative target, from its own directory to the skill folder."""
    up = [".."] * len(LINK_DEST[agent].parts)
    return os.path.join(*up, *(SKILLS_REL / stem(name)).parts)


def with_name(skill_name: str, text: str) -> str:
    """The stub as a SKILL.md: ``name:`` first in the frontmatter."""
    if text.startswith("---\n"):
        return f"---\nname: {skill_name}\n" + text[4:]
    return f"---\nname: {skill_name}\n---\n\n" + text


def render_skill(name: str) -> str:
    return with_name(stem(name), _read_template(name))


def is_link_path(rel: str) -> bool:
    return any(Path(rel).parent == d for d in LINK_DEST.values())


def ensure_link(  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    repo_root: Path, agent: str, name: str, *, dry_run: bool = False, repair: bool = True, owned: bool = False,
) -> str:
    """Create or repair the symlink for ``name``; copy the skill when symlinks fail.

    Returns ``created`` / ``updated`` / ``unchanged`` / ``copied`` / ``skipped (not ours)``,
    or ``REFUSED`` when the link's directory is a symlink out of the repository.
    ``repair`` is permission to replace what is at the path (``--force``, or a
    refresh); ``owned`` is whether the manifest records the path as the kit's.
    Replacement authority comes from the manifest: with no record, whatever is
    at the path is replaced only when it is byte-for-byte a stub this toolkit
    generated (any version), never on a looser text heuristic. Without
    ``repair`` a foreign symlink, file or directory is left alone.
    """
    rel = link_rel(agent, name)
    assert rel is not None
    link = repo_root / rel
    if resolves_outside(repo_root, link.parent):
        return REFUSED
    target = link_target(agent, name)
    canonical = (repo_root / SKILLS_REL / stem(name)).resolve()
    if link.is_symlink() and os.readlink(link) == target:
        return UNCHANGED
    if link.exists() and link.resolve() == canonical:
        return UNCHANGED   # e.g. `.claude/skills` is itself a link to `.agents/skills`
    if link.is_dir() and not link.is_symlink():
        # Only a copy this tool made (one SKILL.md) is ours to replace, and only
        # when the manifest says so or the copy is verbatim ours.
        ours = repair and {q.name for q in link.iterdir()} == {"SKILL.md"} and (owned or _is_generated(link / "SKILL.md", name))
        if not ours:
            return SKIPPED
        if (link / "SKILL.md").read_text(encoding="utf-8") == render_skill(name) and not _symlinks_work(link.parent):
            return UNCHANGED
    outcome = CREATED if not (link.exists() or link.is_symlink()) else UPDATED
    if outcome == UPDATED and not link.is_dir() and not (repair and (owned or _is_generated(link / "SKILL.md", name))):
        return SKIPPED   # a user's own symlink or file at the managed name
    if dry_run:
        return outcome
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)  # an earlier copied fallback, verified above
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        link.mkdir(parents=True, exist_ok=True)
        (link / "SKILL.md").write_text(render_skill(name), encoding="utf-8")
        return COPIED
    return outcome


_VERSION_LINE = re.compile(r"Generated by specyrd \S+")


def generated_match(text: str, name: str, *, skills: bool = True) -> bool:
    """``text`` is the stub this toolkit generates for ``name``, byte-for-byte modulo the version line."""
    expected = render_skill(name) if skills else _read_template(name)
    return _VERSION_LINE.sub("Generated by specyrd", text) == _VERSION_LINE.sub("Generated by specyrd", expected)


def _is_generated(path: Path, name: str, *, skills: bool = True) -> bool:
    """A file on disk that :func:`generated_match` recognises (unreadable counts as not ours)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return generated_match(text, name, skills=skills)


def _symlinks_work(where: Path) -> bool:
    probe = where / f".specyrd-symlink-probe-{os.getpid()}"
    try:
        os.symlink(".", probe, target_is_directory=True)
    except OSError:
        return False
    probe.unlink(missing_ok=True)
    return True


def install_stubs(
    repo_root: Path,
    rel_dest: Path,
    files_to_install: tuple[str, ...],
    force: bool,
    dry_run: bool,
    written: list[str],
    skipped: list[str],
    *,
    agent: str = "generic",
    owned: set[str] | None = None,
) -> None:
    """Write each command as a skill (or a flat file for ``generic``), plus links.

    ``owned`` is what the manifest already records as the kit's: a canonical
    skill file that exists but is nobody's is skipped, and no link is made to
    it — the installer must not expose content it declined to own. ``force``
    rewrites what the manifest owns; with no record it may replace only a file
    that is verbatim a stub this toolkit generated, and otherwise refuses and
    names the path.
    """
    skills = agent in SKILL_AGENTS
    owned = owned or set()
    for name in files_to_install:
        rel_file = skill_rel(name) if skills else rel_dest / name
        dest_file = repo_root / rel_file
        ours = str(rel_file) in owned
        if resolves_outside(repo_root, dest_file):
            skipped.append(f"{rel_file} ({REFUSED})")
            continue
        if dest_file.is_file() and not (force and (ours or _is_generated(dest_file, name, skills=skills))):
            skipped.append(str(rel_file) if not force else f"{rel_file} (not ours: no manifest record and not a specyrd stub; --force refused)")
            if skills and not ours:
                continue   # not ours: no link to it either
        else:
            content = render_skill(name) if skills else _read_template(name)
            if not dry_run:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_text(content, encoding="utf-8")
            written.append(str(rel_file))
        if skills and link_rel(agent, name) is not None:
            outcome = ensure_link(repo_root, agent, name, dry_run=dry_run, repair=force, owned=str(link_rel(agent, name)) in owned)
            if outcome == SKIPPED:
                skipped.append(f"{link_rel(agent, name)} ({outcome})")
            elif outcome != UNCHANGED:
                written.append(f"{link_rel(agent, name)} ({outcome})")


def owned_paths(managed: list[str], skipped: list[str], already_owned: set[str] | None = None) -> list[str]:
    """``managed`` minus what this install skipped, unless another pack in the manifest already owns it.

    A file the kit did not write is not its to rewrite later; a skill file
    shared with a pack that did write it stays the kit's.
    """
    not_ours = {s.split(" (")[0] for s in skipped} - (already_owned or set())
    return [p for p in managed if p not in not_ours]


def managed_paths(rel_dest: Path, files_to_install: tuple[str, ...], *, agent: str) -> list[str]:
    """Every repo path this pack owns, in the order the manifest records them.

    The manifest is what makes ``--force`` answerable: a file listed here is
    the kit's to rewrite, and a file that is not is the consumer's. Skill packs
    record the shared ``.agents/skills`` files plus their own symlinks.
    """
    if agent in SKILL_AGENTS:
        paths = [str(skill_rel(n)) for n in files_to_install]
        paths += [str(link_rel(agent, n)) for n in files_to_install if link_rel(agent, n) is not None]
    else:
        paths = [str(rel_dest / n) for n in files_to_install]
    paths.append(str(Path(".specyrd/README.md")))
    if agent in GUIDE_AGENTS:
        paths.append(AGENT_GUIDE)
    return paths
