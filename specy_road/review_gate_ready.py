"""READY-adjacent gate helpers: the interactive human approval, the trial merge, ``specy-road
ready``.

``specy-road ready`` writes the executor's READY hand-off. After a successful write it warns when
``HEAD`` no longer merges cleanly with the integration branch (the trial merge ``review status``
makes) and when the branch changes product files but adds no line under the CHANGELOG's
``[Unreleased]`` heading.
"""

from __future__ import annotations

import argparse
import shlex
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from specy_road import review_lock
from specy_road.brief_acceptance import acceptance_ids
from specy_road.checks_config import check_commands
from specy_road.cli_args import add_model_arg
from specy_road.finish_implementation_check import base_ref, in_zones
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import (
    commits_behind, current_branch_name, git_stdout, git_text, is_worktree_root, merge_conflicts,
    run,
)
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.nested_repos import (
    NestedRepo, branch_tip, covers, in_nested, nested_base_ref, nested_prefixes, nested_repos,
)
from specy_road.orchestration_config import effective_config, roster_entry
from specy_road.planning_artifacts import resolve_planning_path
from specy_road.ready_run_checks import prepare_live_runs, run_argv, run_check
from specy_road.review_files import (
    HUMAN, READY_PREFIX, load_ready, render_front_matter, review_path, reviews_dir, write_review,
)
from specy_road.review_policy_pin import policy_source
from specy_road.review_signing import NOTES_KEY, SigningError, notes_digest, sign, verify
from specy_road.review_target import ReviewTargetError, full_sha, resolve_target, same_commit
from specy_road.runtime_paths import (
    add_repo_root_arg, project_prefix, rebase_to_project, resolve_repo_root,
)
from specy_road.sibling_repos import sibling_heads_field
from specy_road.toolkit_version import stamp_review_toolkit_version


def write_human_approval(repo_root: Path, node: dict[str, Any], commit: str,
                         sign_key: Path | None = None) -> Path:
    """File the interactive approval as ``REVIEW-human.md`` at ``commit``, signed when a key is
    given.

    A signature is verified against the roster's ``human`` ``public_key``
    before anything is written: a wrong key raises :class:`SigningError` and
    leaves no record behind, as ``review record --sign-key`` does. While a reviewer run on the leaf
    holds its hand-off directory past :data:`~specy_road.review_lock.FILING_WAIT`, raises
    :class:`~specy_road.review_lock.ReviewRunBusy` and writes nothing.
    """
    body = "Approved interactively with `specy-road mark-implementation-reviewed`.\n"
    data = {
        "node_id": node["id"],
        "model": HUMAN,
        "family": HUMAN,
        "date": date.today().isoformat(),
        "verdict": "approve",
        "commit": commit,
        "acceptance": {aid: "pass" for aid in acceptance_ids(node)},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "commands_rerun": [],
        "required_changes": [],
        "fresh_session": True,
        "authored_fix": False,
        # Whoever runs mark-implementation-reviewed is coordinating; say so.
        "is_coordinator": True,
        NOTES_KEY: notes_digest(body),
    }
    data = stamp_review_toolkit_version(data)
    if sign_key is not None:
        data["signature"] = sign(data, sign_key)
        config, _err = effective_config(repo_root, policy_source(repo_root)[0])
        pub = (roster_entry(config, HUMAN) or {}).get("public_key")
        ok, why = verify(data, data["signature"], str(pub or ""), HUMAN)
        if not ok:
            raise SigningError(f"the signature does not verify against the roster public_key for "
                               f"{HUMAN!r} ({why}); wrong key?")
    path = review_path(repo_root, node["id"], HUMAN)
    with review_lock.review_run_lock(path.parent, wait=review_lock.FILING_WAIT):
        # replaces a case variant such as review-human.md
        write_review(path, render_front_matter(data, body))
    return path


#: Project-relative bookkeeping, where a trial-merge conflict blocks nothing; ``x/`` covers below x,
#: a file only itself.
TRIAL_MERGE_BOOKKEEPING = ("work/", "roadmap/", "planning/", "roadmap.md", "roadmap-context.md")


def is_trial_merge_bookkeeping(project_path: str) -> bool:
    return any(project_path.startswith(b) if b.endswith("/") else project_path == b
               for b in TRIAL_MERGE_BOOKKEEPING)


