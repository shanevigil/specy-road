#!/usr/bin/env python3
"""Assemble the verification packet a reviewer reads: ``specy-road review-packet``.

Writes ``work/reviews/<NODE_ID>/PACKET.md`` with, in order:

1. the brief (goal, numbered acceptance, planning, contracts);
2. the implementation summary (``work/implementation-summary-<NODE_ID>.md``);
3. every changed path since the merge base, with paths outside the node's
   touch zones called out;
4. ``git diff <base>...<ref>``;
5. verifier output — the newest valid READY file's ``verify`` tails, plus any
   ``--verify-cmd`` run now.

A reviewer is handed this file and nothing else (proposal §3.2). The commit it
describes is printed at the top; a review record must name that commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import date
from pathlib import Path

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.finish_implementation_check import zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout, head_sha
from specy_road.review_files import PACKET_NAME, latest_ready, reviews_dir
from specy_road.review_gate import policy_source
from specy_road.review_target import REGISTRY_REL, ReviewTarget, full_sha, resolve_target_or_exit, same_commit
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root

TAIL_LINES = 60
# Paths every feature branch touches for bookkeeping; never a touch-zone breach.
# work/ holds the brief, implementation summary, and session files the scaffold
# tracks on the feature branch on purpose.
_BOOKKEEPING_PREFIXES = ("roadmap/", "planning/", "roadmap.md", "roadmap-context.md", "work/")
# ...except the review policy itself. The gate reads it from the integration
# branch, so a change here does not lower the bar, but a reviewer must see it.
_POLICY_PATHS = ("roadmap/orchestration.yaml", "roadmap/git-workflow.yaml")
# Who asserts each section, so a reviewer weighs a claim as a claim.
ASSERTED = "_Asserted by the executor at the reviewed commit; a claim to check, not evidence._"
ASSERTED_WORKING_TREE = ("_Asserted by the executor; read from the working tree, **not committed at the "
                         "reviewed commit**. A claim to check, not evidence._")
SUMMARY_MISSING = "_Not provided: no summary at the reviewed commit or in the working tree._"
# The executor prompt asks the summary to end with an `## Added` inventory (helpers, guards,
# mocks, tests, each with a reason). Its absence is noted, never fatal.
NO_INVENTORY = ("_No `Added` inventory in the summary: helpers, guards, mocks and tests added are not "
                "listed; inventory the diff's additions yourself._")
_INVENTORY = re.compile(r"(?im)^(?:#+\s*added\b|\*\*added\b|added:)")
RENDERED = "_Rendered from the roadmap at the working tree._"
# The registry stays in the diff: only this node's claim row and approval stamp are bookkeeping.
BOOKKEEPING_MARK = "  _← toolkit bookkeeping; any edit beyond this node's claim and approval is under review_"
BOOKKEEPING_NOTE = (f"_`{REGISTRY_REL}` is in this diff. Expected there: this node's claim row (pickup) and its "
                    "approval stamp (`mark-implementation-reviewed`). Any other edit in that file is under review._")


def _computed(t: ReviewTarget) -> str:
    return f"_Computed by review-packet from git (`{t.base}...{t.commit}`)._"


def _tail(text: str, n: int = TAIL_LINES) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def _fence(text: str, lang: str = "") -> list[str]:
    ticks = "````" if "```" in text else "```"
    return [f"{ticks}{lang}", text.rstrip(), ticks, ""]


def _policy_line(root: Path) -> str:
    ref, err = policy_source(root)
    if err:
        return f"- **Policy source:** _{err}_ (the gate fails closed)"
    if ref is None:
        return "- **Policy source:** _the working tree (not a git checkout)_"
    return f"- **Policy source:** `{ref}` @ `{full_sha(root, ref) or '?'}`"


def _header(root: Path, t: ReviewTarget) -> list[str]:
    return [
        f"# Review packet: `{t.node_id}` — {t.node.get('title', '')}",
        "",
        f"- **Commit under review:** `{t.commit or 'unknown'}` (`{t.ref}`)",
        f"- **Base:** `{t.base or 'unknown'}` (merge base with `{t.base_ref or '?'}`)",
        f"- **Touch zones:** {', '.join(f'`{z}`' for z in t.touch_zones) or '_none declared_'}",
        _policy_line(root),
        f"- **Generated:** {date.today().isoformat()} by review-packet at HEAD `{head_sha(root) or '?'}`",
        "",
        "Record your verdict with `specy-road review record "
        f"{t.node_id} --model <id> --verdict approve|block --file <notes.md>`. "
        "Your record's `commit` must equal the commit above.",
        "",
    ]


def _summary(root: Path, t: ReviewTarget) -> list[str]:
    """The summary as committed at the reviewed commit, else the working tree's; each labelled."""
    rel = f"work/implementation-summary-{t.node_id}.md"
    out = ["## Implementation summary", ""]
    text = git_stdout(["show", f"{t.commit}:{rel}"], root) if t.commit else None
    label = ASSERTED
    if text is None and (root / rel).is_file():
        text, label = (root / rel).read_text(encoding="utf-8"), ASSERTED_WORKING_TREE
    if text is None:
        return out + [SUMMARY_MISSING, "", f"_(missing: `{rel}`)_", ""]
    note = [] if _INVENTORY.search(text) else [NO_INVENTORY, ""]
    return out + [label, "", text.rstrip(), ""] + note


