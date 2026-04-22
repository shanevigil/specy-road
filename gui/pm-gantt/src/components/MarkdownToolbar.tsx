import type { Editor } from "@tiptap/core";

type Props = {
  editor: Editor | null;
  disabled?: boolean;
};

export function MarkdownToolbar({ editor, disabled = false }: Props) {
  if (!editor) return null;

  const run = (fn: () => boolean) => {
    if (disabled) return;
    fn();
  };

  return (
    <div
      className="markdown-workspace-toolbar markdown-workspace-toolbar--format"
      role="toolbar"
      aria-label="Text formatting"
    >
      <span className="markdown-workspace-toolbar-group">
        <button
          type="button"
          className={
            editor.isActive("bold")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() => run(() => editor.chain().focus().toggleBold().run())}
          title="Bold"
        >
          B
        </button>
        <button
          type="button"
          className={
            editor.isActive("italic")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() => run(() => editor.chain().focus().toggleItalic().run())}
          title="Italic"
        >
          I
        </button>
        <button
          type="button"
          className={
            editor.isActive("strike")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() => run(() => editor.chain().focus().toggleStrike().run())}
          title="Strikethrough"
        >
          S
        </button>
        <button
          type="button"
          className={
            editor.isActive("code")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() => run(() => editor.chain().focus().toggleCode().run())}
          title="Inline code"
        >
          {"</>"}
        </button>
      </span>
      <span className="markdown-workspace-toolbar-group">
        {([1, 2, 3] as const).map((level) => (
          <button
            key={level}
            type="button"
            className={
              editor.isActive("heading", { level })
                ? "markdown-workspace-mode is-active"
                : "markdown-workspace-mode"
            }
            disabled={disabled}
            onClick={() =>
              run(() =>
                editor.chain().focus().toggleHeading({ level }).run(),
              )
            }
            title={`Heading ${level}`}
          >
            H{level}
          </button>
        ))}
      </span>
      <span className="markdown-workspace-toolbar-group">
        <button
          type="button"
          className={
            editor.isActive("bulletList")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().toggleBulletList().run())
          }
          title="Bullet list"
        >
          • List
        </button>
        <button
          type="button"
          className={
            editor.isActive("orderedList")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().toggleOrderedList().run())
          }
          title="Numbered list"
        >
          1. List
        </button>
        <button
          type="button"
          className={
            editor.isActive("taskList")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().toggleTaskList().run())
          }
          title="Task list"
        >
          ☐ Tasks
        </button>
        <button
          type="button"
          className={
            editor.isActive("blockquote")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().toggleBlockquote().run())
          }
          title="Quote"
        >
          “”
        </button>
        <button
          type="button"
          className={
            editor.isActive("codeBlock")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().toggleCodeBlock().run())
          }
          title="Code block"
        >
          Code
        </button>
        <button
          type="button"
          className="markdown-workspace-mode"
          disabled={disabled}
          onClick={() =>
            run(() => editor.chain().focus().setHorizontalRule().run())
          }
          title="Horizontal rule"
        >
          —
        </button>
      </span>
      <span className="markdown-workspace-toolbar-group">
        <button
          type="button"
          className={
            editor.isActive("link")
              ? "markdown-workspace-mode is-active"
              : "markdown-workspace-mode"
          }
          disabled={disabled}
          onClick={() => {
            if (disabled) return;
            const prev = editor.getAttributes("link").href as
              | string
              | undefined;
            const next = window.prompt("Link URL", prev ?? "https://");
            if (next === null) return;
            const trimmed = next.trim();
            if (trimmed === "") {
              editor.chain().focus().extendMarkRange("link").unsetLink().run();
              return;
            }
            editor
              .chain()
              .focus()
              .extendMarkRange("link")
              .setLink({ href: trimmed })
              .run();
          }}
          title="Link"
        >
          Link
        </button>
      </span>
      <span className="markdown-workspace-toolbar-group">
        <button
          type="button"
          className="markdown-workspace-mode"
          disabled={disabled || !editor.can().undo()}
          onClick={() => run(() => editor.chain().focus().undo().run())}
          title="Undo"
        >
          Undo
        </button>
        <button
          type="button"
          className="markdown-workspace-mode"
          disabled={disabled || !editor.can().redo()}
          onClick={() => run(() => editor.chain().focus().redo().run())}
          title="Redo"
        >
          Redo
        </button>
      </span>
    </div>
  );
}