@dataclass(frozen=True)
class TrialMerge:
    """Merging the integration branch into a branch, done in memory; ``problem()`` says why review
    waits."""
    base_ref: str
    behind: int
    conflicts: list[str]        # project-relative; outside the project, ``../``-relative
    code_conflicts: list[str]   # the ones that block: not bookkeeping, or outside the project

    def problem(self) -> str | None:
        return (f"{self.base_ref} is {self.behind} commit(s) ahead and a trial merge conflicts on "
                f"{', '.join(self.code_conflicts)}: merge it into this branch and resolve before "
                "review") if self.code_conflicts else None


def trial_merge(repo_root: Path, ref: str, integration_ref: str | None) -> TrialMerge | None:
    """Trial-merge ``integration_ref`` into ``ref``, or ``None`` when git cannot answer."""
    behind = commits_behind(repo_root, ref, integration_ref) if integration_ref else None
    conflicts = (merge_conflicts(repo_root, ref, integration_ref)
                 if integration_ref and behind else [])
    if integration_ref is None or behind is None or conflicts is None:
        return None
    prefix = project_prefix(repo_root)
    rebased = {p: rebase_to_project(p, prefix) for p in conflicts}   # None: outside the project
    named = {p: r if r is not None else "../" * prefix.count("/") + p for p, r in rebased.items()}
    code = [named[p] for p, r in rebased.items() if r is None or not is_trial_merge_bookkeeping(r)]
    return TrialMerge(integration_ref, behind, list(named.values()), code)


def trial_merge_or_exit(repo_root: Path) -> None:
    """Refuse before any bookkeeping commit while landing ``HEAD`` would conflict on code."""
    ib, remote, _warnings = resolve_integration_defaults(
        repo_root, explicit_base=None, explicit_remote=None)
    tm = trial_merge(repo_root, "HEAD", base_ref(repo_root, remote, ib))
    if tm is None or tm.problem() is None:
        return
    print(f"error: {tm.problem()}.", file=sys.stderr)
    print(f"  Run `git merge {tm.base_ref}`, resolve, commit, and have the result reviewed.",
          file=sys.stderr)
    raise SystemExit(1)


def policy_source_line(root: Path) -> str:
    """The packet's ``Policy source`` line: where the gate reads its policy from."""
    ref, err = policy_source(root)
    if err:
        return f"- **Policy source:** _{err}_ (the gate fails closed)"
    if ref is None:
        return "- **Policy source:** _the working tree (not a git checkout)_"
    return f"- **Policy source:** `{ref}` @ `{full_sha(root, ref) or '?'}`"


def trial_merge_lines(root: Path, ref: str | None, integration_ref: str | None) -> list[str]:
    """Whether the branch tip still merges into the integration branch; a code conflict stops
    review."""
    tm = trial_merge(root, ref, integration_ref)
    if tm is None:
        return ["- **Trial merge:** _git could not answer_"]
    ahead = f"`{tm.base_ref}` is {tm.behind} commit(s) ahead"
    if not tm.conflicts:
        return [f"- **Trial merge:** {ahead}; merges cleanly" if tm.behind else
                f"- **Trial merge:** up to date with `{tm.base_ref}`"]
    names = ", ".join(f"`{p}`" for p in tm.conflicts)
    if tm.problem() is None:
        return [f"- **Trial merge:** {ahead}; conflicts on bookkeeping only ({names}), "
                "which does not block"]
    return [f"- **Trial merge:** {ahead}; **conflicts on {names}**", "",
            f"**Stop: {tm.problem()}.** Reviewing this commit is wasted work: the merge makes it "
            "stale.", ""]


def parse_check(spec: str) -> tuple[str, int]:
    """``'<cmd>=<exit>'`` as ``(cmd, exit)``; the last ``=`` splits, so the command may contain
    one."""
    cmd, sep, code = spec.rpartition("=")
    try:
        if sep and cmd.strip():
            return cmd.strip(), int(code)
    except ValueError:
        pass
    raise ValueError(f"{spec!r}: expected '<cmd>=<exit>', e.g. 'pytest tests/test_x.py=0'")


