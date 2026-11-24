"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.review import review_text, git
from specy_road.review_files import reviews_dir

def review(repo: Path, model: str, **kw) -> None:
    """Shared test helper."""
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, **kw))
