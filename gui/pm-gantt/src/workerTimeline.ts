/**
 * Phase-bar math and event helpers for the Workers drawer (M10.12).
 *
 * Phase durations come from `GET /api/workers/{id}/events` (`phases`, the
 * same numbers as `specy-road worker timeline`): seconds per phase of the
 * latest turn, `null` when a boundary event is missing.
 */

export type WorkerPhases = Record<string, number | null>;

export type PhaseSegment = {
  name: string;
  label: string;
  seconds: number | null;
  /** Share of the known phases' total, 0–100; 0 for an unknown phase. */
  pct: number;
};

/** `delegated_to_launched` → `delegated → launched`. */
export function phaseLabel(name: string): string {
  return name.replace("_to_", " → ").replace(/_/g, " ");
}

/** One segment per phase, in the server's order; unknown phases take no width. */
export function phaseSegments(phases: WorkerPhases): PhaseSegment[] {
  const entries = Object.entries(phases);
  const total = entries.reduce((sum, [, s]) => sum + (s != null && s > 0 ? s : 0), 0);
  return entries.map(([name, s]) => ({
    name,
    label: phaseLabel(name),
    seconds: s,
    pct: total > 0 && s != null && s > 0 ? (s / total) * 100 : 0,
  }));
}

/** `42s`, `3m 05s`, `1h 02m`; `unknown` for a missing phase. */
export function formatSeconds(s: number | null): string {
  if (s == null) return "unknown";
  const n = Math.max(0, Math.round(s));
  if (n < 60) return `${n}s`;
  const pad = (x: number) => String(x).padStart(2, "0");
  if (n < 3600) return `${Math.floor(n / 60)}m ${pad(n % 60)}s`;
  return `${Math.floor(n / 3600)}h ${pad(Math.floor((n % 3600) / 60))}m`;
}

/** `$0.1234` (`est.` for a client-side estimate); `$?` when no usage event reported a cost. */
export function formatCost(cost: number | null, estimate?: boolean | null): string {
  if (cost == null) return "$?";
  return `$${cost.toFixed(4)}${estimate ? " est." : ""}`;
}

export type WorkerEventLike = { type: string; source: string; summary: string };

/** Codex's `item.completed` types that are tool calls (its `agent_message` and `reasoning` are not). */
const CODEX_TOOL_ITEMS = /^(command_execution|file_change|mcp_tool_call|web_search) done$/;

/**
 * An `output` line the adapters wrote for a tool call: Claude's
 * `(tool use)`, Cursor's `tool call …`, Codex's `<tool item> done`.
 */
export function isToolCall(e: WorkerEventLike): boolean {
  if (e.type !== "output" || e.source !== "worker") return false;
  return (
    e.summary === "(tool use)" ||
    /^tool call\b/.test(e.summary) ||
    CODEX_TOOL_ITEMS.test(e.summary)
  );
}
