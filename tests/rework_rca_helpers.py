"""Public builders for M15.6's rework/RCA tests: an RCA record, writing it, the review CLI, filing order."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import reviews_dir

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
"""


def run_review_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def rca_record(round_: int, instructions: str, action: str = "continue_with_class_fix") -> dict[str, Any]:
    """A valid forced RCA by ``sol`` (independent of the ``opus``/``sonnet`` reviewers) for leaf ``M1.1``."""
    return {
        "node_id": "M1.1", "model": "sol", "date": "2026-11-04",
        "trigger": {"rule": "forced", "acceptance_ids": [], "round": round_, "reason": "fix-round budget spent"},
        "classification": {"primary": "hard_problem", "confidence": 0.7},
        "evidence": [{"kind": "finding", "ref": f"round {round_}/opus", "note": "a new input class"}],
        "recommended_action": {"type": action, "instructions": instructions, "requires_human_approval": True},
    }


def write_rca(repo: Path, data: dict[str, Any]) -> Path:
    path = reviews_dir(repo, "M1.1") / f"RCA-{data['trigger']['round']}.md"
    path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nreasoning\n", encoding="utf-8")
    return path


def file_after(later: Path, earlier: Path, seconds: int = 1) -> None:
    """Set ``later``'s filing time (mtime) to ``seconds`` after ``earlier``'s, so order never rests on a clock tick."""
    t = earlier.stat().st_mtime_ns + seconds * 1_000_000_000
    os.utime(later, ns=(t, t))
