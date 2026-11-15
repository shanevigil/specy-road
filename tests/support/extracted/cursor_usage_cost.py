"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.review import make_review_repo, git
from specy_road.orchestration_pinned import pinned_config
from specy_road.orchestration_pinned import pinned_profile_for_entry
from specy_road.orchestration_config import roster_entry
import shutil

REPO_ROOT = Path(__file__).resolve().parents[2].parent

PROFILES = REPO_ROOT / "specy_road" / "templates" / "project" / "model-profiles"

CODEX_ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: priced
    family: openai
    harness: codex
    profile: model-profiles/openai-gpt/gpt-6.1-sol.md
    roles: [executor]
policy: {}
"""

def priced_repo(tmp_path: Path, roster: str, profiles: tuple[str, ...]) -> Path:
    repo = make_review_repo(tmp_path, orchestration=roster)
    for rel in profiles:
        dest = repo / "model-profiles" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROFILES / rel, dest)
    git(repo, "checkout", "-q", "dev")
    git(repo, "add", "model-profiles")
    git(repo, "commit", "-qm", "priced profiles")
    return repo

def codex_repo(tmp_path: Path) -> Path:
    """Shared test helper."""
    return priced_repo(tmp_path, CODEX_ROSTER, ("openai-gpt/gpt-6.1-sol.md",))

def api_id_for(repo: Path, roster_id: str) -> str | None:
    """The id ``worker_ops._cli_for`` puts on argv: profile api_id, or none when unknown."""
    config, err = pinned_config(repo)
    assert err is None
    entry = roster_entry(config, roster_id)
    prof = pinned_profile_for_entry(repo, entry)
    assert prof is not None and prof.ok
    return None if prof.api_id.strip().lower() == "unknown" else prof.api_id
