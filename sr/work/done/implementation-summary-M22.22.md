# Implementation summary: M22.22 (sandbox-rc4-final-polish)

Scope after the 2026-11-06 split: F4 (planning-sheet save churn) and F9 (Escape, duplicate Link extension).

## F4: planning-sheet save keeps untouched Markdown

Cause: StarterKit's trailing-node plugin appends an empty paragraph on the editor's first transaction, a
`docChanged` update, so `MarkdownWorkspace` emitted the whole document re-serialized. The serializer drops a list
item's two-space continuation indent and changes the ending, and the save queue saved it.

Fix (mechanism: keep the loaded text for unchanged top-level blocks; revised in fix round 1):

- `planningSectionUtils.ts` `preserveUntouchedMarkdown({source, tokens, baseline, next, serialized, codec})`.
  The rule, stated once in its docstring:
  - A top-level block whose editor node is unchanged is written as its loaded source text. ProseMirror keeps the
    same node object for an untouched block, so blocks are paired by node identity, not by serialized text.
  - An edited or new block is written as the editor serializes it.
  - Separators come from the source (`junction`): a pair that was adjacent in the source keeps its separator, and
    otherwise the source separator next to it is used.
  - The result must parse back to the editor's blocks. If it does not, edited junctions get a blank line. If that
    also fails, or the source tokens cannot be paired with the loaded blocks, the whole serialization is used (the
    old behaviour).
  - An unedited document returns `source`. Empty blocks (the editor's trailing paragraph) are ignored.
- `MarkdownWorkspace.tsx` records the loaded text, its tokens (the editor's own marked instance) and its blocks
  (node + Markdown) whenever `value` is loaded, and `onUpdate` emits through the helper. The value-sync layout
  effect compares `value` with the last text loaded or emitted (not with `getMarkdown()`, which would differ
  from preserved text and reset the editor on every keystroke).

- Source blocks the editor cannot show (fix round 2). Each source token is paired with the number of editor
  blocks it parses to on its own. A token with none (a GFM table, a link-reference definition, a footnote-style
  definition) has no editor node, so nobody can edit it. It is always written back as it was, right after the
  source block before it if that block is still written, else before the next kept block that followed it in the
  source (`withUneditable`).

Known limits (stated in the docstring):
- Inline content the editor cannot hold (an image inside a paragraph) is lost only inside a block the person edits.
- A source token that parses to several editor blocks makes an edit fall back to the whole serialization (no
  real case was found).
- Where a newly typed block lands relative to a non-editable piece follows the anchor rule above.

## Fix round 1 (review by gpt-5.6-sol-high at 1b4ad025)

Merged `origin/WIP/improvements-0-3-1` first (clean). One root class behind the three blocking findings: the
helper matched blocks by serialized text and rebuilt separators with a fixed rule. Design change:

- separators changed in tight sheets: separators now come from the source, and a parse-back check guards
  junctions that would merge or split blocks;
- duplicate blocks lost their own source: blocks are now paired by editor node identity, so text equality
  never decides which source a block keeps (the LCS matcher is gone);
- empty loaded document threw: the ending is `pieces[last]?.sep ?? ""`, and an empty source pairs as zero
  pieces with zero blocks;
- `editor.markdown` is used directly (non-null assertion); the editor is always built with `Markdown`, so
  the unreachable null fallback (`loadedMarkdown`) is removed.

## Fix round 2 (review by gpt-5.6-sol-high at c7414080)

Merged `origin/WIP/improvements-0-3-1` first (clean). Both findings (an untouched GFM table deleted, and an
untouched link-reference definition inlined then removed, on an Intent edit) are one class: source content
with no editor node. The helper required one source token per editor block, so either kind broke the pairing,
and an edit fell back to the whole serialization, which cannot hold them. Design change: tokens are paired by
the number of blocks each parses to, and tokens with none are kept verbatim in source order (see above). The
fallback is now reached only when the tokens do not rebuild the source, or a token parses to several blocks.
`blocksOf` replaces the inline parse-back code, so per-token counting and the parse-back check use one rule.

## Probes

- Tight sheet `## Intent\nOld intent.\n## Approach\n- a\n  b\n`, edit the paragraph: only that line changes (test).
- `*same*\n\n_same_\n`, delete the first block: `_same_\n` (test).
- Empty document, type `First`: `First`, no throw (test).
- `Para one.\n## H\nPara two.\n`, delete the heading: the source `\n` would merge the paragraphs, so a blank line is used: `Para one.\n\nPara two.\n` (test).
- Unedited loose sheet with a two-space continuation and trailing-paragraph insert: byte-identical; Intent edit changes only its lines (tests).
- Whitespace-only source `\n\n`, type `Hi`: no throw (round 1 probe; see round 2 for the current output).
- Move the last block first in `## A\n\nx\n\n## B\n`: `## B\n\n## A\n\nx\n`, each block's source kept (ad-hoc probe).
- Append a paragraph to a source with no trailing newline: `## A\n\nx\n\ny`, the source's ending kept (ad-hoc probe).
- Insert a paragraph between a tight heading and paragraph: the parse-back check forces blank lines, `## A\n\nnew\n\nx\n` (ad-hoc probe; correct, at the cost of one extra blank line next to the edit).
- Edit a paragraph before a tight list with a continuation indent: the list's lines unchanged (ad-hoc probe).
- Delete every block: `""`, no throw (ad-hoc probe).
- Round 2, GFM table after the Intent, edit the Intent: table kept byte-for-byte (test).
- Round 2, `See [roadmap][r].` plus `[r]: …`, edit the Intent: reference link and definition kept (test).
- Round 2, table first, edit the paragraph after it: table kept first (ad-hoc probe).
- Round 2, table last, edit the paragraph before it: table kept last (ad-hoc probe).
- Round 2, table between paragraphs, delete the paragraph before it: table kept, then the next paragraph (ad-hoc probe).
- Round 2, table between paragraphs, edit the paragraph after it: order kept (ad-hoc probe).
- Round 2, two tables and a definition in a row, edit the next paragraph: all three kept in order with their separators (ad-hoc probe).
- Round 2, footnote-style definition `[^1]: note`, edit the paragraph: definition kept (ad-hoc probe).
- Round 2, HTML comment and `<div>` block (the editor shows them as paragraphs), edit another block: kept verbatim (ad-hoc probe).
- Round 2, paragraph holding only an image (the editor drops the image), edit another block: image paragraph kept (ad-hoc probe).
- Round 2, YAML frontmatter, edit the last paragraph: frontmatter kept byte-for-byte (ad-hoc probe).
- Round 2, leading blank lines (with and without a table after them), edit a block: blank lines and table kept (ad-hoc probe; the leading blank lines are now a prefix, no longer a fallback).
- Round 2, whitespace-only source `\n\n`, type `Hi`: `\n\nHi` (the source's blank lines kept as a prefix).
- Other readers of the last source piece or of text-based matching in the change: none left (`junction`, `writeBlocks` and `preserveUntouchedMarkdown` are the only users of `pieces`; each indexes with a piece number taken from the identity map or guards with `?.`).
- Escape decision (not in the findings): the reviewer's equal-zIndex probe picks the latest opened; the existing `it.each` covers one, two stacked, Publish over edit, minimized and not-answering frames.

## F9: Escape and the Link extension

- I could not reproduce the Escape failure in a browser here (no Playwright or Chromium on this machine), so the
  root cause is not confirmed. The old listener ran on window in the bubble phase, and every frame with
  `closeOnEscape` closed on each press. With Publish open over an edit modal, both had it set. `ModalFrame` now
  keeps a module-level registry of mounted frames. Its listener runs in the capture phase, so nothing inside the
  dialog (editor or input) can stop it. It closes only the frame that `escapeTargetFrame` picks: the highest
  zIndex, then the latest opened, ignoring frames that are minimized or have `closeOnEscape={false}`.
  `EditModal.tsx` and `PublishRoadmapModal.tsx` needed no change.
- Link: StarterKit v3 already bundles Link; Link options moved into `StarterKit.configure({ link: … })` and the
  second `Link` extension was removed. The list is `markdownWorkspaceExtensions()`, exported for the test.

## Touch zones (final)

Changed: `gui/pm-gantt/src/components/MarkdownWorkspace.tsx`, `gui/pm-gantt/src/components/ModalFrame.tsx`,
`gui/pm-gantt/src/planningSectionUtils.ts`, `gui/pm-gantt/src/markdownWorkspace.test.ts` (new),
`specy_road/pm_gantt_static/`, `CHANGELOG.md`. Unchanged but in zone: `EditModal.tsx`,
`PublishRoadmapModal.tsx`, `planningSectionUtils.test.ts`. No file outside the zones changed.

## Verification

In `gui/pm-gantt`: `npm ci`, `npm run lint` (0 errors; the 3 ModalFrame warnings are pre-existing), `npm test`
(26 files, 212 tests), `npm run build` (static bundle rebuilt and committed). From the git root: `ruff check
specy_road tests scripts` and `specy-road file-limits` pass. No Python changed.

## Added

- `planningSectionUtils.ts` `MarkdownToken`, `MarkdownCodec<N>` (parse, serialize), `EditorBlock` types: minimal shapes so the helper needs no tiptap or marked import.
- `planningSectionUtils.ts` `toEditorBlocks`: each node with its own Markdown; shared by the save path, the parse-back check and the test.
- `planningSectionUtils.ts` `sourcePieces` (module-private): splits the source into leading blank lines plus, per token, its text, the newlines after it and how many editor blocks it parses to; null when tokens do not rebuild the source (→ whole serialization).
- `planningSectionUtils.ts` `blocksOf` (module-private): the non-empty blocks Markdown parses to; one rule for per-token counting and the parse-back check.
- `planningSectionUtils.ts` `withUneditable` (module-private): places source pieces that have no editor node (table, reference definition) in source order, so they are never dropped.
- `planningSectionUtils.ts` `junction` and `writeBlocks` (module-private): the separator rule and the writer.
- `planningSectionUtils.ts` `sameList` (module-private): list equality for node identities and parse-back blocks.
- `planningSectionUtils.ts` `preserveUntouchedMarkdown`: the F4 save rule. Its branches: unchanged → source; unpairable (tokens do not rebuild the source, or one parses to several blocks) → serialized; source separators, then blank lines, then serialized, each tried only if the one before fails the parse-back check.
- `MarkdownWorkspace.tsx` `markdownWorkspaceExtensions` (exported, react-refresh lint disabled on that line): one extension list with Link configured inside StarterKit.
- `MarkdownWorkspace.tsx` `LoadedMarkdown`, `editorBlocks`, `loadedRef`, `lastTextRef`: remember the loaded text and blocks for the save rule and the value sync.
- `ModalFrame.tsx` `EscapeFrame`, `escapeTargetFrame` (exported, react-refresh lint disabled on that line): pure front-most decision.
- `ModalFrame.tsx` `openFrames` registry, `frameCount`, `frameId` state and registration effects: let each press close one frame.
- Test `markdownWorkspace.test.ts` `it.each` "planning-sheet save keeps untouched Markdown": eight cases through the real tiptap Markdown codec, each pinning one rule clause (unedited byte-identical, Intent edit locality, tight separators, duplicate-looking blocks, empty document, untouched GFM table, untouched reference link and definition, merge-guard blank line).
- Test "configures each extension name once (one link)": F9 duplicate extension.
- Test `it.each` "Escape closes the front-most modal only" (one, two stacked, Publish over edit, minimized, not answering, none) and "ignores other keys": F9 Escape decision.
- Mocks: none.
