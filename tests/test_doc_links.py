"""Shipped skills and the AGENTS.md block cite toolkit docs by URL, not by a path the consumer lacks."""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.agents_md_block import render_agents_lines
from specy_road.doc_links import SHIPPED_DOCS, docs_ref, link_toolkit_docs
from specy_road.specyrd_skills import render_skill

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "specy_road" / "templates" / "specyrd"


def test_every_doc_a_shipped_template_cites_exists() -> None:
    """A rename in docs/ would otherwise ship a dead link in every consumer's skills."""
    cited = {m for p in TEMPLATES.rglob("*.md")
             for m in re.findall(r"docs/([\w-]+\.md)", p.read_text(encoding="utf-8"))}
    assert cited
    assert sorted(n for n in cited if not (REPO / "docs" / n).is_file()) == []


def test_release_versions_map_to_their_tag() -> None:
    assert docs_ref("0.3.1rc1") == "v0.3.1-rc1"
    assert docs_ref("0.3.1") == "v0.3.1"
    assert docs_ref("0.3.2.dev4") == "main"


def test_a_shipped_doc_stays_local_and_the_rest_become_urls() -> None:
    text = link_toolkit_docs("`docs/brainstorming.md`, `docs/supply-chain-security.md`", "0.3.1")
    assert text == ("`https://github.com/shanevigil/specy-road/blob/v0.3.1/docs/brainstorming.md`, "
                    "`docs/supply-chain-security.md`")
    assert "supply-chain-security.md" in SHIPPED_DOCS


def test_rendered_skill_and_block_carry_no_bare_toolkit_doc_path() -> None:
    rendered = render_skill("specyrd-brainstorm.md") + "\n".join(render_agents_lines())
    bare = [m for m in re.findall(r"(?<![\w/.-])docs/([\w-]+\.md)", rendered) if m not in SHIPPED_DOCS]
    assert bare == []
    assert "/docs/brainstorming.md" in rendered
