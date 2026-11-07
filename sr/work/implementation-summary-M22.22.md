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

Known limit: when the editor cannot represent a source block (a GFM table, which this editor drops already),
the tokens cannot be paired, so an edit saves the whole serialization as before. An unedited sheet is still
byte-identical.

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

## Probes

- Tight sheet `## Intent\nOld intent.\n## Approach\n- a\n  b\n`, edit the paragraph: only that line changes (test).
- `*same*\n\n_same_\n`, delete the first block: `_same_\n` (test).
- Empty document, type `First`: `First`, no throw (test).
- `Para one.\n## H\nPara two.\n`, delete the heading: the source `\n` would merge the paragraphs, so a blank line is used: `Para one.\n\nPara two.\n` (test).
- Unedited loose sheet with a two-space continuation and trailing-paragraph insert: byte-identical; Intent edit changes only its lines (tests).
- Whitespace-only source `\n\n`, type `Hi`: falls back to the serialization (`Hi\n\n`), no throw (ad-hoc probe).
- Move the last block first in `## A\n\nx\n\n## B\n`: `## B\n\n## A\n\nx\n`, each block's source kept (ad-hoc probe).
- Append a paragraph to a source with no trailing newline: `## A\n\nx\n\ny`, the source's ending kept (ad-hoc probe).
- Insert a paragraph between a tight heading and paragraph: the parse-back check forces blank lines, `## A\n\nnew\n\nx\n` (ad-hoc probe; correct, at the cost of one extra blank line next to the edit).
- Edit a paragraph before a tight list with a continuation indent: the list's lines unchanged (ad-hoc probe).
- Delete every block: `""`, no throw (ad-hoc probe).
- A sheet with a GFM table, edit another block: falls back to the whole serialization (known limit above; the table loss predates this leaf).
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
(26 files, 210 tests), `npm run build` (static bundle rebuilt and committed). From the git root: `ruff check
specy_road tests scripts` and `specy-road file-limits` pass. No Python changed.

## Added

- `planningSectionUtils.ts` `MarkdownToken`, `MarkdownCodec<N>` (parse, serialize), `EditorBlock` types: minimal shapes so the helper needs no tiptap or marked import.
- `planningSectionUtils.ts` `toEditorBlocks`: each node with its own Markdown; shared by the save path, the parse-back check and the test.
- `planningSectionUtils.ts` `sourcePieces` (module-private): splits the source into block text plus following newlines; null when tokens do not rebuild the source (→ whole serialization).
- `planningSectionUtils.ts` `junction` and `writeBlocks` (module-private): the separator rule and the writer.
- `planningSectionUtils.ts` `sameList` (module-private): list equality for node identities and parse-back blocks.
- `planningSectionUtils.ts` `preserveUntouchedMarkdown`: the F4 save rule. Its branches: unchanged → source; unpairable → serialized; source separators, then blank lines, then serialized, each tried only if the one before fails the parse-back check.
- `MarkdownWorkspace.tsx` `markdownWorkspaceExtensions` (exported, react-refresh lint disabled on that line): one extension list with Link configured inside StarterKit.
- `MarkdownWorkspace.tsx` `LoadedMarkdown`, `editorBlocks`, `loadedRef`, `lastTextRef`: remember the loaded text and blocks for the save rule and the value sync.
- `ModalFrame.tsx` `EscapeFrame`, `escapeTargetFrame` (exported, react-refresh lint disabled on that line): pure front-most decision.
- `ModalFrame.tsx` `openFrames` registry, `frameCount`, `frameId` state and registration effects: let each press close one frame.
- Test `markdownWorkspace.test.ts` `it.each` "planning-sheet save keeps untouched Markdown": six cases through the real tiptap Markdown codec, each pinning one rule clause (unedited byte-identical, Intent edit locality, tight separators, duplicate-looking blocks, empty document, merge-guard blank line).
- Test "configures each extension name once (one link)": F9 duplicate extension.
- Test `it.each` "Escape closes the front-most modal only" (one, two stacked, Publish over edit, minimized, not answering, none) and "ignores other keys": F9 Escape decision.
- Mocks: none.
