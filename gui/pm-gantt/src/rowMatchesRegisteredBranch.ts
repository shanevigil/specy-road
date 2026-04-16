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
 * Dev column cell text: owner → forge PR/MR author → remote tip author
 * → local `git config user.name` when current branch matches registered branch.
 * Does not show branch names; use {@link devColumnDetailTitle} on hover for branch and hints.
 */
export function devColumnLabel(
  nid: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitEnrichment: Record<string, Record<string, unknown>>,
  gitBranchCurrent: string | null | undefined,
  gitUserName: string | null | undefined,
): string {
  const e = registryByNode?.[nid];
  const owner = e?.owner;
  if (typeof owner === "string" && owner.trim()) return owner.trim();
  const g = gitEnrichment[nid];
  if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
    const author = g.author as string | undefined;
    if (author) return `@${author}`;
  }
  if (g?.kind === "remote_tip") {
    const a = g.author as string | undefined;
    if (typeof a === "string" && a.trim()) return a.trim();
  }
  const regBranch = e?.branch;
  const curBr = gitBranchCurrent?.trim() || "";
  const regBrStr = typeof regBranch === "string" ? regBranch.trim() : "";
  if (curBr && regBrStr && curBr === regBrStr) {
    const local = gitUserName?.trim();
    if (local) return local;
  }
  return "—";
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
  const startedTrim =
    started != null && String(started).trim() ? String(started).trim() : "";
  if (startedTrim) {
    lines.push(`Started: ${startedTrim}`);
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
    const redundant =
      Boolean(hint) &&
      Boolean(branch) &&
      (hint === branch ||
        (startedTrim.length > 0 && hint === `${branch} · ${startedTrim}`));
    if (hint && !redundant) lines.push(hint);
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
  if (s === "complete" || s === "blocked") return false;
  return true;
}

/** PM outline / Gantt display label for active work (includes registry-promoted In Progress). */
export function isDisplayStatusInProgress(
  displayStatus: string | undefined,
): boolean {
  return (displayStatus || "").trim().toLowerCase() === "in progress";
}

/** True when registry lists a non-empty feature branch for this node (`feature/rm-*`, etc.). */
export function hasRegisteredFeatureBranch(
  nodeId: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
): boolean {
  const br = registryByNode?.[nodeId]?.branch;
  return typeof br === "string" && br.trim().length > 0;
}

/**
 * Gantt green bar: active feature work tied to a registered branch.
 * Requires a dedicated branch in registry plus in-progress display (or current checkout).
 * Terminal display states (Complete, Blocked) are excluded — merged work
 * should move the roadmap off those or clear registration; we do not infer merge from git here.
 */
export function showActiveFeatureBranchBar(
  nodeId: string,
  displayStatus: string | undefined,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitCheckoutById: Record<string, boolean> | undefined,
): boolean {
  if (!displayStatusAllowsCheckoutBar(displayStatus)) return false;
  if (!hasRegisteredFeatureBranch(nodeId, registryByNode)) return false;
  const checkout = Boolean(gitCheckoutById?.[nodeId]);
  const inProgress = isDisplayStatusInProgress(displayStatus);
  return checkout || inProgress;
}
