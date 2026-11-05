"""M15.19: a Cursor turn whose init line names the rostered model by its display name is priced, with no mismatch
note; a real mismatch keeps the note and drops the roster-price estimate."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_cursor_usage_cost import PROFILES
from tests.test_worker_adapters import CURSOR_RESULT

from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.model_names import normalise, same_model
from specy_road.worker_adapters import Launch

SLUG = "cursor-grok-4.6-high"
# The field roster entry (sr/roadmap/orchestration.yaml): its profile lists no Cursor aliases.
ROSTER = f"""version: 1
roster:
  - {{id: human, family: human, roles: [coordinator, reviewer]}}
  - id: {SLUG}
    family: xai
    harness: cursor
    harness_model: {SLUG}
    profile: model-profiles/spacexai-grok/grok-4.6.md
    roles: [executor]
policy: {{}}
"""


def _repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    dest = repo / "model-profiles" / "spacexai-grok" / "grok-4.6.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = (PROFILES / "spacexai-grok" / "grok-4.6.md").read_text()
    dest.write_text(re.sub(r"^aliases:\n(?:  - .*\n)+", "", text, flags=re.M))
    git(repo, "checkout", "-q", "dev")
    git(repo, "add", "model-profiles")
    git(repo, "commit", "-qm", "grok profile")
    return repo


def _usage_event(tmp_path: Path, reported: str) -> ws.WorkerEvent:
    """Run a fake cursor turn printing an init line naming ``reported`` and the recorded result line."""
    repo = _repo(tmp_path)
    init = {"type": "system", "subtype": "init", "apiKeySource": "login", "cwd": str(repo),
            "session_id": "<session>", "model": reported, "permissionMode": "default"}
    spec = tmp_path / "turn.json"
    spec.write_text(json.dumps([init, CURSOR_RESULT]))
    script = tmp_path / "fake-cursor.py"
    script.write_text("import json, sys\nfor l in json.load(open(sys.argv[1])):\n    print(json.dumps(l), flush=True)\n")
    rec = ws.create_record(repo, "M1.1", "cursor", SLUG, repo)
    argv = [sys.executable, str(script), str(spec), "--model", SLUG, "--workspace", str(repo)]
    assert wr.run(repo, rec.worker_id, Launch(argv)) == 0
    return next(e for e in ws.events_since(repo, rec.worker_id) if e.type == "usage")


def test_display_name_is_the_rostered_slug_and_the_turn_is_priced(tmp_path: Path) -> None:
    ev = _usage_event(tmp_path, "Grok 4.6 High")
    assert "model mismatch" not in ev.summary
    assert ev.detail["cost_usd"] == 0.021228 and ev.detail["cost_is_estimate"] is True
    assert "$0.0212 est." in ev.summary


def test_real_mismatch_keeps_the_note_and_leaves_cost_unknown(tmp_path: Path) -> None:
    ev = _usage_event(tmp_path, "Composer 2.5")
    assert ev.summary.endswith(f"; model mismatch: told {SLUG}, harness reported Composer 2.5")
    assert "$?" in ev.summary
    assert ev.detail["cost_usd"] is None and ev.detail["cost_is_estimate"] is None


def test_normalise_treats_case_spaces_dots_hyphens_alike() -> None:
    assert normalise("Grok 4.6 High") == normalise("grok-4.6-high") == normalise("GROK_4-6 high") == "grok-4-6-high"
    assert normalise("Grok 4.7  High Fast​​") == "grok-4-7-high-fast"   # Cursor's padded display name
    assert normalise("composer-2.5") != normalise("composer-25")


@pytest.mark.parametrize(("reported", "same"), [
    ("Grok 4.6 High", True),    # the slug without Cursor's prefix
    ("Grok 4.6", True),         # the profile's model name (Cursor's model list shows it for the high slug)
    ("grok-4.6", True),         # the profile's api_id
    ("Grok 4.7 High", False),
    ("Composer 2.5", False),
])
def test_same_model_against_slug_harness_model_and_profile(reported: str, same: bool) -> None:
    from specy_road.model_profiles import Profile

    prof = Profile(Path("grok-4.6.md"), {"api_id": "grok-4.6", "model": "Grok 4.6"})
    assert same_model(reported, SLUG, SLUG, prof) is same
    assert same_model("Grok Display", SLUG, profile=Profile(Path("x.md"), {"display_name": "Grok Display"}))
