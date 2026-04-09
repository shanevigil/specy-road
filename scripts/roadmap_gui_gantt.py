"""Dependency-step Gantt view for roadmap_gui (not calendar-based)."""

from __future__ import annotations

import sys
from pathlib import Path

_GANTT_DIR = Path(__file__).resolve().parent
if str(_GANTT_DIR) not in sys.path:
    sys.path.insert(0, str(_GANTT_DIR))

import plotly.graph_objects as go  # noqa: E402
from plotly.graph_objects import Figure  # noqa: E402

# Row height (px) — outline labels, bars, and hit targets share this pitch.
ROW_PX = 38

STATUS_COLORS = {
    "not started": "#b0b0b0",
    "in progress": "#1976d2",
    "blocked": "#d32f2f",
    "complete": "#424242",
    "cancelled": "#757575",
}

HIGHLIGHT_BAR = "#e53935"


def compute_depths(nodes: list[dict]) -> dict[str, int]:
    by_id = {n["id"]: n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        deps = by_id[nid].get("dependencies") or []
        if not deps:
            memo[nid] = 0
            return 0
        d = 1 + max(depth(x) for x in deps)
        memo[nid] = d
        return d

    for n in nodes:
        depth(n["id"])
    return memo


def ordered_tree_rows(nodes: list[dict]) -> list[tuple[dict, int]]:
    """
    Parent/child order: roots first (by id), then DFS children.
    Returns (node, depth) with depth 0 for roots. Orphans attach at end.
    """
    by_id = {n["id"]: n for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in by_id:
            pid = None
        children.setdefault(pid, []).append(n["id"])
    for lst in children.values():
        lst.sort()
    out: list[tuple[dict, int]] = []

    def dfs(nid: str, depth: int) -> None:
        node = by_id[nid]
        out.append((node, depth))
        for cid in children.get(nid, []):
            dfs(cid, depth + 1)

    for rid in children.get(None, []):
        dfs(rid, 0)
    placed = {t[0]["id"] for t in out}
    for n in sorted(nodes, key=lambda x: x["id"]):
        if n["id"] not in placed:
            out.append((n, 0))
    return out


def dependency_edges(nodes: list[dict]) -> list[tuple[str, str]]:
    """Edges (dependency_id, dependent_id) for graph overlays."""
    ids = {n["id"] for n in nodes}
    edges: list[tuple[str, str]] = []
    for n in nodes:
        for dep in n.get("dependencies") or []:
            if dep in ids:
                edges.append((dep, n["id"]))
    return edges


def node_color(node: dict) -> str:
    s = (node.get("status") or "Not Started").strip().lower()
    return STATUS_COLORS.get(s, "#9e9e9e")


def _outline_ticktext(ordered: list[dict], row_depths: list[int]) -> list[str]:
    out: list[str] = []
    for node, depth in zip(ordered, row_depths, strict=True):
        indent = "\u00a0" * (depth * 3)
        t = str(node.get("title", ""))[:44]
        out.append(f"{indent}{node['id']} — {t}")
    return out


def _gantt_hover_customdata(
    ordered: list[dict],
    pr_hints: dict[str, str],
) -> tuple[list[str], list[list[str]]]:
    hover: list[str] = []
    customdata: list[list[str]] = []
    for node in ordered:
        nid = node["id"]
        bits = [nid, str(node.get("title", ""))]
        if pr_hints.get(nid):
            bits.append(pr_hints[nid])
        hover.append("<br>".join(bits))
        customdata.append([nid])
    return hover, customdata


def _gantt_arrows(
    fig: Figure,
    row_of: dict[str, int],
    dep_depths: dict[str, int],
    edges: list[tuple[str, str]],
    bar_w: float,
    arrow_color: str,
) -> None:
    for dep, tgt in edges:
        if dep not in row_of or tgt not in row_of:
            continue
        y0, y1 = row_of[dep], row_of[tgt]
        x0 = dep_depths[dep] + bar_w
        x1 = dep_depths[tgt]
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=0.85,
            arrowwidth=1,
            arrowcolor=arrow_color,
        )


def _gantt_apply_layout(
    fig: Figure,
    n: int,
    template: str,
    x_range: tuple[float, float],
) -> None:
    fig.update_layout(
        template=template,
        barmode="overlay",
        bargap=0,
        bargroupgap=0,
        showlegend=False,
        title=dict(
            text="Roadmap (outline left, dependency step right — not calendar dates)",
            font=dict(size=14),
        ),
        xaxis_title="Later steps depend on earlier (to the left)",
        xaxis=dict(showgrid=True, range=list(x_range)),
        yaxis=dict(
            showticklabels=False,
            showgrid=True,
            autorange="reversed",
            side="left",
            automargin=True,
        ),
        margin=dict(l=12, r=28, t=52, b=48),
        autosize=True,
        height=max(400, n * ROW_PX + 100),
    )


def _bar_fill_colors(
    ordered: list[dict],
    highlight_nid: str | None,
) -> list[str]:
    out: list[str] = []
    for n in ordered:
        if highlight_nid and n["id"] == highlight_nid:
            out.append(HIGHLIGHT_BAR)
        else:
            out.append(node_color(n))
    return out


def _add_dependency_bars(
    fig: Figure,
    widths: list[float],
    bases: list[float],
    y_idx: list[int],
    colors: list[str],
    hover: list[str],
    customdata: list[list[str]],
) -> None:
    fig.add_trace(
        go.Bar(
            orientation="h",
            x=widths,
            y=y_idx,
            base=bases,
            marker_color=colors,
            marker_line=dict(width=1, color="rgba(0,0,0,0.22)"),
            hovertext=hover,
            hoverinfo="text",
            customdata=customdata,
            width=1.0,
        ),
    )


def _add_clickable_row_labels(
    fig: Figure,
    ordered: list[dict],
    row_depths: list[int],
    hover: list[str],
    customdata: list[list[str]],
    *,
    highlight_nid: str | None,
    label_color: str,
    label_highlight: str,
    label_x: float,
) -> None:
    ticktext = _outline_ticktext(ordered, row_depths)
    n = len(ordered)
    text_colors = [
        label_highlight
        if (highlight_nid and ordered[i]["id"] == highlight_nid)
        else label_color
        for i in range(n)
    ]
    marker_rgba = [
        "rgba(229, 57, 53, 0.42)"
        if (highlight_nid and ordered[i]["id"] == highlight_nid)
        else "rgba(120, 120, 120, 0.22)"
        for i in range(n)
    ]
    y_idx = list(range(n))
    fig.add_trace(
        go.Scatter(
            x=[label_x] * n,
            y=y_idx,
            mode="markers+text",
            text=ticktext,
            textposition="middle left",
            textfont=dict(size=11, color=text_colors),
            marker=dict(size=28, color=marker_rgba, line=dict(width=0)),
            hovertext=hover,
            hoverinfo="text",
            customdata=customdata,
            showlegend=False,
            cliponaxis=False,
        ),
    )


def build_gantt_figure(
    ordered: list[dict],
    row_depths: list[int],
    dep_depths: dict[str, int],
    edges: list[tuple[str, str]],
    pr_hints: dict[str, str],
    *,
    template: str,
    arrow_color: str,
    highlight_nid: str | None,
    label_color: str,
    label_highlight: str,
) -> Figure:
    """Bars use dependency depth on x; y rows follow ``ordered``."""
    n = len(ordered)
    if n == 0:
        fig = go.Figure()
        fig.update_layout(template=template)
        return fig
    if len(row_depths) != n:
        raise ValueError("row_depths must match ordered")
    row_of = {ordered[i]["id"]: i for i in range(n)}
    bar_w = 0.82
    bases = [float(dep_depths[ordered[i]["id"]]) for i in range(n)]
    widths = [bar_w] * n
    y_idx = list(range(n))
    colors = _bar_fill_colors(ordered, highlight_nid)
    hover, customdata = _gantt_hover_customdata(ordered, pr_hints)

    label_x = -1.65
    fig = go.Figure()
    _add_dependency_bars(fig, widths, bases, y_idx, colors, hover, customdata)
    _add_clickable_row_labels(
        fig,
        ordered,
        row_depths,
        hover,
        customdata,
        highlight_nid=highlight_nid,
        label_color=label_color,
        label_highlight=label_highlight,
        label_x=label_x,
    )
    _gantt_arrows(fig, row_of, dep_depths, edges, bar_w, arrow_color)

    max_x = max(b + bar_w for b in bases) + 0.45
    x_min = label_x - 0.55
    _gantt_apply_layout(fig, n, template, (x_min, max_x))
    return fig
