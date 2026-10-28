import { useState } from "react";
import { canTriage, sortIdeasForTriage } from "../brainstormIdeas";
import type { BrainstormIdea } from "../types";

type Props = {
  ideas: BrainstormIdea[];
  busy: boolean;
  onTriage: (ideaId: string, status: string) => void;
};

function RecommendationChip({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <span className={`brainstorm-chip brainstorm-chip--${value}`}>{value}</span>
  );
}

type RowProps = { idea: BrainstormIdea; showVerdicts: boolean } & Omit<Props, "ideas">;

function IdeaRow({ idea, showVerdicts, busy, onTriage }: RowProps) {
  const editable = canTriage(idea);
  return (
    <li className={`brainstorm-idea brainstorm-idea--${idea.status}`}>
      <div className="brainstorm-idea-head">
        <span className="brainstorm-idea-id">{idea.id}</span>
        <span className="brainstorm-idea-title">{idea.title}</span>
        {showVerdicts ? <RecommendationChip value={idea.recommendation} /> : null}
        <span className="brainstorm-idea-kind">{idea.kind}</span>
        {idea.effort ? (
          <span className="brainstorm-idea-kind">{idea.effort}</span>
        ) : null}
      </div>
      {idea.rationale ? (
        <p className="brainstorm-idea-rationale">{idea.rationale}</p>
      ) : null}
      {idea.evidence.length > 0 ? (
        <ul className="brainstorm-idea-sources">
          {idea.evidence.map((url) => (
            <li key={url}>
              <a href={url} target="_blank" rel="noreferrer noopener">
                {url}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="brainstorm-idea-actions">
        {editable ? (
          <>
            <button
              type="button"
              disabled={busy || idea.status === "accepted"}
              onClick={() => onTriage(idea.id, "accepted")}
            >
              Accept
            </button>
            <button
              type="button"
              disabled={busy || idea.status === "rejected"}
              onClick={() => onTriage(idea.id, "rejected")}
            >
              Reject
            </button>
            {idea.status !== "proposed" ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => onTriage(idea.id, "proposed")}
              >
                Undo
              </button>
            ) : null}
          </>
        ) : (
          <span className="brainstorm-idea-promoted">
            On the roadmap — edit the node from the outline.
          </span>
        )}
        <span className="brainstorm-idea-status">{idea.status}</span>
      </div>
    </li>
  );
}

export function BrainstormIdeaList({ ideas, busy, onTriage }: Props) {
  // Hidden by default, as in the CLI's `list`, so verdicts do not steer triage.
  const [showVerdicts, setShowVerdicts] = useState(false);
  if (ideas.length === 0) {
    return (
      <p className="outline-meta">
        No ideas yet. Ask the assistant to start generating.
      </p>
    );
  }
  return (
    <>
      <label className="brainstorm-verdict-toggle">
        <input
          type="checkbox"
          checked={showVerdicts}
          onChange={(e) => setShowVerdicts(e.target.checked)}
        />{" "}
        Show verdicts (strongest first)
      </label>
      <ul className="brainstorm-idea-list">
        {sortIdeasForTriage(ideas, showVerdicts).map((idea) => (
          <IdeaRow
            key={idea.id}
            idea={idea}
            showVerdicts={showVerdicts}
            busy={busy}
            onTriage={onTriage}
          />
        ))}
      </ul>
    </>
  );
}
