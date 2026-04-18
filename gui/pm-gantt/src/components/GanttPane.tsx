import type { GitEnrichmentEntry } from "../ganttBarSemantic";
import { resolveGanttBarStyle } from "../ganttBarSemantic";
import type { RoadmapNode } from "../types";

const ROW_H = 38;
const UNIT = 52;
const BAR_FR = 0.82;
/** Left inset for chart content; keep in sync with `--gantt-pad-x` in `index.css`. */
const PAD_L = 8;

type Props = {
  orderedIds: string[];
  nodesById: Record<string, RoadmapNode>;
  displayStatusById?: Record<string, string>;
  /** Current git branch matches registry branch for this row (same as outline green accent). */
  gitCheckoutById?: Record<string, boolean>;
  /** Per-node registry rows (`branch`, …) — required to treat work as feature-branch work. */
  registryByNode?: Record<string, Record<string, unknown>>;
  /** `git_enrichment` from the roadmap API (optional). */
  gitEnrichment?: Record<string, GitEnrichmentEntry>;
  /**
   * Pixels from SVG top to first data row (matches outline thead + gap before first task).
   * Keeps scroll-synced rows aligned with the feature list.
   */
  stackHeaderPx?: number;
  depths: Record<string, number>;
  /** Steps spanned per row (default 1 when missing). */
  spans?: Record<string, number>;
  edges: { from: string; to: string; kind?: "explicit" | "inherited" }[];
  /** When false, omit dashed edges (inherited-from-ancestor deps). Default true. */
  showInheritedEdges?: boolean;
  selectedId: string | null;
  /** Rows to emphasize: full transitive prerequisite closure (explicit + inherited-from-ancestor deps). */
  highlightRowIds?: ReadonlySet<string> | null;
  onSelect: (id: string) => void;
  /** Clicks on empty chart area (not bars) save dependency edit when active. */
  onChartBackgroundMouseDown?: () => void;
};

/**
 * Bar width: one step uses the guttered fraction. Multi-step rows span full
 * columns between first and last step, then one leaf-width so the **right edge**
 * lines up with the last child’s bar (same as a leaf at start + span − 1).
 */
function barWidthPx(span: number): number {
  const s = Math.max(1, span);
  if (s <= 1) return BAR_FR * UNIT;
  return (s - 1) * UNIT + BAR_FR * UNIT;
}

