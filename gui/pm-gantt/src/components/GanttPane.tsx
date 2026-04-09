import type { RoadmapNode } from "../types";

const ROW_H = 38;
const UNIT = 52;
const BAR_FR = 0.82;
/** Left inset for chart content; keep in sync with `--gantt-pad-x` in `index.css`. */
const PAD_L = 8;

function statusColor(status: string | undefined): string {
  const s = (status || "Not Started").toLowerCase();
  if (s === "not started") return "var(--bar-not-started)";
  if (s === "in progress") return "var(--bar-progress)";
  if (s === "blocked") return "var(--bar-blocked)";
  if (s === "complete") return "var(--bar-complete)";
  if (s === "cancelled") return "var(--bar-cancelled)";
  return "#9e9e9e";
}

type Props = {
  orderedIds: string[];
  nodesById: Record<string, RoadmapNode>;
  depths: Record<string, number>;
  edges: { from: string; to: string; kind?: "explicit" | "inherited" }[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Clicks on empty chart area (not bars) save dependency edit when active. */
  onChartBackgroundMouseDown?: () => void;
};

export function GanttPane({
  orderedIds,
  nodesById,
  depths,
  edges,
  selectedId,
  onSelect,
  onChartBackgroundMouseDown,
}: Props) {
  const n = orderedIds.length;
  if (n === 0) return null;

  let maxD = 0;
  for (const id of orderedIds) {
    const d = depths[id] ?? 0;
    if (d > maxD) maxD = d;
  }
  const colCount = maxD + 3;
  const chartW = PAD_L + colCount * UNIT + 16;
  const svgH = n * ROW_H + 36;

  const rowOf: Record<string, number> = {};
  orderedIds.forEach((id, i) => {
    rowOf[id] = i;
  });

  const barW = BAR_FR * UNIT;

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
        Solid = explicit dep · Dashed = inherited
      </text>
      {Array.from({ length: colCount }, (_, c) => (
        <g key={c} pointerEvents="none">
          <line
            x1={PAD_L + c * UNIT}
            y1={28}
            x2={PAD_L + c * UNIT}
            y2={svgH}
            stroke="var(--border)"
            strokeWidth={1}
          />
          <text
            x={PAD_L + c * UNIT + 4}
            y={32}
            fontSize={10}
            fill="var(--muted)"
          >
            {c + 1}
          </text>
        </g>
      ))}
      <line
        x1={0}
        y1={28}
        x2={chartW}
        y2={28}
        stroke="var(--border)"
        strokeWidth={1}
        pointerEvents="none"
      />
      {orderedIds.map((id, i) => (
        <line
          key={`h-${id}`}
          x1={0}
          y1={36 + i * ROW_H + ROW_H}
          x2={chartW}
          y2={36 + i * ROW_H + ROW_H}
          stroke="var(--border)"
          strokeOpacity={0.5}
          strokeWidth={1}
          pointerEvents="none"
        />
      ))}
      {orderedIds.map((id, i) => {
        const node = nodesById[id];
        const d = depths[id] ?? 0;
        const y = 36 + i * ROW_H;
        const x = PAD_L + d * UNIT;
        const sel = selectedId === id;
        return (
          <rect
            key={`bar-${id}`}
            x={x}
            y={y + 6}
            width={barW}
            height={ROW_H - 12}
            rx={3}
            fill={sel ? "var(--accent)" : statusColor(node?.status)}
            stroke="rgba(0,0,0,0.15)"
            strokeWidth={1}
            style={{ cursor: "pointer", pointerEvents: "all" }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onSelect(id)}
          />
        );
      })}
      {edges.map(({ from: dep, to: tgt, kind }) => {
        const yi = rowOf[dep];
        const yj = rowOf[tgt];
        if (yi === undefined || yj === undefined) return null;
        const d0 = depths[dep] ?? 0;
        const d1 = depths[tgt] ?? 0;
        const x0 = PAD_L + d0 * UNIT + barW;
        const x1 = PAD_L + d1 * UNIT;
        const cy0 = 36 + yi * ROW_H + ROW_H / 2;
        const cy1 = 36 + yj * ROW_H + ROW_H / 2;
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
