import type { ActivityEntry } from "./types";

/**
 * Compact relative age for the outline's "Last worked" column.
 *
 * Deliberately coarse: the column is a glanceable staleness signal on a dense
 * table, not a precise clock. The exact timestamp goes in the cell's `title`.
 */
export function formatRelativeAge(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);
  // Clock skew and same-second writes both land here; "now" beats "in -3s".
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 31) return `${days}d ago`;

  // Calendar-aware from here. Dividing days by an average month/year length
  // gets the boundaries wrong in ways people notice: an exact two-year gap
  // spanning one leap day is 730 days, which floor-divides by 365.25 to "1y".
  let months =
    (now.getFullYear() - then.getFullYear()) * 12 +
    (now.getMonth() - then.getMonth());
  if (now.getDate() < then.getDate()) months -= 1;
  if (months < 12) return `${Math.max(1, months)}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

/** Human label for why the timestamp exists, shown in the cell tooltip. */
export function activityKindLabel(kind: ActivityEntry["kind"]): string {
  switch (kind) {
    case "picked_up":
      return "picked up";
    case "reviewed":
      return "implementation reviewed";
    case "finished":
      return "finished";
    case "edited":
      return "edited";
    case "backfilled":
      // Derived from git history rather than observed, so it is a lower bound.
      return "from git history";
    default:
      return kind;
  }
}

export function lastWorkedTooltip(entry: ActivityEntry): string {
  return `${activityKindLabel(entry.kind)} — ${entry.at}`;
}
