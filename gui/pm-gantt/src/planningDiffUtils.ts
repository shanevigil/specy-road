import { diffLines } from "diff";

export type DiffSideRow = {
  left?: { text: string; kind: "ctx" | "del" };
  right?: { text: string; kind: "ctx" | "add" };
};

function chompToLines(s: string): string[] {
  if (!s) return [];
  const lines = s.split("\n");
  if (lines.length && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines;
}

/** Line-aligned side-by-side rows for git-like display (original vs revised). */
export function buildPlanningSideBySideRows(
  original: string,
  revised: string,
): DiffSideRow[] {
  const a = original.endsWith("\n") ? original : `${original}\n`;
  const b = revised.endsWith("\n") ? revised : `${revised}\n`;
  const parts = diffLines(a, b);
  const rows: DiffSideRow[] = [];
  let i = 0;
  while (i < parts.length) {
    const p = parts[i];
    if (!p.added && !p.removed) {
      for (const line of chompToLines(p.value)) {
        rows.push({
          left: { text: line, kind: "ctx" },
          right: { text: line, kind: "ctx" },
        });
      }
      i += 1;
      continue;
    }
    if (p.removed) {
      const rem = chompToLines(p.value);
      const next = parts[i + 1];
      if (next?.added) {
        const add = chompToLines(next.value);
        const n = Math.max(rem.length, add.length);
        for (let k = 0; k < n; k++) {
          const row: DiffSideRow = {};
          if (k < rem.length) {
            row.left = { text: rem[k], kind: "del" };
          }
          if (k < add.length) {
            row.right = { text: add[k], kind: "add" };
          }
          rows.push(row);
        }
        i += 2;
      } else {
        for (const line of rem) {
          rows.push({ left: { text: line, kind: "del" } });
        }
        i += 1;
      }
    } else {
      for (const line of chompToLines(p.value)) {
        rows.push({ right: { text: line, kind: "add" } });
      }
      i += 1;
    }
  }
  return rows;
}
