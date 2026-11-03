"""M11.67: worker usage estimates Cursor turn cost from roster profile cost_usd_per_mtok."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_adapters import CURSOR_RESULT, RECORDED

from specy_road import worker_adapters as wa
from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli
from specy_road.worker_adapter_parsers import estimate_usage_cost, mtok_rates
from specy_road.worker_adapters import Launch

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES = REPO_ROOT / "specy_road" / "templates" / "project" / "model-profiles"

CURSOR_ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: priced
    family: cursor
    harness: cursor
    profile: model-profiles/cursor-composer/composer-2.5.md
    roles: [executor]
  - id: unpriced
    family: cursor
    harness: cursor
    profile: model-profiles/cursor-composer/composer-2.md
    roles: [executor]
policy: {}
"""


def _cursor_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path, orchestration=CURSOR_ROSTER)
    for rel in ("cursor-composer/composer-2.5.md", "cursor-composer/composer-2.md"):
        dest = repo / "model-profiles" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROFILES / rel, dest)
    git(repo, "checkout", "-q", "dev")
    git(repo, "add", "model-profiles")
    git(repo, "commit", "-qm", "cursor profiles")
    return repo


def test_estimate_usage_cost_prices_cached_input_at_cached_rate() -> None:
    rates = {"input": 4.0, "output": 20.0, "cached_input": 0.2}
    usage = {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 100}
    assert estimate_usage_cost(usage, rates) == 0.00296


def test_estimate_usage_cost_returns_none_without_list_prices() -> None:
    usage = {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 10}
    assert estimate_usage_cost(usage, mtok_rates({"cost_usd_per_mtok": {"input": "unknown", "output": "unknown"}})) is None


def test_cursor_parse_events_estimates_cost_for_cached_input(tmp_path: Path, monkeypatch) -> None:
    repo = _cursor_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECY_ROAD_REPO_ROOT", raising=False)
    cu = wa.adapter_for("cursor")
    launch = Launch(["agent", "-p", "--output-format", "stream-json", "--model", "priced",
                     "--workspace", str(repo), "ok"])
    usage = cu.parse_events(json.dumps(CURSOR_RESULT), launch)[0].usage
    assert usage["input_tokens"] == 9323 + 4864 and usage["cached_input_tokens"] == 4864
    assert usage["cost_usd"] == 0.007156 and usage["cost_is_estimate"] is True


def test_cursor_parse_events_leaves_cost_null_when_profile_has_no_price(tmp_path: Path, monkeypatch) -> None:
    repo = _cursor_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("SPECY_ROAD_REPO_ROOT", raising=False)
    cu = wa.adapter_for("cursor")
    launch = Launch(["agent", "-p", "--model", "unpriced", "--workspace", str(repo)])
    usage = cu.parse_events(json.dumps(CURSOR_RESULT), launch)[0].usage
    assert usage["cost_usd"] is None and usage["cost_is_estimate"] is None


def test_worker_usage_shows_estimated_cursor_cost(tmp_path: Path, capsys) -> None:
    from specy_road import worker_runner as wr

    repo = _cursor_repo(tmp_path)
    script = tmp_path / "fake-cursor.py"
    script.write_text(
        "import json, sys\n"
        "for line in json.loads(open(sys.argv[1]).read())['lines']:\n"
        "    print(json.dumps(line), flush=True)\n"
    )
    rec = ws.create_record(repo, "M1.1", "cursor", "priced", repo)
    spec = tmp_path / "turn.json"
    spec.write_text(json.dumps({"lines": RECORDED["cursor"]["lines"], "exit": 0}))
    wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec), "--model", "priced",
                                        "--workspace", str(repo)]))
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    out = capsys.readouterr().out
    assert "est." in out and "$?" not in out.split("attempt 1")[1].split("total")[0]
