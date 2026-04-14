#!/usr/bin/env python3
"""Advisory LLM review of a roadmap node (brief + constraints + cited docs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from generate_brief import index as make_index, render_brief
from roadmap_load import load_roadmap

from specy_road.runtime_paths import default_user_repo_root

ALLOWED_PREFIXES = ("shared/", "docs/", "specs/", "adr/")


class ReviewError(Exception):
    """LLM review failed (missing config, missing package, or API error)."""


# Concise: the model returns a replacement feature sheet, not a narrative review.
SYSTEM_PROMPT = """You revise the Markdown feature sheet for one roadmap item.

Output rules (strict):
- Return ONLY the full revised feature sheet as Markdown. No preamble, title line, or closing commentary.
- Do not wrap the document in a fenced code block.
- Be concise: short paragraphs, tight bullets, minimal words per line.
- Use ordinary feature-sheet shape: level-2 sections (## …). Prefer ## Intent, ## Approach, ## Tasks / checklist, ## References when structuring or rewriting. If the current sheet uses other ## headings (e.g. ## Source, ## Contracts), you may keep those names when they still fit.
- Do not repeat the roadmap node id, display id, title, or node_key in the body—they belong in the roadmap JSON and filename.
- Do not explain what you changed; the UI will diff against the previous sheet.

Context below includes the roadmap brief, constraints, cited contracts, and the current feature sheet. Improve clarity, checklist completeness, and alignment with constraints and citations—not generic advice."""

FEATURE_SHEET_SHAPE_HINT = (
    "Typical sections (adapt to the node): ## Intent, ## Approach, "
    "## Tasks / checklist (markdown `- [ ]` items), ## References."
)


def _repo_root(ns: argparse.Namespace) -> Path:
    return Path(ns.repo_root).resolve() if ns.repo_root else default_user_repo_root()


def _constraints_text(root: Path) -> str:
    p = root / "constraints" / "README.md"
    if not p.is_file():
        return "_(no constraints/README.md)_"
    return p.read_text(encoding="utf-8", errors="replace")


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


def _cited_snippets(root: Path, node: dict) -> str:
    ac = node.get("agentic_checklist") or {}
    citation = ac.get("contract_citation", "") or ""
    parts: list[str] = []
    root_res = root.resolve()
    for raw in citation.split(";"):
        token = raw.strip()
        if not token:
            continue
        path_part = token.split()[0] if token else ""
        if not any(path_part.startswith(p) for p in ALLOWED_PREFIXES):
            continue
        rel = Path(path_part)
        if rel.is_absolute():
            continue
        target = (root / rel).resolve()
        try:
            target.relative_to(root_res)
        except ValueError:
            parts.append(f"### (skipped path outside repo) `{path_part}`\n")
            continue
        if target.is_file():
            text = target.read_text(encoding="utf-8", errors="replace")
            cap = 12000
            if len(text) > cap:
                text = text[:cap] + "\n\n…(truncated)…"
            parts.append(f"### `{path_part}`\n\n{text}\n")
    if not parts:
        return "_(no readable cited files parsed from contract_citation)_"
    return "\n".join(parts)


def _make_client():
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as e:
        raise ReviewError(
            "openai package not installed. Run: pip install "
            "'specy-road[review]' or 'specy-road[gui]'",
        ) from e

    ep = os.environ.get("SPECY_ROAD_AZURE_OPENAI_ENDPOINT", "").strip()
    if ep:
        key = os.environ.get("SPECY_ROAD_AZURE_OPENAI_API_KEY", "").strip()
        dep = os.environ.get("SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT", "").strip()
        ver = os.environ.get(
            "SPECY_ROAD_OPENAI_API_VERSION",
            "2024-02-15-preview",
        ).strip()
        if not key or not dep:
            raise ReviewError(
                "Azure mode needs SPECY_ROAD_AZURE_OPENAI_API_KEY and "
                "SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT",
            )
        return AzureOpenAI(
            azure_endpoint=ep,
            api_key=key,
            api_version=ver,
        )

    ak = os.environ.get("SPECY_ROAD_ANTHROPIC_API_KEY", "").strip()
    if ak:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ReviewError(
                "anthropic package not installed. Run: pip install "
                "'specy-road[review]' or 'specy-road[gui-next]'",
            ) from e
        return Anthropic(api_key=ak)

    key = os.environ.get("SPECY_ROAD_OPENAI_API_KEY", "").strip()
    if not key:
        raise ReviewError(
            "set SPECY_ROAD_OPENAI_API_KEY, SPECY_ROAD_ANTHROPIC_API_KEY, "
            "or Azure variables (see docs/pm-workflow.md)",
        )
    base = os.environ.get("SPECY_ROAD_OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=key, base_url=base)


def _anthropic_text(resp: object) -> str:
    parts: list[str] = []
    for block in getattr(resp, "content", ()) or ():
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def _complete_anthropic(client: object, user_content: str) -> str:
    default_m = "claude-sonnet-4-20250514"
    model = os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", default_m)
    resp = client.messages.create(  # type: ignore[union-attr]
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return _anthropic_text(resp)


def _complete(client, user_content: str) -> str:
    cls_mod = type(client).__module__
    if cls_mod.startswith("anthropic"):
        return _complete_anthropic(client, user_content)

    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = os.environ["SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT"]
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    choice = resp.choices[0].message.content
    return choice or ""


def ping_llm() -> None:
    """Minimal request to verify credentials (used by Test LLM in GUIs)."""
    client = _make_client()
    cls_mod = type(client).__module__
    if cls_mod.startswith("anthropic"):
        default_m = "claude-sonnet-4-20250514"
        model = os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", default_m)
        r = client.messages.create(  # type: ignore[union-attr]
            model=model,
            max_tokens=3,
            messages=[{"role": "user", "content": "ping"}],
        )
        _ = _anthropic_text(r)
        return
    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = os.environ["SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT"]
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=3,
    )
    _ = resp.choices[0].message.content


def run_review(
    node_id: str,
    repo_root: Path | None = None,
    *,
    planning_body: str | None = None,
) -> str:
    """
    Build context (brief, constraints, cited docs, current sheet) and return
    the revised feature sheet Markdown from the LLM.

    ``planning_body`` — when not ``None`` (including empty string), used as the
    current feature sheet instead of reading ``planning_dir`` from disk (live
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
    constraints = _constraints_text(root)
    cited = _cited_snippets(root, node)
    sheet = _feature_sheet_for_prompt(root, node, planning_body)
    user_content = "\n\n".join(
        [
            "## Brief\n\n" + brief,
            "## constraints/README.md\n\n" + constraints,
            "## Cited documents (from contract_citation)\n\n" + cited,
            "## Current feature sheet\n\n" + sheet,
            "## Expected shape\n\n" + FEATURE_SHEET_SHAPE_HINT,
        ],
    )
    client = _make_client()
    raw = _complete(client, user_content)
    return _normalize_review_markdown_output(raw)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("node_id", metavar="NODE_ID")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write Markdown report to this file (default: stdout)",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: git root or cwd).",
    )
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
