"""What an agent reads before it starts a task: the unconditional start-up closure stays within 400 lines.

The closure is each file once per repo: the entry files (``AGENTS.md`` and ``CLAUDE.md``), the
always-applied Cursor rules, the files ``CLAUDE.md`` imports (the managed rules in a consumer repo),
and the load order up to its "By task" line. The "By task" part and the generated
``roadmap-context.md`` digest are task-conditional and not counted. Run with ``-s`` to see the
counted paths and totals; ``CLAUDE.md``'s size is printed against its estimate, not enforced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from specy_road.agents_md_block import load_order_paths, render_rules
from specy_road.harness_instruction_files import AGENTS_MD, RULES_MD, claude_imports, cursor_paths
from specy_road.init_project import run_init_project
from specy_road.specyrd_init import run_init
from tests.helpers import REPO

START_UP_LIMIT = 400
CLAUDE_MD_ESTIMATE = 20
CONDITIONAL = "By task"


def _consumer(tmp_path: Path) -> Path:
    run_init_project(tmp_path)
    run_init(target=tmp_path, agent="claude-code", dry_run=False, force=False,
             ai_commands_dir=None, write_claude_md=True)
    return tmp_path


def _always_load_order(root: Path) -> list[str]:
    """The files the load order names before its task-conditional part."""
    source = root / RULES_MD if (root / RULES_MD).is_file() else root / AGENTS_MD
    lines = source.read_text(encoding="utf-8").splitlines()
    cut = next(i for i, ln in enumerate(lines) if ln.startswith(CONDITIONAL))
    return load_order_paths(lines[:cut])


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize("repo", ["toolkit", "consumer"])
def test_start_up_reading_exists_and_stays_within_the_limit(repo: str, tmp_path: Path) -> None:
    root = REPO if repo == "toolkit" else _consumer(tmp_path)
    entries = cursor_paths(root, root)
    order = _always_load_order(root)
    assert order, f"{repo}: no unconditional load order found"
    missing = [rel for rel in order if not (root / rel).is_file()]
    assert not missing, f"{repo}: the default load order names missing files {missing}"
    assert "docs/supply-chain-security.md" not in order, f"{repo}: the supply-chain doc is task-conditional"

    closure = dict.fromkeys(p.resolve() for p in [*entries, *claude_imports(entries), *(root / r for r in order)])
    total = 0
    for path in closure:
        n = _lines(path)
        total += n
        print(f"{repo}: {n:4d} {path.relative_to(root.resolve())}")
    claude = root / "CLAUDE.md"
    print(f"{repo}: total {total} lines (limit {START_UP_LIMIT}); CLAUDE.md {_lines(claude)} lines "
          f"(estimate about {CLAUDE_MD_ESTIMATE}, not enforced)")
    assert total <= START_UP_LIMIT, f"{repo}: start-up reading is {total} lines, over {START_UP_LIMIT}"


def test_shipped_rules_cite_only_files_an_adopter_has(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    # No provenance comment ships: tests/test_agents_md_block.py checks render_rules() has no "<!--".
    cited = re.findall(r"`(docs/[\w-]+\.md)`", render_rules())
    assert [d for d in cited if not (root / d).is_file()] == []
