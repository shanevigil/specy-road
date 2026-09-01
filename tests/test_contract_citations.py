"""Tests for contract_citations.

The citation styles exercised here are not invented: each one was observed in
the ``## References`` sections of a real 48-node consumer repo before the
parser was written. A parser that only handles the tidy form would silently
un-inline contracts that people had cited correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.contract_citations import (
    SHARED_README,
    all_contracts,
    cited_contracts,
    citations_in_sheet,
    normalize_citation,
)


def _sheet(body: str) -> str:
    return f"## Intent\n\nSomething.\n\n## References\n\n{body}\n"


# --- normalize_citation -----------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("shared/api-contract.md", "shared/api-contract.md"),
        ("./shared/api-contract.md", "shared/api-contract.md"),
        # Sheets live at planning/<file>.md, so ../ is the project root.
        ("../shared/api-contract.md", "shared/api-contract.md"),
        ("../shared/contracts/auth.md", "shared/contracts/auth.md"),
        ("/shared/api-contract.md", "shared/api-contract.md"),
        ("shared/API-Contract.MD", "shared/API-Contract.MD"),
        # A link target may carry a title.
        ('../shared/x.md "Contract"', "shared/x.md"),
    ],
)
def test_normalize_citation_accepts_real_shapes(token: str, expected: str) -> None:
    assert normalize_citation(token) == expected


@pytest.mark.parametrize(
    "token",
    [
        "shared/",  # the placeholder the feature-sheet template ships
        "shared",
        "docs/api-contract.md",
        "../docs/api-contract.md",
        ".cursor/rules/",
        "M10.1",
        "roadmap/manifest.json",
        "shared/notes.txt",  # not markdown: never inlined
        "shared/../../etc/passwd",  # no escaping out through a citation
        "",
        "   ",
    ],
)
def test_normalize_citation_rejects_non_contracts(token: str) -> None:
    assert normalize_citation(token) is None


# --- citations_in_sheet -----------------------------------------------------


def test_markdown_link_with_backticked_label() -> None:
    """The dominant real-world form."""
    body = (
        "- Frontend patterns: [`shared/lazy-loading.md`]"
        "(../shared/lazy-loading.md)"
    )
    assert citations_in_sheet(_sheet(body)) == ["shared/lazy-loading.md"]


def test_plain_markdown_link() -> None:
    body = "- **Related:** [shared/README.md](../shared/README.md)"
    assert citations_in_sheet(_sheet(body)) == ["shared/README.md"]


def test_inline_code_and_bare_paths() -> None:
    body = "- `shared/a.md` and also shared/b.md in prose"
    assert citations_in_sheet(_sheet(body)) == ["shared/a.md", "shared/b.md"]


def test_bare_shared_directory_is_not_a_citation() -> None:
    """The template placeholder must not read as 'inline everything'."""
    body = "- Contracts (read selectively): `shared/`"
    assert citations_in_sheet(_sheet(body)) == []


def test_mixed_bullet_keeps_only_shared_paths() -> None:
    body = (
        "- **Touch zones:** `backend/app/services/attachment_service.py`\n"
        "- **Related:** [docs/api-contract.md](../docs/api-contract.md), "
        "[shared/README.md](../shared/README.md), "
        "[`.cursor/rules/`](../.cursor/rules/)"
    )
    assert citations_in_sheet(_sheet(body)) == ["shared/README.md"]


def test_malformed_link_wrapped_in_backticks_is_ignored() -> None:
    """Seen verbatim in a real sheet; must not crash or match."""
    body = "- `[.cursor/rules/](../.cursor/rules/)`"
    assert citations_in_sheet(_sheet(body)) == []


def test_no_references_section() -> None:
    assert citations_in_sheet("## Intent\n\nNo references here.\n") == []


def test_empty_references_section() -> None:
    assert citations_in_sheet("## References\n\n## Approach\n\nx\n") == []


def test_heading_matching_is_forgiving() -> None:
    text = "## references:\n\n- `shared/a.md`\n"
    assert citations_in_sheet(text) == ["shared/a.md"]


def test_only_the_references_section_is_scanned() -> None:
    """A contract merely discussed in prose is not a citation."""
    text = (
        "## Approach\n\nConform to `shared/a.md` throughout.\n\n"
        "## References\n\n- `shared/b.md`\n"
    )
    assert citations_in_sheet(text) == ["shared/b.md"]


def test_duplicate_citations_collapse_in_document_order() -> None:
    body = "- [`shared/a.md`](../shared/a.md) and `shared/a.md` again"
    assert citations_in_sheet(_sheet(body)) == ["shared/a.md"]


# --- cited_contracts / all_contracts ----------------------------------------


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "README.md").write_text("idx\n", encoding="utf-8")
    (tmp_path / "shared" / "a.md").write_text("A\n", encoding="utf-8")
    (tmp_path / "shared" / "contracts").mkdir()
    (tmp_path / "shared" / "contracts" / "b.md").write_text("B\n", encoding="utf-8")
    (tmp_path / "planning").mkdir()
    return tmp_path


def test_cited_contracts_is_sorted_and_deduplicated(tmp_path: Path) -> None:
    """Sorted explicitly: the brief's determinism test runs in one process and
    would not catch set-iteration order differing across machines."""
    root = _repo(tmp_path)
    one = root / "planning" / "one.md"
    two = root / "planning" / "two.md"
    one.write_text(_sheet("- `shared/contracts/b.md`"), encoding="utf-8")
    two.write_text(
        _sheet("- `shared/a.md`\n- `shared/contracts/b.md`"), encoding="utf-8"
    )

    assert cited_contracts([one, two], root) == [
        "shared/a.md",
        "shared/contracts/b.md",
    ]


def test_cited_contracts_drops_citations_that_do_not_exist(tmp_path: Path) -> None:
    """A stale citation must not put an unreadable heading in the brief."""
    root = _repo(tmp_path)
    sheet = root / "planning" / "one.md"
    sheet.write_text(_sheet("- `shared/gone.md`\n- `shared/a.md`"), encoding="utf-8")

    assert cited_contracts([sheet], root) == ["shared/a.md"]


def test_cited_contracts_tolerates_a_missing_sheet(tmp_path: Path) -> None:
    """A brief must still render when a planning sheet has been deleted."""
    root = _repo(tmp_path)
    assert cited_contracts([root / "planning" / "nope.md"], root) == []


def test_all_contracts_is_recursive_and_sorted(tmp_path: Path) -> None:
    """The flat glob this replaces never saw shared/<dir>/*.md."""
    root = _repo(tmp_path)
    assert all_contracts(root) == [
        "shared/README.md",
        "shared/a.md",
        "shared/contracts/b.md",
    ]


def test_all_contracts_without_a_shared_directory(tmp_path: Path) -> None:
    assert all_contracts(tmp_path) == []


def test_shared_readme_constant_matches_the_discovered_path(tmp_path: Path) -> None:
    """Guards the always-inline rule against a rename of either side."""
    root = _repo(tmp_path)
    assert SHARED_README in all_contracts(root)
