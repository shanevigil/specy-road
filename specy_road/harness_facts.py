"""The harness facts fixture: one record per harness, from which ``refresh-profiles`` renders.

``model-profiles/harness-facts.yaml`` (shipped under ``templates/project``) holds what
specy-road knows about each harness a roster can name — version, headless command,
session flags, permissions, instruction files, skill directories, hooks, autonomous git
actions and their switches, model families, quota behaviour — each fact labelled
``documented``, ``runtime`` or ``unverified`` with its source. It is validated against
``schemas/harness-facts.schema.json``.

Two parts of ``model-profiles/`` are *rendered* from it, and a hand edit to either is
drift: each profile's ``access.cli`` (the executor command template of the harness whose
``executor_template.renders_cli_for`` names the profile's ``family``) and the README's
harness block between :data:`BLOCK_START` and :data:`BLOCK_END`.

The version-bump check compares a new capture of a harness's ``--version`` and ``--help``
output (and any inventory listing) with the accepted one under
``model-profiles/harness-captures/<harness>/``. Every identifier the new capture adds is
classified; one containing a :data:`WORKFLOW_WORDS` entry fails the diff until the
record's ``relationships`` assigns it one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.init_project import project_template_root
from specy_road.model_profiles import PROFILES_REL, list_profiles

FACTS_NAME = "harness-facts.yaml"
CAPTURES_DIRNAME = "harness-captures"
SCHEMA_NAME = "harness-facts.schema.json"
README_NAME = "README.md"
BLOCK_START = "<!-- >>> harness facts: rendered by `specy-road refresh-profiles --render` from harness-facts.yaml; do not edit inside <<< -->"
BLOCK_END = "<!-- >>> end harness facts <<< -->"
#: The README block goes before this heading when the README has no block yet.
BLOCK_ANCHOR = "## Role rankings"
#: Matched as a substring of the lower-cased identifier, as the acceptance states it.
WORKFLOW_WORDS = (
    "plan", "memory", "task", "todo", "worktree", "branch", "commit", "push", "pr",
    "background", "delegate", "cloud", "schedule", "review", "resume", "fork", "autopilot",
    "goal", "loop", "queue", "persist", "gist", "fleet", "teleport", "remote", "spawn",
)
VERSION_FILE = "version.txt"
#: ``access:`` and its block mapping: every following line that is blank or indented.
_ACCESS_BLOCK = re.compile(r"^access:[ \t]*(?:#[^\n]*)?$(?:\n(?:[ \t][^\n]*)?)*", re.MULTILINE)
_CLI_LINE = re.compile(r"^  cli:[^\n]*$", re.MULTILINE)
_FLAG = re.compile(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*")
_COMMAND_ROW = re.compile(r"^ {2,4}([a-z][\w|-]*)(?=\s|$)")


class HarnessFactsError(ValueError):
    """The fixture is missing, unparsable, or does not match its schema."""


def bundled_facts_path() -> Path:
    return project_template_root() / PROFILES_REL / FACTS_NAME


def bundled_captures_dir() -> Path:
    return project_template_root() / PROFILES_REL / CAPTURES_DIRNAME


def schema_errors(data: Any) -> list[str]:
    schema = json.loads((project_template_root() / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))
    errs = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in errs]


def load_facts(path: Path | None = None) -> dict[str, Any]:
    """The fixture as data, or :class:`HarnessFactsError` naming every schema error."""
    path = path or bundled_facts_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise HarnessFactsError(f"cannot read {path}: {e}") from e
    errs = schema_errors(data)
    ids = [h.get("id") for h in data.get("harnesses", [])] if isinstance(data, dict) else []
    errs += [f"harnesses: duplicate id {i!r}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if errs:
        raise HarnessFactsError(f"{path} does not match {SCHEMA_NAME}:\n  " + "\n  ".join(errs))
    return data


def harness(facts: dict[str, Any], harness_id: str) -> dict[str, Any]:
    for rec in facts["harnesses"]:
        if rec["id"] == harness_id:
            return rec
    known = ", ".join(h["id"] for h in facts["harnesses"])
    raise HarnessFactsError(f"no harness {harness_id!r} in {FACTS_NAME} (known: {known})")


# --- rendering ---------------------------------------------------------------

def rendered_cli(facts: dict[str, Any], family: Any, api_id: str) -> str | None:
    """The executor command template for a profile of ``family``, or ``None`` when no harness renders it."""
    for rec in facts["harnesses"]:
        tmpl = rec["executor_template"]
        if family in tmpl["renders_cli_for"]:
            return tmpl["value"].replace("{api_id}", api_id)
    return None


def _cli_line(value: str) -> str:
    """``  cli: <value>``, quoted only when YAML would read the bare value differently."""
    try:
        plain = yaml.safe_load(f"cli: {value}") == {"cli": value}
    except yaml.YAMLError:
        plain = False
    return f"  cli: {value}" if plain else "  cli: " + yaml.safe_dump(value, default_style="'").strip()


def _prose(text: str) -> str:
    """``<id>`` and friends would be read as HTML tags in Markdown."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _evidence(f: dict[str, Any]) -> str:
    return f"_[{f['label']}: {_prose(f['source'])}]_" if f.get("source") else f"_[{f['label']}]_"


