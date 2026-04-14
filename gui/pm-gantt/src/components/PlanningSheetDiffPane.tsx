import { useId } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildPlanningSideBySideRows } from "../planningDiffUtils";

/** Keep each diff row as a single block; avoid margins that collapse across rows. */
const mdComponents: Components = {
  p: ({ children }) => <p className="planning-md-diff-md-block">{children}</p>,
  ul: ({ children, className }) => (
    <ul className={`planning-md-diff-md-list ${className ?? ""}`.trim()}>
      {children}
    </ul>
  ),
  ol: ({ children, className }) => (
    <ol className={`planning-md-diff-md-list ${className ?? ""}`.trim()}>
      {children}
    </ol>
  ),
  li: ({ children, className, ...rest }) => (
    <li
      className={`planning-md-diff-md-li ${className ?? ""}`.trim()}
      {...rest}
    >
      {children}
    </li>
  ),
};

function MdLine({
  line,
  tone,
}: {
  line: string;
  tone: "ctx" | "add" | "del";
}) {
  const cls =
    tone === "add"
      ? "planning-md-diff-line planning-md-diff-line--add"
      : tone === "del"
        ? "planning-md-diff-line planning-md-diff-line--del"
        : "planning-md-diff-line planning-md-diff-line--ctx";
  if (!line) {
    return <div className={cls}>&nbsp;</div>;
  }
  return (
    <div className={cls}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {line}
      </ReactMarkdown>
    </div>
  );
}

type Props = {
  /** Markdown in the editor when the review ran. */
  originalMarkdown: string;
  /** Full proposed sheet from the LLM (normalized). */
  proposedMarkdown: string;
};

export function PlanningSheetDiffPane({ originalMarkdown, proposedMarkdown }: Props) {
  const rows = buildPlanningSideBySideRows(originalMarkdown, proposedMarkdown);
  const labelId = useId();

  return (
    <div
      className="planning-md-diff-pane"
      role="region"
      aria-labelledby={labelId}
    >
      <div id={labelId} className="planning-md-diff-legend">
        <span>Before (snapshot)</span>
        <span>Proposed (green = insert · red = delete)</span>
      </div>
      <div className="planning-md-diff-scroll">
        {rows.map((row, idx) => (
          <div className="planning-md-diff-row" key={idx}>
            <div
              className={
                row.left
                  ? row.left.kind === "del"
                    ? "planning-md-diff-cell planning-md-diff-cell--del"
                    : "planning-md-diff-cell planning-md-diff-cell--ctx"
                  : "planning-md-diff-cell planning-md-diff-cell--empty"
              }
            >
              {row.left ? (
                <MdLine line={row.left.text} tone={row.left.kind} />
              ) : (
                <div className="planning-md-diff-line planning-md-diff-line--pad">
                  &nbsp;
                </div>
              )}
            </div>
            <div
              className={
                row.right
                  ? row.right.kind === "add"
                    ? "planning-md-diff-cell planning-md-diff-cell--add"
                    : "planning-md-diff-cell planning-md-diff-cell--ctx"
                  : "planning-md-diff-cell planning-md-diff-cell--empty"
              }
            >
              {row.right ? (
                <MdLine line={row.right.text} tone={row.right.kind} />
              ) : (
                <div className="planning-md-diff-line planning-md-diff-line--pad">
                  &nbsp;
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
