/**
 * Minimum 0-based dependency step among visible rows. Used to crop leading
 * empty Gantt columns when "Hide Complete" leaves only high step-index rows.
 */
export function minDependencyDepth(
  visibleIds: string[],
  depths: Record<string, number>,
): number {
  if (visibleIds.length === 0) return 0;
  let min = Infinity;
  for (const id of visibleIds) {
    const d = depths[id] ?? 0;
    if (d < min) min = d;
  }
  return min === Infinity ? 0 : min;
}
