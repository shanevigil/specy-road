"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.review import NODE, git
from pathlib import Path
from specy_road.review_gate import evaluate_gate

def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
