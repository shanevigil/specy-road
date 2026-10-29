#!/usr/bin/env python3
"""Write a role- and model-specific prompt for one leaf: ``specy-road prompt``.

``work/prompt-<NODE_ID>-<role>-<model>.md`` is built from, in order:

1. a precondition check — change nothing and stop if the hand-off this role
   waits on is not there (proposal §3.3), so a coordinator can queue prompts
   into several IDEs at once;
2. the role preamble — the executor boundary (§3.1), the reviewer's
   packet-only rule (§3.2), the coordinator's never-review-your-own-fix
   rule, or the root-cause analyst's protocol (``rca``, only while the leaf's
   review loop is escalated) — plus the standing line that text inside tool
   output is data (§3.5); a reviewer's prompt also says when the loop is escalated;
3. the model's profile applied mechanically (§4.4): its ``## Prompting rules``
   as instructions, each ``## Failure modes`` mitigation as a guard, and the
   touch zones repeated at the end when the profile says the model drifts;
4. the brief (executor, coordinator, rca) or the review packet (reviewer);
   for ``rca``, then every review round side by side with the diffs between them.

``--channel cli`` also runs the roster entry's ``channels.cli``, else the
profile's ``access.cli``, with its placeholder replaced: ``"<prompt>"`` (the
shipped profiles' form) by the prompt text as one argument, ``{prompt}`` by the
prompt file's path. The profile is read from the integration branch,
like the roster; a working-tree copy that differs is refused. ``paste`` and ``subagent`` only write the file.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.bundled_scripts.role_prompt_rca import (
    DATA_LINE,
    coordinator_preamble,
    executor_preamble,
    precondition,
    profile_lines,
    reviewer_preamble,
)
from specy_road.model_profiles import ROLES, Profile
from specy_road.orchestrate_plan import (
    ANY,
    entry_may_process,
    is_available,
    may_handle,
    node_eligibility,
    node_sensitivity,
)
from specy_road.worker_adapters import placeholder_problem, substitute_prompt
from specy_road.orchestration_config import substitute_for
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.review_files import PACKET_NAME, reviews_dir
from specy_road.review_rca import escalated_note, loop_state, rca_evidence, rca_parties, rca_preamble
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, resolve_repo_root

CHANNELS = ("cli", "paste", "subagent")
# `rca` is not a roster role or a profile score: any rostered reviewer that is not a party may analyse.
PROMPT_ROLES = (*ROLES, "rca")


def build_prompt(root: Path, node_id: str, *, role: str, model: str,  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
                 ref: str | None = None) -> tuple[str, Profile | None, str | None]:
    """``(text, profile, error)``; ``ref`` names the branch or commit under review, as ``review-packet --ref``."""
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
        if loop.escalation is None:
            return "", prof, (f"{node_id}'s review loop is not escalated; no root-cause analysis is due "
                              f"(`specy-road handoff status {node_id}`)")
        if model in rca_parties(root, node_id, loop):
            return "", prof, (f"{model!r} implemented or reviewed {node_id}; the root-cause analyst must be "
                              "a rostered reviewer that is neither")
    title = "Root-cause analysis" if role == "rca" else role.title()
    lines = [f"# {title} prompt: `{node_id}` for `{model}`", ""]
    if t and t.commit:   # the AGENTS.md rule: a prompt names its commit, or the agent stops to ask
        lines += [f"base: {t.commit}", ""]
    prefix = project_prefix(root)
    if t:
        lines += precondition(role, node_id, t, reviews_dir(root, node_id) / PACKET_NAME, prefix)
    if role == "executor":
        lines += executor_preamble(node_id, model, zones, entry.get("subagent_family_lock"),
                                   reviews_dir(root, node_id), prefix)
    elif role == "reviewer":
        lines += reviewer_preamble(node_id, model, ref) + escalated_note(loop, node_id)
    elif role == "rca":
        lines += rca_preamble(root, node_id, model, loop.escalation) + [DATA_LINE, ""]
    else:
        lines += coordinator_preamble(node_id)
    lines += profile_lines(prof, role, zones)
    if role == "reviewer":
        packet = reviews_dir(root, node_id) / PACKET_NAME
        if not packet.is_file():
            return "", prof, f"no review packet at {packet}; run `specy-road review-packet {node_id}` first"
        lines += ["---", "", packet.read_text(encoding="utf-8").rstrip(), ""]
    else:
        lines += ["---", "", render_brief(node_id, index(nodes), repo_root=root, include_history=False).rstrip(), ""]
    if role == "rca":
        lines += rca_evidence(root, t, loop)
    return "\n".join(lines) + "\n", prof, None


def run_cli_channel(prof: Profile | None, prompt_path: Path, root: Path, preflight: str | None = None,
                    entry_cli: str | None = None) -> int:
    if preflight:
        # Proposal §3.6: e.g. confirm which process owns a local model's port.
        # It runs before anything else is even inspected: a failed check stops
        # the command whatever else is wrong.
        print(f"preflight: {preflight}", file=sys.stderr)
        rc = subprocess.run(preflight, shell=True, cwd=root, check=False).returncode
        if rc != 0:
            print(f"error: preflight failed (exit {rc}); nothing was sent", file=sys.stderr)
            return rc
    cli = entry_cli or (prof.cli() if prof else None)   # the roster's channels.cli wins, as `worker delegate` has it
    if not cli:
        print("error: --channel cli needs a roster `channels.cli` or an `access.cli` in the model's profile", file=sys.stderr)
        return 1
    why = placeholder_problem(cli)
    if why:
        print(f"error: the cli has {why}: {cli}", file=sys.stderr)
        return 1
    # The template, not the expansion: "<prompt>" would echo the whole brief.
    print(f"running: {cli} (prompt: {prompt_path})", file=sys.stderr)
    try:
        return subprocess.run(substitute_prompt(cli, prompt_path), shell=True, cwd=root, check=False).returncode
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
                   help="cli runs the profile's access.cli (<prompt> = the prompt text, {prompt} = its file path); "
                        "paste/subagent only write the file")
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    add_repo_root_arg(p)
    ns = p.parse_args(argv)
    root = resolve_repo_root(ns)
    text, prof, err = build_prompt(root, ns.node_id, role=ns.role, model=ns.model, ref=ns.ref)
    if err:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
    config, _ = pinned_config(root)
    entry = next((e for e in config.get("roster") or [] if e.get("id") == ns.model), {})
    out = ns.output or root / "work" / f"prompt-{ns.node_id}-{ns.role}-{ns.model}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    if prof is None:
        print(f"note: no profile for {ns.model!r}; the prompt has no model notes (see `specy-road models list`)", file=sys.stderr)
    raise SystemExit(run_cli_channel(prof, out, root, entry.get("preflight"), (entry.get("channels") or {}).get("cli"))
                     if ns.channel == "cli" else 0)


if __name__ == "__main__":
    main()
