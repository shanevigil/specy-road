"""Keep specy-road's agent rules in a file it owns, and a short stub in the project's ``AGENTS.md``.

``init project`` used to write the whole of ``AGENTS.md`` and skip an existing
one; then it wrote the full rule set as a managed block inside it, which still
took over much of a file the team owns and left no place for a team's own
specy-road notes that ``upgrade`` would never touch. So (design note
``docs/design-notes/agent-guidance-and-shared-checkouts.md``, 2026-11-04):

- ``.specyrd/AGENTS.md`` under the project root holds the full rule set.
  specy-road owns it; ``refresh-stubs`` (so ``upgrade``) rewrites it whole.
- ``AGENTS.md`` keeps a marked stub (:mod:`specy_road.managed_block`, HTML-comment
  markers): a pointer to that file and the few rules that prevent damage if an
  agent never opens it. Codex reads only ``AGENTS.md``, so the stub is all a Codex
  session is sure to see. The ``CLAUDE.md`` block imports the rules file instead.
- ``.specyrd/AGENTS.team.md`` (tracked) is created when missing and never
  rewritten; ``.specyrd/AGENTS.local.md`` is personal and gitignored, and never
  created. Both add to the rules and never relax their floor.

``validate`` warns when the stub or the rules file is missing or differs from what
the installed version writes, and when the load order names a file the project
does not have. It also meters what those files cost: the lines and bytes each
harness injects into every session, against the limit its vendor documents.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import strip_provenance
from specy_road.agents_md_report import MINIMAL, agents_block_mode, claude_reread, minimal_lines, print_rules_overlap, total
from specy_road.digest import DEFAULT_OUTPUT as DIGEST
from specy_road.doc_links import link_toolkit_docs
from specy_road.harness_instruction_files import (
    AGENTS_MD,
    CLAUDE_MAX_FILE_BYTES,
    CLAUDE_MEMORY_BYTES,
    CLAUDE_MEMORY_LINES,
    CODEX_CANDIDATES,
    LOCAL_MD,
    RULES_MD,
    TEAM_MD,
    claude_imports,
    claude_memory_file,
    claude_loads,
    claude_memory_loaded,
    claude_paths,
    claude_rules,
    claude_skipped,
    codex_paths,
    copilot_paths,
    cursor_nested_agents,
    cursor_paths,
    inside,
    machine_local_paths,
)
from specy_road.managed_block import (
    CREATED,
    HTML_COMMENT,
    REFUSED,
    UNCHANGED,
    UPDATED,
    _split,
    apply_managed_block,
    render_block,
    resolves_outside,
)
from specy_road.runtime_paths import git_root

#: Codex truncates its project instructions at ``project_doc_max_bytes``, 32 KiB by default:
#: https://developers.openai.com/codex/guides/agents-md
CODEX_PROJECT_DOC_MAX_BYTES = 32 * 1024
#: "target under 200 lines per CLAUDE.md file": https://code.claude.com/docs/en/memory
CLAUDE_MD_TARGET_LINES = 200
_TEMPLATES = Path(__file__).resolve().parent / "templates" / "specyrd"
_TEMPLATE = _TEMPLATES / "agents-md-block.md"
_RULES_TEMPLATE = _TEMPLATES / "agents-rules.md"
_TEAM_TEMPLATE = _TEMPLATES / "agents-team.md"
_H1 = "# Agents — load order\n"
#: What :func:`apply_agents_files` writes, relative to the project root.
AGENTS_FILES = (AGENTS_MD, RULES_MD, TEAM_MD)


def _render(template: Path) -> str:
    text = strip_provenance(template.read_text(encoding="utf-8"))
    return link_toolkit_docs(text.replace("{{SPECYRD_VERSION}}", __version__)).rstrip("\n") + "\n"


def render_agents_lines(project_root: Path | None = None) -> list[str]:
    """The ``AGENTS.md`` stub: the pointer to :data:`RULES_MD` and the core rules, or only the pointer
    when the project sets ``agents_block: minimal`` (:func:`agents_block_mode`)."""
    if project_root is not None and agents_block_mode(project_root) == MINIMAL:
        return minimal_lines()
    return _render(_TEMPLATE).splitlines()


def render_rules() -> str:
    """The text of :data:`RULES_MD`, the full rule set."""
    return _render(_RULES_TEMPLATE)


def apply_agents_md_block(project_root: Path, *, dry_run: bool = False) -> str:
    """Write the specy-road stub into ``AGENTS.md``. Returns the outcome.

    A file that does not exist yet gets the scaffold's H1 above the block, so a
    fresh ``init project`` still produces a readable file rather than a bare
    marked section.
    """
    path = project_root / AGENTS_MD
    lines = render_agents_lines(project_root)
    if not path.is_file() and not path.is_symlink() and not dry_run:   # never write through a dangling link
        path.write_text(_H1, encoding="utf-8")
    return apply_managed_block(path, lines, style=HTML_COMMENT, dry_run=dry_run)


def _write_file(project_root: Path, rel: str, text: str, *, replace: bool, dry_run: bool) -> str:
    """Create ``rel``, or rewrite it when ``replace`` and it differs; never through a link out of the project."""
    path = project_root / rel
    if resolves_outside(project_root, path):
        return REFUSED
    if path.is_file() and (not replace or path.read_text(encoding="utf-8") == text):
        return UNCHANGED
    outcome = UPDATED if path.is_file() else CREATED
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return outcome


def apply_agents_files(project_root: Path, *, dry_run: bool = False, stub: bool = True) -> dict[str, str]:
    """The ``AGENTS.md`` stub, the rules file, and the team addendum when missing: ``{rel: outcome}``.

    ``stub=False`` leaves ``AGENTS.md`` alone: what the ``CLAUDE.md`` imports need in a repo with no project yet.
    """
    outcomes = {AGENTS_MD: apply_agents_md_block(project_root, dry_run=dry_run)} if stub else {}
    return outcomes | {
        RULES_MD: _write_file(project_root, RULES_MD, render_rules(), replace=True, dry_run=dry_run),
        TEAM_MD: _write_file(project_root, TEAM_MD, _TEAM_TEMPLATE.read_text(encoding="utf-8"),
                             replace=False, dry_run=dry_run),
    }


def _read(path: Path) -> str | None:
    """``path``'s text, or None when it is absent or unreadable."""
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def _agents_block(project_root: Path) -> str | None:
    text = _read(project_root / AGENTS_MD)
    return None if text is None else _split(text, HTML_COMMENT)[1]


