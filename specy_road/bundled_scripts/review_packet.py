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
import subprocess
from pathlib import Path

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.finish_implementation_check import zone_matches
from specy_road.git_subprocess import git_stdout, head_sha
from specy_road.review_files import PACKET_NAME, latest_ready, reviews_dir
from specy_road.review_target import ReviewTarget, resolve_target, same_commit
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root

TAIL_LINES = 60
# Paths every feature branch touches for bookkeeping; never a touch-zone breach.
_BOOKKEEPING_PREFIXES = ("roadmap/", "planning/", "roadmap.md")


def _tail(text: str, n: int = TAIL_LINES) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def _fence(text: str, lang: str = "") -> list[str]:
    ticks = "````" if "```" in text else "```"
    return [f"{ticks}{lang}", text.rstrip(), ticks, ""]


def _header(t: ReviewTarget) -> list[str]:
    return [
        f"# Review packet: `{t.node_id}` — {t.node.get('title', '')}",
        "",
        f"- **Commit under review:** `{t.commit or 'unknown'}` (`{t.ref}`)",
        f"- **Base:** `{t.base or 'unknown'}` (merge base with `{t.base_ref or '?'}`)",
        f"- **Touch zones:** {', '.join(f'`{z}`' for z in t.touch_zones) or '_none declared_'}",
        "",
        "Record your verdict with `specy-road review record "
        f"{t.node_id} --model <id> --verdict approve|block --file <notes.md>`. "
        "Your record's `commit` must equal the commit above.",
        "",
    ]


def _summary(root: Path, node_id: str) -> list[str]:
    path = root / "work" / f"implementation-summary-{node_id}.md"
    out = ["## Implementation summary", ""]
    if path.is_file():
        out += [path.read_text(encoding="utf-8").rstrip(), ""]
    else:
        out += [f"_(missing: `{path.relative_to(root)}`)_", ""]
    return out


def _changed(root: Path, t: ReviewTarget) -> tuple[list[str], list[str]]:
    if not t.base or not t.commit:
        return [], ["_(cannot compute: no merge base or no commit)_", ""]
    out = git_stdout(["diff", "--name-only", f"{t.base}...{t.commit}"], root) or ""
    paths = [p.strip() for p in out.splitlines() if p.strip()]
    zones = [z.strip().strip("/") for z in t.touch_zones if isinstance(z, str) and z.strip()]
    lines = ["## Changed paths", ""]
    outside = []
    for p in paths:
        inside = not zones or any(zone_matches(z, p) for z in zones)
        bookkeeping = p.startswith(_BOOKKEEPING_PREFIXES)
        if not inside and not bookkeeping:
            outside.append(p)
        mark = "" if inside or bookkeeping else "  **← outside touch zones**"
        lines.append(f"- `{p}`{mark}")
    if not paths:
        lines.append("- _none_")
    lines.append("")
    if outside:
        lines += [f"**{len(outside)} path(s) outside the touch zones.** "
                  "An executor must stop for the coordinator rather than edit these.", ""]
    return paths, lines


def _diff(root: Path, t: ReviewTarget) -> list[str]:
    out = ["## Diff", ""]
    if not t.base or not t.commit:
        return out + ["_(cannot compute)_", ""]
    diff = git_stdout(["diff", f"{t.base}...{t.commit}"], root) or ""
    return out + (_fence(diff, "diff") if diff.strip() else ["_(empty)_", ""])


def _ready_verify(root: Path, t: ReviewTarget) -> list[str]:
    ready = latest_ready(root, t.node_id)
    if ready is None:
        return ["_(no valid READY hand-off file)_", ""]
    out = [f"From `{ready.path.name}` (commit `{ready.data['commit']}`):", ""]
    if not same_commit(ready.data["commit"], t.commit):
        out += ["**Warning:** the READY commit is not the commit under review.", ""]
    for v in ready.data.get("verify") or []:
        out.append(f"### `{v['cmd']}` → exit {v['exit']}")
        out += [""] + _fence(v.get("tail") or "(no output recorded)")
    return out


def _run_verify(root: Path, cmds: list[str], t: ReviewTarget) -> list[str]:
    out: list[str] = []
    here = head_sha(root)
    if cmds and not same_commit(here, t.commit):
        out += [f"**Warning:** commands ran at HEAD `{here}`, not the commit under review.", ""]
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, check=False)
        out.append(f"### `{cmd}` → exit {r.returncode} (run by review-packet)")
        out += [""] + _fence(_tail((r.stdout or "") + (r.stderr or "")) or "(no output)")
    return out


def build_packet(root: Path, node_id: str, *, ref: str | None, verify_cmds: list[str]) -> str:
    t = resolve_target(root, node_id, ref)
    brief = render_brief(node_id, index(t.nodes), repo_root=root, include_history=False)
    _paths, changed = _changed(root, t)
    parts = [
        _header(t),
        ["---", ""] + brief.rstrip().splitlines() + ["", "---", ""],
        _summary(root, node_id),
        changed,
        _diff(root, t),
        ["## Verifier output", ""] + _ready_verify(root, t) + _run_verify(root, verify_cmds, t),
    ]
    return "\n".join("\n".join(p) for p in parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.2")
    p.add_argument("--ref", help="Branch or commit to review (default: the node's registered branch, else HEAD)")
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
