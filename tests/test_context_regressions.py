"""docs/context-regressions.yaml matches the format agentic-sandbox-runbook.md section 9 documents."""

from __future__ import annotations

import copy
from pathlib import Path

import jsonschema
import pytest
import yaml

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
                    "prompt": TEXT,
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


@pytest.mark.parametrize("break_it", [_eleven_cases, _no_pass_condition, _judged_by_the_model])
def test_the_schema_refuses_a_broken_set(break_it) -> None:
    data = copy.deepcopy(_load())
    break_it(data)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, SCHEMA)