def _fact(f: dict[str, Any], *, code: bool = False) -> str:
    value = f["value"]
    if isinstance(value, list):
        text = ", ".join(f"`{v}`" for v in value) or "none listed"
    else:
        text = f"`{value}`" if code else _prose(str(value))
    return f"{text} {_evidence(f)}"


def render_block(facts: dict[str, Any]) -> str:
    """The README's harness block, markers included, ending in a newline."""
    out = [BLOCK_START, "", "### Harness facts", "",
           "Rendered from `harness-facts.yaml`. Each fact carries its label: `documented` (a vendor page or",
           "repository doc), `runtime` (observed by running the binary) or `unverified`. The `access.cli` of",
           "every profile whose `family` a harness's executor template names is rendered from it too;",
           "`refresh-profiles --check` reports a hand edit to either as drift.", ""]
    for rec in facts["harnesses"]:
        out += [f"#### {rec['name']} (`{rec['id']}`, binary `{rec['binary']}`)", ""]
        inst = rec["instruction_files"]
        rows = [
            ("Version", _fact(rec["version"], code=True)),
            ("Headless command", _fact(rec["headless_command"], code=True)),
            ("Executor template", _fact(rec["executor_template"], code=True)),
            ("Session", _fact(rec["session_flags"])),
            ("Permissions", _fact(rec["permission_example"])),
            ("Instruction files", f"{_fact(inst)}; size: {_prose(inst['size_guidance'])}"),
            ("Skill directories", _fact(rec["skill_dirs"])),
            ("Hooks", _fact(rec["hooks"])),
            ("Model families", _fact(rec["model_families"])),
            ("Quota", _fact(rec["quota"])),
        ]
        out += [f"- **{k}:** {v}" for k, v in rows]
        out.append("- **Autonomous git actions:**")
        out += [f"  - {_prose(a['action'])}; switch: {_prose(a['switch'])} {_evidence(a)}" for a in rec["git_actions"]]
        out.append("")
    out.append(BLOCK_END)
    return "\n".join(out) + "\n"


def _block_span(text: str) -> tuple[int, int] | None:
    """The block's ``(start, end)``: exactly one start marker, then exactly one end marker."""
    if text.count(BLOCK_START) != 1 or text.count(BLOCK_END) != 1:
        return None
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if end < start:
        return None
    end += len(BLOCK_END)
    return start, end + 1 if text[end:end + 1] == "\n" else end


