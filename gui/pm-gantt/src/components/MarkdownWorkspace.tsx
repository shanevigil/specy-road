import { TaskItem } from "@tiptap/extension-task-item";
import { TaskList } from "@tiptap/extension-task-list";
import { Markdown } from "@tiptap/markdown";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import { StarterKit } from "@tiptap/starter-kit";
import { useEffect, useId, useLayoutEffect, useMemo, useRef } from "react";
import {
  preserveUntouchedMarkdown,
  toEditorBlocks,
  type EditorBlock,
  type MarkdownToken,
} from "../planningSectionUtils";
import { MarkdownToolbar } from "./MarkdownToolbar";

/** Must include `ProseMirror` so `index.css` rules and ProseMirror plugins can target the root. */
const EDITOR_ROOT_CLASS = "ProseMirror markdown-workspace-editor";

function normalizeMd(s: string): string {
  return s.replace(/\r\n/g, "\n");
}

/** True when the document starts with YAML frontmatter (--- … ---). */
function hasLeadingYamlFrontmatter(text: string): boolean {
  if (!text.startsWith("---")) return false;
  const nl = text.indexOf("\n");
  if (nl === -1) return false;
  const rest = text.slice(nl + 1);
  const close = rest.search(/^\s*---\s*$/m);
  return close !== -1;
}

/**
 * The editor's extensions. StarterKit already bundles Link, so Link is configured there
 * (adding a second Link logged a duplicate-extension warning on every open).
 */
// eslint-disable-next-line react-refresh/only-export-components -- shared with tests
export function markdownWorkspaceExtensions() {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      link: {
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
      },
    }),
    TaskList.configure({
      HTMLAttributes: { class: "pm-tiptap-task-list" },
    }),
    TaskItem.configure({
      nested: true,
      HTMLAttributes: { class: "pm-tiptap-task-item" },
    }),
    Markdown.configure({
      markedOptions: { gfm: true },
    }),
  ];
}

/** The loaded text and its blocks, so a save keeps untouched blocks as loaded. */
type LoadedMarkdown = {
  text: string;
  tokens: MarkdownToken[];
  blocks: EditorBlock[];
};

/** The editor's top-level blocks; the editor is built from {@link markdownWorkspaceExtensions}. */
function editorBlocks(editor: Editor): EditorBlock[] {
  return toEditorBlocks(editor.markdown!, editor.state.doc.content.content, (n) =>
    n.toJSON(),
  );
}

type Props = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  spellCheck?: boolean;
  /** Accessible label for the editor region (file path or role). */
  editorLabel?: string;
  className?: string;
  /** When false, hide the formatting toolbar (e.g. read-only preview). */
  showToolbar?: boolean;
};

export function MarkdownWorkspace({
  value,
  onChange,
  disabled = false,
  spellCheck = false,
  editorLabel = "Markdown editor",
  className,
  showToolbar = true,
}: Props) {
  const regionId = useId();
  const frontmatterNote = hasLeadingYamlFrontmatter(value);

  // Stable extension instances — new arrays each render made useEditor's setOptions
  // treat options as changed every frame and broke hydration of loaded markdown.
  const extensions = useMemo(() => markdownWorkspaceExtensions(), []);

  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  /** After mount, ignore onUpdate until the editor has applied the first document (avoids wiping loaded markdown). */
  const emitUpdatesRef = useRef(false);
  /** What the editor last loaded from `value`; null until the first load. */
  const loadedRef = useRef<LoadedMarkdown | null>(null);
  /** Last text loaded from or emitted to `value`. */
  const lastTextRef = useRef<string | null>(null);

  useEffect(() => {
    onChangeRef.current = onChange;
  });

  useEffect(() => {
    valueRef.current = value;
  });

  const editor = useEditor(
    {
      extensions,
      content: value,
      contentType: "markdown",
      editable: !disabled,
      shouldRerenderOnTransaction: true,
      editorProps: {
        attributes: {
          class: EDITOR_ROOT_CLASS,
          spellcheck: spellCheck ? "true" : "false",
        },
      },
      onCreate: () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            emitUpdatesRef.current = true;
          });
        });
      },
      onUpdate: ({ editor: ed, transaction }) => {
        if (!emitUpdatesRef.current) return;
        if (transaction && !transaction.docChanged) return;
        const serialized = normalizeMd(ed.getMarkdown());
        const loaded = loadedRef.current;
        const next = loaded
          ? preserveUntouchedMarkdown({
              source: loaded.text,
              tokens: loaded.tokens,
              baseline: loaded.blocks,
              next: editorBlocks(ed),
              serialized,
              codec: ed.markdown!,
            })
          : serialized;
        lastTextRef.current = next;
        if (next === normalizeMd(valueRef.current)) return;
        onChangeRef.current(next);
      },
    },
    [],
  );

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!disabled);
  }, [editor, disabled]);

  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.setOptions({
      editorProps: {
        attributes: {
          class: EDITOR_ROOT_CLASS,
          spellcheck: spellCheck ? "true" : "false",
        },
      },
    });
  }, [editor, spellCheck]);

  useLayoutEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const v = normalizeMd(value);
    if (v === lastTextRef.current) return;
    lastTextRef.current = v;
    editor.commands.setContent(v, {
      contentType: "markdown",
      emitUpdate: false,
    });
    loadedRef.current = {
      text: v,
      tokens: editor.markdown!.instance.lexer(v),
      blocks: editorBlocks(editor),
    };
  }, [editor, value]);

  const rootClass = className
    ? `markdown-workspace ${className}`
    : "markdown-workspace";

  return (
    <div className={rootClass}>
      {showToolbar ? (
        <MarkdownToolbar editor={editor} disabled={disabled} />
      ) : null}
      {showToolbar && frontmatterNote ? (
        <p className="markdown-workspace-frontmatter-note outline-meta">
          This file starts with YAML frontmatter (optional for planning sheets;
          identity is in the filename). The editor may not round-trip frontmatter
          exactly; body content below should still save as markdown. (
          <code>@tiptap/markdown</code> differs from the old{" "}
          <code>remark-frontmatter</code> preview.)
        </p>
      ) : null}
      <div
        className="markdown-workspace-editor-wrap md-preview"
        role="region"
        id={regionId}
        aria-label={editorLabel}
      >
        <EditorContent
          editor={editor}
          className="markdown-workspace-tiptap-root"
        />
      </div>
    </div>
  );
}
