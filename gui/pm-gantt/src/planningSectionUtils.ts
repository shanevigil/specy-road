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
  parse(markdown: string): { content?: N[] };
  serialize(doc: { type: string; content?: N[] }): string;
};

/**
 * One top-level editor block: its node object and its Markdown on its own. The editor keeps
 * the same node object for a block the person did not touch, so `node` is its identity.
 */
export type EditorBlock = { node: unknown; markdown: string };

/** Each node serialized on its own (`json` gives the codec's form of a node). */
export function toEditorBlocks<N, J>(
  codec: MarkdownCodec<J>,
  nodes: readonly N[],
  json: (node: N) => J,
): EditorBlock[] {
  return nodes.map((node) => ({
    node,
    markdown: codec.serialize({ type: "doc", content: [json(node)] }),
  }));
}

/** The non-empty top-level blocks `markdown` parses to, each serialized on its own. */
function blocksOf<J>(codec: MarkdownCodec<J>, markdown: string): string[] {
  return toEditorBlocks(codec, codec.parse(markdown).content ?? [], (n) => n)
    .map((b) => b.markdown)
    .filter((m) => m.trim());
}

/**
 * A top-level source token: its text, the newlines after it, and how many editor blocks it
 * parses to on its own. A token with none (a GFM table, a link-reference definition) has no
 * editor node, so nobody can edit it: it is always written back as it was.
 */
type SourcePiece = { body: string; sep: string; blocks: number };

/**
 * The source as leading blank lines plus one piece per non-blank top-level token.
 * Null when the tokens do not rebuild `source` exactly.
 */
function sourcePieces<J>(
  source: string,
  tokens: MarkdownToken[],
  codec: MarkdownCodec<J>,
): { lead: string; pieces: SourcePiece[] } | null {
  if (tokens.map((t) => t.raw).join("") !== source) return null;
  let lead = "";
  const pieces: SourcePiece[] = [];
  for (const t of tokens) {
    const last = pieces[pieces.length - 1];
    if (t.type === "space") {
      if (last) last.sep += t.raw;
      else lead += t.raw;
      continue;
    }
    const body = t.raw.replace(/\n+$/, "");
    const blocks = blocksOf(codec, t.raw).length;
    pieces.push({ body, sep: t.raw.slice(body.length), blocks });
  }
  return { lead, pieces };
}

/** A block to write: the source piece it keeps (index) or, when edited, its new text. */
type Placed = { piece?: number; text: string };

/**
 * Adds every source piece with no editor block to `placed`, in source order: right after the
 * nearest earlier piece that has a block when that block is still written, else before the
 * next kept piece that came after it in the source (or at the end).
 */
function withUneditable(pieces: SourcePiece[], placed: Placed[]): Placed[] {
  const kept = new Set(placed.map((b) => b.piece));
  const anchor = pieces.map((_, i) => {
    let a = i - 1;
    while (a >= 0 && pieces[a]!.blocks === 0) a--;
    return a;
  });
  const pending = pieces.flatMap((p, i) => (p.blocks === 0 ? [i] : []));
  const out: Placed[] = [];
  const flush = (take: (i: number) => boolean) => {
    for (const i of pending.filter(take)) out.push({ piece: i, text: "" });
    pending.splice(0, pending.length, ...pending.filter((i) => !take(i)));
  };
  flush((i) => anchor[i] === -1);
  for (const b of placed) {
    const at = b.piece;
    if (at !== undefined) flush((i) => i < at && !kept.has(anchor[i]));
    out.push(b);
    if (at !== undefined) flush((i) => anchor[i] === at);
  }
  flush(() => true);
  return out;
}

/**
 * The separator between two written blocks. A pair that was adjacent in the source keeps
 * its separator. Otherwise, when `fromSource`, the separator that followed the earlier block
 * (or preceded the later one) in the source; else, or with neither, one blank line.
 */
function junction(
  pieces: SourcePiece[],
  x: Placed,
  y: Placed,
  fromSource: boolean,
): string {
  const last = pieces.length - 1;
  if (x.piece !== undefined && y.piece === x.piece + 1) return pieces[x.piece]!.sep;
  if (!fromSource) return "\n\n";
  if (x.piece !== undefined && x.piece < last) return pieces[x.piece]!.sep;
  if (y.piece !== undefined && y.piece > 0) return pieces[y.piece - 1]!.sep;
  return "\n\n";
}

function writeBlocks(
  { lead, pieces }: { lead: string; pieces: SourcePiece[] },
  placed: Placed[],
  fromSource: boolean,
): string {
  const ending = pieces[pieces.length - 1]?.sep ?? "";
  return lead + placed
    .map((b, k) => {
      const body = b.piece === undefined ? b.text : pieces[b.piece]!.body;
      const next = placed[k + 1];
      return body + (next ? junction(pieces, b, next, fromSource) : ending);
    })
    .join("");
}

const sameList = <T>(a: readonly T[], b: readonly T[]) =>
  a.length === b.length && a.every((x, k) => x === b[k]);

/**
 * Markdown to save after an edit. Rule: every source block the person did not touch is
 * written as its loaded `source` text, and only edited or new blocks as the editor serializes
 * them. A source block is untouched when its editor node is the same object as at load, or
 * when it has no editor node at all (a GFM table, a link-reference definition: the editor
 * cannot show it, so it cannot be edited; it keeps its place after the source block before
 * it). Separators come from the source (see {@link junction}). The result must parse back to
 * the editor's blocks: if source separators would merge or split blocks, edited junctions get
 * a blank line instead. The whole `serialized` document is returned only when that also
 * fails, or when the source tokens cannot be paired one-to-one with the loaded blocks (a
 * token that parses to several blocks). An unedited document returns `source` unchanged.
 * Empty blocks (the editor's trailing paragraph) are ignored. Limit: inline content the
 * editor cannot hold is lost only inside a block the person edits. `baseline` is the blocks
 * right after `source` loaded, `next` the current ones, `tokens` the editor's lexer output
 * for `source`.
 */
export function preserveUntouchedMarkdown<J>(input: {
  source: string;
  tokens: MarkdownToken[];
  baseline: EditorBlock[];
  next: EditorBlock[];
  serialized: string;
  codec: MarkdownCodec<J>;
}): string {
  const { source, codec } = input;
  const base = input.baseline.filter((b) => b.markdown.trim());
  const cur = input.next.filter((b) => b.markdown.trim());
  if (sameList(base.map((b) => b.node), cur.map((b) => b.node))) return source;
  const src = sourcePieces(source, input.tokens, codec);
  const shown = src?.pieces.flatMap((p, i) => (p.blocks ? [i] : [])) ?? [];
  if (
    !src ||
    shown.length !== base.length ||
    src.pieces.some((p) => p.blocks > 1)
  ) {
    return input.serialized;
  }
  const pieceOf = new Map(base.map((b, k) => [b.node, shown[k]]));
  const placed = withUneditable(
    src.pieces,
    cur.map((b) => ({
      piece: pieceOf.get(b.node),
      text: b.markdown.replace(/\n+$/, ""),
    })),
  );
  const expected = cur.map((b) => b.markdown);
  for (const fromSource of [true, false]) {
    const out = writeBlocks(src, placed, fromSource);
    if (sameList(blocksOf(codec, out), expected)) return out;
  }
  return input.serialized;
}
