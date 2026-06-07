"""Human-readable rendering of a :class:`session_plan.SessionPlan`.

Kept separate from ``session_plan.py`` so both stay under the file-line cap.
The rendered text is oriented toward sub-agent orchestration: a "Dispatch now"
section (wave 0 parallel batch), "Later waves" with their unlock predecessors,
and a "Blocked — do not start yet" section so an orchestrator does not spawn a
sub-agent for work whose dependencies are unmet.
"""

from __future__ import annotations

from session_plan import SessionPlan


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
    lines.extend(_render_blocked(plan))
    lines.extend(_render_misc(plan))
    return "\n".join(lines) + "\n"


def _render_dispatch(plan: SessionPlan) -> list[str]:
    lines: list[str] = ["## Suggested sub-agent batches", ""]
    if plan.parallel_batches:
        first = plan.parallel_batches[0]
        lines.append(
            f"**Dispatch now (parallel):** {_fmt(first)}  "
            f"— {len(first)} independent leaf/leaves, all dependencies satisfied."
        )
    else:
        lines.append(
            "**Dispatch now:** _none ready._ See Blocked / gates below."
        )
    lines.append("")
    # Full dependency layering (includes leaves still blocked today) so an
    # orchestrator can see the whole plan and NOT spawn a later wave early.
    if len(plan.waves) > 1:
        lines.append(
            "**Later waves (do NOT start until every leaf in the prior wave is Complete):**"
        )
        for w in plan.waves[1:]:
            lines.append(f"- wave {w.index}: {_fmt(w.node_ids)}")
        lines.append("")
    if plan.active:
        lines.append(f"_In flight (already claimed / In Progress):_ {_fmt(plan.active)}")
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
    if plan.needs_codename:
        lines.append(
            f"**Needs codename (cannot be auto-claimed):** {_fmt(plan.needs_codename)}"
        )
        lines.append("")
    return lines
