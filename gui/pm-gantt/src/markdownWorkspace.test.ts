import { MarkdownManager } from "@tiptap/markdown";
import { flattenExtensions, type JSONContent } from "@tiptap/react";
import { describe, expect, it } from "vitest";
import { markdownWorkspaceExtensions } from "./components/MarkdownWorkspace";
import { escapeTargetFrame, type EscapeFrame } from "./components/ModalFrame";
import {
  markdownTopLevelBlocks,
  preserveUntouchedMarkdown,
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

/** Load `source` the way the editor does, apply `edit` to the document, and save. */
function roundTrip(source: string, edit?: (doc: JSONContent) => void): string {
  const codec = new MarkdownManager({
    extensions: markdownWorkspaceExtensions(),
    markedOptions: { gfm: true },
  });
  const doc = codec.parse(source);
  const baseline = markdownTopLevelBlocks(codec, doc);
  // The editor appends an empty trailing paragraph after a list on the first transaction.
  doc.content = [...(doc.content ?? []), { type: "paragraph" }];
  edit?.(doc);
  return preserveUntouchedMarkdown(
    source,
    codec.instance.lexer(source),
    baseline,
    markdownTopLevelBlocks(codec, doc),
    codec.serialize(doc),
  );
}

describe("planning-sheet save", () => {
  it("saves an unedited sheet byte-identical", () => {
    expect(roundTrip(SHEET)).toBe(SHEET);
  });

  it("changes only the Intent paragraph's lines when it is edited", () => {
    const saved = roundTrip(SHEET, (doc) => {
      doc.content![1] = {
        type: "paragraph",
        content: [{ type: "text", text: "A new intent." }],
      };
    });
    expect(saved).toBe(
      SHEET.replace("Saving keeps what the person did not touch.", "A new intent."),
    );
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