def _markers_malformed(text: str) -> bool:
    """Some marker is present but they do not make one block: one is missing, repeated, or out of order."""
    return (BLOCK_START in text or BLOCK_END in text) and _block_span(text) is None


def render_readme(text: str, facts: dict[str, Any]) -> str:
    block = render_block(facts)
    span = _block_span(text)
    if span:
        return text[:span[0]] + block + text[span[1]:]
    at = text.find(f"\n{BLOCK_ANCHOR}\n")
    if at < 0:
        return text.rstrip("\n") + "\n\n" + block
    return text[:at + 1] + block + "\n" + text[at + 1:]


def _shipped_layout(block: str) -> bool:
    """The layout the shipped profiles use: every child of ``access:`` on one line, indented two spaces."""
    return all(not ln.strip() or (ln.startswith("  ") and not ln[2:3].isspace()) for ln in block.split("\n")[1:])


def _renders_to(old_head: str, new_head: str, cli: str) -> bool:
    """``new_head`` parses to ``old_head``'s front matter with only ``access.cli`` set to ``cli``."""
    try:
        old, new = yaml.safe_load(old_head), yaml.safe_load(new_head)
    except (yaml.YAMLError, ValueError):
        return False
    if not isinstance(old, dict) or not isinstance(old.get("access") or {}, dict):
        return False
    return new == {**old, "access": {**(old.get("access") or {}), "cli": cli}}


def render_profile(text: str, cli: str) -> str:
    """``text`` with its front matter's ``access.cli`` line set to ``cli``; a removed one goes back first
    under ``access:``. Only the shipped layout (a block-style ``access:`` whose children are one-line,
    two-space keys) is rewritten, and only when the result parses to the same front matter with that
    one value changed. Any other layout, or front matter that does not parse, comes back unchanged."""
    head, sep, body = text.partition("\n---\n")
    access = _ACCESS_BLOCK.search(head) if sep else None
    if not access or not _shipped_layout(access.group(0)):
        return text
    block = access.group(0)
    new_block, n = _CLI_LINE.subn(lambda _m: _cli_line(cli), block, count=1)
    if not n:
        first, nl, rest = block.partition("\n")
        new_block = f"{first}\n{_cli_line(cli)}{nl}{rest}"
    new_head = head[:access.start()] + new_block + head[access.end():]
    return new_head + sep + body if _renders_to(head, new_head, cli) else text


@dataclass
class Finding:
    """``kind`` is ``drift`` (a rendered region was edited) or ``behind`` (it predates rendering)."""
    rel: str
    kind: str
    detail: str


@dataclass
class RenderPlan:
    findings: list[Finding] = field(default_factory=list)
    updates: dict[Path, str] = field(default_factory=dict)


def plan_render(repo_root: Path, facts: dict[str, Any]) -> RenderPlan:
    """What ``model-profiles/`` under ``repo_root`` would need for its rendered regions to match ``facts``."""
    plan = RenderPlan()
    pdir = repo_root / PROFILES_REL
    for prof in list_profiles(repo_root):
        if not prof.data and prof.errors:   # front matter missing or not YAML: its family is unknowable
            plan.findings.append(Finding(prof.path.relative_to(repo_root).as_posix(), "drift",
                                         f"front matter does not parse ({prof.errors[0]})"))
            continue
        want = rendered_cli(facts, prof.data.get("family"), str(prof.data.get("api_id") or prof.path.stem))
        if want is None:
            continue
        rel = prof.path.relative_to(repo_root).as_posix()
        have = (prof.data.get("access") or {}).get("cli") if isinstance(prof.data.get("access"), dict) else None
        if have == want:
            continue
        plan.findings.append(Finding(rel, "drift", f"access.cli is {have!r}; the fixture renders {want!r}"))
        text = prof.path.read_text(encoding="utf-8")
        new = render_profile(text, want)
        if new != text:
            plan.updates[prof.path] = new
        else:
            plan.findings[-1].detail += ("; only the shipped layout (block-style `access:` with one-line, "
                                         "two-space keys) is rewritten")
    readme = pdir / README_NAME
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        rel = readme.relative_to(repo_root).as_posix()
        if _markers_malformed(text):   # a hand edit to the markers: drift, and never guessed at
            plan.findings.append(Finding(rel, "drift", "the harness block markers are missing one, "
                                         "repeated or out of order"))
            return plan
        span = _block_span(text)
        new = render_readme(text, facts)
        if new != text:
            plan.findings.append(Finding(rel, "drift", "the harness block differs from the fixture") if span
                                 else Finding(rel, "behind", "no harness block yet"))
            plan.updates[readme] = new
    return plan


