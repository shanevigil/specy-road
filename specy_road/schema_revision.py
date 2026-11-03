"""A bundled JSON schema as a specy-road checkout has it at a revision, beside the installed copy.

The installed package checks records with the schemas it ships. A leaf that
adds or changes a field in one of them (a policy key, a review-record field)
writes records that copy rejects, so the installed specy-road could not gate or
finish the leaf: the coordinator had to rerun both with the branch's own code.

When the project lives in a specy-road checkout (``specy_road/__init__.py`` at
its git root), a record the schema accepts *as committed at the record's
revision* is valid too: a review or READY file at its ``commit``, a config read
from a ref at that ref, a working-tree file against the working tree's copy.
That copy is part of what the reviewers approve. Anywhere else (an adopter
repo) there is no such copy and only the installed schema counts.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import specy_road_package_dir

#: Where a specy-road checkout keeps the package, from its git root.
PACKAGE_REL = "specy_road"


def checkout_top(start: Path) -> Path | None:
    """The git root above ``start`` when it holds the specy-road package; git is not run."""
    here = Path(start).resolve()
    top = next((p for p in (here, *here.parents) if (p / ".git").exists()), None)
    return top if top is not None and (top / PACKAGE_REL / "__init__.py").is_file() else None


@cache
def _installed_text(sub: str) -> str:
    return (specy_road_package_dir() / sub).read_text(encoding="utf-8")


@cache
def _validator(text: str) -> Draft202012Validator | None:
    """The compiled schema, or ``None`` for one that is not valid JSON Schema."""
    try:
        schema = json.loads(text)
        Draft202012Validator.check_schema(schema)
    except (ValueError, SchemaError):
        return None
    return Draft202012Validator(schema)


def revision_text(top: Path, sub: str, rev: str | None) -> str | None:
    """``specy_road/<sub>`` at ``rev`` (``git show``), or in the working tree when ``rev`` is ``None``."""
    if rev is None:
        try:
            return (top / PACKAGE_REL / sub).read_text(encoding="utf-8")
        except OSError:
            return None
    if not isinstance(rev, str) or not rev or rev.startswith("-"):   # never let a record's value reach git as an option
        return None
    return git_stdout(["show", f"{rev}:{PACKAGE_REL}/{sub}"], top)


def accepted_at_revision(data: Any, sub: str, where: Path | None, rev: str | None = None) -> bool:
    """Whether ``specy_road/<sub>`` accepts ``data`` as the checkout holding ``where`` has it at ``rev``.

    ``rev`` ``None`` is the working tree. False outside a specy-road checkout,
    for a revision without the file or with an unusable one, and when that copy
    is the installed one, which the caller has already run.
    """
    top = checkout_top(where) if where is not None else None
    text = revision_text(top, sub, rev) if top is not None else None
    if text is None or text == _installed_text(sub):
        return False
    v = _validator(text)
    return v is not None and v.is_valid(data)
