#!/usr/bin/env python3
"""Advisory LLM review of a roadmap node (brief + constraints + cited docs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from generate_brief import index as make_index, render_brief
from roadmap_load import load_roadmap

ROOT_DEFAULT = Path(__file__).resolve().parent.parent

ALLOWED_PREFIXES = ("shared/", "docs/", "specs/", "adr/")

SYSTEM_PROMPT = """You are a senior reviewer for roadmap readiness. Output Markdown only.
Assess: agentic checklist completeness, contract/spec clarity, alignment with project
constraints, risks, and open questions for the PM. Do not claim the implementation exists;
evaluate whether a developer could execute without blocking ambiguities. Be concise."""


def _repo_root(ns: argparse.Namespace) -> Path:
    return Path(ns.repo_root).resolve() if ns.repo_root else ROOT_DEFAULT


def _constraints_text(root: Path) -> str:
    p = root / "constraints" / "README.md"
    if not p.is_file():
        return "_(no constraints/README.md)_"
    return p.read_text(encoding="utf-8", errors="replace")


def _cited_snippets(root: Path, node: dict) -> str:
    ac = node.get("agentic_checklist") or {}
    citation = ac.get("spec_citation", "") or ""
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
        return "_(no readable cited files parsed from spec_citation)_"
    return "\n".join(parts)


def _make_client():
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError:
        print(
            "error: openai package not installed. Run: pip install 'specy-road[review]'",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    ep = os.environ.get("SPECY_ROAD_AZURE_OPENAI_ENDPOINT", "").strip()
    if ep:
        key = os.environ.get("SPECY_ROAD_AZURE_OPENAI_API_KEY", "").strip()
        dep = os.environ.get("SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT", "").strip()
        ver = os.environ.get(
            "SPECY_ROAD_OPENAI_API_VERSION",
            "2024-02-15-preview",
        ).strip()
        if not key or not dep:
            print(
                "error: Azure mode needs SPECY_ROAD_AZURE_OPENAI_API_KEY and "
                "SPECY_ROAD_AZURE_OPENAI_DEPLOYMENT",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return AzureOpenAI(
            azure_endpoint=ep,
            api_key=key,
            api_version=ver,
        )

    key = os.environ.get("SPECY_ROAD_OPENAI_API_KEY", "").strip()
    if not key:
        print(
            "error: set SPECY_ROAD_OPENAI_API_KEY or Azure variables "
            "(see docs/pm-workflow.md)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    base = os.environ.get("SPECY_ROAD_OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=key, base_url=base)


def _complete(client, user_content: str) -> str:
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
        help="Repository root (default: parent of scripts/).",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = _repo_root(args)
    nodes = load_roadmap(root)["nodes"]
    by_id = make_index(nodes)
    if args.node_id not in by_id:
        print(f"error: unknown node {args.node_id!r}", file=sys.stderr)
        raise SystemExit(1)
    node = by_id[args.node_id]
    brief = render_brief(args.node_id, by_id, repo_root=root)
    constraints = _constraints_text(root)
    cited = _cited_snippets(root, node)
    user_content = "\n\n".join(
        [
            "## Brief\n\n" + brief,
            "## constraints/README.md\n\n" + constraints,
            "## Cited documents (from spec_citation)\n\n" + cited,
        ],
    )
    client = _make_client()
    report = _complete(client, user_content)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
