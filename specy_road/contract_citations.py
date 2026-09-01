"""Which ``shared/`` contracts a node actually needs.

A brief used to inline every ``shared/*.md`` verbatim, so its size tracked the
repository rather than the task: on a repo with 444 KB of contracts, one leaf
task's brief measured 436 KB — roughly 109,000 tokens — of which the node
contributed about 3 KB. That is the opposite of what ``AGENTS.md`` asks for on
its first line, and it fails outright at exactly the scale specy-road exists
to serve.

The citation channel already existed and was already being authored: both
planning-sheet templates ship a ``## References`` section, and real repos fill
it in accurately — the milestones that need a contract link to it, and the ones
that do not, do not. Nothing read it. This module does.

**Why the sheet and not the node.** The obvious alternative, a field on the
node, is a breaking schema change: ``$defs.node`` sets
``additionalProperties: false`` and each consumer repo holds its own copy of
``schemas/roadmap.schema.json``, so a new field fails ``specy-road validate``
everywhere until every project runs ``specy-road refresh-schemas``. Reviving
the old ``agentic_checklist.contract_citation`` is worse: ``validate_self_heal``
does not merely ignore that object, it deletes it from chunk JSON on disk.

Citations are read from the node's own sheet **and every ancestor's**, because
a contract cited once at the phase level governs the whole subtree.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from specy_road.text_sections import find_section, read_text_safely

#: Heading whose body carries the citations. Matched through
#: ``text_sections.normalize_heading``, so case and a trailing colon are free.
REFERENCES_HEADINGS = {"references"}

SHARED_DIR = "shared"

#: Always inlined regardless of citations: it is the index that makes the
#: listed-but-not-inlined paths navigable, and the load order in ``AGENTS.md``
#: already reads "shared/README.md, then cited contracts only".
SHARED_README = "shared/README.md"

# Three shapes a citation takes in the wild, all seen in real planning sheets:
#   [`shared/x.md`](../shared/x.md)   markdown link (target and label both hit)
#   `shared/x.md`                     inline code
#   shared/x.md                       bare, in prose
_LINK_TARGET_RE = re.compile(r"\]\(\s*([^)\s]+)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BARE_PATH_RE = re.compile(r"(?:\.{1,2}/)*shared/[^\s,;:`)\]]+")


def _candidate_tokens(body: str) -> list[str]:
    """Every path-shaped token in a ``## References`` body, in document order."""
    tokens: list[str] = []
    tokens.extend(_LINK_TARGET_RE.findall(body))
    tokens.extend(_INLINE_CODE_RE.findall(body))
    tokens.extend(_BARE_PATH_RE.findall(body))
    return tokens


def normalize_citation(token: str) -> str | None:
    """A raw token as a project-relative ``shared/…`` path, or ``None``.

    Sheets live at ``planning/<file>.md`` — one level down, enforced by
    ``planning_artifacts`` — so a ``../``-relative link target resolves against
    the project root. Leading ``./`` and ``../`` segments are therefore simply
    stripped, which makes ``shared/x.md``, ``./shared/x.md`` and
    ``../shared/x.md`` the same citation.

    Rejects anything that is not a markdown file under ``shared/``: the bare
    ``shared/`` directory reference that the feature-sheet template ships as a
    placeholder, paths under ``docs/`` or ``.cursor/``, node ids, and prose.
    """
    raw = (token or "").strip().replace("\\", "/")
    if not raw:
        return None
    # A link target may carry a title: [x](../shared/x.md "Contract").
    raw = raw.split()[0]
    while raw.startswith("./") or raw.startswith("../"):
        raw = raw[2:] if raw.startswith("./") else raw[3:]
    raw = raw.lstrip("/")
    if not raw.startswith(SHARED_DIR + "/"):
        return None
    if not raw.lower().endswith(".md"):
        return None
    # No escaping back out of shared/ through a citation.
    if ".." in raw.split("/"):
        return None
    return raw


def citations_in_sheet(text: str) -> list[str]:
    """Normalised ``shared/…`` citations from one sheet's ``## References``."""
    body = find_section(text, REFERENCES_HEADINGS)
    if not body:
        return []
    out: list[str] = []
    for token in _candidate_tokens(body):
        rel = normalize_citation(token)
        if rel is not None and rel not in out:
            out.append(rel)
    return out


def cited_contracts(sheet_paths: Iterable[Path], root: Path) -> list[str]:
    """Contracts cited across a node's planning chain, sorted and existing.

    Sorted rather than merely deduplicated: the brief's determinism test runs
    twice in one process and would not catch set-iteration order differing
    across machines.
    """
    shared = (root / SHARED_DIR).resolve()
    found: set[str] = set()
    for path in sheet_paths:
        text, ok = read_text_safely(path)
        if not ok:
            continue
        for rel in citations_in_sheet(text):
            if (root / rel).is_file() and _is_under(root / rel, shared):
                found.add(rel)
    return sorted(found)


def all_contracts(root: Path) -> list[str]:
    """Every contract under ``shared/``, project-relative and sorted.

    Recursive, unlike the flat glob the brief used to inline with: a repo that
    files its contracts under ``shared/contracts/`` had none of them inlined at
    all, which is the same bug in the opposite direction.
    """
    shared = root / SHARED_DIR
    if not shared.is_dir():
        return []
    return sorted(
        p.relative_to(root).as_posix()
        for p in shared.rglob("*.md")
        if p.is_file()
    )


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent)
    except ValueError:
        return False
    return True
