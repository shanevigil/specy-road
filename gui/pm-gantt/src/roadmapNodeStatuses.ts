/** Matches `status` enum in roadmap.schema.json (consumer + toolkit templates). */
export const ROADMAP_NODE_STATUS_ORDERED = [
  "Not Started",
  "In Progress",
  "Complete",
  "Blocked",
] as const;

export type RoadmapNodeStatus = (typeof ROADMAP_NODE_STATUS_ORDERED)[number];