def _changed(root: Path, t: ReviewTarget) -> tuple[list[str], list[str]]:
    if not t.base or not t.commit:
        return [], ["_(cannot compute: no merge base or no commit)_", ""]
    paths = diff_paths(root, f"{t.base}...{t.commit}") or []   # both sides of a rename or copy
    zones = [z.strip().strip("/") for z in t.touch_zones if isinstance(z, str) and z.strip()]
    lines = ["## Changed paths", "", _computed(t), ""]
    outside = []
    policy = [p for p in paths if p in _POLICY_PATHS]
    for p in paths:
        inside = not zones or any(zone_matches(z, p) for z in zones)
        bookkeeping = p.startswith(_BOOKKEEPING_PREFIXES) and p not in _POLICY_PATHS
        if not inside and not bookkeeping:
            outside.append(p)
        mark = "" if inside or bookkeeping else "  **← outside touch zones**"
        if p in policy:
            mark = "  **← review policy changed on this branch**"
        if p == REGISTRY_REL:
            mark = BOOKKEEPING_MARK
        lines.append(f"- `{p}`{mark}")
    if not paths:
        lines.append("- _none_")
    lines.append("")
    if outside:
        lines += [f"**{len(outside)} path(s) outside the touch zones.** "
                  "An executor must stop for the coordinator rather than edit these.", ""]
    if policy:
        lines += ["**This branch edits review policy.** The gate ignores it (policy is read "
                  "from the integration branch); block unless the leaf is about policy.", ""]
    return paths, lines


def _diff(root: Path, t: ReviewTarget, paths: list[str]) -> list[str]:
    out = ["## Diff", ""]
    if not t.base or not t.commit:
        return out + ["_(cannot compute)_", ""]
    note = [BOOKKEEPING_NOTE, ""] if REGISTRY_REL in paths else []
    diff = git_stdout(["diff", f"{t.base}...{t.commit}"], root) or ""
    return out + [_computed(t), ""] + note + (_fence(diff, "diff") if diff.strip() else ["_(empty)_", ""])


def _ready_verify(root: Path, t: ReviewTarget) -> list[str]:
    ready = latest_ready(root, t.node_id, branch=(t.entry or {}).get("branch"))
    if ready is None:
        return ["_(no valid READY hand-off file for this node and branch)_", ""]
    out = [ASSERTED, "", f"From `{ready.path.name}` (commit `{ready.data['commit']}`):", ""]
    if not same_commit(root, ready.data["commit"], t.commit):
        out += ["**Warning:** the READY commit is not the commit under review.", ""]
    entries = ready.data.get("verify") or []
    if not entries:
        out += ["**No verifier evidence recorded.**", ""]
    for v in entries:
        mark = "  **← verifier failed**" if v["exit"] != 0 else ""
        out.append(f"### `{v['cmd']}` → exit {v['exit']}{mark}")
        out += [""] + _fence(v.get("tail") or "(no output recorded)")
    return out


def _run_verify(root: Path, cmds: list[str], t: ReviewTarget) -> list[str]:
    out: list[str] = []
    here = head_sha(root)
    if cmds:
        out += [f"_Run now by review-packet at HEAD `{here}`._", ""]
    if cmds and not same_commit(root, here, t.commit):
        out += ["**Warning:** that HEAD is not the commit under review.", ""]
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, check=False)
        out.append(f"### `{cmd}` → exit {r.returncode} (run by review-packet)")
        out += [""] + _fence(_tail((r.stdout or "") + (r.stderr or "")) or "(no output)")
    return out


def build_packet(root: Path, node_id: str, *, ref: str | None, verify_cmds: list[str]) -> str:
    t = resolve_target_or_exit(root, node_id, ref)
    brief = render_brief(node_id, index(t.nodes), repo_root=root, include_history=False)
    paths, changed = _changed(root, t)
    brief_lines = brief.rstrip().splitlines()
    parts = [
        _header(root, t),
        ["---", ""] + brief_lines[:1] + ["", RENDERED] + brief_lines[1:] + ["", "---", ""],
        _summary(root, t),
        changed,
        _diff(root, t, paths),
        ["## Verifier output", ""] + _ready_verify(root, t) + _run_verify(root, verify_cmds, t),
    ]
    return "\n".join("\n".join(p) for p in parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.2")
    p.add_argument("--ref", help="Branch or commit to review (default: the node's registered branch, local or remote-tracking)")
    p.add_argument("--verify-cmd", action="append", default=[], metavar="CMD",
                   help="Run CMD now and include its exit code and output tail (repeatable)")
    p.add_argument("-o", "--output", type=Path, help=f"Write here instead of work/reviews/<NODE_ID>/{PACKET_NAME}")
    add_repo_root_arg(p)
    args = p.parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    text = build_packet(root, args.node_id, ref=args.ref, verify_cmds=args.verify_cmd)
    out = args.output or reviews_dir(root, args.node_id) / PACKET_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
