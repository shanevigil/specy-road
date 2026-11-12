#!/usr/bin/env python3
"""Advisory LLM review of a roadmap node (brief + shared/ index + constraints)."""

from __future__ import annotations

import argparse
import hashlib
import sys
import threading
from collections import OrderedDict
from pathlib import Path

from specy_road.brief_generation import index as make_index, render_brief
from specy_road.llm_client import ReviewError, complete
from specy_road.planning_sheet_bootstrap import (
    feature_sheet_structure_instruction_for_llm,
    gate_sheet_structure_instruction_for_llm,
    planning_review_expected_shape_block,
)
from specy_road.roadmap_load import load_roadmap
from specy_road.git_subprocess import git_ok
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root
from specy_road.node_kinds import is_gate

# Deterministic `shared/` index for LLM review: bounded reads, sorted paths.
_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".mdx",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".csv",
    },
)
_SHARED_CATALOG_SAMPLE_BYTES = 2048
_SHARED_CATALOG_MAX_BLURB_CHARS = 120
_SHARED_CATALOG_MAX_FILES = 400
_SHARED_CATALOG_MAX_CHARS = 28_000
_SHARED_CATALOG_CACHE_MAX_ENTRIES = 32

_SHARED_CATALOG_CACHE: OrderedDict[str, str] = OrderedDict()
_SHARED_CATALOG_CACHE_LOCK = threading.Lock()


def _feature_sheet_system_prompt() -> str:
    """LLM system prompt for task/milestone/phase-style feature sheets."""
    return (
        "You revise the Markdown feature sheet for one roadmap item.\n\n"
        "Output rules (strict):\n"
        "- Return ONLY the full revised feature sheet as Markdown. No preamble, "
        "title line, or closing commentary.\n"
        "- Do not wrap the document in a fenced code block.\n"
        "- Be concise: short paragraphs, tight bullets, minimal words per line.\n"
        "- "
        + feature_sheet_structure_instruction_for_llm()
        + "\n"
        "- Do not repeat the roadmap node id, display id, title, or node_key in "
        "the body—they belong in the roadmap JSON and filename.\n"
        "- Do not duplicate roadmap structure in prose: remove or rewrite "
        "sentences that name other milestones by display id (e.g. M6, M9.1), "
        "narrate parent/child relationships, or use phrases like \"gated on\" or "
        "\"blocked by\" a roadmap item—dependencies and ordering live in the graph "
        "and brief. Intent and Approach should describe what to build and how, "
        "not restate the dependency list.\n"
        "- **Dependency context is already in the brief.** The brief ships "
        "`## 6. Dependency context (intent of upstream work)` with each "
        "effective dependency's `## Intent` block inlined verbatim. Before "
        "writing or keeping any sentence in the revised sheet that paraphrases "
        "what an upstream dependency delivers, scan brief section 6: if the "
        "dep's Intent already covers the context this task needs, omit the "
        "paraphrase from the sheet (it is redundant and creates drift). Only "
        "add a one-line clarification under `## Approach` when there is a "
        "non-obvious aspect of how this task **uses** an upstream dep (an "
        "integration seam, a contract version, a sequencing constraint) that "
        "the dep's own Intent does not state; cite the dep by display id "
        "(e.g. `(see M0.1)`).\n"
        "- Keep legitimate technical prerequisites (e.g. requires a shipped API, "
        "after a DB migration) when they are not the same as roadmap milestone "
        "references.\n"
        "- Do not explain what you changed; the UI will diff against the previous "
        "sheet.\n\n"
        "Context below includes the roadmap brief, a deterministic index of files "
        "under shared/ (one-line descriptions each), constraints, "
        "and the current planning sheet. Treat the shared/ index as optional "
        "references when improving the sheet (including ## References); it does not "
        "replace contract bodies. Improve clarity, checklist completeness, "
        "and alignment with constraints and citations—not generic advice."
    )