# --- version-bump diff -------------------------------------------------------

def identifiers(name: str, text: str) -> set[str]:
    """Identifiers in one captured file: an ``inventory*`` file lists one per line (its first word);
    help output contributes every ``--flag`` and each subcommand row under a ``Commands:`` heading."""
    if name.startswith("inventory"):
        return {line.split()[0] for line in text.splitlines() if line.strip()}
    found = set(_FLAG.findall(text))
    in_commands = False
    for line in text.splitlines():
        if line.strip().lower().endswith("commands:") and not line.startswith(" "):
            in_commands = True
            continue
        if in_commands and line and not line.startswith(" "):
            in_commands = False
        m = _COMMAND_ROW.match(line) if in_commands else None
        if m:
            found.update(p for p in m.group(1).split("|") if p)
    return found


def workflow_word(identifier: str) -> str | None:
    low = identifier.lower()
    return next((w for w in WORKFLOW_WORDS if w in low), None)


def read_capture(directory: Path) -> dict[str, str]:
    """``{file name: text}`` for every ``*.txt`` in a capture directory (empty when there is none)."""
    if not directory.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.txt"))}


@dataclass
class CaptureDiff:
    harness: str
    version: tuple[str, str]
    assigned: dict[str, str] = field(default_factory=dict)      # new identifier -> relationship
    unassigned: dict[str, str] = field(default_factory=dict)    # new identifier -> workflow word: fails
    other: list[str] = field(default_factory=list)              # new, no workflow word
    removed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unassigned


def _all_identifiers(capture: dict[str, str]) -> set[str]:
    return {i for name, text in capture.items() if name != VERSION_FILE for i in identifiers(name, text)}


def classify_capture(facts: dict[str, Any], harness_id: str, old: dict[str, str], new: dict[str, str]) -> CaptureDiff:
    """Classify what ``new`` adds to and drops from the accepted capture ``old``.

    ``new`` must hold every file the record's ``capture_commands`` names and every file ``old`` has:
    a file left out of a capture is a missing input, not evidence that its identifiers were removed."""
    rec = harness(facts, harness_id)
    missing = sorted((set(rec.get("capture_commands") or {VERSION_FILE: []}) | set(old)) - set(new))
    if missing:
        raise HarnessFactsError(f"incomplete {harness_id} capture: no {', '.join(missing)} "
                                f"({VERSION_FILE} is the harness's --version output)")
    rels = rec.get("relationships") or {}
    before, after = _all_identifiers(old), _all_identifiers(new)
    diff = CaptureDiff(harness_id, (old.get(VERSION_FILE, "").strip(), new[VERSION_FILE].strip()))
    for ident in sorted(after - before):
        word = workflow_word(ident)
        if ident in rels:
            diff.assigned[ident] = rels[ident]
        elif word:
            diff.unassigned[ident] = word
        else:
            diff.other.append(ident)
    diff.removed = sorted(before - after)
    return diff


def write_capture(directory: Path, capture: dict[str, str]) -> None:
    """Write ``capture`` over the accepted one in ``directory``; :func:`classify_capture` has
    already refused a capture that lacks a file the accepted one has, so nothing is deleted."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in capture.items():
        (directory / name).write_text(text, encoding="utf-8")
