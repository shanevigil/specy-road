"""Shipped skills and the AGENTS.md block cite toolkit docs by URL, not by a path the consumer lacks."""

from __future__ import annotations

from tests.support import REPO
import pytest

import re
from pathlib import Path

from specy_road.agents_md_block import render_agents_lines, render_rules
from specy_road.doc_links import SHIPPED_DOCS, docs_ref, link_toolkit_docs
from specy_road.specyrd_skills import render_skill

TEMPLATES = REPO / "specy_road" / "templates" / "specyrd"


@pytest.mark.repo
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
    rendered = render_skill("specyrd-brainstorm.md") + render_rules() + "\n".join(render_agents_lines())
    bare = [m for m in re.findall(r"(?<![\w/.-])docs/([\w-]+\.md)", rendered) if m not in SHIPPED_DOCS]
    assert bare == []
    assert "/docs/brainstorming.md" in rendered


_RC_PIN = re.compile(r"\d+\.\d+\.\d+rc\d+")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CODE = re.compile(r"^```.*?^```|`[^`\n]*`", re.M | re.S)
_TOOLKIT_URL = re.compile(
    r"https://github\.com/shanevigil/specy-road/blob/main/(docs/[\w-]+\.md)(#[\w-]+)?")


def _docs() -> list[Path]:
    return [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]


def _without_install_section(text: str) -> str:
    """docs/install-and-usage.md's ``## Install`` section keeps its worked release-candidate
    commands."""
    start = text.index("\n## Install\n")
    end = text.index("\n## ", start + 1)
    return text[:start] + text[end:]


@pytest.mark.repo
def test_no_doc_pins_a_release_candidate() -> None:
    """A pinned ``X.Y.ZrcN`` goes stale with the next candidate; the release runbook's worked
    examples and the install section of install-and-usage.md are the only places one belongs.
    Every file under docs/ is scanned, whatever its type (Markdown, YAML, …), and README.md."""
    hits = []
    files = [REPO / "README.md", *sorted(p for p in (REPO / "docs").rglob("*") if p.is_file())]
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        if rel == "docs/release-runbook.md":
            continue
        text = path.read_text(encoding="utf-8")
        if rel == "docs/install-and-usage.md":
            text = _without_install_section(text)
        hits += [f"{rel}: {m.group(0)}" for m in _RC_PIN.finditer(text)]
    assert hits == [], "write X.Y.ZrcN instead of a release candidate's number:\n" + "\n".join(hits)


