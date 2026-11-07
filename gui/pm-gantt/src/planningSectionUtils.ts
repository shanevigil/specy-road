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

/** A top-level token from the editor's Markdown lexer (marked's shape). */
export type MarkdownToken = { type: string; raw: string };

/** The parts of the editor's Markdown codec the save path needs. */
export type MarkdownCodec<N> = {
  serialize(doc: { type: string; content?: N[] }): string;
};

/** Each top-level node of `doc`, serialized on its own. */
export function markdownTopLevelBlocks<N>(
  codec: MarkdownCodec<N>,
  doc: { content?: N[] },
): string[] {
  return (doc.content ?? []).map((node) =>
    codec.serialize({ type: "doc", content: [node] }),
  );
}

type SourcePiece = { body: string; sep: string };

/**
 * One piece per non-blank top-level token: its text, and the newlines after it.
 * Null when the tokens do not rebuild `source` exactly.
 */
function sourcePieces(
  source: string,
  tokens: MarkdownToken[],
): SourcePiece[] | null {
  if (tokens.map((t) => t.raw).join("") !== source) return null;
  const pieces: SourcePiece[] = [];
  for (const t of tokens) {
    if (t.type === "space") {
      const last = pieces[pieces.length - 1];
      if (!last) return null;
      last.sep += t.raw;
      continue;
    }
    const body = t.raw.replace(/\n+$/, "");
    pieces.push({ body, sep: t.raw.slice(body.length) });
  }
  return pieces;
}

/** Pairs of equal entries (index in `a`, index in `b`), longest common subsequence. */
function matchBlocks(a: string[], b: string[]): Map<number, number> {
  const n = a.length;
  const m = b.length;
  const len: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      len[i]![j] =
        a[i] === b[j]
          ? len[i + 1]![j + 1]! + 1
          : Math.max(len[i + 1]![j]!, len[i]![j + 1]!);
    }
  }
  const byB = new Map<number, number>();
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      byB.set(j, i);
      i++;
      j++;
    } else if (len[i + 1]![j]! >= len[i]![j + 1]!) {
      i++;
    } else {
      j++;
    }
  }
  return byB;
}

/**
 * Markdown to save after an edit: the loaded `source` text for every top-level block the
 * editor still holds unchanged, and the editor's serialization only for edited blocks.
 * `baseline` holds the per-block serialization right after `source` was loaded and
 * `next` the current one (see {@link markdownTopLevelBlocks}); `tokens` is the editor's
 * lexer output for `source`. Empty blocks (the editor's trailing paragraph) are ignored.
 * When the blocks cannot be paired with the source, `serialized` (the whole document)
 * is returned.
 */
export function preserveUntouchedMarkdown(
  source: string,
  tokens: MarkdownToken[],
  baseline: string[],
  next: string[],
  serialized: string,
): string {
  const base = baseline.filter((b) => b.trim());
  const cur = next.filter((b) => b.trim());
  if (base.length === cur.length && base.every((b, k) => b === cur[k])) {
    return source;
  }
  const pieces = sourcePieces(source, tokens);
  if (!pieces || pieces.length !== base.length || cur.length === 0) {
    return serialized;
  }
  const matched = matchBlocks(base, cur);
  const finalSep = pieces[pieces.length - 1]!.sep;
  return cur
    .map((block, k) => {
      const at = matched.get(k);
      const piece =
        at === undefined
          ? { body: block.replace(/\n+$/, ""), sep: "\n\n" }
          : pieces[at]!;
      if (k === cur.length - 1) return piece.body + finalSep;
      return piece.body + (/\n[ \t]*\n/.test(piece.sep) ? piece.sep : "\n\n");
    })
    .join("");
}
