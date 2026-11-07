# Implementation summary: M22.22 (sandbox-rc4-final-polish)

Scope after the 2026-11-06 split: F4 (planning-sheet save churn) and F9 (Escape, duplicate Link extension).

## F4: planning-sheet save keeps untouched Markdown

Cause: StarterKit's trailing-node plugin appends an empty paragraph on the editor's first transaction, a
`docChanged` update, so `MarkdownWorkspace` emitted the whole document re-serialized. The serializer drops a list
item's two-space continuation indent and changes the ending, and the save queue saved it.

Fix (mechanism: keep the loaded text for unchanged top-level blocks):

- `planningSectionUtils.ts`: `markdownTopLevelBlocks` serializes each top-level node on its own;
  `preserveUntouchedMarkdown(source, tokens, baseline, next, serialized)` returns `source` when the non-empty
  blocks are unchanged, otherwise pairs the source's top-level lexer tokens with the load-time blocks, matches
  current blocks to those (longest common subsequence) and emits the source text for matched blocks and the
  serializer's text only for edited ones, keeping the source's blank lines and final ending. When tokens cannot
  be paired with blocks (e.g. a token the editor drops), an edit falls back to the whole serialization (the old
  behaviour); an unedited sheet is still returned byte-identical.
- `MarkdownWorkspace.tsx`: records the loaded text, its tokens (the editor's own marked instance) and block
  serializations whenever `value` is loaded; `onUpdate` emits through `preserveUntouchedMarkdown`. The
  value-sync layout effect now compares `value` with the last text loaded or emitted (not with
  `getMarkdown()`, which would differ from preserved text and reset the editor on every keystroke).

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
(26 files, 206 tests), `npm run build` (static bundle rebuilt and committed).

## Added

- `planningSectionUtils.ts` `MarkdownToken`, `MarkdownCodec<N>` types: minimal shapes so the helper needs no tiptap or marked import.
- `planningSectionUtils.ts` `markdownTopLevelBlocks`: per-block serialization that the save path and the test share.
- `planningSectionUtils.ts` `sourcePieces` (module-private): splits the source into block text plus following newlines; returns null when tokens do not rebuild the source (guard → fallback).
- `planningSectionUtils.ts` `matchBlocks` (module-private): LCS pairing of load-time and current blocks.
- `planningSectionUtils.ts` `preserveUntouchedMarkdown`: the F4 save rule; guards: unchanged → source, unpairable/empty → serialized.
- `MarkdownWorkspace.tsx` `markdownWorkspaceExtensions` (exported, react-refresh lint disabled on that line): one extension list with Link configured inside StarterKit.
- `MarkdownWorkspace.tsx` `LoadedMarkdown` / `loadedMarkdown`, `loadedRef`, `lastTextRef`: remember the loaded text for the save rule and the value sync.
- `ModalFrame.tsx` `EscapeFrame`, `escapeTargetFrame` (exported, react-refresh lint disabled on that line): pure front-most decision.
- `ModalFrame.tsx` `openFrames` registry, `frameCount`, `frameId` state and registration effects: let each press close one frame.
- Test `markdownWorkspace.test.ts` "saves an unedited sheet byte-identical": F4 round trip through the real tiptap Markdown codec, with the trailing empty paragraph the editor adds.
- Test "changes only the Intent paragraph's lines when it is edited": F4 edit locality.
- Test "configures each extension name once (one link)": F9 duplicate extension.
- Test `it.each` "Escape closes the front-most modal only" (one, two stacked, Publish over edit, minimized, not answering, none) and "ignores other keys": F9 Escape decision.
- Mocks: none.