def _anchors(path: Path) -> set[str]:
    """GitHub's heading anchors: lower case, punctuation dropped, spaces to hyphens, repeats
    numbered."""
    seen: dict[str, int] = {}
    fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fence = not fence
        if fence or not (m := re.match(r"#{1,6} (.+)", line)):
            continue
        slug = re.sub(r"[^\w\- ]", "", m.group(1).strip().lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        seen.setdefault(slug if n == 0 else f"{slug}-{n}", 1)
    return set(seen)


def _broken(source: Path, target: Path, anchor: str) -> str | None:
    if not target.exists():
        shown = target.relative_to(REPO) if target.is_relative_to(REPO) else target
        return f"{source.relative_to(REPO)}: no {shown}"
    if anchor and target.suffix == ".md" and anchor not in _anchors(target):
        return f"{source.relative_to(REPO)}: no #{anchor} in {target.relative_to(REPO)}"
    return None


@pytest.mark.repo
def test_doc_links_resolve() -> None:
    """Every relative link in README.md and docs/, and every toolkit-docs URL there, names a file
    that exists and a heading it has, so a moved or merged doc leaves no dead inbound link."""
    broken = []
    for path in _docs():
        text = _CODE.sub("", path.read_text(encoding="utf-8"))
        for m in _TOOLKIT_URL.finditer(text):
            broken.append(_broken(path, REPO / m.group(1), (m.group(2) or "#")[1:]))
        for m in _LINK.finditer(text):
            target = m.group(1)
            if re.match(r"[a-z]+:", target):
                continue
            name, _, anchor = target.partition("#")
            broken.append(_broken(path, (path.parent / name).resolve() if name else path, anchor))
    assert [b for b in broken if b] == []


@pytest.mark.repo
def test_project_templates_cite_toolkit_docs_by_url() -> None:
    """``init project`` copies templates/project verbatim: a doc the consumer does not get is cited
    by its toolkit URL, and that doc exists."""
    project = REPO / "specy_road" / "templates" / "project"
    bare, missing = [], []
    for path in sorted(p for p in project.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(REPO)
        bare += [f"{rel}: docs/{n}" for n in re.findall(r"(?<![\w/.-])docs/([\w-]+\.md)", text)
                 if n not in SHIPPED_DOCS]
        missing += [f"{rel}: {m.group(1)}" for m in _TOOLKIT_URL.finditer(text)
                    if not (REPO / m.group(1)).is_file()]
    assert bare == []
    assert missing == []


_SHELL_CMD = re.compile(r"^(?:specyrd|specy-road|pip|pipx|uv)\s")
_REAL_PIPE = re.compile(r"\|\s*(?:grep|head|tail|sha256sum|sh|bash|jq|less|sort|tee|xargs|wc)\b")
_PLACEHOLDER = re.compile(r"<[^>]*>|(?:^|\s)\[[^\]]*\]|…|\.\.\.")


def _commands(text: str) -> list[str]:
    """Each command a reader may copy: a fenced-block line, or an inline code span, minus a ``#``
    comment."""
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        elif fence:
            out.append(line.strip())
        else:
            out += [m.group(1).strip() for m in re.finditer(r"`([^`\n]+)`", line)]
    return [c.split(" #")[0].rstrip() for c in out]


def _alternation_offenders(text: str) -> list[str]:
    """The rule: a ``specyrd``/``specy-road``/``pip``/``pipx``/``uv`` command with no placeholder
    (``<…>``, `` […]``, ``…``) is runnable as written, so a ``|`` in it must be a real pipe into
    another program; ``a|b`` alternatives belong in prose. A synopsis with a placeholder is not
    runnable and may use ``|``. Limits: only those five command names, and only the pipe targets in
    ``_REAL_PIPE`` count as pipes."""
    return [c for c in _commands(text)
            if _SHELL_CMD.match(c) and "|" in _REAL_PIPE.sub("", c) and not _PLACEHOLDER.search(c)]


def test_alternation_rule_clauses() -> None:
    assert _alternation_offenders("Run `specyrd init . --ai cursor|codex`.") == [
        "specyrd init . --ai cursor|codex"]
    assert _alternation_offenders("```bash\npip install x|y  # note\n```\n") == ["pip install x|y"]
    real_pipes = "`specy-road worker list --json | jq .` and `pip download x | sha256sum`"
    assert _alternation_offenders(real_pipes) == []
    assert _alternation_offenders("`specy-road prompt <NODE_ID> --role executor|reviewer`") == []
    assert _alternation_offenders("`specyrd init [PATH] --ai cursor|codex`") == []
    extra = 'pip install "specy-road[gui]" --x a|b'
    assert _alternation_offenders(f"`{extra}`") == [extra]


@pytest.mark.repo
def test_no_runnable_doc_command_uses_a_bar_for_alternatives() -> None:
    """A shell reads ``a|b`` as a pipe, so a copied command would run a pipeline: README.md, docs/
    and the Markdown templates ``init project`` and ``specyrd init`` copy into a consumer repo."""
    templates = REPO / "specy_road" / "templates"
    files = [*_docs(), *sorted((templates / "project").rglob("*.md")),
             *sorted((templates / "specyrd").rglob("*.md"))]
    hits = [f"{path.relative_to(REPO)}: {c}" for path in files
            for c in _alternation_offenders(path.read_text(encoding="utf-8"))]
    assert hits == [], ("write one runnable example and name the alternatives in prose:\n"
                        + "\n".join(hits))
