#!/usr/bin/env python3
"""Assemble the verification packet a reviewer reads: ``specy-road review-packet``.

Writes ``work/reviews/<NODE_ID>/PACKET.md`` (and ``-o``'s path too) with, in order:

1. the brief (goal, numbered acceptance, planning, contracts);
2. the implementation summary (``work/implementation-summary-<NODE_ID>.md``);
3. every changed path since the merge base (with the integration branch, or
   ``--base``), with paths outside the node's touch zones called out;
4. the Python test files that import a changed module (``specy-road impact``);
5. ``git diff <base>...<ref>``, with a warning when it is empty; past
   ``--max-diff-lines`` (default 1500) or ``--max-diff-bytes`` (default 200000)
   the first files that fit both are inlined whole, the rest are listed with
   their ``+``/``-`` counts and diff bytes, and the full diff is written to
   ``work/reviews/<NODE_ID>/DIFF.patch`` (``0`` = no cap); a generated file is
   never inlined, only listed;
6. verifier output — the newest valid READY file's ``verify`` tails, plus any
   ``--verify-cmd`` run now.

A reviewer is handed this file and nothing else (proposal §3.2). The commit it
describes is printed at the top; a review record must name that commit. With
``prior``, ``prompt --role reviewer`` builds one reviewer's delta packet; ``--full`` stops that.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.finish_implementation_check import in_zones
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout, git_text, head_sha
from specy_road.impact import impact_for_diff, section_lines
from specy_road.integrity import compare_integrity
from specy_road.review_files import PACKET_NAME, ReviewFile, latest_ready, reviews_dir
from specy_road.review_gate import policy_source, trial_merge
from specy_road.review_target import REGISTRY_REL, ReviewTarget, full_sha, resolve_target_or_exit, same_commit
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root, project_prefix, rebase_to_project

TAIL_LINES = 60
MAX_DIFF_LINES = 1500
MAX_DIFF_BYTES = 200_000   # a minified bundle is a few very long lines; lines alone do not bound it
# Generated artefacts, git-root relative; with .gitattributes `linguist-generated` paths, listed, never inlined.
GENERATED_PATHS = ("specy_road/pm_gantt_static/",)   # the packaged PM GUI bundle
GENERATED_NOTE = "_Generated files are never inlined: review the source they are built from._"
DIFF_NAME = "DIFF.patch"   # beside PACKET.md when the diff is capped
FULL_MARK = "- **Delta review:** off (`--full`): every reviewer reads this full packet"
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
    return "\n".join(text.rstrip().splitlines()[-n:])


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


def _trial_merge_line(root: Path, ref: str | None, integration_ref: str | None) -> list[str]:
    """Whether the branch tip still merges into the integration branch; a code conflict stops review."""
    tm = trial_merge(root, ref, integration_ref)
    if tm is None:
        return ["- **Trial merge:** _git could not answer_"]
    ahead = f"`{tm.base_ref}` is {tm.behind} commit(s) ahead"
    if not tm.conflicts:
        return [f"- **Trial merge:** {ahead}; merges cleanly" if tm.behind else
                f"- **Trial merge:** up to date with `{tm.base_ref}`"]
    names = ", ".join(f"`{p}`" for p in tm.conflicts)
    if tm.problem() is None:
        return [f"- **Trial merge:** {ahead}; conflicts on bookkeeping only ({names}), which does not block"]
    return [f"- **Trial merge:** {ahead}; **conflicts on {names}**", "",
            f"**Stop: {tm.problem()}.** Reviewing this commit is wasted work: the merge makes it stale.", ""]


def _header(root: Path, t: ReviewTarget, integration_ref: str | None) -> list[str]:
    return [
        f"# Review packet: `{t.node_id}` — {t.node.get('title', '')}", "",
        f"- **Commit under review:** `{t.commit or 'unknown'}` (`{t.ref}`)",
        f"- **Base:** `{t.base or 'unknown'}` (merge base with `{t.base_ref or '?'}`)",
        f"- **Touch zones:** {', '.join(f'`{z}`' for z in t.touch_zones) or '_none declared_'}",
        _policy_line(root),
        f"- **Generated:** {date.today().isoformat()} by review-packet at HEAD `{head_sha(root) or '?'}`",
        *_trial_merge_line(root, t.ref, integration_ref), "",
        "Record your verdict with `specy-road review record "
        f"{t.node_id} --model <id> --verdict approve|block --file <notes.md>`. "
        "Your record's `commit` must equal the commit above.", "",
    ]


def _summary(root: Path, t: ReviewTarget) -> list[str]:
    """The summary as committed at the reviewed commit, else the working tree's; each labelled."""
    rel = f"work/implementation-summary-{t.node_id}.md"
    out = ["## Implementation summary", ""]
    text = git_stdout(["show", f"{t.commit}:./{rel}"], root) if t.commit else None   # ./ = project-root relative
    label = ASSERTED
    if text is None and (root / rel).is_file():
        text, label = (root / rel).read_text(encoding="utf-8"), ASSERTED_WORKING_TREE
    if text is None:
        return out + [SUMMARY_MISSING, "", f"_(missing: `{rel}`)_", ""]
    note = [] if _INVENTORY.search(text) else [NO_INVENTORY, ""]
    return out + [label, "", text.rstrip(), ""] + note