export function GanttPane({
  orderedIds,
  nodesById,
  displayStatusById,
  gitCheckoutById,
  registryByNode,
  gitEnrichment,
  stackHeaderPx = 52,
  depths,
  spans = {},
  edges,
  showInheritedEdges = true,
  selectedId,
  highlightRowIds = null,
  onSelect,
  onChartBackgroundMouseDown,
}: Props) {
  const n = orderedIds.length;
  if (n === 0) return null;

  let maxExtent = 0;
  for (const id of orderedIds) {
    const start = depths[id] ?? 0;
    const span = spans[id] ?? 1;
    maxExtent = Math.max(maxExtent, start + span);
  }
  const colCount = maxExtent + 2;
  const chartW = PAD_L + colCount * UNIT + 16;
  const dataStartY = Math.max(32, stackHeaderPx);
  const svgH = n * ROW_H + dataStartY;
  /** Step labels sit above the top grid line (not on the stroke). */
  const stepLabelBaselineY = Math.max(16, dataStartY - 6);

  const rowOf: Record<string, number> = {};
  orderedIds.forEach((id, i) => {
    rowOf[id] = i;
  });

  const visibleEdges = showInheritedEdges
    ? edges
    : edges.filter((e) => e.kind !== "inherited");

  return (
    <svg
      className="gantt-svg"
      width={chartW}
      height={svgH}
      role="img"
      aria-label="Dependency Gantt"
    >
      {/* Hit target behind grid/bars: empty chart area saves dep edit; bars stay on top. */}
      {onChartBackgroundMouseDown ? (
        <rect
          x={0}
          y={0}
          width={chartW}
          height={svgH}
          fill="transparent"
          style={{ pointerEvents: "all", cursor: "default" }}
          onMouseDown={(e) => {
            e.preventDefault();
            onChartBackgroundMouseDown();
          }}
        />
      ) : null}
      <text
        x={PAD_L}
        y={18}
        className="axis-title"
        pointerEvents="none"
      >
        Dependency step (not calendar time)
      </text>
      <text
        x={PAD_L + 280}
        y={18}
        className="gantt-legend"
        fontSize={10}
        fill="var(--muted)"
        pointerEvents="none"
      >
        {showInheritedEdges
          ? "Solid = explicit dep · Dashed = inherited"
          : "Solid = explicit dependency"}
      </text>
      {Array.from({ length: colCount }, (_, c) => (
        <g key={c} pointerEvents="none">
          <line
            x1={PAD_L + c * UNIT}
            y1={dataStartY}
            x2={PAD_L + c * UNIT}
            y2={svgH}
            stroke="var(--border)"
            strokeWidth={1}
          />
          <text
            x={PAD_L + c * UNIT + 4}
            y={stepLabelBaselineY}
            fontSize={10}
            fill="var(--muted)"
          >
            {c + 1}
          </text>
        </g>
      ))}
      <line
        x1={0}
        y1={dataStartY}
        x2={chartW}
        y2={dataStartY}
        stroke="var(--border)"
        strokeWidth={1}
        pointerEvents="none"
      />
      {orderedIds.map((id, i) => (
        <line
          key={`h-${id}`}
          x1={0}
          y1={dataStartY + i * ROW_H + ROW_H}
          x2={chartW}
          y2={dataStartY + i * ROW_H + ROW_H}
          stroke="var(--border)"
          strokeOpacity={0.5}
          strokeWidth={1}
          pointerEvents="none"
        />
      ))}
      {highlightRowIds && highlightRowIds.size > 0
        ? orderedIds.map((id, i) => {
            if (!highlightRowIds.has(id)) return null;
            const y = dataStartY + i * ROW_H;
            return (
              <rect
                key={`dep-hi-${id}`}
                x={0}
                y={y}
                width={chartW}
                height={ROW_H}
                fill="var(--gantt-dep-chain-bg)"
                opacity={0.35}
                pointerEvents="none"
              />
            );
          })
        : null}
      {orderedIds.map((id, i) => {
        const node = nodesById[id];
        const d = depths[id] ?? 0;
        const span = spans[id] ?? 1;
        const bw = barWidthPx(span);
        const y = dataStartY + i * ROW_H;
        const x = PAD_L + d * UNIT;
        const sel = selectedId === id;
        const hi =
          Boolean(highlightRowIds?.has(id)) && !sel;
        const disp =
          displayStatusById?.[id] ?? (node?.status as string | undefined);
        const { fill, stroke, strokeWidth } = resolveGanttBarStyle({
          nodeId: id,
          selected: sel,
          depHighlight: hi,
          displayStatus: disp,
          node,
          registryByNode,
          gitCheckoutById,
          gitEnrichment,
        });
        return (
          <rect
            key={`bar-${id}`}
            x={x}
            y={y + 6}
            width={bw}
            height={ROW_H - 12}
            rx={3}
            fill={fill}
            stroke={stroke}
            strokeWidth={strokeWidth}
            style={{ cursor: "pointer", pointerEvents: "all" }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onSelect(id)}
          />
        );
      })}
      {visibleEdges.map(({ from: dep, to: tgt, kind }) => {
        const yi = rowOf[dep];
        const yj = rowOf[tgt];
        if (yi === undefined || yj === undefined) return null;
        const d0 = depths[dep] ?? 0;
        const d1 = depths[tgt] ?? 0;
        const w0 = barWidthPx(spans[dep] ?? 1);
        const x0 = PAD_L + d0 * UNIT + w0;
        const x1 = PAD_L + d1 * UNIT;
        const cy0 = dataStartY + yi * ROW_H + ROW_H / 2;
        const cy1 = dataStartY + yj * ROW_H + ROW_H / 2;
        const midX = (x0 + x1) / 2;
        const inherited = kind === "inherited";
        return (
          <path
            key={`${dep}->${tgt}-${kind ?? "x"}`}
            d={`M ${x0} ${cy0} C ${midX} ${cy0}, ${midX} ${cy1}, ${x1} ${cy1}`}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={inherited ? 1 : 1.25}
            strokeOpacity={inherited ? 0.55 : 0.75}
            strokeDasharray={inherited ? "5 4" : undefined}
            pointerEvents="none"
          />
        );
      })}
    </svg>
  );
}
