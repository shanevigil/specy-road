import type { BrainstormIdea } from "./types";

export type IdeaCounts = {
  proposed: number;
  accepted: number;
  rejected: number;
  revised: number;
  parked: number;
  promoted: number;
};

export function ideaCounts(ideas: BrainstormIdea[]): IdeaCounts {
  const out: IdeaCounts = {
    proposed: 0,
    accepted: 0,
    rejected: 0,
    revised: 0,
    parked: 0,
    promoted: 0,
  };
  for (const i of ideas) {
    out[i.status] += 1;
    if (i.promoted_node_key) out.promoted += 1;
  }
  return out;
}

/**
 * A promoted idea is a roadmap node now, so flipping it would say nothing
 * true. The server refuses it either way; this keeps the buttons honest.
 */
export function canTriage(idea: BrainstormIdea): boolean {
  return !idea.promoted_node_key;
}

const RECOMMENDATION_RANK: Record<string, number> = {
  strong: 0,
  consider: 1,
  park: 2,
};

export function recommendationRank(rec: string | null): number {
  if (rec == null) return 3;
  return RECOMMENDATION_RANK[rec] ?? 3;
}

/**
 * Triage order. With verdicts shown, what the model argued hardest for comes
 * first; hidden (the default, as in the CLI's `list`), capture order, so the
 * verdicts do not steer the PM.
 *
 * Ideas already promoted sink to the bottom — they are done, and leaving them
 * interleaved makes the list look like there is more to decide than there is.
 * Ties keep insertion order so ids stay readable.
 */
export function sortIdeasForTriage(
  ideas: BrainstormIdea[],
  showVerdicts: boolean,
): BrainstormIdea[] {
  return ideas
    .map((idea, index) => ({ idea, index }))
    .sort((a, b) => {
      const promoted =
        Number(Boolean(a.idea.promoted_node_key)) -
        Number(Boolean(b.idea.promoted_node_key));
      if (promoted !== 0) return promoted;
      if (!showVerdicts) return a.index - b.index;
      const rank =
        recommendationRank(a.idea.recommendation) -
        recommendationRank(b.idea.recommendation);
      if (rank !== 0) return rank;
      return a.index - b.index;
    })
    .map((e) => e.idea);
}

export function filterIdeas(
  ideas: BrainstormIdea[],
  status: string,
): BrainstormIdea[] {
  if (!status || status === "all") return ideas;
  return ideas.filter((i) => i.status === status);
}

/** Nothing accepted means nothing to promote — used to disable the button. */
export function promotableCount(ideas: BrainstormIdea[]): number {
  return ideas.filter((i) => i.status === "accepted" && !i.promoted_node_key)
    .length;
}
