"""``specy-road chore garden`` (``docs/orchestration-chores.md``, Gardening): read-only drift scans.

Each finding is one line, ``<class>: <path>:<line>: <detail>``, with git-root-relative paths:

- ``stale-command``: ``docs/**/*.md`` or an agent file names a ``specy-road`` / ``specyrd``
  command this version does not register (the scanner ``validate`` runs on agent files).
- ``advisory-rule``: a provenance comment marked ``enforced: advisory`` in a managed agent
  file, or in the templates they are rendered from when those are in this checkout
  (rendering strips the comments): a rule nothing checks.
- ``ratchet-grew``: a ``policy.ratchet_paths`` baseline with lines added since the newest tag.

:func:`open_chores` files each class as at most one leaf through the add-node write; nothing
here edits code, docs or agent files. Each run is recorded in ``work/chores/.garden.json``,
which ``validate`` reads for ``policy.garden_cadence_days``.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import PROVENANCE
from specy_road.bundled_scripts.chore_cli import chores_dir
from specy_road.bundled_scripts.validate_stale_commands import (
    agent_files,
    file_unregistered_commands,
    stale_command_advice,
)
from specy_road.git_subprocess import git_text
from specy_road.harness_instruction_files import RULES_MD
from specy_road.integrity import _ratchet_findings, integration_ratchet_paths
from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked
from specy_road.orchestration_config import effective_config
from specy_road.runtime_paths import git_root
from specy_road.worker_state import WorkerError, _write_atomic

#: Finding class -> the title of the chore leaf ``--open-chores`` files for it.
CLASSES = {
    "stale-command": "Garden: stale command mentions",
    "advisory-rule": "Garden: advisory rules nothing enforces",
    "ratchet-grew": "Garden: ratchet baselines grown since the last tag",
}
#: Per path, what the chore leaf must leave true; ``{path}`` is the finding path.
_ACCEPTANCE = {
    "stale-command": "`{path}` names no specy-road command this version does not register",
    "advisory-rule": "each `enforced: advisory` rule in `{path}` gains a check that enforces it, "
                     "or a note on why it stays advisory",
    "ratchet-grew": "`{path}` is back to its size at the last tag, or the summary says why it grew",
}
ACCEPTANCE_CAP = 10
_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "specyrd"
_RULE_TEMPLATES = ("agents-md-block.md", "agents-rules.md", "claude-md-block.md")


@dataclass(frozen=True)
class Finding:
    cls: str
    path: str
    line: int | None
    detail: str

    def text(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{self.cls}: {where}: {self.detail}"


def _roots(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    return root, git_root(root) or root


def stale_command_findings(root: Path) -> list[Finding]:
    root, checkout = _roots(root)
    docs = [p for base in (root, checkout) for p in sorted((base / "docs").rglob("*.md"))]
    return list(dict.fromkeys(   # a line naming one command twice is one finding
        Finding("stale-command", path.relative_to(checkout).as_posix(), lineno,
                f"`{mention}` is not a command in specy-road {__version__}; {stale_command_advice(mention)}")
        for path in dict.fromkeys([*docs, *agent_files(root), root / RULES_MD])   # validate's set, plus the rules
        for lineno, mention in file_unregistered_commands(path)))


def advisory_rule_findings(root: Path) -> list[Finding]:
    root, checkout = _roots(root)
    templates = [t for t in (_TEMPLATES / n for n in _RULE_TEMPLATES) if t.is_relative_to(checkout)]
    out: list[Finding] = []
    for path in dict.fromkeys([*agent_files(root), root / RULES_MD, *templates]):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            line = line.strip()
            if PROVENANCE.fullmatch(line) and "| enforced: advisory" in line:
                prevents = line.removeprefix("<!-- ").split(" | ")[0]
                out.append(Finding("advisory-rule", path.relative_to(checkout).as_posix(), lineno, prevents))
    return out


def ratchet_findings(root: Path) -> tuple[list[Finding], list[str]]:
    """Findings, and the one note saying why the scan was skipped when there is no tag."""
    paths = integration_ratchet_paths(root)
    if not paths:
        return [], []
    tag = git_text(["describe", "--tags", "--abbrev=0"], root)
    if not tag:
        return [], ["ratchet-grew: skipped; no tag to compare against (`git describe --tags` found none)"]
    return [Finding("ratchet-grew", f.path, None, f"+{f.detail} line(s) since {tag}")
            for f in _ratchet_findings(root, tag, "HEAD", paths)], []


def scan(root: Path) -> tuple[list[Finding], list[str]]:
    ratchet, notes = ratchet_findings(root)
    return [*stale_command_findings(root), *advisory_rule_findings(root), *ratchet], notes


def _acceptance(cls: str, found: list[Finding]) -> list[str]:
    by_path: dict[str, list[Finding]] = {}
    for f in found:
        by_path.setdefault(f.path, []).append(f)
    lines = [_ACCEPTANCE[cls].format(path=path) + " (now: "
             + ", ".join(f"line {f.line}" if f.line else f.detail for f in fs) + ")"
             for path, fs in list(by_path.items())[:ACCEPTANCE_CAP]]
    if len(by_path) > ACCEPTANCE_CAP:
        rest = list(by_path.values())[ACCEPTANCE_CAP:]
        lines.append(f"the same for {len(rest)} more path(s) ({sum(map(len, rest))} finding(s)); "
                     "`specy-road chore garden` lists them")
    return lines


def open_chores(root: Path, findings: list[Finding], under: str) -> list[str]:
    """One leaf under ``under`` per class with findings, unless a non-Complete one is open; what was done."""
    # Lazy: roadmap_crud_ops imports validate_roadmap, which imports this module.
    from specy_road.bundled_scripts.roadmap_crud_ops import append_node_to_chunk  # noqa: PLC0415
    from specy_road.bundled_scripts.roadmap_crud_prepare import next_sibling_order  # noqa: PLC0415
    from specy_road.bundled_scripts.roadmap_layout import next_child_id  # noqa: PLC0415
    from specy_road.bundled_scripts.roadmap_load import load_roadmap  # noqa: PLC0415
    from specy_road.bundled_scripts.roadmap_node_keys import new_node_key  # noqa: PLC0415

    nodes = load_roadmap(root)["nodes"]
    if under not in {n["id"] for n in nodes}:
        raise WorkerError(f"--under {under}: no such node in the roadmap")
    try:   # the lock add-node and brainstorm promotion honour
        assert_pm_nodes_not_milestone_locked(nodes, under)
    except ValueError as e:
        raise WorkerError(f"--under {under}: {e} Pass another --under parent, or run after the milestone closes.") from e
    done: list[str] = []
    for cls, title in CLASSES.items():
        found = [f for f in findings if f.cls == cls]
        if not found:
            continue
        # Codenames and titles are unique, so a class filed again after its leaf is Complete gets a number.
        mine = [n for n in nodes if re.fullmatch(rf"garden-{cls}(-\d+)?", n.get("codename") or "")]
        still_open = next((n for n in mine if n.get("status") != "Complete"), None)
        if still_open:
            done.append(f"{cls}: {still_open['id']} is still open; added nothing")
            continue
        gen = f"-{len(mine) + 1}" if mine else ""
        node = {"id": next_child_id(nodes, under), "node_key": new_node_key(), "parent_id": under,
                "type": "task", "title": f"{title} ({len(mine) + 1})" if mine else title,
                "codename": f"garden-{cls}{gen}", "status": "Not Started",
                "acceptance": _acceptance(cls, found), "touch_zones": sorted({f.path for f in found}),
                "sibling_order": next_sibling_order(root, under, None)}
        append_node_to_chunk(root, None, node)
        nodes = load_roadmap(root)["nodes"]
        done.append(f"{cls}: added {node['id']} ({node['title']})")
    return done


def record_path(root: Path) -> Path:
    """A dot-file: a chore slug starts with a letter or digit, so no chore record can be this file."""
    return chores_dir(root) / ".garden.json"


def garden(root: Path, under: str | None = None) -> dict:
    """Scan, file chore leaves under ``under`` when given, and record the run; the report."""
    findings, notes = scan(root)
    chores = open_chores(root, findings, under) if under else []
    chores_dir(root).mkdir(parents=True, exist_ok=True)
    _write_atomic(record_path(root), json.dumps({"last_run": date.today().isoformat()}) + "\n")
    return {"findings": findings, "notes": notes, "chores": chores}


def as_json(report: dict) -> str:
    return json.dumps({**report, "findings": [asdict(f) for f in report["findings"]]}, indent=2)


def garden_due(root: Path, today: date) -> str | None:
    """Why gardening is due under ``policy.garden_cadence_days``; ``None`` when it is not or the key is unset.

    The arithmetic of a research register entry: due when more than the cadence's days have passed.
    """
    cadence = effective_config(root)[0]["policy"].get("garden_cadence_days")
    if not cadence:
        return None
    try:
        last = date.fromisoformat(json.loads(record_path(root).read_text(encoding="utf-8"))["last_run"])
    except (OSError, ValueError, KeyError, TypeError):
        last = None
    if last is not None and (today - last).days <= cadence:
        return None
    when = "never run" if last is None else f"last run {last}"
    return f"gardening due: {when}, every {cadence} days; run `specy-road chore garden`"


def warn_garden_due(root: Path, today: date | None = None) -> None:
    """One non-fatal ``validate`` line when gardening is due."""
    why = garden_due(root, today or date.today())
    if why:
        print(f"garden: warning — {why} (see docs/orchestration-chores.md)", file=sys.stderr)