def _gate_planning_system_prompt() -> str:
    """LLM system prompt for ``type: gate`` planning sheets (PM hold, not dev work)."""
    return (
        "You revise the Markdown planning sheet for one roadmap **gate** "
        "(a PM hold or approval point, not an implementation task).\n\n"
        "Output rules (strict):\n"
        "- Return ONLY the full revised planning sheet as Markdown. No preamble, "
        "title line, or closing commentary.\n"
        "- Do not wrap the document in a fenced code block.\n"
        "- Be concise: short paragraphs, tight bullets, minimal words per line.\n"
        "- "
        + gate_sheet_structure_instruction_for_llm()
        + "\n"
        "- Do not repeat the roadmap node id, display id, title, or node_key in "
        "the body—they belong in the roadmap JSON and filename.\n"
        "- Do not duplicate roadmap structure in prose: remove or rewrite "
        "sentences that name other milestones by display id, narrate parent/child "
        "relationships, or restate dependency edges—those live in the graph and "
        "brief. Focus on why the gate exists, criteria to clear it, decisions, and "
        "resolution—not implementation task lists.\n"
        "- **Dependency context is already in the brief.** The brief ships "
        "`## 6. Dependency context (intent of upstream work)` with each "
        "effective dependency's intent block (`## Intent` for feature deps; "
        "`## Why this gate exists` for upstream gates) inlined verbatim. Do "
        "not paraphrase any of it in this sheet. Only add a one-line "
        "clarification under `## Decisions and notes` when there is a "
        "non-obvious aspect of how this gate **uses** an upstream dep "
        "(criteria carry-over, sequencing, ownership) that the dep's own "
        "intent does not state; cite the dep by display id "
        "(e.g. `(see M2 gate)`).\n"
        "- Do not explain what you changed; the UI will diff against the previous "
        "sheet.\n\n"
        "Context below includes the roadmap brief, a deterministic index of files "
        "under shared/ (one-line descriptions each), constraints, "
        "and the current planning sheet. Treat the shared/ index as optional "
        "references when improving the sheet (including ## References); it does not "
        "replace contract bodies. Improve clarity and alignment with constraints "
        "and citations—not generic advice."
    )


def system_prompt_for_planning_review(node_type: str | None = None) -> str:
    """System prompt for LLM planning review: gate sheet vs feature sheet."""
    if is_gate(node_type):
        return _gate_planning_system_prompt()
    return _feature_sheet_system_prompt()


# Default feature-sheet prompt (tests and callers that expect ``SYSTEM_PROMPT``).
SYSTEM_PROMPT = system_prompt_for_planning_review(None)


def _repo_root(ns: argparse.Namespace) -> Path:
    return Path(ns.repo_root).resolve() if ns.repo_root else default_user_repo_root()


def _constraints_text(root: Path) -> str:
    p = root / "constraints" / "README.md"
    if not p.is_file():
        return "_(no constraints/README.md)_"
    return p.read_text(encoding="utf-8", errors="replace")


def _read_file_prefix(path: Path, max_bytes: int) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read(max_bytes)
    except OSError:
        return b""


def _blurb_from_decoded_text(decoded: str) -> str:
    """First ATX heading in sample, else first non-empty line; single line."""
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    chosen = ""
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            rest = line
            while rest.startswith("#"):
                rest = rest[1:]
            title = rest.strip()
            if title:
                chosen = title
                break
            continue
        chosen = line
        break
    if not chosen:
        return "_(empty file)_"
    one = " ".join(chosen.split())
    cap = _SHARED_CATALOG_MAX_BLURB_CHARS
    if len(one) > cap:
        return one[: cap - 1] + "…"
    return one


def _file_blurb_for_catalog(path: Path, size: int) -> str:
    suf = path.suffix.lower()
    if suf not in _TEXT_SUFFIXES:
        label = suf if suf else "file"
        return f"`{size}` bytes ({label})"

    sample = _read_file_prefix(path, _SHARED_CATALOG_SAMPLE_BYTES)
    if b"\x00" in sample:
        return f"`{size}` bytes (binary)"

    decoded = sample.decode("utf-8", errors="replace")
    return _blurb_from_decoded_text(decoded)


def _shared_catalog_cache_clear() -> None:
    """Drop all cached ``shared/`` catalog strings (tests / rare tooling only)."""
    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_CACHE.clear()