def agents_md_block_state(project_root: Path) -> str:
    """``"current"``, ``"stale"`` (block differs from this version), or ``"missing"``."""
    block = _agents_block(project_root)
    if block is None:
        return "missing"
    return "current" if block + "\n" == render_block(render_agents_lines(project_root), style=HTML_COMMENT) else "stale"


def warn_if_agents_md_block_stale(project_root: Path) -> None:
    """One non-fatal line when ``AGENTS.md`` or :data:`RULES_MD` lacks this version's text."""
    state, rules = agents_md_block_state(project_root), _read(project_root / RULES_MD)
    if state == "missing":
        what = f"{AGENTS_MD} has no specy-road section"
    elif state == "stale":
        what = f"{AGENTS_MD} has a specy-road section that differs from what specy-road {__version__} writes"
    elif rules is None:
        what = f"{RULES_MD} is missing"
    elif rules != render_rules():
        what = f"{RULES_MD} differs from what specy-road {__version__} writes"
    else:
        return
    print(
        f"agents: warning — {what}, so agents here miss the current coordination rules. "
        "Run: specy-road refresh-stubs (it needs no stub pack and touches only managed blocks "
        "and the files specy-road owns)",
        file=sys.stderr,
    )


def print_migration(project_root: Path, prefix: str = "") -> None:
    """Before a refresh first writes :data:`RULES_MD`: its overlap with ``AGENTS.md``, and what moves out of a pre-stub section.

    A section with no rules file beside it is the full block older versions wrote.
    """
    if (project_root / RULES_MD).exists():
        return
    print_rules_overlap(project_root, render_rules(), prefix)
    if (block := _agents_block(project_root)) is None:
        return
    stub = render_block(render_agents_lines(project_root), style=HTML_COMMENT)
    print(
        f"migration: the specy-road section of {prefix}{AGENTS_MD} ({len(block.splitlines())} lines) becomes a "
        f"{len(stub.splitlines())}-line stub that points at {prefix}{RULES_MD}, which now holds the full rules "
        "and which upgrade rewrites; a CLAUDE.md section becomes an @ import of that file. Anything you added "
        f"inside the old markers is replaced (see git diff): put team notes in {prefix}{TEAM_MD} (tracked) and "
        f"your own in {prefix}{LOCAL_MD} (gitignored); upgrade never rewrites either."
    )


_LOAD_ORDER_ITEM = re.compile(r"^\d+\.\s+`([^`]+)`")


