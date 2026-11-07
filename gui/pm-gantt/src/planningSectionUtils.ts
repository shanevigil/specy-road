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

/** A block to write: the source piece it keeps (index) or, when edited, its new text. */
type Placed = { piece?: number; text: string };

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
  pieces: SourcePiece[],
  placed: Placed[],
  fromSource: boolean,
): string {
  const ending = pieces[pieces.length - 1]?.sep ?? "";
  return placed
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
 * Markdown to save after an edit. Rule: every top-level block whose editor node is unchanged
 * is written as its loaded `source` text; an edited or new block is written as the editor
 * serializes it; separators come from the source (see {@link junction}). The result must
 * parse back to the editor's blocks: if source separators would merge or split blocks, edited
 * junctions get a blank line instead, and if that also fails (or the source tokens cannot be
 * paired with the loaded blocks) the whole `serialized` document is returned. An unedited
 * document returns `source` unchanged. Empty blocks (the editor's trailing paragraph) are
 * ignored. `baseline` is the blocks right after `source` loaded, `next` the current ones,
 * `tokens` the editor's lexer output for `source`.
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
  const pieces = sourcePieces(source, input.tokens);
  if (!pieces || pieces.length !== base.length) return input.serialized;
  const pieceOf = new Map(base.map((b, k) => [b.node, k]));
  const placed = cur.map((b) => ({
    piece: pieceOf.get(b.node),
    text: b.markdown.replace(/\n+$/, ""),
  }));
  const expected = cur.map((b) => b.markdown);
  for (const fromSource of [true, false]) {
    const out = writeBlocks(pieces, placed, fromSource);
    const back = toEditorBlocks(codec, codec.parse(out).content ?? [], (n) => n)
      .map((b) => b.markdown)
      .filter((m) => m.trim());
    if (sameList(back, expected)) return out;
  }
  return input.serialized;
}
