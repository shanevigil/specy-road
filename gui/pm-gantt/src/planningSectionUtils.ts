import type { DiffSideRow } from "./planningDiffUtils";

/** One slice of markdown split on level-2 headings at line start (`## `). */
export type H2Section = {
  /** Exact slice including newlines, including the `##` line when present. */
  raw: string;
};

/**
 * Split markdown on lines matching `/^## /` (first block may be preamble with no `##`).
 */
export function splitByH2(md: string): H2Section[] {
  const normalized = md.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  const chunks: string[][] = [];
  let buf: string[] = [];

  function flush() {
    chunks.push([...buf]);
    buf = [];
  }

  for (const line of lines) {
    if (/^## /.test(line)) {
      flush();
      buf.push(line);
    } else {
      buf.push(line);
    }
  }
  flush();

  if (chunks.length === 0) {
    return [{ raw: "" }];
  }
  return chunks.map((ch) => ({ raw: ch.join("\n") }));
}

/**
 * Build merged markdown from per-section choices. Uses the first `choices.length`
 * sections from each document (paired by index).
 */
export function mergeBySectionChoices(
  originalMarkdown: string,
  proposedMarkdown: string,
  choices: Array<"before" | "proposed">,
): string {
  const o = splitByH2(originalMarkdown);
  const p = splitByH2(proposedMarkdown);
  const n = Math.min(o.length, p.length, choices.length);
  const parts: string[] = [];
  for (let i = 0; i < n; i++) {
    parts.push(choices[i] === "before" ? o[i].raw : p[i].raw);
  }
  return parts.join("\n\n");
}

/**
 * For each side-by-side diff row, the H2-aligned section index (0 = preamble before first `##`).
 * Matches {@link splitByH2} segment boundaries: a row containing a line starting with `## `
 * starts section index ≥ 1.
 */
export function assignDiffRowSectionIndices(rows: DiffSideRow[]): number[] {
  let seg = 0;
  const out: number[] = [];
  for (const row of rows) {
    const L = row.left?.text ?? "";
    const R = row.right?.text ?? "";
    if (/^## /.test(L) || /^## /.test(R)) {
      seg += 1;
    }
    out.push(seg);
  }
  return out;
}

export function groupContiguousSectionRanges(
  rowSectionIndices: number[],
): { sectionIndex: number; start: number; end: number }[] {
  const groups: { sectionIndex: number; start: number; end: number }[] = [];
  const n = rowSectionIndices.length;
  if (n === 0) return groups;
  let start = 0;
  let current = rowSectionIndices[0]!;
  for (let r = 1; r < n; r++) {
    const idx = rowSectionIndices[r]!;
    if (idx !== current) {
      groups.push({ sectionIndex: current, start, end: r });
      start = r;
      current = idx;
    }
  }
  groups.push({ sectionIndex: current, start, end: n });
  return groups;
}