def load_order_paths(lines: list[str]) -> list[str]:
    """The files a rules file's ``### Load order`` names, in order.

    Placeholders (``planning/<id>_…``) and the digest are left out: one names no
    file, and ``digest --check`` already reports the other.
    """
    paths: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("#"):
            in_section = line.strip() == "### Load order"
            continue
        m = _LOAD_ORDER_ITEM.match(line) if in_section else None
        if m and "<" not in m.group(1) and m.group(1) != DIGEST:
            paths.append(m.group(1))
    return paths


def warn_missing_load_order_paths(project_root: Path) -> None:
    """One non-fatal line naming the files the :data:`RULES_MD` load order sends agents to that do not exist."""
    text = _read(project_root / RULES_MD)
    if text is None:
        return
    missing = [rel for rel in load_order_paths(text.splitlines()) if not (project_root / rel).exists()]
    if missing:
        print(
            f"agents: warning — the {RULES_MD} load order names {', '.join(missing)}, which "
            f"{'does' if len(missing) == 1 else 'do'} not exist here. Run: specy-road upgrade "
            "(it copies the docs specy-road ships); create the others.",
            file=sys.stderr,
        )


def apply_agents_and_report(project_root: Path, written: list[str], *, dry_run: bool = False,
                            prefix: str = "", stub: bool = True) -> None:
    """``prefix`` is the project's path under the git root, so a nested layout reports ``sr/AGENTS.md``."""
    for rel, outcome in apply_agents_files(project_root, dry_run=dry_run, stub=stub).items():
        if outcome != UNCHANGED:
            written.append(f"{prefix}{rel} ({outcome})")


@dataclass(frozen=True)
class InjectedFile:
    """One instruction file a harness injects into every session, and its specy-road section."""

    rel: str
    lines: int
    size: int
    block_lines: int
    block_size: int

    def describe(self) -> str:
        own = f" (specy-road section {self.block_lines} lines, {self.block_size:,} bytes)" if self.block_size else ""
        return f"{self.rel} {self.lines} lines, {self.size:,} bytes{own}"


def _measure(path: Path, rel: str) -> InjectedFile:
    data = path.read_bytes()
    _before, block, _after = _split(data.decode("utf-8", errors="replace"), HTML_COMMENT)
    own = (block or "").encode("utf-8")
    return InjectedFile(rel, len(data.splitlines()), len(data), len(own.splitlines()), len(own))


def _display(path: Path, top: Path) -> str:
    """Repo-relative inside the checkout; absolute for a file above the git root."""
    try:
        return path.relative_to(top).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _measured(paths: list[Path], top: Path) -> list[InjectedFile]:
    return [_measure(p, _display(p, top)) for p in paths]


def _roots(project_root: Path) -> tuple[Path, Path]:
    root = project_root.resolve()
    return root, git_root(root) or root


def _claude_files(root: Path, top: Path) -> tuple[list[Path], list[Path]]:
    """Claude Code's launch files in the git root and what they ``@``-import: ``(counted, imported from outside)``.

    The personal :data:`LOCAL_MD` is never counted, imported or not; :func:`_print_machine_local` notes it.
    """
    own = [p for p in (*claude_paths(root), *claude_rules(root, top)) if inside(p, top) and claude_loads(p)]
    imported = claude_imports(own)
    personal = (root / LOCAL_MD).resolve()
    counted = [p for p in imported if inside(p, top) and p.resolve() != personal and claude_loads(p)]
    return own + counted, [p for p in imported if not inside(p, top) and claude_loads(p)]


def injected_context(project_root: Path) -> dict[str, list[InjectedFile]]:
    """Per harness, the repository files a session started in ``project_root`` injects.

    Only paths inside the git root. Anything outside is :func:`machine_local_paths`.
    Claude Code's list leaves out a file over its 4 MiB cap, which it never loads.
    """
    project_root, top = _roots(project_root)
    found = {"Codex": codex_paths(project_root, top),
             "Claude Code": _claude_files(project_root, top)[0],
             "Cursor": cursor_paths(project_root, top), "Copilot": copilot_paths(project_root, top)}
    return {harness: _measured(paths, top) for harness, paths in found.items()}


def _note_suffix(path: Path) -> str:
    """What a machine-local file does beyond being read: a global override hides the global file."""
    if path.name == CODEX_CANDIDATES[0]:
        return (f"; a global {path.name}: every Codex session on this machine reads it "
                f"in place of the {AGENTS_MD} beside it")
    return ""


