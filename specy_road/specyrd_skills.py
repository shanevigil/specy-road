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

from specy_road import __version__, safe_write
from specy_road.agent_guide_block import AGENT_GUIDE, GUIDE_AGENTS
from specy_road.doc_links import link_toolkit_docs
from specy_road.managed_block import CREATED, UNCHANGED, UPDATED

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
    """The per-skill symlink's relative target (``../../.agents/skills/<name>``)."""
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


#: The one link text each agent skills directory may have, byte for byte: the other one (maintainer, 2026-11-06).
SKILLS_LINK_TEXT: dict[Path, str] = {SKILLS_REL: "../.claude/skills", LINK_DEST["claude-code"]: "../.agents/skills"}


def skill_path(repo_root: Path, rel: str | Path, expected: str | None = safe_write.FILE) -> Path:
    """Where ``rel`` is written under the skills-link rule; raises ``SafeWriteError`` naming a refused path.

    The one exception to the safe-write rule's ancestor clause (maintainer,
    2026-11-06): an agent skills directory may be a symlink only when its raw
    ``os.readlink`` text is exactly :data:`SKILLS_LINK_TEXT`'s value for it
    (``.claude/skills -> ../.agents/skills`` or ``.agents/skills -> ../.claude/skills``).
    The text is never normalised: the rule walks the un-normalised join of the
    link's directory and that text with ``lstat``, so a linked ``.agents`` or
    ``.claude`` is refused, and the final component must be a real directory.
    Any other text (an in-repository alias, a ``..`` through a link, a chained,
    dangling or outward link) is refused. The rule then applies from
    ``repo_root`` to the result (``expected`` is the final kind, ``None`` for a
    skill link itself), so any other link on the path is refused.
    """
    rel = Path(rel)
    for skills, allowed in SKILLS_LINK_TEXT.items():
        link = repo_root / skills
        if rel.parts[: len(skills.parts)] == skills.parts and link.is_symlink():
            safe_write.check(repo_root, link, None)   # the directories above the skills link are real
            text, other = os.readlink(link), link.parent / allowed
            if text != allowed or safe_write.refused(repo_root, other, safe_write.DIRECTORY) or not other.is_dir():
                raise safe_write.SafeWriteError(
                    f"{link} is a symlink (to {text}), not a real directory or a link to {allowed}"
                    f" (the skills directories may link only {SKILLS_REL} -> ../.claude/skills"
                    f" or {LINK_DEST['claude-code']} -> ../.agents/skills)")
            return safe_write.check(repo_root, other.joinpath(*rel.parts[len(skills.parts):]), expected)
    return safe_write.check(repo_root, repo_root / rel, expected)


def check_install_paths(repo_root: Path, rel_dest: Path, files_to_install: tuple[str, ...], *, agent: str) -> None:
    """Raise ``SafeWriteError`` for the first stub, canonical skill file or skill link :func:`install_stubs` would
    write that the skills-link rule refuses, so ``specyrd init`` can stop before it writes anything."""
    skills = agent in SKILL_AGENTS
    for name in files_to_install:
        skill_path(repo_root, skill_rel(name) if skills else rel_dest / name)
        if skills and link_rel(agent, name) is not None:
            skill_path(repo_root, link_rel(agent, name), None)


