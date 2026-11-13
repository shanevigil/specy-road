"""``checks:`` in ``roadmap/git-workflow.yaml``: the commands pickup, ready, land and prompts use.

Each entry names a command once (``run``) with the stages it is used at (``when``): ``baseline``
(pickup's check of the integration branch), ``ready`` (``specy-road ready`` runs it beside its
``--run`` commands), ``land`` (the land check on the merge commit) and ``prompt`` (the leaf test
command executor briefs and reviewer prompts give, with the test paths appended). The schema and
its rules are in ``docs/git-workflow.md`` (Checks).

The legacy keys ``baseline_cmd``, ``land_check_cmd`` and ``verify_cmd`` are still read, each as
one entry of its stage, until the release after 0.3.1; when ``checks:`` is present they are
ignored. :func:`legacy_notice` is validate's one notice about them and :func:`migrate_text` is
``upgrade``'s rewrite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from specy_road.git_workflow_config import GIT_WORKFLOW_REL, load_git_workflow_config

#: Each legacy key, the stage it is one entry of, and the ``name`` ``upgrade`` gives that entry.
LEGACY_KEYS = {"baseline_cmd": ("baseline", "baseline"), "land_check_cmd": ("land", "land check"),
               "verify_cmd": ("prompt", "verify")}


def _stages(entry: dict[str, Any]) -> list[str]:
    when = entry.get("when")
    return [when] if isinstance(when, str) else list(when or [])


def stage_commands(data: dict[str, Any] | None, stage: str) -> list[str]:
    """The non-blank commands of ``stage`` in a loaded ``git-workflow.yaml``, in file order.

    ``checks:`` when present, else the stage's legacy key (a blank one is no command).
    """
    data = data or {}
    if "checks" in data:
        found = [str(e.get("run") or "") for e in data["checks"] or [] if stage in _stages(e)]
    else:
        found = [str(data.get(key) or "") for key, (st, _name) in LEGACY_KEYS.items()
                 if st == stage]
    return [cmd.strip() for cmd in found if cmd.strip()]


def check_commands(repo_root: Path, stage: str, *, cli: str | None = None) -> list[str]:
    """The commands ``stage`` runs: the CLI value when given, else the config's.

    An empty CLI value runs none. An unreadable config has none, as the legacy readers did.
    """
    if cli is not None:
        return [cli.strip()] if cli.strip() else []
    data, err = load_git_workflow_config(repo_root)
    return [] if err else stage_commands(data, stage)


def verify_cmd_lines(repo_root: Path) -> list[str]:
    """The sentence an executor brief and a reviewer prompt carry about running the leaf's tests.

    The first ``prompt`` command is named. The wording is the one prompts gave before ``checks:``
    and still names ``verify_cmd``, so a prompt reads the same from either form.
    """
    cmds = check_commands(repo_root, "prompt")
    if cmds:
        line = (f"**Running tests:** run this leaf's tests with `{cmds[0]}` followed by the test "
                f"paths (`verify_cmd` in `{GIT_WORKFLOW_REL.as_posix()}`); other workers may share "
                "this machine, and the full suite runs at landing.")
    else:
        line = ("**Running tests:** when other workers share this machine, cap parallel test "
                "workers (for example `pytest -n 4`, not `-n auto`): each full parallel suite "
                "starts one worker per core. A project can name the command as `verify_cmd` in "
                f"`{GIT_WORKFLOW_REL.as_posix()}`.")
    return [line, ""]


def legacy_notice(data: dict[str, Any] | None) -> str | None:
    """validate's one notice when the config uses a legacy key, or ``None``."""
    keys = [k for k in LEGACY_KEYS if k in (data or {})]
    if not keys:
        return None
    named = ", ".join(keys)
    if "checks" in (data or {}):
        return (f"notice: {GIT_WORKFLOW_REL.as_posix()} has checks:, so {named} "
                "(removed in the release after 0.3.1) is ignored; delete it.")
    return (f"notice: {GIT_WORKFLOW_REL.as_posix()} uses {named}, read until the release after "
            "0.3.1; run specy-road upgrade to rewrite it as checks: "
            "(docs/git-workflow.md, Checks).")


def _without_keys(text: str, keys: list[str]) -> str:
    """``text`` without the top-level ``key:`` lines of ``keys`` and indented lines after them."""
    out: list[str] = []
    dropping = False
    for line in text.splitlines(keepends=True):
        if re.match(r"\S", line):
            dropping = any(re.match(rf"{re.escape(k)}\s*:", line) for k in keys)
            if dropping:
                continue
        elif dropping and line.strip():
            continue
        out.append(line)
    return "".join(out)


def migrate_text(text: str) -> str | None:
    """``upgrade``'s rewrite of ``git-workflow.yaml``: legacy keys become ``checks:`` entries.

    Each non-blank key becomes one entry of its stage, appended in :data:`LEGACY_KEYS` order; with
    ``checks:`` already present the keys are only removed, since they were ignored. Every other line
    is kept as written. ``None`` when there is nothing to rewrite, so a second run changes nothing,
    or when the text is not YAML (validate reports that).
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    keys = [k for k in LEGACY_KEYS if isinstance(data, dict) and k in data]
    if not keys:
        return None
    entries = [] if "checks" in data else [
        {"name": LEGACY_KEYS[k][1], "run": str(data[k]).strip(), "when": LEGACY_KEYS[k][0]}
        for k in keys if str(data[k] or "").strip()]
    out = _without_keys(text, keys)
    if entries:
        block = yaml.safe_dump({"checks": entries}, sort_keys=False, default_flow_style=False,
                               width=1000)
        out = out.rstrip("\n") + "\n" + block
    return out
