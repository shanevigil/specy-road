"""docs/context-regressions.yaml matches the format agentic-sandbox-runbook.md section 9 documents."""

from __future__ import annotations

import copy
import shlex
from pathlib import Path

import jsonschema
import pytest
import yaml

from tests.review_repo_helpers import make_review_repo

from specy_road.bundled_scripts import role_prompt

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "docs" / "context-regressions.yaml"

TEXT = {"type": "string", "minLength": 1}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["version", "cases"],
    "properties": {
        "version": {"const": 1},
        "cases": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "source", "app", "harnesses", "prompt", "pass", "runs"],
                "properties": {
                    "id": {"type": "string", "pattern": "^CR[0-9]+$"},
                    "title": TEXT,
                    "source": {"type": "array", "minItems": 1, "items": TEXT},
                    "app": {"enum": ["todo", "calculator", "notes"]},
                    "harnesses": {"type": "array", "minItems": 1, "uniqueItems": True,
                                  "items": {"enum": ["claude-code", "codex", "cursor"]}},
                    "setup": TEXT,
                    "prompt": {"oneOf": [TEXT, {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["command", "send"],
                        "properties": {"command": {"type": "string", "pattern": "^specy-road prompt "},
                                       "send": TEXT},
                    }]},
                    "pass": {"type": "array", "minItems": 1, "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["artifact", "expect"],
                        "properties": {"artifact": TEXT, "expect": TEXT},
                    }},
                    "runs": {"type": "integer", "minimum": 1},
                },
            },
        },
    },
}


def _load() -> dict:
    return yaml.safe_load(CASES.read_text(encoding="utf-8"))


def test_the_set_validates_and_cites_sources_that_exist() -> None:
    data = _load()
    jsonschema.validate(data, SCHEMA)
    ids = [c["id"] for c in data["cases"]]
    assert len(ids) == len(set(ids))
    cited = {s.split("::")[0].split("#")[0] for c in data["cases"] for s in c["source"]}
    assert sorted(p for p in cited if not (REPO / p).is_file()) == []


def _eleven_cases(data: dict) -> None:
    data["cases"] = [data["cases"][0]] * 11


def _no_pass_condition(data: dict) -> None:
    del data["cases"][0]["pass"]


def _judged_by_the_model(data: dict) -> None:
    data["cases"][0]["pass"] = ["the agent says it did not approve"]


def _prompt_from_another_command(data: dict) -> None:
    data["cases"][0]["prompt"] = {"command": "cat notes.md", "send": "notes.md"}


@pytest.mark.parametrize("break_it", [_eleven_cases, _no_pass_condition, _judged_by_the_model,
                                      _prompt_from_another_command])
def test_the_schema_refuses_a_broken_set(break_it) -> None:
    data = copy.deepcopy(_load())
    break_it(data)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, SCHEMA)


@pytest.mark.parametrize("case", [c for c in _load()["cases"] if isinstance(c["prompt"], dict)],
                         ids=lambda c: c["id"])
def test_a_rendered_prompt_writes_the_file_it_sends_and_renders_the_same_twice(
    case: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 9 step 1: run `command` in the git root, send the file `send` names."""
    def fill(text: str) -> str:
        return text.replace("<ID>", "M1.1").replace("<roster id>", "exec")

    argv = shlex.split(fill(case["prompt"]["command"]))
    git_root = tmp_path / "git"
    project = git_root / (argv[argv.index("--repo-root") + 1] if "--repo-root" in argv else ".")
    project.parent.mkdir(parents=True, exist_ok=True)
    make_review_repo(tmp_path, orchestration="version: 1\nroster:\n"
                     "  - {id: exec, family: anthropic, roles: [executor]}\n").rename(project)
    monkeypatch.chdir(git_root)
    texts = []
    for _ in range(2):
        with pytest.raises(SystemExit) as done:
            role_prompt.main(argv[2:])
        assert done.value.code == 0
        texts.append(Path(fill(case["prompt"]["send"])).read_text(encoding="utf-8"))
    assert texts[0] == texts[1]
    assert "## Your role: executor" in texts[0] and "# Work-packet brief: `M1.1`" in texts[0]