def changed_paths_section(root: Path, t: ReviewTarget) -> tuple[list[str], list[str]]:
    """``(paths, lines)``: the project-relative changed paths and the rendered section."""
    if not t.base or not t.commit:
        return [], ["_(cannot compute: no merge base or no commit)_", ""]
    # git names paths from the repository root; bookkeeping and policy paths
    # are project-relative, and zones may be either. A path outside the project
    # (a monorepo's other trees) keeps its repository-root name.
    prefix = project_prefix(root)
    changed = diff_paths(root, f"{t.base}...{t.commit}") or []   # both sides of a rename or copy
    paths = [rebase_to_project(p, prefix) or p for p in changed]
    zones = [z.strip().strip("/") for z in t.touch_zones if isinstance(z, str) and z.strip()]
    lines = ["## Changed paths", "", _computed(t), ""]
    outside = []
    policy = [p for p in paths if p in _POLICY_PATHS]
    for git_path, p in zip(changed, paths):
        inside = not zones or in_zones(zones, git_path, prefix)
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


def test_integrity_section(root: Path, t: ReviewTarget) -> list[str]:
    """Deterministic ``## Test integrity`` block for the review packet."""
    if not t.base or not t.commit:
        return ["## Test integrity", "", "_(cannot compute: no merge base or no commit)_", ""]
    findings = [f.line() for f in compare_integrity(root, t.base, t.commit)]
    return ["## Test integrity", "", _computed(t), "", *(findings or ["_none_"]), ""]


def tests_at_risk_section(root: Path, t: ReviewTarget) -> list[str]:
    """``## Tests at risk``: test files importing a changed module, from git objects (advisory)."""
    impact = impact_for_diff(root, t.base, t.commit) if t.base and t.commit else None
    intro = (f"{_computed(t)} Python test files that import, at any depth, a module this diff changes "
             "(advisory; not a gate).")
    return section_lines(impact, intro=intro, full_cmd=f"specy-road impact {t.node_id} --ref {t.commit}")


def _empty_diff_reason(t: ReviewTarget) -> str:
    return (f"the diff is empty: `{t.commit}` adds nothing past its merge base with `{t.base_ref}`, as when the "
            "branch is already merged there; `review-packet --base <ref>` sets the diff range (e.g. the commit "
            "before the leaf)")


def _split_files(diff: str) -> list[str]:
    """One chunk per file, each starting at its ``diff --git`` header."""
    chunks: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git ") or not chunks:
            chunks.append(line)
        else:
            chunks[-1] += line
    return chunks


def _numstat(root: Path, t: ReviewTarget) -> list[tuple[str, str, str]]:
    """``(added, removed, path)`` per file, in diff order (``-`` for binary; a rename's new path)."""
    fields = iter((git_stdout(["diff", "--numstat", "-z", f"{t.base}...{t.commit}"], root) or "").split("\0"))
    rows = []
    for f in fields:
        a, _, rest = f.partition("\t")
        r, tab, path = rest.partition("\t")
        if not tab:
            continue
        if not path:   # a rename or copy: the old and the new path follow
            next(fields, "")
            path = next(fields, "")
        rows.append((a, r, path))
    return rows


