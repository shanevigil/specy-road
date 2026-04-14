import { useId, useMemo, useState, type MutableRefObject } from "react";
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
  /** Ref slots for scrolling — parent owns the array; index = section index. */
  sectionScrollRefs: MutableRefObject<(HTMLDivElement | null)[]>;
};

export function PlanningSheetDiffPane({
  originalMarkdown,
  proposedMarkdown,
  pairedSectionCount,
  sectionChoices,
  onSectionChoice,
  sectionScrollRefs,
}: Props) {
  const [hoverPick, setHoverPick] = useState<{
    section: number;
    side: "before" | "proposed";
  } | null>(null);

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
        <span>
          Proposed (green = insert · red = delete) — click a column to choose
        </span>
      </div>
      <div className="planning-md-diff-scroll">
        {groups.map((g) => {
          const s = g.sectionIndex;
          const isPaired = s < pairedSectionCount;
          const choice = isPaired ? sectionChoices[s] : null;
          const resolved = choice != null;
          const hoverBefore =
            hoverPick?.section === s && hoverPick.side === "before";
          const hoverProposed =
            hoverPick?.section === s && hoverPick.side === "proposed";

          return (
            <div
              key={`${g.start}-${g.end}-${s}`}
              className={[
                "planning-md-diff-section",
                resolved ? "planning-md-diff-section--resolved" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              data-section-index={s}
              data-choice={choice ?? undefined}
              ref={(el) => {
                if (!isPaired) return;
                const arr = sectionScrollRefs.current;
                arr[s] = el;
              }}
              onMouseLeave={(e) => {
                const rel = e.relatedTarget;
                if (rel instanceof Node && e.currentTarget.contains(rel)) return;
                setHoverPick(null);
              }}
            >
              {rows.slice(g.start, g.end).map((row, j) => {
                const idx = g.start + j;
                const baseLeft = row.left
                  ? row.left.kind === "del"
                    ? "planning-md-diff-cell planning-md-diff-cell--del"
                    : "planning-md-diff-cell planning-md-diff-cell--ctx"
                  : "planning-md-diff-cell planning-md-diff-cell--empty";
                const baseRight = row.right
                  ? row.right.kind === "add"
                    ? "planning-md-diff-cell planning-md-diff-cell--add"
                    : "planning-md-diff-cell planning-md-diff-cell--ctx"
                  : "planning-md-diff-cell planning-md-diff-cell--empty";
                const leftPickable = isPaired
                  ? [
                      baseLeft,
                      "planning-md-diff-cell--pickable",
                      hoverBefore ? "planning-md-diff-cell--column-hover-before" : "",
                      choice === "before"
                        ? "planning-md-diff-cell--picked-before"
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ")
                  : baseLeft;
                const rightPickable = isPaired
                  ? [
                      baseRight,
                      "planning-md-diff-cell--pickable",
                      hoverProposed
                        ? "planning-md-diff-cell--column-hover-proposed"
                        : "",
                      choice === "proposed"
                        ? "planning-md-diff-cell--picked-proposed"
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ")
                  : baseRight;

                return (
                  <div className="planning-md-diff-row" key={idx}>
                    <div
                      className={leftPickable}
                      title={
                        isPaired
                          ? "Click to choose the before (snapshot) column for this section"
                          : undefined
                      }
                      onMouseEnter={() => {
                        if (isPaired) setHoverPick({ section: s, side: "before" });
                      }}
                      onClick={() => {
                        if (isPaired) onSectionChoice(s, "before");
                      }}
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
                      className={rightPickable}
                      title={
                        isPaired
                          ? "Click to choose the proposed column for this section"
                          : undefined
                      }
                      onMouseEnter={() => {
                        if (isPaired)
                          setHoverPick({ section: s, side: "proposed" });
                      }}
                      onClick={() => {
                        if (isPaired) onSectionChoice(s, "proposed");
                      }}
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