def ready_body(red_green: list[tuple[str, int]], note: str | None) -> str:
    """Red-green evidence stays out of ``verify``: a non-zero exit there fails the gate."""
    out = []
    if red_green:
        out += ["## Red-green evidence", "",
                "Checks that fail without the fix, by design; listed here, not under `verify`, "
                "so they do not gate.",
                "", *(f"- `{cmd}` exited {code}" for cmd, code in red_green), ""]
    if note:
        out += [note.strip(), ""]
    return "\n".join(out)


def _ready_errors(text: str, node_id: str, t: Any) -> list[str]:
    """The same checks ``handoff status`` makes, on ``text`` before anything is written."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "READY.md").write_text(text, encoding="utf-8")
        return load_ready(Path(td) / "READY.md", node_id, (t.entry or {}).get("branch"),
                          acceptance_ids(t.node)).errors


_RED_GREEN_HINT = ("Fix it, or, if it is a check meant to fail without the fix, pass it as "
                   "--red-green instead of --verify or --run")


def _cleaned_zones(zones) -> list[str]:
    """Touch-zone strings with surrounding slashes removed; non-strings are skipped."""
    cleaned = []
    for zone in zones or []:
        if isinstance(zone, str) and (text := zone.strip().strip("/")):
            cleaned.append(text)
    return cleaned


def _status_paths(repo: Path) -> list[str] | None:
    """Paths ``git status`` lists, both sides of a rename, or ``None`` when git cannot answer.

    ``-z`` keeps a path with a space as one field. Ignored files are absent, so an
    untracked file the project ignores is not an in-zone change.
    """
    out = git_stdout(["status", "--porcelain", "--untracked-files=all", "-z"], repo)
    if out is None:
        return None
    fields, paths, i = out.split("\0"), [], 0
    while i < len(fields):
        entry = fields[i]
        if len(entry) < 4:
            i += 1
            continue
        paths.append(entry[3:])
        i += 1
        if entry[0] in "RC":   # the next field is the path before the rename or copy
            if i < len(fields) and fields[i]:
                paths.append(fields[i])
            i += 1
    return paths


def uncommitted_in_zone(root: Path, zones: list[str]) -> list[str] | None:
    """In-zone paths that are staged, unstaged, deleted or untracked, outer repo and covered nested
    repos.

    ``None`` when git cannot list the outer tree, or a covered nested repository that is present:
    a missing answer is not a clean tree. One that is not checked out here is skipped, as is a
    nested repository the zones do not cover.
    """
    prefix = project_prefix(root)
    listed = _status_paths(root)
    if listed is None:
        return None
    skip = nested_prefixes(root)
    found = [p for p in listed if not in_nested(p, skip) and in_zones(zones, p, prefix)]
    for nr in nested_repos(root):
        if not covers(zones, nr.path, prefix):
            continue
        repo = root / nr.path
        # absent here: the nested-zone diff helper has nothing to read either
        if not is_worktree_root(repo):
            continue
        sub = _status_paths(repo)
        if sub is None:
            return None
        lead = f"{prefix}{nr.path}/"
        found += [lead + p for p in sub if in_zones(zones, lead + p, prefix)]
    return sorted(set(found))


def _nested_gap(nr: NestedRepo, evidence: str) -> str:
    return f"nested repository {nr.path!r} cannot be assessed: {evidence}"


def _nested_in_zone(root: Path, zones: list[str]) -> tuple[list[str], str | None]:
    """In-zone commits in covered nested repositories that are checked out here, or why one cannot
    be read.

    One rule. A checkout is assessed only when its integration base resolves and, when the leaf
    branch exists there, the merge base and the committed diff can be listed. Any of those missing
    is a refusal that names the repository and the missing evidence, not an empty change. No leaf
    branch means no commits. A covered repository that is not checked out is left unread: this
    command does not invent a checkout. ``nested_zone_paths`` is not used: it turns a missing base
    or an unreadable diff into no paths.
    """
    branch = current_branch_name(root) or ""
    prefix = project_prefix(root)
    found: list[str] = []
    for nr in nested_repos(root):
        if not covers(zones, nr.path, prefix):
            continue
        repo = root / nr.path
        if not is_worktree_root(repo):
            continue
        base_ref_name = nested_base_ref(repo, nr)
        if not base_ref_name:
            return [], _nested_gap(
                nr, f"no integration base for {nr.integration_branch!r} (remote {nr.remote})")
        listed = _status_paths(repo)
        if listed is None:
            return [], _nested_gap(nr, "git cannot list uncommitted paths")
        tip = branch_tip(repo, nr, branch) if branch else None
        if not tip:
            continue
        mb = git_text(["merge-base", base_ref_name, tip], repo)
        if not mb:
            return [], _nested_gap(nr, f"no merge base of {base_ref_name} and {branch}")
        diff = diff_paths(repo, f"{mb}...{tip}")
        if diff is None:
            return [], _nested_gap(nr, f"git cannot list the committed diff {mb[:12]}...{tip[:12]}")
        lead = f"{prefix}{nr.path}/"
        found += [f"{nr.path}/{p}" for p in diff if in_zones(zones, f"{lead}{p}", prefix)]
    return found, None


def committed_in_zone(root: Path, base: str, commit: str,
                      zones: list[str]) -> tuple[list[str] | None, str | None]:
    """``(in-zone commits, refusal)``. The refusal names a covered nested repository that cannot be
    assessed.

    ``(None, None)`` when the outer diff cannot be listed. Paths git lists for the outer repository
    inside a nested repository's directory are that repository's, so they are not counted twice.
    """
    changed = diff_paths(root, f"{base}...{commit}")
    if changed is None:
        return None, None
    nested, gap = _nested_in_zone(root, zones)
    if gap:
        return [], gap
    prefix = project_prefix(root)
    skip = nested_prefixes(root)
    outer = [p for p in changed if in_zones(zones, p, prefix) and not in_nested(p, skip)]
    return sorted(set(outer).union(nested)), None


def leaf_work_problem(root: Path, zones, base: str, commit: str) -> str | None:
    """Why ``ready`` must refuse, or ``None`` when in-zone work is committed and the tree is clean
    there.

    Zones are the claim's, or the node's when the claim has none. A path matches in either the
    project-root or the git-root spelling, and a directory zone does not match a sibling whose
    name only starts with the zone's. A covered nested repository that is checked out but whose
    integration base or committed diff cannot be read is named; that is not an empty change.
    """
    cleaned = _cleaned_zones(zones)
    committed, gap = committed_in_zone(root, base, commit, cleaned)
    if gap:   # a covered nested repository with no base or no diff is not an empty change
        return gap
    dirty = uncommitted_in_zone(root, cleaned)
    if dirty is None:
        return "git cannot list uncommitted paths"
    if dirty:
        return "uncommitted in-zone changes: " + ", ".join(dirty)
    if committed is None:
        return f"git cannot list the paths changed in {base[:12]}...{commit[:12]}"
    if not committed:
        return "no committed in-zone path differs from the integration merge base"
    return None


def empty_ready_error(root: Path, zones, data: dict[str, Any]) -> str | None:
    """An unblocked READY whose commit is its base, when the leaf's zones cover no nested
    repository.

    A ``blocked_on`` hand-off stays valid: the executor stopped on purpose. A leaf whose zones cover
    a configured nested repository keeps today's reading, because an outer commit equal to its base
    does not say whether the nested repository holds the work.
    """
    if data.get("blocked_on"):
        return None
    prefix = project_prefix(root)
    if any(covers(_cleaned_zones(zones), nr.path, prefix) for nr in nested_repos(root)):
        return None
    if not same_commit(root, data.get("commit"), data.get("base")):
        return None
    return "commit resolves to its base: no committed work on this leaf"


def _checked_runs(root: Path, zones, base: str, commit: str, runs: list[str],
                  argv_runs: list[list[str]]) -> tuple[list[dict[str, Any]], str | None]:
    """Run the verifiers only when the leaf already has committed, clean in-zone work.

    The same check runs again afterwards, and a command that moved ``HEAD`` is refused. Either
    refusal is returned with no READY write, so an existing file stays byte-for-byte.
    ``commit`` is the fallback tip when ``HEAD`` cannot be read.
    """
    tip = git_text(["rev-parse", "HEAD"], root) or commit
    if problem := leaf_work_problem(root, zones, base, tip):
        return [], problem
    live, refuse = _live_run_rows(runs, argv_runs)
    if refuse:
        return live, refuse
    after = git_text(["rev-parse", "HEAD"], root) or ""
    if after != tip:
        return live, f"HEAD moved during --run ({tip[:12]} -> {after[:12] or '?'})"
    return live, leaf_work_problem(root, zones, base, after)


def _live_run_rows(runs: list[str],
                   argv_runs: list[list[str]]) -> tuple[list[dict[str, Any]], str | None]:
    """Run ``--run`` and ``--run-argv`` verifiers; return new rows or a refusal message."""
    rows: list[dict[str, Any]] = []
    for cmd in runs:
        print(f"running: {cmd}", file=sys.stderr)
        v = run_check(cmd)
        if v["exit"] != 0:
            return rows, (f"failing verifier: `{cmd}` exited {v['exit']}; its last lines:\n"
                          f"{v['tail']}\n{_RED_GREEN_HINT}")
        if w := v.get("warning"):
            print(f"warning: {w}", file=sys.stderr)
        rows.append(v)
    for argv in argv_runs:
        cmd = shlex.join(argv)
        print(f"running: {cmd}", file=sys.stderr)
        v = run_argv(argv)
        if v["exit"] != 0:
            return rows, (f"failing verifier: `{cmd}` exited {v['exit']}; its last lines:\n"
                          f"{v['tail']}\n{_RED_GREEN_HINT}")
        if w := v.get("warning"):
            print(f"warning: {w}", file=sys.stderr)
        rows.append(v)
    return rows, None


def cmd_ready(ns: argparse.Namespace) -> int:
    """Write ``READY-<model>.md`` for ``HEAD``, validated by the loader ``handoff status`` uses;
    exit 1 on refusal.

    ``--run`` commands run last, after every cheap refusal, so a wrong branch never costs a test
    run; the ``checks:`` entries with ``when: ready`` run first among them, in the same way.
    A leaf with no committed in-zone change, or with uncommitted in-zone changes, is refused before
    those commands and again after them; a command that moves ``HEAD`` is refused too, and an
    existing READY file is left as it was.
    """
    root = resolve_repo_root(ns)
    raw_runs = check_commands(root, "ready") + (getattr(ns, "run", None) or [])
    run_argv_specs = getattr(ns, "run_argv", None) or []
    try:
        verify = [{"cmd": cmd, "exit": code} for cmd, code in (parse_check(s) for s in ns.verify)]
        red_green = [parse_check(s) for s in ns.red_green]
        t = resolve_target(root, ns.node_id, "HEAD")
    except (ValueError, ReviewTargetError) as e:
        return _refuse(str(e))
    runs, argv_runs, live_err = prepare_live_runs(raw_runs, run_argv_specs)
    if live_err:
        return _refuse(live_err)
    if failing := [f"`{v['cmd']}` exited {v['exit']}" for v in verify if v["exit"] != 0]:
        return _refuse(f"failing verifier: {'; '.join(failing)}. {_RED_GREEN_HINT}")
    branch = current_branch_name(root)
    if not branch or not t.base or not t.commit:
        return _refuse("needs a checked-out branch with a merge base on the integration branch")
    changed = diff_paths(root, f"{t.base}...{t.commit}")
    if changed is None:
        return _refuse(f"git cannot list the paths changed in {t.base[:12]}...{t.commit[:12]}")
    data = {"node_id": ns.node_id, "agent": ns.model, "branch": branch, "commit": t.commit,
            "base": t.base, "changed_paths": changed, "verify": verify,
            **sibling_heads_field(root),
            **({"fix_of": ns.fix_of} if getattr(ns, "fix_of", None) else {})}
    body = ready_body(red_green, ns.note)
    if errs := _ready_errors(render_front_matter(data, body), ns.node_id, t):
        return _refuse("; ".join(errs))
    live, problem = _checked_runs(root, t.touch_zones, t.base, t.commit, runs, argv_runs)
    if problem:
        return _refuse(problem)
    verify.extend(live)
    text = render_front_matter({**data, "verify": verify}, body)
    if errs := _ready_errors(text, ns.node_id, t):
        return _refuse("; ".join(errs))
    dest = reviews_dir(root, ns.node_id) / f"{READY_PREFIX}{ns.model}.md"
    write_review(dest, text)
    print(f"Wrote {dest} at {t.commit[:12]}")
    _print_post_write_warnings(root, ns.node_id)
    return 0


def _refuse(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def add_ready_parser(sub: argparse._SubParsersAction) -> None:
    r = sub.add_parser(
        "ready", help="Write the executor's READY hand-off for HEAD into work/reviews/<NODE_ID>/")
    r.add_argument("node_id")
    add_model_arg(r, help="Your roster id; the file is READY-<model>.md", required=True)
    r.add_argument("--run", action="append", default=[], metavar="CMD",
                   help="Run this verifier or test now from the current directory and record its "
                        "exit and the last lines of its output, which the review packet shows "
                        "(repeatable); a non-zero exit is refused")
    r.add_argument("--run-argv", action="append", default=[], metavar="JSON",
                   help="Like --run but runs a JSON array of strings without a shell (repeatable); "
                        "invalid JSON or a value that is not a non-empty JSON array of strings "
                        "whose first element is non-empty (e.g. not-json, [], {}, [1], [\"\"]) is "
                        "refused before anything runs; later elements may be empty or whitespace; "
                        'e.g. ["echo", "ok"] or ["echo", ""] is accepted')
    r.add_argument("--verify", action="append", default=[], metavar="CMD=EXIT",
                   help="A verifier or test you ran and its exit, without its output (repeatable); "
                        "a non-zero exit is refused")
    r.add_argument("--red-green", action="append", default=[], metavar="CMD=EXIT",
                   help="A check that fails without the fix, by design (repeatable); goes in the "
                        "notes, not verify")
    r.add_argument("--fix-of", metavar="MODEL@SHA",
                   help="The one block this commit fixes: the blocking reviewer and the commit it "
                        "blocked, which must be HEAD's sole parent; another family's approval of "
                        "that commit may then count here, and the blocker checks the fix")
    r.add_argument("--note",
                   help="Notes for the coordinator: anything you could not finish, and why")
    add_repo_root_arg(r)
    r.set_defaults(func=cmd_ready)


# --- Post-write warnings of ``specy-road ready`` ---

def trial_merge_warning(root: Path, node_id: str) -> list[str]:
    """Lines warning that ``HEAD`` no longer merges cleanly with the integration branch; empty when
    it does."""
    try:
        t = resolve_target(root, node_id, "HEAD")
    except ReviewTargetError:
        return []
    tm = trial_merge(root, t.ref, t.base_ref)   # the same call handoff status makes
    if tm is None or not tm.conflicts:
        return []
    if tm.problem() is None:
        return [f"note: a trial merge with {tm.base_ref} conflicts on bookkeeping only "
                f"({', '.join(tm.conflicts)}), which does not block review"]
    return [f"warning: {tm.problem()}.",
            f"  Before handing off: run `git merge {tm.base_ref}`, resolve, commit, run the "
            f"verifiers again, and rerun `specy-road ready`; a reviewer cannot pass this commit."]


def _changelog_at(root: Path, rev: str) -> str | None:
    """Blob text of ``CHANGELOG.md`` at ``rev``.

    One rule: ``git cat-file blob`` is the text. ``""`` when that path is absent.
    None when git cannot answer or the object is not a blob (a tree or a gitlink,
    reported as ``bad file``). A symlink is a blob, so the text is the link
    target, not the file it names.
    """
    result = run(["cat-file", "blob", f"{rev}:CHANGELOG.md"], root)
    if result.ok:
        return result.out
    if result.failure:
        return None
    msg = result.message
    quoted = f"'{rev}'"
    absent = quoted in msg and ("does not exist in " in msg or "not in " in msg)
    return "" if absent else None


def _exempt_text(root: Path, node: dict) -> str | None:
    """Acceptance plus the planning sheet, or None when a configured sheet cannot be read.

    One rule: a set ``planning_dir`` is read as text, and any ``Exception`` from that read
    stays silent. That includes a missing path, a directory, an unreadable file, and
    ``RuntimeError`` from a symlink loop. ``KeyboardInterrupt`` and ``SystemExit`` are not
    caught. An empty file is a successful read. No ``planning_dir`` uses the acceptance
    lines only.
    """
    acceptance = node.get("acceptance") or []
    parts = [str(item) for item in acceptance] if isinstance(acceptance, list) else []
    rel = node.get("planning_dir")
    if not isinstance(rel, str) or not rel.strip():
        return "\n".join(parts)
    try:
        parts.append(resolve_planning_path(root, rel).read_text(encoding="utf-8"))
    except Exception:
        return None
    return "\n".join(parts)


def _changelog_warning(root: Path, node_id: str) -> list[str]:
    """The reminder line after a successful ready, or nothing when git or a read cannot answer."""
    try:
        target = resolve_target(root, node_id, "HEAD")
    except ReviewTargetError:
        return []
    if not target.base or not target.commit:
        return []
    changed = diff_paths(root, f"{target.base}...{target.commit}")
    if changed is None:
        return []
    head = _changelog_at(root, target.commit)
    base = _changelog_at(root, target.base)
    if head is None or base is None:
        return []
    exempt = _exempt_text(root, target.node)
    if exempt is None:
        return []
    warning = missing_entry_warning(changed, project_prefix(root), base, head, exempt)
    return [warning] if warning else []


def _print_post_write_warnings(root: Path, node_id: str) -> None:
    """After a successful write: the trial-merge warning, then the CHANGELOG reminder, on stderr."""
    for line in trial_merge_warning(root, node_id) + _changelog_warning(root, node_id):
        print(line, file=sys.stderr)


# --- The CHANGELOG reminder's rule: callers supply the diff and the changelog text; no git here ---

_UNRELEASED = "## [Unreleased]"
_EXEMPT = "no changelog entry"
_SHOWN = 3


def missing_entry_warning(
    changed: list[str], prefix: str, base_text: str, head_text: str, exempt_text: str,
) -> str | None:
    """One warning line, or None when the branch needs no CHANGELOG reminder.

    ``changed`` paths are git-root relative. ``prefix`` is ``project_prefix``
    (``sr/`` or ``""``). ``base_text`` is ``CHANGELOG.md`` at the merge base, empty
    when that file is absent, and an absent heading there counts as an empty section.
    ``head_text`` is ``CHANGELOG.md`` at HEAD: no file or no ``## [Unreleased]`` heading
    returns None. The section is the lines after that heading up to the next ``## ``
    heading; an edited line keeps the non-blank count, so it still warns. ``exempt_text``
    is the leaf's acceptance plus its planning sheet; ``no CHANGELOG entry`` in any case
    returns None. Each displayed path escapes ``\\`` and every non-printable character, so
    the result is one line. Other printable characters, including commas and non-ASCII, are
    kept, so a comma inside a path is not distinguished from the comma between paths.
    """
    if _EXEMPT in exempt_text.lower():
        return None
    head = _unreleased_nonblank(head_text)
    if head is None:
        return None
    base = _unreleased_nonblank(base_text)
    if head > (0 if base is None else base):
        return None
    products = [path for path in changed if _product(path, prefix)]
    if not products:
        return None
    names = ", ".join(_display_path(path) for path in products[:_SHOWN])
    return (
        "warning: ## [Unreleased] in CHANGELOG.md gained no line, but this branch changes "
        f"{names}; write `no CHANGELOG entry` in the leaf's acceptance or planning sheet to "
        "exempt it"
    )


def _display_path(path: str) -> str:
    """One line for ``path``: ``\\`` and every non-printable character use ``unicode_escape``."""
    return "".join(
        ch if ch.isprintable() and ch != "\\" else ch.encode("unicode_escape").decode("ascii")
        for ch in path
    )


def _unreleased_nonblank(text: str) -> int | None:
    """Non-blank lines under ``## [Unreleased]`` until the next ``## `` heading, or None."""
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if _unreleased_heading(line)), None)
    if start is None:
        return None
    count = 0
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            count += 1
    return count


def _unreleased_heading(line: str) -> bool:
    rest = line[len(_UNRELEASED):] if line.startswith(_UNRELEASED) else None
    return rest is not None and not rest.strip()


def _product(path: str, prefix: str) -> bool:
    """True for a changed path that is not ``CHANGELOG.md``, under ``tests/``, or bookkeeping.

    A file named ``tests`` is a product path. In a nested layout (non-empty ``prefix``)
    bookkeeping is every path under the project directory. Otherwise it is
    :func:`is_trial_merge_bookkeeping`.
    """
    if path == "CHANGELOG.md" or path.startswith("tests/"):
        return False
    if prefix:
        return not path.startswith(prefix)
    return not is_trial_merge_bookkeeping(path)