def _generated(root: Path, commit: str, paths: list[str]) -> set[str]:
    """The git-root ``paths`` under GENERATED_PATHS or marked ``linguist-generated`` at ``commit``."""
    out = {p for p in paths if p.startswith(GENERATED_PATHS)}
    top = Path(git_text(["rev-parse", "--show-toplevel"], root) or root)   # check-attr paths are cwd-relative
    attr = ["check-attr", "-z", "linguist-generated", "--", *paths]
    raw = git_stdout(attr[:2] + [f"--source={commit}"] + attr[2:], top) or git_stdout(attr, top) or ""
    f = raw.split("\0")   # path, attribute, value; repeated
    return out | {f[i] for i in range(0, len(f) - 2, 3) if f[i + 2] in ("set", "true")}


def _budget(cap: int, max_bytes: int) -> str:
    caps = [f"**Diff capped at {cap} lines**"] if cap else []
    if max_bytes:
        caps.append(f"**{max_bytes} bytes**" if cap else f"**Diff capped at {max_bytes} bytes**")
    return " and ".join(caps) or "**Diff not inlined in full**"


def _capped_diff(root: Path, t: ReviewTarget, diff: str, rows: list[tuple[str, str, str]], generated: set[str],
                 cap: int, max_bytes: int, patch_name: str = DIFF_NAME) -> list[str]:
    """Inline the first whole files within both budgets, list the rest and every generated file, write DIFF.patch."""
    chunks = _split_files(diff)
    if len(rows) != len(chunks):   # name each file from its header instead
        rows = [("?", "?", c.split("\n", 1)[0].rsplit(" b/", 1)[-1]) for c in chunks]
    kept: list[str] = []
    listed: list[str] = []
    lines = size = 0
    full = False   # once a file misses a budget, every later one is listed too
    for c, (a, r, path) in zip(chunks, rows):
        n, b, gen = c.count("\n"), len(c.encode()), path in generated
        full = full or (not gen and bool(cap and lines + n > cap or max_bytes and size + b > max_bytes))
        if gen or full:
            listed.append(f"- `{path}` (+{a} -{r}) — not inlined{', generated' if gen else ''} ({b} bytes of diff)")
        else:
            kept, lines, size = kept + [c], lines + n, size + b
    patch = reviews_dir(root, t.node_id) / patch_name
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(diff, encoding="utf-8")
    out = [f"{_budget(cap, max_bytes)} ({diff.count(chr(10))} lines, {len(diff.encode())} bytes in all): the first "
           f"{len(kept)} of {len(chunks)} changed file(s) are inlined whole below; the full diff is at `{patch}`.", ""]
    out += [GENERATED_NOTE, ""] if generated & {path for *_, path in rows} else []
    out += listed + [""]
    return out + (_fence("".join(kept), "diff") if kept else [])


def _diff(root: Path, t: ReviewTarget, paths: list[str], max_diff_lines: int = MAX_DIFF_LINES,
          max_diff_bytes: int = MAX_DIFF_BYTES, patch_name: str = DIFF_NAME) -> list[str]:
    out = ["## Diff", ""]
    (reviews_dir(root, t.node_id) / patch_name).unlink(missing_ok=True)   # only a capped packet names one
    if not t.base or not t.commit:
        return out + ["_(cannot compute)_", ""]
    note = [BOOKKEEPING_NOTE, ""] if REGISTRY_REL in paths else []
    diff = git_stdout(["diff", f"{t.base}...{t.commit}"], root) or ""
    if not diff.strip():
        print(f"warning: {_empty_diff_reason(t)}", file=sys.stderr)
        return out + [_computed(t), ""] + note + [f"_({_empty_diff_reason(t)})_", ""]
    rows = _numstat(root, t)
    generated = _generated(root, t.commit, [path for *_, path in rows])
    if generated or (max_diff_lines and diff.count("\n") > max_diff_lines) or \
            (max_diff_bytes and len(diff.encode()) > max_diff_bytes):
        return out + [_computed(t), ""] + note + _capped_diff(root, t, diff, rows, generated, max_diff_lines,
                                                              max_diff_bytes, patch_name)
    return out + [_computed(t), ""] + note + _fence(diff, "diff")


