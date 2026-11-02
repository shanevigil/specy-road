#!/usr/bin/env python3
"""Replay recorded review packets through roster reviewers at two effort levels (M10.6).

Usage:
    python scripts/review_effort_study.py --model grok-4.7-high --levels high medium M3.16 M9.1 M3.13

For each packet ``work/reviews/<ID>/PACKET.md``, each ``--model`` (a roster reviewer) and
each level, the roster entry's ``channels.cli`` runs once and ``results.csv`` (under
``-o``, default ``work/effort-study``) gets one row with the verdict and block reasons.
Only that command runs, never a model API, so the reviewer is billed and sandboxed as the
roster has it. A level reaches the command the way M10.5 passes effort:

* a harness with an effort flag (``claude-code``, ``codex``): the command must name
  ``{effort}``, which becomes the flag for the level;
* a harness without one (``cursor``): the model id carries the effort, so the roster id
  must end in ``-<level>`` and appear in the command, and is swapped for ``<stem>-<level>``.

The replay files nothing: the reviewer gets a study preamble and the packet, runs in its
own directory under ``-o`` (prompt and output are kept there), and ends with a YAML block
the script reads. Every check runs before the first reviewer, and a study larger than
``--max-runs`` (the maintainer's budget, default 12) is refused whole.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from specy_road.orchestration_pinned import pinned_config
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import ADAPTERS, placeholder_problem, substitute_prompt

#: Cursor's effort suffixes on a model id (`agent --list-models`, 2026-11-02).
ID_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
COLUMNS = ("node_id", "commit", "model", "family", "level", "verdict", "block_reasons", "exit_code", "seconds")
PREAMBLE = """# Review replay: `{node}` (effort study)

You are one reviewer in a measurement of reviewer effort. Review the packet below as you
would for the gate: judge the commit it names against the brief's acceptance criteria.
Judge from the packet alone. Do not run commands, do not edit files, and do not run
`specy-road review record`: this replay files nothing.

End your reply with exactly one fenced block in this form, and nothing after it:

```yaml
verdict: approve        # or block
block_reasons: []       # when you block: one short line per reason, e.g. ["A2 fails: ..."]
```

---

