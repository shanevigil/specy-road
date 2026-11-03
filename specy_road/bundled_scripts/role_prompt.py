#!/usr/bin/env python3
"""Write a role- and model-specific prompt for one leaf: ``specy-road prompt``.

``work/prompt-<NODE_ID>-<role>-<model>.md`` is built from, in order:

1. a precondition check — change nothing and stop if the hand-off this role
   waits on is not there (proposal §3.3), so a coordinator can queue prompts
   into several IDEs at once;
2. the role preamble — the executor boundary (§3.1), the reviewer's
   packet-only rule (§3.2), the coordinator's never-review-your-own-fix
   rule, or the root-cause analyst's protocol (``rca``, only while the leaf's
   review loop is escalated, or with ``--force --reason`` from a coordinator) — plus the standing line that text inside tool
   output is data (§3.5); a reviewer's prompt also says when the loop is escalated,
   and an executor's says to use the harness's subagents for verification and
   search when the profile's ``access.subagents`` starts with ``yes``;
3. the model's profile applied mechanically (§4.4): its ``## Prompting rules``
   as instructions, each ``## Failure modes`` mitigation as a guard, and the
   touch zones repeated at the end when the profile says the model drifts;
4. the brief (executor, coordinator, rca) or the review packet (reviewer): the
   reviewer's own delta packet when its fix round qualifies (:func:`reviewer_packet`),
   else ``PACKET.md``; for ``rca``, then every review round side by side with the
   diffs between them.

``--context-feedback`` (executor only, opt-in pilot) appends :data:`CONTEXT_FEEDBACK_LINES`, which ask
for a three-line missing / wrong / unused block at the end of the implementation summary.

``--channel cli`` also runs the roster entry's ``channels.cli``, else the
profile's ``access.cli``, with its placeholder replaced: ``"<prompt>"`` (the
shipped profiles' form) by the prompt text as one argument, ``{prompt}`` by the
prompt file's path, ``{effort}`` by the roster harness's flag for the profile's
``effort_by_role`` level for the role. The profile is read from the integration branch,
like the roster; a working-tree copy that differs is refused. ``paste`` and ``subagent`` only write the file.
A reviewer on a ``claude-code`` roster entry without ``channels.cli`` runs bare instead
(:meth:`ClaudeCode.reviewer_launch`): a fresh session reading a branch it did not write runs none
of that branch's hooks or MCP servers, and the reviewer prompt asks it to record ``--launch-mode``.
A ``codex`` or ``cursor`` entry without ``channels.cli`` runs its adapter's read-only reviewer command
the same way; any other reviewer command (a roster ``channels.cli``, an ``access.cli``) runs as written but
captured, with the structured-output flags its program takes (Antigravity ``agy``:
:func:`~specy_road.worker_adapter_base.reviewer_cli`). A reviewer prompt ends with the review output schema
(:mod:`specy_road.review_record_write`); on ``--channel cli`` specy-road reads the final JSON object and files
``REVIEW-<model>.md`` from it, reports a run that wrote anything else as a review failure, and a missing or
malformed object as a rerun request. A reviewer it does not read back (``paste``, ``subagent``) files with
``review record``.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

from specy_road.bundled_scripts.do_next_prompt import SUBAGENT_LINE
from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.bundled_scripts.review_packet import build_packet
from specy_road.bundled_scripts.role_prompt_rca import (
    DATA_LINE,
    coordinator_preamble,
    executor_preamble,
    precondition,
    profile_lines,
    reviewer_preamble,
)
from specy_road.decisions import coordinator_decision_lines
from specy_road.model_profiles import ROLES, Profile
from specy_road.orchestrate_plan import (
    ANY,
    entry_may_process,
    is_available,
    may_handle,
    node_eligibility,
    node_sensitivity,
)
from specy_road.worker_adapter_parsers import effort_note
from specy_road.worker_adapters import ADAPTERS, Launch, Unsupported, placeholder_problem, reviewer_cli, substitute_prompt
from specy_road.orchestration_config import substitute_for
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_record_write import output_path, run_and_file, schema_lines, write_schema
from specy_road.review_gate import delta_basis
from specy_road.review_rca import escalated_note, loop_state, rca_evidence, rca_preamble, rca_trigger
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, resolve_repo_root

CHANNELS = ("cli", "paste", "subagent")
# `rca` is not a roster role or a profile score: any rostered reviewer that is not a party may analyse.
PROMPT_ROLES = (*ROLES, "rca")
# Opt-in pilot (`--context-feedback`): three structured lines on what the brief and prompt got wrong, before
# the question is asked of every implementation summary (docs/design-notes/context-feedback-pilot.md).
CONTEXT_FEEDBACK_LINES = [
    "## Context feedback (pilot)",
    "",
    "End your implementation summary with a `## Context feedback` section of exactly three lines. Each line "
    "quotes the brief or prompt line it is about, or names the turn where you noticed it; without one of "
    "those it is not acted on. Write `none` when there is nothing to report.",
    "",
    "- missing: <what the brief or prompt should have told you and did not; quote the line that should have "
    "said it, or name the turn where you had to find it out yourself>",
    "- wrong: <a line of the brief or prompt that was false or out of date; quote it>",
    "- unused: <a section of the brief or prompt you never needed; quote its heading>",
    "",
]
# Executors once deleted unrelated docstrings and messages to stay under a line cap; reviewers caught it a round late.
FILE_LIMIT_LINES = [
    "If a change would push a file over a `specy-road file-limits` cap, move the new or related code into a new "
    "module and name that file in your implementation summary so the touch zones can be updated; never delete or "
    "shorten unrelated docstrings, comments or user-facing text to fit.",
    "",
]
REMOVED_TEXT_LINES = [
    "Also check the diff for docstrings, comments or messages removed or shortened that the leaf did not need to "
    "touch (often to fit a file-limits cap), and require their restoration under `required_changes`.",
    "",
]
LAUNCH_MODE_LINES = [
    "Add `--launch-mode full|bare|explicit` to that `review record` command, naming how this session was "
    "started: `bare` for Claude Code's `--bare` (no repository hooks, skills, MCP servers or CLAUDE.md; "
    "`specy-road prompt --channel cli` starts a Claude Code reviewer that way), `explicit` when the command "
    "named exactly which settings and MCP servers to load, `full` when it loaded the repository's own as an "
    "interactive session does.",
    "",
]
#: Reviewer harnesses whose default command specy-road launches, reads back and files from.
READ_BACK_HARNESSES = ("claude-code", "codex", "cursor")
READ_BACK_LINES = [
    "**specy-road files your record.** It launched this session and reads your final message: end it with the JSON "
    "object described at the end of this prompt, and skip the `review record` and `--launch-mode` steps above. "
    "Write no file but your notes (which belong in the object's `notes`), and do not commit, push or run `gh`: "
    "a run that writes anything else is reported as a review failure, and output with no valid object is a rerun "
    "request, never a verdict. That includes caches and build output in ignored or `work/` paths: specy-road runs "
    "you with no Python bytecode and no pytest cache, so re-run commands that only read.",
    "",
]
PASTED_LINES = [
    "End your reply with the JSON object described at the end of this prompt as well; nothing reads this "
    "session back, so you still file the record yourself with `review record` as above.",
    "",
]


def has_subagents(prof: Profile | None) -> bool:
    """``access.subagents`` starts with ``yes`` (YAML reads a bare ``yes`` as true)."""
    access = prof.data.get("access") if prof is not None else None
    value = access.get("subagents") if isinstance(access, dict) else None
    return value is True or str(value or "").startswith("yes")


def reviewer_packet(root: Path, node_id: str, model: str, t: ReviewTarget,
                    ref: str | None = None) -> tuple[str | None, str]:
    """``(packet text, error)``. ``model``'s own delta packet, written now to ``PACKET-<model>.md``, when
    ``policy.delta_review`` lets its fix round be reviewed from one (``review_gate.delta_basis``, which
    also honours ``review-packet --full``); else ``PACKET.md``, the full packet."""
    packet, own = reviews_dir(root, node_id) / PACKET_NAME, reviews_dir(root, node_id) / f"PACKET-{model}.md"
    own.unlink(missing_ok=True)   # a stale delta packet never stands in for this round's
    if not packet.is_file():
        return None, f"no review packet at {packet}; run `specy-road review-packet {node_id}` first"
    text = packet.read_text(encoding="utf-8")
    prior = delta_basis(root, t.node, model, t.commit)[0]   # None under `review-packet --full`
    if prior is None:
        return text, ""
    text = build_packet(root, node_id, ref=ref, verify_cmds=[], max_diff_lines=0, max_diff_bytes=0, prior=prior)
    own.write_text(text, encoding="utf-8")
    print(f"note: {model} reviews the change since its approval of {prior.data['commit']} from {own}",
          file=sys.stderr)
    return text, ""


def reviewer_lines(node_id: str, model: str, ref: str | None, loop, read_back: bool) -> list[str]:
    """The reviewer's preamble; ``read_back`` (specy-road reads its final message and files the record, as
    ``review delegate`` and the default ``--channel cli`` reviewer commands do) says not to file it by hand."""
    return (reviewer_preamble(node_id, model, ref) + REMOVED_TEXT_LINES + LAUNCH_MODE_LINES
            + escalated_note(loop, node_id) + (READ_BACK_LINES if read_back else PASTED_LINES))


def build_prompt(root: Path, node_id: str, *, role: str, model: str,  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
                 ref: str | None = None, context_feedback: bool = False, read_back: bool = True,
                 force_reason: str | None = None) -> tuple[str, Profile | None, str | None]:
    """``(text, profile, error)``; ``ref`` names the branch or commit under review, as ``review-packet --ref``;
    ``context_feedback`` adds the pilot's three-line block to an executor prompt; ``read_back``: :func:`reviewer_lines`;
    ``force_reason`` starts an ``rca`` prompt although the loop is not escalated (:func:`review_rca.rca_trigger`)."""
    config, err = pinned_config(root)
    if err:
        return "", None, f"orchestration config: {err}"
    entry = next((e for e in config.get("roster") or [] if e.get("id") == model), None)
    if entry is None:
        return "", None, f"{model!r} is not in the roster (roadmap/orchestration.yaml)"
    need = "reviewer" if role == "rca" else role
    substitute = need == "reviewer" and substitute_for(config, node_id, model) is not None
    if need not in (entry.get("roles") or []) and not substitute:
        return "", None, f"{model!r} does not have the {need} role in the roster"
    if not is_available(entry):
        return "", None, f"{model!r} is marked unavailable until {entry.get('unavailable_until')} in the roster"
    try:
        t = resolve_target(root, node_id, ref)
    except ReviewTargetError as e:
        if role != "coordinator":
            return "", None, str(e)
        t = None   # the coordinator's prompt is what picks the leaf up
    nodes = t.nodes if t else load_roadmap(root)["nodes"]
    node = t.node if t else next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        return "", None, f"unknown node id: {node_id}"
    if t and role == "executor":
        need = node_eligibility(t.node)
        if need != ANY and str(entry.get("class") or "") != need:
            return "", None, (f"{node_id} needs executor class {need!r}; {model!r} is "
                              f"{entry.get('class') or 'unclassed'} (`specy-road orchestrate plan`)")
    if not may_handle(entry, node_sensitivity(node)):
        return "", None, (f"{node_id} is {node_sensitivity(node)!r} and {model!r} may process only "
                          f"{entry_may_process(entry)}; route it to a model that may "
                          "(`specy-road orchestrate plan`)")
    prof = pinned_profile_for_entry(root, entry)
    if prof is not None and not prof.ok:
        return "", prof, f"profile for {model!r}: " + "; ".join(prof.errors)
    zones = list(t.touch_zones) if t else []
    loop = loop_state(root, node_id) if role in ("reviewer", "rca") else None
    if role == "rca":
        loop.escalation, err = rca_trigger(root, node_id, model, loop, force_reason)
        if err:
            return "", prof, err
    title = "Root-cause analysis" if role == "rca" else role.title()
    lines = [f"# {title} prompt: `{node_id}` for `{model}`", ""]
    if t and t.commit:   # the AGENTS.md rule: a prompt names its commit, or the agent stops to ask
        lines += [f"base: {t.commit}", ""]
    prefix = project_prefix(root)
    if t:
        lines += precondition(role, node_id, t, reviews_dir(root, node_id) / PACKET_NAME, prefix,
                              forced=role == "rca" and loop.escalation.rule == "forced")
    if role == "executor":
        lines += executor_preamble(node_id, model, zones, entry.get("subagent_family_lock"),
                                   reviews_dir(root, node_id), prefix)
        lines += FILE_LIMIT_LINES
        if has_subagents(prof):
            lines += [SUBAGENT_LINE, ""]
        if context_feedback:
            lines += CONTEXT_FEEDBACK_LINES
    elif role == "reviewer":
        lines += reviewer_lines(node_id, model, ref, loop, read_back)
    elif role == "rca":
        lines += rca_preamble(root, node_id, model, loop.escalation) + [DATA_LINE, ""]
    else:
        lines += coordinator_preamble(node_id)
        lines += coordinator_decision_lines()
    lines += profile_lines(prof, role, zones)
    if role == "reviewer":
        packet, err = reviewer_packet(root, node_id, model, t, ref)
        if packet is None:
            return "", prof, err
        lines += ["---", "", packet.rstrip(), "", "---", ""] + schema_lines()
    else:
        lines += ["---", "", render_brief(node_id, index(nodes), repo_root=root, include_history=False).rstrip(), ""]
    if role == "rca":
        lines += rca_evidence(root, t, loop)
    return "\n".join(lines) + "\n", prof, None


def _shown(argv: list[str]) -> str:
    """The command for the terminal, a long argument (the prompt, an inline schema) shortened."""
    return shlex.join(a if len(a) <= 200 else f"<{len(a)} chars>" for a in argv)


def run_default_reviewer(prof: Profile | None, prompt_path: Path, root: Path, model: str | None, reviews: Path,
                         level: str | None, harness: str = "claude-code", ref: str | None = None) -> int:
    """The harness's own read-only reviewer command (Claude Code bare, with ``--add-dir`` for the hand-off
    directory), its final JSON filed as the record (:func:`~specy_road.review_record_write.file_review`);
    0 only when a record was filed."""
    api_id = prof.api_id if prof is not None else model
    api_id = None if (api_id or "").strip().lower() in ("", "unknown") else api_id   # unknown: the harness default
    adapter, out = ADAPTERS[harness], output_path(reviews, str(model))
    out.unlink(missing_ok=True)   # a stale answer never stands in for this run's
    session = (str(uuid.uuid4()), False) if harness == "claude-code" else None   # stream-json, to read the result
    launch = adapter.reviewer_launch(prompt_path, api_id, reviews, level, session=session,
                                     schema=write_schema(reviews), output=out)
    if harness == "claude-code":
        print("note: the reviewer runs with --bare (no repository hooks, MCP servers or CLAUDE.md), and bare mode "
              "never reads your subscription login: it needs ANTHROPIC_API_KEY (or an apiKeyHelper)", file=sys.stderr)
    print(f"running: {_shown(launch.argv)}" + (f" < {prompt_path}" if launch.stdin is not None else ""), file=sys.stderr)
    return run_and_file(launch, adapter, root, str(model), reviews, ref)


def run_custom_reviewer(prof: Profile | None, cli: str, prompt_path: Path, root: Path, model: str, reviews: Path,
                        ref: str | None, harness: str | None, effort: list[str]) -> int:
    """A roster ``channels.cli`` or profile ``access.cli`` reviewer, run as written plus its program's
    structured-output flags (:func:`reviewer_cli`), captured and filed like the default commands."""
    try:
        cli = reviewer_cli(cli, write_schema(reviews))
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    output_path(reviews, model).unlink(missing_ok=True)   # a stale answer never stands in for this run's
    launch = Launch(["sh", "-c", substitute_prompt(cli, prompt_path, effort=effort)],
                    launch_mode=prof.launch_mode() if prof is not None else "full")
    return run_and_file(launch, ADAPTERS.get(harness or "generic", ADAPTERS["generic"]), root, model, reviews, ref)


def run_cli_channel(prof: Profile | None, prompt_path: Path, root: Path, preflight: str | None = None,
                    entry_cli: str | None = None, *, harness: str | None = None, role: str | None = None,
                    model: str | None = None, reviews: Path | None = None, ref: str | None = None) -> int:
    if preflight:
        # Proposal §3.6: e.g. confirm which process owns a local model's port.
        # It runs before anything else is even inspected: a failed check stops
        # the command whatever else is wrong.
        print(f"preflight: {preflight}", file=sys.stderr)
        rc = subprocess.run(preflight, shell=True, cwd=root, check=False).returncode
        if rc != 0:
            print(f"error: preflight failed (exit {rc}); nothing was sent", file=sys.stderr)
            return rc
    # `rca` is a reviewer's turn; a harness the roster does not name has no effort flag.
    level = prof.effort("reviewer" if role == "rca" else role) if prof and role else None
    if role == "reviewer" and harness in READ_BACK_HARNESSES and not entry_cli and reviews is not None:
        return run_default_reviewer(prof, prompt_path, root, model, reviews, level, harness, ref)
    cli = entry_cli or (prof.cli() if prof else None)   # the roster's channels.cli wins, as `worker delegate` has it
    if not cli:
        print("error: --channel cli needs a roster `channels.cli` or an `access.cli` in the model's profile", file=sys.stderr)
        return 1
    why = placeholder_problem(cli)
    if why:
        print(f"error: the cli has {why}: {cli}", file=sys.stderr)
        return 1
    note = effort_note(cli, level)
    if note:
        print(note, file=sys.stderr)
    effort = ADAPTERS.get(harness or "generic", ADAPTERS["generic"]).effort_flag(level)
    if role == "reviewer" and reviews is not None:   # captured, flagged and filed like the default commands
        return run_custom_reviewer(prof, cli, prompt_path, root, str(model), reviews, ref, harness, effort)
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    try:
        return subprocess.run(substitute_prompt(cli, prompt_path, effort=effort), shell=True, cwd=root,
                              check=False).returncode
    except OSError as e:   # E2BIG: "<prompt>" puts the whole text on the command line
        print(f"error: could not launch the cli: {e.strerror}; if the prompt is too long for a command line, "
              'use {prompt} (its file path) instead of "<prompt>"', file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="specy-road prompt", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("node_id")
    p.add_argument("--model", required=True, help="Roster id")
    p.add_argument("--role", required=True, choices=PROMPT_ROLES)
    p.add_argument("--channel", choices=CHANNELS, default="paste",
                   help="cli runs the profile's access.cli (<prompt> = the prompt text, {prompt} = its file path, "
                        "{effort} = the harness's flag for the role's effort); "
                        "paste/subagent only write the file")
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    p.add_argument("--context-feedback", action="store_true",
                   help="Executor only: ask for the pilot's three-line context-feedback block "
                        "(missing / wrong / unused) at the end of the implementation summary")
    p.add_argument("--force", action="store_true",
                   help="rca only: build a root-cause prompt although the loop is not escalated "
                        "(a coordinator-initiated analysis); needs --reason")
    p.add_argument("--reason", help="With --force: why the analysis is due; the prompt and the RCA record carry it")
    add_repo_root_arg(p)
    ns = p.parse_args(argv)
    if ns.force and ns.role != "rca":
        p.error("--force applies only to --role rca")
    if ns.force != bool((ns.reason or "").strip()):
        p.error("--force needs a non-empty --reason, and --reason needs --force")
    root = resolve_repo_root(ns)
    config, _ = pinned_config(root)
    entry = next((e for e in config.get("roster") or [] if e.get("id") == ns.model), {})
    entry_cli = (entry.get("channels") or {}).get("cli")
    read_back = ns.channel == "cli"   # every --channel cli reviewer turn is read back and filed
    text, prof, err = build_prompt(root, ns.node_id, role=ns.role, model=ns.model, ref=ns.ref,
                                   context_feedback=ns.context_feedback, read_back=read_back,
                                   force_reason=ns.reason if ns.force else None)
    if err:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
    out = ns.output or root / "work" / f"prompt-{ns.node_id}-{ns.role}-{ns.model}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    if prof is None:
        print(f"note: no profile for {ns.model!r}; the prompt has no model notes (see `specy-road models list`)", file=sys.stderr)
    raise SystemExit(run_cli_channel(prof, out, root, entry.get("preflight"), entry_cli,
                                     harness=entry.get("harness"), role=ns.role, model=ns.model,
                                     reviews=reviews_dir(root, ns.node_id), ref=ns.ref)
                     if ns.channel == "cli" else 0)


if __name__ == "__main__":
    main()