def _iter_shared_repo_relative_paths(root_res: Path) -> list[str]:
    """Sorted repo-relative POSIX paths for regular files under ``shared/``."""
    shared = root_res / "shared"
    if not shared.is_dir():
        return []
    rel_posix: list[str] = []
    for p in shared.rglob("*"):
        if not p.is_file():
            continue
        try:
            resolved = p.resolve()
            resolved.relative_to(root_res)
        except ValueError:
            continue
        rel_posix.append(resolved.relative_to(root_res).as_posix())
    rel_posix.sort()
    return rel_posix


def _stat_fingerprint_shared_paths(root_res: Path) -> str:
    """Stable hash from path + mtime + size (no file reads)."""
    parts: list[str] = []
    for rel in _iter_shared_repo_relative_paths(root_res):
        p = root_res / rel
        try:
            st = p.stat()
            parts.append(f"{rel}\t{st.st_mtime_ns}\t{st.st_size}")
        except OSError:
            parts.append(f"{rel}\t\t")
    raw = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _shared_catalog_cache_key(root_res: Path) -> str:
    """
    Cache key when ``shared/`` is unchanged.

    Prefer ``git rev-parse HEAD:shared`` when the worktree matches HEAD for
    everything under ``shared/`` (including untracked and ignored — otherwise
    we fall back to a stat fingerprint so the catalog cannot go stale).
    """
    root_key = str(root_res)
    shared = root_res / "shared"
    if not shared.is_dir():
        return f"{root_key}\0missing"

    ok_stat, porcelain = git_ok(
        ["status", "--porcelain=v1", "--ignored", "--", "shared"],
        root_res,
        3.0,
    )
    if ok_stat and not porcelain.strip():
        ok_tree, tree_out = git_ok(["rev-parse", "HEAD:shared"], root_res, 2.0)
        if ok_tree and tree_out.strip():
            tree_id = tree_out.strip().splitlines()[0]
            if tree_id:
                return f"{root_key}\0git:{tree_id}"

    return f"{root_key}\0stat:{_stat_fingerprint_shared_paths(root_res)}"


def _shared_catalog_build(root_res: Path) -> str:
    """
    Sorted recursive listing under ``shared/`` with deterministic one-line blurbs.

    Truncation: if there are more than ``_SHARED_CATALOG_MAX_FILES`` paths, only
    the first paths in sorted order are listed and the rest are counted in a
    footer. If the section would exceed ``_SHARED_CATALOG_MAX_CHARS``, listing
    stops early with a footer (sorted order, earliest paths win).
    """
    shared = root_res / "shared"
    if not shared.is_dir():
        return "_(`shared/` directory not present — nothing to index)_\n"

    rel_posix = _iter_shared_repo_relative_paths(root_res)
    total_files = len(rel_posix)
    if total_files == 0:
        body = "- _(empty `shared/` directory — no files to index)_\n"
    else:
        capped = rel_posix[:_SHARED_CATALOG_MAX_FILES]
        omitted_by_cap = total_files - len(capped)

        lines: list[str] = []
        char_budget = _SHARED_CATALOG_MAX_CHARS
        intro = (
            "Sorted paths under `shared/` (deterministic one-line blurbs from a "
            f"prefix of at most {_SHARED_CATALOG_SAMPLE_BYTES} bytes per text "
            "file). Optional references for this task.\n\n"
        )
        remaining = char_budget - len(intro)
        truncated_mid_list = False
        for rel in capped:
            abs_path = root_res / rel
            try:
                size = abs_path.stat().st_size
            except OSError:
                size = 0
            blurb = _file_blurb_for_catalog(abs_path, size)
            line = f"- `{rel}` — {blurb}\n"
            if len(line) > remaining:
                truncated_mid_list = True
                break
            lines.append(line)
            remaining -= len(line)

        body = intro + "".join(lines)
        footers: list[str] = []
        if omitted_by_cap > 0:
            footers.append(
                f"\n_({omitted_by_cap} more path(s) under `shared/` omitted; "
                "listing is lexicographic by path.)_\n",
            )
        if truncated_mid_list:
            listed = len(lines)
            footers.append(
                f"\n_(Catalog truncated at ~{_SHARED_CATALOG_MAX_CHARS} characters "
                f"after {listed} path(s); see remaining files in the repo.)_\n",
            )
        body += "".join(footers)

    return body + "\nUse this index only for optional references.\n"