"""


class StudyError(Exception):
    pass


def level_command(entry: dict, level: str) -> tuple[str, list[str]]:
    """``(cli, effort_args)`` for one level of the roster ``entry``: what :func:`substitute_prompt` takes."""
    cli, rid = (entry.get("channels") or {}).get("cli"), str(entry.get("id"))
    why = placeholder_problem(cli)
    if why:
        raise StudyError(f"{rid}: roster channels.cli: {why}")
    adapter = ADAPTERS.get(entry.get("harness") or "generic", ADAPTERS["generic"])
    if adapter.effort_flag(level):
        if "{effort}" not in cli:   # placeholder_problem has refused one inside a larger word
            raise StudyError(f"{rid}: channels.cli names no {{effort}}, so both levels would run the same: {cli}")
        return cli, adapter.effort_flag(level)
    stem, _, suffix = rid.rpartition("-")
    word = re.compile(rf"(?<![\w.-]){re.escape(rid)}(?![\w.-])")
    if suffix not in ID_LEVELS or not word.search(cli):
        raise StudyError(f"{rid}: {adapter.harness} carries effort in the model id, so the roster id must end in "
                         f"-<{'|'.join(ID_LEVELS)}> and appear in channels.cli: {cli}")
    return word.sub(f"{stem}-{level}", cli), []


def packet_commit(text: str) -> str:
    m = re.search(r"\*\*Commit under review:\*\* `([0-9a-f]{7,40})`", text)
    return m.group(1) if m else ""


def parse_verdict(output: str) -> tuple[str, list[str]]:
    """The last fenced YAML block naming a verdict; ``unparsed`` when there is none."""
    for block in reversed(re.findall(r"```ya?ml\s*\n(.*?)```", output, re.S)):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("verdict") in ("approve", "block"):
            reasons = data.get("block_reasons") or []
            return data["verdict"], [str(r) for r in (reasons if isinstance(reasons, list) else [reasons])]
    return "unparsed", []


def plan(root: Path, models: list[str], levels: list[str], nodes: list[str], max_runs: int) -> list[tuple]:
    """Every run as ``(node, packet text, entry, level, cli, effort_args)``; raises before anything runs."""
    total = len(nodes) * len(models) * len(levels)
    if total > max_runs:
        raise StudyError(f"{len(nodes)} packet(s) x {len(models)} model(s) x {len(levels)} level(s) = {total} "
                         f"reviewer runs, over the budget of {max_runs}; nothing was run")
    config, err = pinned_config(root)
    if err:
        raise StudyError(f"orchestration config: {err}")
    entries = {e.get("id"): e for e in config.get("roster") or []}
    runs = []
    for node in nodes:
        packet = reviews_dir(root, node) / PACKET_NAME
        if not packet.is_file():
            raise StudyError(f"no recorded packet at {packet}")
        text = packet.read_text(encoding="utf-8")
        for rid in models:
            entry = entries.get(rid)
            if entry is None or "reviewer" not in (entry.get("roles") or []):
                raise StudyError(f"{rid!r} is not a reviewer in the roster (roadmap/orchestration.yaml)")
            runs += [(node, text, entry, lv, *level_command(entry, lv)) for lv in levels]
    return runs


def run_one(out: Path, node: str, text: str, entry: dict, level: str, cli: str, effort: list[str],
            timeout: int) -> dict:
    run_dir = out / "runs" / node / f"{entry['id']}-{level}"
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt = run_dir / "prompt.md"
    prompt.write_text(PREAMBLE.format(node=node) + text, encoding="utf-8")
    started = time.monotonic()
    try:
        done = subprocess.run(substitute_prompt(cli, prompt, effort=effort), shell=True, cwd=run_dir,
                              capture_output=True, text=True, timeout=timeout, check=False)
        output, code = done.stdout + done.stderr, done.returncode
    except subprocess.TimeoutExpired as e:
        output, code = f"{e.stdout or ''}{e.stderr or ''}\n(timed out after {timeout}s)", "timeout"
    (run_dir / "output.txt").write_text(str(output), encoding="utf-8")
    verdict, reasons = parse_verdict(str(output))
    return {"node_id": node, "commit": packet_commit(text), "model": entry["id"], "family": entry.get("family", ""),
            "level": level, "verdict": verdict, "block_reasons": " | ".join(reasons), "exit_code": code,
            "seconds": round(time.monotonic() - started)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nodes", nargs="+", metavar="NODE_ID", help="Leaves whose work/reviews/<ID>/PACKET.md to replay")
    p.add_argument("--model", action="append", required=True, help="Roster reviewer id (repeatable)")
    p.add_argument("--levels", nargs=2, required=True, metavar=("LEVEL", "LEVEL"),
                   help="The model's own effort levels, e.g. high medium")
    p.add_argument("--max-runs", type=int, default=12, help="Refuse a study with more reviewer runs (default 12)")
    p.add_argument("--timeout", type=int, default=1800, help="Seconds per reviewer run (default 1800)")
    p.add_argument("-o", "--output", type=Path, help="Study directory (default work/effort-study)")
    add_repo_root_arg(p)
    ns = p.parse_args(argv)
    root = resolve_repo_root(ns)
    out = ns.output or root / "work" / "effort-study"
    try:
        runs = plan(root, ns.model, ns.levels, ns.nodes, ns.max_runs)
    except StudyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for i, run in enumerate(runs, 1):
            print(f"run {i}/{len(runs)}: {run[0]} {run[2]['id']} at {run[3]}", file=sys.stderr)
            writer.writerow(run_one(out, *run, timeout=ns.timeout))
            f.flush()
    print(f"{len(runs)} reviewer run(s); results in {out / 'results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
