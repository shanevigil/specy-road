/**
 * Current git HEAD matches the task's registered feature branch in roadmap/registry.yaml.
 */
export function rowMatchesRegisteredBranch(
  nodeId: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitBranchCurrent: string | null | undefined,
): boolean {
  const cur = gitBranchCurrent?.trim() || "";
  const reg = registryByNode?.[nodeId];
  const br = reg?.branch;
  return Boolean(cur && typeof br === "string" && br.trim() === cur);
}

/**
 * Tooltip for the outline Dev column: branch and registry / remote enrichment
 * (content that previously appeared under the task title as outline-meta).
 */
export function devColumnDetailTitle(
  nid: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitEnrichment: Record<string, Record<string, unknown>>,
  prHints: Record<string, string>,
): string | undefined {
  const lines: string[] = [];
  const reg = registryByNode?.[nid];
  const branch = typeof reg?.branch === "string" ? reg.branch.trim() : "";
  if (branch) lines.push(`Branch: ${branch}`);
  const started = reg?.started;
  if (started != null && String(started).trim()) {
    lines.push(`Started: ${String(started).trim()}`);
  }

  const g = gitEnrichment[nid];
  if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
    const t = (g.title as string | undefined)?.trim();
    const url = (g.url as string | undefined)?.trim();
    if (t) lines.push(`PR/MR: ${t}`);
    if (url) lines.push(url);
  } else if (g?.kind === "remote_tip") {
    const hint = (g.hint_line as string | undefined)?.trim();
    if (hint) lines.push(hint);
    else {
      const author = (g.author as string | undefined)?.trim();
      if (author && branch) lines.push(`${branch} · ${author}`);
    }
  } else if (g?.kind === "registry") {
    const hint = (g.hint_line as string | undefined)?.trim();
    if (hint) lines.push(hint);
  } else if (g?.hint_line) {
    const h = String(g.hint_line).trim();
    if (h) lines.push(h);
  }

  const ph = prHints[nid]?.replace(/<br>/g, " · ").trim();
  if (ph) lines.push(ph);

  const seen = new Set<string>();
  const deduped = lines.filter((l) => {
    const k = l.toLowerCase();
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return deduped.length ? deduped.join("\n") : undefined;
}

/** Bar uses checkout green only when status is not a terminal / frozen state. */
export function displayStatusAllowsCheckoutBar(
  displayStatus: string | undefined,
): boolean {
  const s = (displayStatus || "Not Started").toLowerCase();
  if (s === "complete" || s === "cancelled" || s === "blocked") return false;
  return true;
}