def _not_loaded(path: Path, top: Path) -> str:
    return (f"{_display(path, top)} is {path.stat().st_size:,} bytes, over Claude Code's "
            f"{CLAUDE_MAX_FILE_BYTES // (1024 * 1024)} MiB limit, so Claude Code loads none of it")


def _print_machine_local(root: Path, top: Path) -> None:
    """Notes for files not counted: user-level, imported from outside the repo, personal, auto memory, too large."""
    local = machine_local_paths(root, top)
    for path, note in zip(local, _measured(local, top)):
        print(f"context: note — {note.describe()}, user-level / machine-local; "
              f"not counted toward this repository's limit{_note_suffix(path)}")
    if (memory := claude_memory_file(top)) is not None:
        lines, size = claude_memory_loaded(memory)
        print(f"context: note — {_measure(memory, _display(memory, top)).describe()}, Claude Code auto memory: "
              f"it loads the first {CLAUDE_MEMORY_LINES} lines or {CLAUDE_MEMORY_BYTES // 1000} KB "
              f"({lines} lines, {size:,} bytes here); machine-local, not counted toward this repository's limit")
    for path in claude_skipped(root, top):
        if not inside(path, top):
            print(f"context: note — {_not_loaded(path, top)}; machine-local, not counted")
    for path in _claude_files(root, top)[1]:
        print(f"context: note — {_measure(path, _display(path, top)).describe()}, imported by a Claude Code "
              "file; machine-local, not counted toward this repository's limit")
    if (local := root / LOCAL_MD).is_file():
        print(f"context: note — {_measure(local, _display(local, top)).describe()}, personal and gitignored; "
              "machine-local, not counted toward this repository's limit")


def print_injected_context(project_root: Path) -> None:
    """One line per harness: what every session pays, against the documented limit."""
    meter = injected_context(project_root)
    codex, claude = meter["Codex"], meter["Claude Code"]
    root, top = _roots(project_root)
    if codex:
        print(f"context: Codex reads {'; '.join(f.describe() for f in codex)} — "
              f"{sum(f.size for f in codex):,} of its {CODEX_PROJECT_DOC_MAX_BYTES:,}-byte "
              f"project_doc_max_bytes budget; {total(codex)}")
    if claude:
        print(f"context: Claude Code reads {'; '.join(f.describe() for f in claude)} — "
              f"target under {CLAUDE_MD_TARGET_LINES} lines per file; {total(claude)}"
              f"{claude_reread(_claude_files(root, top)[0], root, top)}")
    for harness in ("Cursor", "Copilot"):
        if meter[harness]:
            print(f"context: {harness} reads {'; '.join(f.describe() for f in meter[harness])} — "
                  f"no documented limit; {total(meter[harness])} per session")
        if harness == "Cursor" and (nested := cursor_nested_agents(root, top)):
            print(f"context: note — Cursor also applies {'; '.join(f.describe() for f in _measured(nested, top))} "
                  "when the agent edits a file below it; not counted per session")
    _print_machine_local(root, top)


def warn_if_context_over_limits(project_root: Path) -> None:
    """A non-fatal line for each documented limit the injected files exceed."""
    meter = injected_context(project_root)
    codex, claude = meter["Codex"], meter["Claude Code"]
    total = sum(f.size for f in codex)
    if total > CODEX_PROJECT_DOC_MAX_BYTES:
        print(
            f"context: warning — {', '.join(f.rel for f in codex)} total {total:,} bytes, and Codex "
            f"truncates project instructions at {CODEX_PROJECT_DOC_MAX_BYTES:,} (project_doc_max_bytes), "
            "so its sessions here never see the rest. Shorten them, or raise project_doc_max_bytes "
            "in ~/.codex/config.toml.",
            file=sys.stderr,
        )
    for f in claude:
        if f.lines >= CLAUDE_MD_TARGET_LINES:
            print(
                f"context: warning — {f.rel} is {f.lines} lines; Claude Code's documented target is under "
                f"{CLAUDE_MD_TARGET_LINES} per file, because every session pays for the rest in context "
                "and adherence. Move what only some tasks need into a doc it links to.",
                file=sys.stderr,
            )
    root, top = _roots(project_root)
    for path in claude_skipped(root, top):
        if inside(path, top):
            print(f"context: warning — {_not_loaded(path, top)}; its sessions here never see it. "
                  "Split it, or move what only some tasks need into a doc it links to.", file=sys.stderr)
