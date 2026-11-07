import { MarkdownManager } from "@tiptap/markdown";
import { flattenExtensions, type JSONContent } from "@tiptap/react";
import { describe, expect, it } from "vitest";
import { markdownWorkspaceExtensions } from "./components/MarkdownWorkspace";
import { escapeTargetFrame, type EscapeFrame } from "./components/ModalFrame";
import {
  preserveUntouchedMarkdown,
  toEditorBlocks,
} from "./planningSectionUtils";

const SHEET = [
  "## Intent",
  "",
  "Saving keeps what the person did not touch.",
  "",
  "## Approach",
  "",
  "- **F4.** first line of the item",
  "  continued on a two-space indent",
  "- second item",
  "",
  "## Tasks / checklist",
  "",
  "- [ ] one",
  "- [x] two",
  "",
].join("\n");

const TIGHT = "## Intent\nOld intent.\n## Approach\n- a\n  b\n";

const TABLE =
  "## Intent\n\nOld.\n\n## Cases\n\n| Case | Expected |\n|---|---|\n| a | b |\n";
const REFERENCE =
  "## Intent\n\nOld.\n\nSee [roadmap][r].\n\n[r]: https://example.com/roadmap\n";

const paragraph = (text: string): JSONContent => ({
  type: "paragraph",
  content: [{ type: "text", text }],
});

/**
 * Load `source` the way the editor does, let `edit` change the top-level nodes (an untouched
 * node keeps its object, as in the editor), and save.
 */
function save(
  source: string,
  edit: (nodes: JSONContent[]) => JSONContent[] = (nodes) => nodes,
): string {
  const codec = new MarkdownManager({
    extensions: markdownWorkspaceExtensions(),
    markedOptions: { gfm: true },
  });
  const loaded = codec.parse(source).content ?? [];
  // The editor appends an empty trailing paragraph after a list on the first transaction.
  const nodes = [...edit([...loaded]), { type: "paragraph" }];
  return preserveUntouchedMarkdown({
    source,
    tokens: codec.instance.lexer(source),
    baseline: toEditorBlocks(codec, loaded, (n) => n),
    next: toEditorBlocks(codec, nodes, (n) => n),
    serialized: codec.serialize({ type: "doc", content: nodes }),
    codec,
  });
}

describe("planning-sheet save keeps untouched Markdown", () => {
  it.each([
    ["an unedited sheet, byte-identical", SHEET, undefined, SHEET],
    [
      "an Intent edit changes only its lines",
      SHEET,
      (n: JSONContent[]) => n.with(1, paragraph("A new intent.")),
      SHEET.replace("Saving keeps what the person did not touch.", "A new intent."),
    ],
    [
      "a tight sheet keeps its single-newline separators",
      TIGHT,
      (n: JSONContent[]) => n.with(1, paragraph("New intent.")),
      TIGHT.replace("Old intent.", "New intent."),
    ],
    [
      "deleting one of two equal-looking blocks keeps the other's source",
      "*same*\n\n_same_\n",
      (n: JSONContent[]) => n.slice(1),
      "_same_\n",
    ],
    [
      "first text typed into an empty document",
      "",
      () => [paragraph("First")],
      "First",
    ],
    [
      "an Intent edit keeps an untouched GFM table",
      TABLE,
      (n: JSONContent[]) => n.with(1, paragraph("New.")),
      TABLE.replace("Old.", "New."),
    ],
    [
      "an Intent edit keeps an untouched reference link and its definition",
      REFERENCE,
      (n: JSONContent[]) => n.with(1, paragraph("New.")),
      REFERENCE.replace("Old.", "New."),
    ],
    [
      "a source separator that would merge blocks becomes a blank line",
      "Para one.\n## H\nPara two.\n",
      (n: JSONContent[]) => [n[0]!, n[2]!],
      "Para one.\n\nPara two.\n",
    ],
  ] as const)("%s", (_case, source, edit, expected) => {
    expect(save(source, edit)).toBe(expected);
  });
});

describe("editor extensions", () => {
  it("configures each extension name once (one link)", () => {
    const names = flattenExtensions(markdownWorkspaceExtensions()).map(
      (e) => e.name,
    );
    expect(names.filter((n) => n === "link")).toEqual(["link"]);
    expect(new Set(names).size).toBe(names.length);
  });
});

describe("Escape closes the front-most modal only", () => {
  const frame = (id: number, zIndex: number, more: Partial<EscapeFrame> = {}) => ({
    id,
    zIndex,
    order: id,
    closeOnEscape: true,
    minimized: false,
    ...more,
  });

  it.each([
    ["one edit modal", [frame(1, 200)], 1],
    ["two stacked edit modals", [frame(1, 200), frame(2, 201)], 2],
    ["Publish opened over an edit modal", [frame(1, 200), frame(2, 200)], 2],
    ["the front one minimized", [frame(1, 200), frame(2, 201, { minimized: true })], 1],
    ["a frame told not to answer", [frame(1, 200), frame(2, 201, { closeOnEscape: false })], 1],
    ["no open frame", [], null],
  ] as const)("%s", (_case, frames, expected) => {
    expect(escapeTargetFrame("Escape", frames)).toBe(expected);
  });

  it("ignores other keys", () => {
    expect(escapeTargetFrame("Enter", [frame(1, 200)])).toBeNull();
  });
});