def ensure_link(  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    repo_root: Path, agent: str, name: str, *, dry_run: bool = False, repair: bool = True, owned: bool = False,
) -> str:
    """Create or repair the symlink for ``name``; copy the skill when symlinks fail.

    Returns ``created`` / ``updated`` / ``unchanged`` / ``copied`` / ``skipped (not ours)``,
    or ``refused: <why>`` when the skills-link rule (:func:`skill_path`) refuses the link's path.
    ``repair`` is permission to replace what is at the path (``--force``, or a
    refresh); ``owned`` is whether the manifest records the path as the kit's.
    Replacement authority comes from the manifest: with no record, whatever is
    at the path is replaced only when it is byte-for-byte a stub this toolkit
    generated (any version), never on a looser text heuristic. Without
    ``repair`` a foreign symlink, file or directory is left alone.
    """
    rel = link_rel(agent, name)
    assert rel is not None
    try:   # both by the skills-link rule: either skills directory may link to the other
        link = skill_path(repo_root, rel, None)
        canonical = skill_path(repo_root, SKILLS_REL / stem(name), None)
    except safe_write.SafeWriteError as e:
        return f"refused: {e}"
    if link == canonical:
        return UNCHANGED   # one skills directory links to the other: the canonical skill is the link's place
    target = link_target(agent, name)
    if link.is_symlink() and os.readlink(link) == target:
        return UNCHANGED
    if link.exists() and link.resolve() == canonical.resolve():
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
    safe_write.mkdirs(repo_root, link.parent)
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)  # an earlier copied fallback, verified above
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        safe_write.write(repo_root, link / "SKILL.md", render_skill(name))
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
    names the path. Paths follow the skills-link rule (:func:`skill_path`);
    ``specyrd init`` checks them all with :func:`check_install_paths` first.
    """
    skills = agent in SKILL_AGENTS
    owned = owned or set()
    for name in files_to_install:
        rel_file = skill_rel(name) if skills else rel_dest / name
        dest_file = skill_path(repo_root, rel_file)
        ours = str(rel_file) in owned
        if dest_file.is_file() and not (force and (ours or _is_generated(dest_file, name, skills=skills))):
            skipped.append(str(rel_file) if not force else f"{rel_file} (not ours: no manifest record and not a specyrd stub; --force refused)")
            if skills and not ours:
                continue   # not ours: no link to it either
        else:
            content = render_skill(name) if skills else _read_template(name)
            if not dry_run:
                safe_write.write(repo_root, dest_file, content)
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


#: Skill and command directories other harnesses scan besides ``.agents/skills``.
#: specy-road writes none of them; a ``specyrd-*`` copy there loads the skill twice
#: (docs/design-notes/harness-compatibility-triage.md, finding 6).
MIRROR_DIRS = (Path(".cursor/skills"), Path(".codex/skills"), Path(".cursor/commands"))


def _mirror_rel(mirror_dir: Path, name: str) -> Path:
    return mirror_dir / name if mirror_dir.name == "commands" else mirror_dir / stem(name)


def _is_disposable_copy(path: Path, name: str, canonical: Path) -> bool:
    """Deleting ``path`` loses nothing: a link to the canonical skill, or a verbatim specyrd stub or copy of it."""
    if path.is_symlink():
        return path.resolve() in (canonical.resolve(), (canonical / "SKILL.md").resolve())
    if path.is_dir():
        skill = path / "SKILL.md"
        if {q.name for q in path.iterdir()} != {"SKILL.md"}:
            return False
        try:
            same = skill.read_bytes() == (canonical / "SKILL.md").read_bytes()
        except OSError:
            same = False
        return same or _is_generated(skill, name)
    return _is_generated(path, name, skills=False)


def mirrored_copies(repo_root: Path, names: tuple[str, ...], managed: set[str]) -> tuple[list[str], list[str]]:
    """``(disposable, kept)``: ``specyrd-*`` copies of an installed skill in :data:`MIRROR_DIRS`.

    Only names whose canonical ``.agents/skills/<name>/SKILL.md`` exists count,
    and a path the manifest records (a ``generic`` pack pointed at
    ``.cursor/commands``) is the pack's, not a copy. A mirror directory that
    is a symlink (or under one) is skipped, as the safe-write rule would refuse
    deleting through it: it could reach the canonical skill or someone else's file.
    """
    disposable: list[str] = []
    kept: list[str] = []
    for mirror_dir in MIRROR_DIRS:
        where = repo_root / mirror_dir
        if not where.is_dir() or safe_write.refused(repo_root, where, safe_write.DIRECTORY):
            continue
        for name in names:
            rel, canonical = _mirror_rel(mirror_dir, name), repo_root / SKILLS_REL / stem(name)
            path = repo_root / rel
            if str(rel) in managed or not (canonical / "SKILL.md").is_file():
                continue
            if path.is_symlink() or path.exists():
                (disposable if _is_disposable_copy(path, name, canonical) else kept).append(str(rel))
    return disposable, kept
