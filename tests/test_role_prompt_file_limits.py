"""M11.55: executors split modules to meet file limits; reviewers ask for removed text back."""

from __future__ import annotations

from pathlib import Path

from tests.test_models_and_prompt import make_profile_repo

from specy_road.bundled_scripts import role_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir


def test_executor_prompt_says_split_into_a_new_module_never_delete_docs(tmp_path: Path) -> None:
    text, _prof, err = role_prompt.build_prompt(make_profile_repo(tmp_path), "M1.1", role="executor", model="opus")
    assert err is None
    assert ("If a change would push a file over a `specy-road file-limits` cap, move the new or related code "
            "into a new module and name that file in your implementation summary") in text
    assert "never delete or shorten unrelated docstrings, comments or user-facing text to fit" in text


def test_reviewer_prompt_asks_for_removed_docs_to_be_restored(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert ("check the diff for docstrings, comments or messages removed or shortened that the leaf did not "
            "need to touch") in text
    assert "require their restoration under `required_changes`" in text
    assert "move the new or related code into a new module" not in text   # the executor's line only
