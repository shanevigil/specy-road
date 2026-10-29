"""Human-readable rendering (and the JSON view) of a :class:`session_plan.SessionPlan`.

Kept separate from ``session_plan.py`` so both stay under the file-line cap.
The rendered text is oriented toward sub-agent orchestration: a "Dispatch now"
section (wave 0 parallel batch), "Later waves" with their unlock predecessors,
and a "Blocked — do not start yet" section so an orchestrator does not spawn a
sub-agent for work whose dependencies are unmet.

It also holds the touch-zone overlap rule, which ``session_plan._parallel_batches``
applies and the rendering names, so both read the same comparison.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only: session_plan re-exports session_plan_to_dict from here
    from specy_road.bundled_scripts.session_plan import SessionPlan


def _norm_zone(zone: str) -> str:
    return zone.strip().removeprefix("./").rstrip("/")


def zone_clash(
    nid: str, others: list[str], zones: dict[str, list[str]]
) -> tuple[str, str, str] | None:
    """First leaf in ``others`` sharing a touch zone with ``nid``, as
    ``(other, nid's zone, other's zone)``: the same path, or one a directory
    prefix of the other (the rule the registry overlap warning uses)."""
    for other in others:
        for mine in zones.get(nid, []):
            for theirs in zones.get(other, []):
                a, b = _norm_zone(mine), _norm_zone(theirs)
                if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                    return other, mine, theirs
    return None


def split_on_zone_overlap(
    batch: list[str], zones: dict[str, list[str]]
) -> list[list[str]]:
    """Split one wave's dispatchable leaves so no two in a set share a touch zone.

    In pickup order, a leaf that overlaps one already in the set moves to the
    next set, which is split the same way: two leaves editing one file in
    parallel collide when the second lands.
    """
    out: list[list[str]] = []
    while batch:
        layer: list[str] = []
        for nid in batch:
            if not zone_clash(nid, layer, zones):
                layer.append(nid)
        out.append(layer)
        batch = [nid for nid in batch if nid not in layer]
    return out


def zone_overlaps(plan: SessionPlan) -> list[dict]:
    """Each leaf a touch-zone overlap held out of the set before it, and why.

    Derived from ``parallel_batches`` rather than stored, because
    ``session_plan_git`` recomputes the batches after dropping leaves finished
    on a branch; a stored list would name leaves no longer in the plan.
    """
    zones = {nid: z for w in plan.waves for nid, z in w.touch_zones.items()}
    batches = plan.parallel_batches
    out: list[dict] = []
    for prev, batch in zip(batches, batches[1:]):
        for nid in batch:
            clash = zone_clash(nid, prev, zones)
            if clash:
                other, mine, theirs = clash
                out.append({"node_id": nid, "waits_for": other, "zones": [mine, theirs]})
    return out


def _fmt(ids) -> str:
    vals = list(ids)
    return ", ".join(vals) if vals else "—"


def render_session_plan_text(plan: SessionPlan) -> str:
    lines: list[str] = []
    scope = f" (under {plan.under})" if plan.under else ""
    lines.append(f"# grind-session plan{scope}")
    lines.append("")
    t = plan.totals
    lines.append(
        "Totals: "
        f"ready={t.get('ready', 0)} blocked={t.get('blocked', 0)} "
        f"active={t.get('active', 0)} closed={t.get('closed', 0)} "
        f"gated={t.get('gated', 0)} gates_open={t.get('gates_open', 0)} "
        f"waves={t.get('waves', 0)}"
    )
    lines.append("")

    lines.extend(_render_dispatch(plan))
    lines.extend(_render_finished_on_branch(plan))
    lines.extend(_render_blocked(plan))
    lines.extend(_render_misc(plan))
    return "\n".join(lines) + "\n"


def _render_dispatch(plan: SessionPlan) -> list[str]:
    lines: list[str] = ["## Suggested sub-agent batches", ""]
    if plan.parallel_batches:
        first = plan.parallel_batches[0]
        lines.append(
            f"**Dispatch now (parallel, in pickup order):** {_fmt(first)}  "
            f"— {len(first)} independent leaf/leaves, all dependencies satisfied, "
            "listed in the order the loop will claim them."
        )
    else:
        lines.append(
            "**Dispatch now:** _none ready._ See Blocked / gates below."
        )
    lines.append("")
    lines.extend(_render_zone_overlaps(plan))
    lines.extend(_render_next_pick(plan))
    # Full dependency layering (includes leaves still blocked today) so an
    # orchestrator can see the whole plan and NOT spawn a later wave early.
    if len(plan.waves) > 1:
        lines.append(
            "**Later waves (a leaf starts once its own dependencies are Complete; wave = dependency depth):**"
        )
        for w in plan.waves[1:]:
            lines.append(f"- wave {w.index}: {_fmt(w.node_ids)}")
        lines.append("")
    if plan.active:
        lines.append(f"_In flight (already claimed / In Progress):_ {_fmt(plan.active)}")
        lines.append("")
    return lines


def _render_zone_overlaps(plan: SessionPlan) -> list[str]:
    held = zone_overlaps(plan)
    if not held:
        return []
    lines = [
        "**Held for the next batch (shares a touch zone with a leaf in the "
        "batch before it; dispatch once that leaf lands):**"
    ]
    lines.extend(
        f"- `{h['node_id']}` waits for `{h['waits_for']}`: "
        f"`{h['zones'][0]}` overlaps `{h['zones'][1]}`"
        for h in held
    )
    lines.append("")
    return lines


def _render_next_pick(plan: SessionPlan) -> list[str]:
    """Name the leaf pickup would claim, with its execution milestone, and say
    that this plan is a snapshot.

    ``ready`` is the pickup queue itself, so its head is the answer to "what
    happens if I just run the loop". Printing it stops the plan from being read
    as a *recommendation* that pickup then contradicts: the two disagree only
    when state moved between the two commands, most often because a leaf listed
    in flight here had its claim released before pickup ran.
    """
    if not plan.ready:
        return []
    scope = f" --under {plan.under}" if plan.under else ""
    nxt = plan.ready[0]
    execution = plan.ready_execution.get(nxt) or "no execution milestone"
    order = (
        " Ready leaves are ordered Agentic-led first (prefer_agentic_pick_order)."
        if plan.prefer_agentic
        else ""
    )
    return [
        f"**Next auto-pick:** `{nxt}` ({execution}) — what "
        f"`specy-road do-next-available-task{scope}` claims if you run it now.{order}",
        "",
        "_This plan reads feature-branch tips locally so ``ready`` and "
        "``Next auto-pick`` match what pickup skips after sync. Pickup still "
        "fetches the integration branch first, so a leaf listed in flight "
        "below can become the next pick once its claim is released._",
        "",
    ]


def _render_finished_on_branch(plan: SessionPlan) -> list[str]:
    """Leaves Complete on an unmerged feature branch — same rule pickup uses."""
    if not plan.finished_unmerged and not plan.finished_claimed:
        return []
    lines: list[str] = ["## Finished on branch (pickup skips)", ""]
    if plan.finished_unmerged:
        lines.append(
            f"**Unclaimed, Complete on `feature/rm-*`:** {_fmt(plan.finished_unmerged)}  "
            "— omitted from Dispatch now / Next auto-pick. Land the branch to "
            "close the node on the integration branch, or delete it to redo."
        )
        lines.append("")
    if plan.finished_claimed:
        lines.append(
            f"**Still claimed, Complete on branch:** {_fmt(plan.finished_claimed)}  "
            "— finish already ran on the feature branch; open or merge the PR to "
            "close the node on the integration branch. Do not re-run "
            "`finish-this-task` (the registry row here was released on finish). "
            "Do not abort-task-pickup (that deletes the branch)."
        )
        lines.append("")
    return lines


def _render_blocked(plan: SessionPlan) -> list[str]:
    lines: list[str] = ["## Blocked — do not start yet", ""]
    if not plan.blocked:
        lines.append("_None._")
        lines.append("")
        return lines
    for b in plan.blocked:
        tag = "GATE" if b.reason == "gate" else "deps"
        lines.append(
            f"- `{b.node_id}` ({b.codename or 'no codename'}) "
            f"[{tag}] waiting on: {_fmt(b.waiting_on)}"
        )
    lines.append("")
    if plan.gates_open:
        lines.append(
            f"**Gates needing human action:** {_fmt(plan.gates_open)} "
            "(clear via the PM gate workflow; never auto-picked)."
        )
        lines.append("")
    return lines


def _render_misc(plan: SessionPlan) -> list[str]:
    lines: list[str] = []
    if plan.unauthored:
        lines.append(
            "**Not ready — placeholder planning sheet, no acceptance "
            "(pickup skips these; --allow-unauthored picks them):**"
        )
        lines.extend(f"- `{u.node_id}`: {u.reason}" for u in plan.unauthored)
        lines.append("")
    if plan.needs_codename:
        lines.append(
            f"**Needs codename (cannot be auto-claimed):** {_fmt(plan.needs_codename)}"
        )
        lines.append("")
    return lines


def session_plan_to_dict(plan: SessionPlan) -> dict:
    """JSON-serializable view of a :class:`SessionPlan`."""
    return {
        "under": plan.under,
        "ready": list(plan.ready),
        "blocked": [asdict(b) for b in plan.blocked],
        "active": list(plan.active),
        "closed": list(plan.closed),
        "gated": list(plan.gated),
        "gates_open": list(plan.gates_open),
        "needs_codename": list(plan.needs_codename),
        "waves": [{"index": w.index, "node_ids": list(w.node_ids)} for w in plan.waves],
        "parallel_batches": [list(b) for b in plan.parallel_batches],
        "zone_overlaps": zone_overlaps(plan),
        "finished_unmerged": list(plan.finished_unmerged),
        "finished_claimed": list(plan.finished_claimed),
        "unauthored": [asdict(u) for u in plan.unauthored],
        "totals": dict(plan.totals),
        "ready_execution": {i: plan.ready_execution.get(i) for i in plan.ready},
        "prefer_agentic": plan.prefer_agentic,
    }
