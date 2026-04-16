/**
 * Contiguous preorder subtree in a flat outline: ids from `rootId` through the
 * last descendant before the next sibling (or uncle) at the same depth.
 */
export function contiguousSubtreeIds(
  orderedIds: string[],
  rowDepths: number[],
  rootId: string,
): string[] {
  const start = orderedIds.indexOf(rootId);
  if (start < 0) return [];
  const baseDepth = rowDepths[start] ?? 0;
  const out: string[] = [orderedIds[start]!];
  for (let j = start + 1; j < orderedIds.length; j++) {
    const d = rowDepths[j] ?? 0;
    if (d <= baseDepth) break;
    out.push(orderedIds[j]!);
  }
  return out;
}
