"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.review import review_text
from specy_road.review_files import reviews_dir
from specy_road.bundled_scripts import role_prompt
from specy_road.orchestration.workers import worker_state as ws
import yaml

def file_review(repo: Path, model: str, commit: str, verdict: str, changes: list[str] | None = None) -> None:
    text = review_text(commit, model=model, verdict=verdict)
    if changes is not None:
        _, front, body = text.split("---\n", 2)
        data = yaml.safe_load(front) | {"required_changes": changes}
        text = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n" + body
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text, encoding="utf-8")

def stopped_worker(repo: Path, model: str, state: str, message: str | None) -> ws.WorkerRecord:
    rec = ws.create_record(repo, "M1.1", "generic", model, repo)
    if message is not None:
        ws.append_event(repo, rec, "turn_completed", source="worker", authority="worker_suggestion",
                        summary="success", detail={"message": message})
    ws.append_event(repo, rec, "output", source="worker", authority="worker_suggestion", summary="(tool use)")
    return ws.set_state(repo, rec, state, pid=None)

def executor_prompt(repo: Path) -> str:
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None
    return text
