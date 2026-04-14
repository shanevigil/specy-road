import { useId, useMemo, type MutableRefObject } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { buildPlanningSideBySideRows } from "../planningDiffUtils";
import {
  assignDiffRowSectionIndices,
  groupContiguousSectionRanges,
} from "../planningSectionUtils";

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

type SectionChoice = "before" | "proposed" | null;

type Props = {
  /** Markdown in the editor when the review ran. */
  originalMarkdown: string;
  /** Full proposed sheet from the LLM (normalized). */
  proposedMarkdown: string;
  /** Number of paired sections (min of original vs proposed H2 counts). */
  pairedSectionCount: number;
  sectionChoices: SectionChoice[];
  onSectionChoice: (sectionIndex: number, choice: "before" | "proposed") => void;
  hoveredSection: number | null;
  onHoverSection: (sectionIndex: number | null) => void;
  /** Ref slots for scrolling — parent owns the array; index = section index. */
  sectionScrollRefs: MutableRefObject<(HTMLDivElement | null)[]>;
};

export function PlanningSheetDiffPane({
  originalMarkdown,
  proposedMarkdown,
  pairedSectionCount,
  sectionChoices,
  onSectionChoice,
  hoveredSection,
  onHoverSection,
  sectionScrollRefs,
}: Props) {
  const rows = useMemo(
    () => buildPlanningSideBySideRows(originalMarkdown, proposedMarkdown),
    [originalMarkdown, proposedMarkdown],
  );
  const rowSectionIdx = useMemo(
    () => assignDiffRowSectionIndices(rows),
    [rows],
  );
  const groups = useMemo(
    () => groupContiguousSectionRanges(rowSectionIdx),
    [rowSectionIdx],
  );

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
        {groups.map((g) => {
          const s = g.sectionIndex;
          const isPaired = s < pairedSectionCount;
          const resolved = isPaired && sectionChoices[s] != null;
          const hovered = hoveredSection === s;

          return (
            <div
              key={`${g.start}-${g.end}-${s}`}
              className={[
                "planning-md-diff-section",
                resolved ? "planning-md-diff-section--resolved" : "",
                hovered ? "planning-md-diff-section--hover" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              data-section-index={s}
              ref={(el) => {
                if (!isPaired) return;
                const arr = sectionScrollRefs.current;
                arr[s] = el;
              }}
              onMouseEnter={() => onHoverSection(s)}
              onMouseLeave={() => onHoverSection(null)}
            >
              {isPaired ? (
                <div className="planning-md-diff-section-actions">
                  <button
                    type="button"
                    className="planning-md-diff-use-btn"
                    onClick={() => onSectionChoice(s, "before")}
                    aria-label="Use before snapshot for this section"
                  >
                    Use before
                  </button>
                  <button
                    type="button"
                    className="planning-md-diff-use-btn"
                    onClick={() => onSectionChoice(s, "proposed")}
                    aria-label="Use proposed text for this section"
                  >
                    Use proposed
                  </button>
                </div>
              ) : null}
              {rows.slice(g.start, g.end).map((row, j) => {
                const idx = g.start + j;
                return (
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
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
