import { Link } from "@tiptap/extension-link";
import { Markdown } from "@tiptap/markdown";
import { EditorContent, useEditor } from "@tiptap/react";
import { StarterKit } from "@tiptap/starter-kit";
import { useEffect, useId, useLayoutEffect, useMemo, useRef } from "react";
import { MarkdownToolbar } from "./MarkdownToolbar";

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

type Props = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  spellCheck?: boolean;
  /** Accessible label for the editor region (file path or role). */
  editorLabel?: string;
  className?: string;
};

export function MarkdownWorkspace({
  value,
  onChange,
  disabled = false,
  spellCheck = false,
  editorLabel = "Markdown editor",
  className,
}: Props) {
  const regionId = useId();
  const frontmatterNote = hasLeadingYamlFrontmatter(value);

  // Stable extension instances — new arrays each render made useEditor's setOptions
  // treat options as changed every frame and broke hydration of loaded markdown.
  const extensions = useMemo(
    () => [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Markdown.configure({
        markedOptions: { gfm: true },
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        linkOnPaste: true,
      }),
    ],
    [],
  );

  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  /** After mount, ignore onUpdate until the editor has applied the first document (avoids wiping loaded markdown). */
  const emitUpdatesRef = useRef(false);

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
          class: "markdown-workspace-editor",
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
        const next = normalizeMd(ed.getMarkdown());
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
          class: "markdown-workspace-editor",
          spellcheck: spellCheck ? "true" : "false",
        },
      },
    });
  }, [editor, spellCheck]);

  useLayoutEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const v = normalizeMd(value);
    const current = normalizeMd(editor.getMarkdown());
    if (v === current) return;
    editor.commands.setContent(value, {
      contentType: "markdown",
      emitUpdate: false,
    });
  }, [editor, value]);

  const rootClass = className
    ? `markdown-workspace ${className}`
    : "markdown-workspace";

  return (
    <div className={rootClass}>
      <MarkdownToolbar editor={editor} disabled={disabled} />
      {frontmatterNote ? (
        <p className="markdown-workspace-frontmatter-note outline-meta">
          YAML frontmatter at the top of this file may not round-trip exactly in
          the editor; body content below should still save as markdown. (
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