def _shared_catalog(root: Path) -> str:
    """Like :func:`_shared_catalog_build` but memoized while ``shared/`` is stable."""
    root_res = root.resolve()
    key = _shared_catalog_cache_key(root_res)
    with _SHARED_CATALOG_CACHE_LOCK:
        hit = _SHARED_CATALOG_CACHE.get(key)
        if hit is not None:
            _SHARED_CATALOG_CACHE.move_to_end(key)
            return hit

    text = _shared_catalog_build(root_res)

    with _SHARED_CATALOG_CACHE_LOCK:
        _SHARED_CATALOG_CACHE[key] = text
        _SHARED_CATALOG_CACHE.move_to_end(key)
        while len(_SHARED_CATALOG_CACHE) > _SHARED_CATALOG_CACHE_MAX_ENTRIES:
            _SHARED_CATALOG_CACHE.popitem(last=False)
    return text


def _normalize_review_markdown_output(text: str) -> str:
    """Strip accidental ```markdown fences some models wrap around the sheet."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if not lines:
        return t
    first = lines[0].strip()
    if not first.startswith("```"):
        return t
    rest = lines[1:]
    while rest and rest[-1].strip() == "```":
        rest = rest[:-1]
    return "\n".join(rest).strip()


def _feature_sheet_for_prompt(
    root: Path,
    node: dict,
    planning_body: str | None,
) -> str:
    """Current sheet text: live editor wins, else on-disk planning_dir."""
    if planning_body is not None:
        return planning_body
    pd = (node.get("planning_dir") or "").strip()
    if not pd:
        return "_(no planning_dir on this node — save a feature sheet first.)_"
    path = root / pd
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return f"_(planning file not found on disk: `{pd}`)_"


def run_review(
    node_id: str,
    repo_root: Path | None = None,
    *,
    planning_body: str | None = None,
) -> str:
    """
    Build context (brief, shared/ index, constraints, current sheet) and return
    the revised planning Markdown from the LLM (feature-sheet
    or gate-sheet shape, depending on ``node.type``).

    ``planning_body`` — when not ``None`` (including empty string), used as the
    current planning sheet instead of reading ``planning_dir`` from disk (live
    editor in the GUI).

    Raises ``ReviewError`` on configuration or API failure, ``ValueError`` if
    ``node_id`` is unknown.
    """
    root = (repo_root or default_user_repo_root()).resolve()
    nodes = load_roadmap(root)["nodes"]
    by_id = make_index(nodes)
    if node_id not in by_id:
        raise ValueError(f"unknown node {node_id!r}")
    node = by_id[node_id]
    brief = render_brief(node_id, by_id, repo_root=root)
    shared_index = _shared_catalog(root)
    constraints = _constraints_text(root)
    sheet = _feature_sheet_for_prompt(root, node, planning_body)
    nt = node.get("type")
    system_prompt = system_prompt_for_planning_review(
        nt if isinstance(nt, str) else None,
    )
    user_content = "\n\n".join(
        [
            "## Brief\n\n" + brief,
            "## shared/ index (possible references)\n\n" + shared_index,
            "## constraints/README.md\n\n" + constraints,
            "## Current planning sheet\n\n" + sheet,
            "## Expected shape\n\n" + planning_review_expected_shape_block(
                nt if isinstance(nt, str) else None,
            ),
        ],
    )
    raw = complete(
        [{"role": "user", "content": user_content}],
        system_prompt=system_prompt,
    )
    return _normalize_review_markdown_output(raw)


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road review-node`` parser."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", metavar="NODE_ID")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write Markdown report to this file (default: stdout)",
    )
    add_repo_root_arg(p)
    return p


def main(argv: list[str] | None = None) -> None:
    p = build_parser()
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = _repo_root(args)
    try:
        report = run_review(args.node_id, root)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        code = 2 if "not installed" in str(e).lower() else 1
        raise SystemExit(code) from e
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