def _with_base(root: Path, t: ReviewTarget, base: str) -> ReviewTarget:
    """``t`` diffed from the merge base of ``base`` and the commit under review; the commit is unchanged."""
    if not full_sha(root, base):
        print(f"error: --base {base!r} does not resolve to a commit", file=sys.stderr)
        raise SystemExit(1)
    return replace(t, base_ref=base, base=git_text(["merge-base", base, str(t.commit)], root) or None)


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


def _delta_section(prior: ReviewFile) -> list[str]:
    sha, model = prior.data["commit"], prior.data["model"]
    return ["## Delta review", "", f"`{model}`, you approved `{sha}`. This packet covers only the change since: "
            "at most three documentation or test files inside the touch zones, with no integrity findings. Add "
            f"`delta_from: \"{sha}\"` to your record's front matter; the gate counts it only for `{model}`.", "",
            f"### Your notes on `{sha}`", "", prior.body.strip() or "_(none)_", ""]


def build_packet(root: Path, node_id: str, *, ref: str | None, verify_cmds: list[str],
                 base: str | None = None, max_diff_lines: int = MAX_DIFF_LINES,
                 max_diff_bytes: int = MAX_DIFF_BYTES, prior: ReviewFile | None = None, full: bool = False) -> str:
    t = resolve_target_or_exit(root, node_id, ref)
    integration_ref = t.base_ref   # --base moves the diff range, never the trial merge mark and finish check
    if base or prior:
        t = _with_base(root, t, prior.data["commit"] if prior else str(base))
    brief = render_brief(node_id, index(t.nodes), repo_root=root, include_history=False)
    paths, changed = changed_paths_section(root, t)
    brief_lines = brief.rstrip().splitlines()
    parts = [
        _header(root, t, integration_ref) + (_delta_section(prior) if prior else [FULL_MARK, ""] if full else []),
        ["---", ""] + brief_lines[:1] + ["", RENDERED] + brief_lines[1:] + ["", "---", ""],
        _summary(root, t),
        changed,
        test_integrity_section(root, t),
        tests_at_risk_section(root, t),
        _diff(root, t, paths, max_diff_lines, max_diff_bytes, f"DIFF-{prior.data['model']}.patch" if prior else
              DIFF_NAME),
        ["## Verifier output", ""] + _ready_verify(root, t) + _run_verify(root, verify_cmds, t),
    ]
    return "\n".join("\n".join(p) for p in parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("node_id", help="Roadmap node id, e.g. M1.2")
    p.add_argument("--ref", help="Branch or commit to review (default: the node's registered branch, local or remote-tracking)")
    p.add_argument("--base", metavar="REF",
                   help="Diff from the merge base with REF instead of the integration branch's "
                        "(e.g. the commit before the leaf, when its branch is already merged)")
    p.add_argument("--verify-cmd", action="append", default=[], metavar="CMD",
                   help="Run CMD now and include its exit code and output tail (repeatable)")
    p.add_argument("--max-diff-lines", type=int, default=MAX_DIFF_LINES, metavar="N",
                   help=f"Inline at most N diff lines (default {MAX_DIFF_LINES}): whole files up to the cap, "
                        f"the rest listed with +/- counts and the full diff written to "
                        f"work/reviews/<NODE_ID>/{DIFF_NAME}; 0 = no line cap")
    p.add_argument("--max-diff-bytes", type=int, default=MAX_DIFF_BYTES, metavar="N",
                   help=f"Inline at most N bytes of diff too (default {MAX_DIFF_BYTES}), as for --max-diff-lines; "
                        f"0 = no byte cap. With both 0 and no generated file, nothing is listed and no {DIFF_NAME}")
    p.add_argument("--full", action="store_true", help="Every reviewer reads this full packet: `prompt --role "
                   "reviewer` builds no delta packet (policy.delta_review) while it is current")
    p.add_argument("-o", "--output", type=Path,
                   help=f"Also write here; work/reviews/<NODE_ID>/{PACKET_NAME} is always written, "
                        "since `prompt --role reviewer` reads that path")
    add_repo_root_arg(p)
    args = p.parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    text = build_packet(root, args.node_id, ref=args.ref, verify_cmds=args.verify_cmd, base=args.base,
                        max_diff_lines=args.max_diff_lines, max_diff_bytes=args.max_diff_bytes, full=args.full)
    for out in [reviews_dir(root, args.node_id) / PACKET_NAME, *([args.output] if args.output else [])]:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
