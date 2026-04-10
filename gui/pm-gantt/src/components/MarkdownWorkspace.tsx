import { useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkFrontmatter from "remark-frontmatter";
import remarkGfm from "remark-gfm";

export type MarkdownViewMode = "source" | "split" | "preview";

const REMARK_PLUGINS = [remarkFrontmatter, remarkGfm];
const REHYPE_PLUGINS = [rehypeSanitize];

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
  defaultViewMode?: MarkdownViewMode;
  spellCheck?: boolean;
  /** Label for the source editor (accessibility). */
  sourceLabel?: string;
  /** Label for the preview region (accessibility). */
  previewLabel?: string;
  className?: string;
};

export function MarkdownWorkspace({
  value,
  onChange,
  disabled = false,
  defaultViewMode = "split",
  spellCheck = false,
  sourceLabel = "Markdown source",
  previewLabel = "Markdown preview",
  className,
}: Props) {
  const baseId = useId();
  const sourceId = `${baseId}-source`;
  const previewId = `${baseId}-preview`;
  const [mode, setMode] = useState<MarkdownViewMode>(defaultViewMode);

  const showSource = mode === "source" || mode === "split";
  const showPreview = mode === "preview" || mode === "split";
  const frontmatterNote = hasLeadingYamlFrontmatter(value);

  return (
    <div className={className ? `markdown-workspace ${className}` : "markdown-workspace"}>
      <div
        className="markdown-workspace-toolbar"
        role="toolbar"
        aria-label="Markdown view mode"
      >
        {(["source", "split", "preview"] as const).map((m) => (
          <button
            key={m}
            type="button"
            className={
              mode === m
                ? "markdown-workspace-mode is-active"
                : "markdown-workspace-mode"
            }
            onClick={() => setMode(m)}
            disabled={disabled}
            aria-pressed={mode === m}
          >
            {m === "source" ? "Source" : m === "split" ? "Split" : "Preview"}
          </button>
        ))}
      </div>
      {frontmatterNote ? (
        <p className="markdown-workspace-frontmatter-note outline-meta">
          YAML frontmatter at the top of this file is parsed and not shown in the
          preview body.
        </p>
      ) : null}
      <div
        className={
          mode === "split"
            ? "markdown-workspace-panes markdown-workspace-panes--split"
            : "markdown-workspace-panes"
        }
      >
        {showSource ? (
          <div className="markdown-workspace-pane markdown-workspace-pane--source">
            <label className="sr-only" htmlFor={sourceId}>
              {sourceLabel}
            </label>
            <textarea
              id={sourceId}
              className="markdown-workspace-source"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              spellCheck={spellCheck}
              disabled={disabled}
              aria-label={sourceLabel}
            />
          </div>
        ) : null}
        {showPreview ? (
          <div className="markdown-workspace-pane markdown-workspace-pane--preview">
            <div
              id={previewId}
              className="md-preview markdown-workspace-md"
              aria-label={previewLabel}
              role="region"
            >
              <ReactMarkdown
                remarkPlugins={REMARK_PLUGINS}
                rehypePlugins={REHYPE_PLUGINS}
              >
                {value}
              </ReactMarkdown>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
