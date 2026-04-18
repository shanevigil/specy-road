/**
 * Browser-only PM GUI preferences (theme, splitter, refresh, outline toggles).
 * Namespaced by repo_id (SHA-256 hex of resolved repo root, same as gui-settings.json keys).
 * Legacy keys (no suffix) are read once and copied into namespaced keys when repo_id is known.
 */

export const BROWSER_PREF_KEYS = {
  splitPct: "pmGanttSplitPct",
  refreshSec: "pmGanttRefreshSec",
  showInheritedDeps: "pmGanttShowInheritedDeps",
  highlightDepChain: "pmGanttHighlightDepChain",
  themeMode: "pmGanttThemeMode",
} as const;

function namespacedKey(baseKey: string, repoId: string | null): string {
  return repoId ? `${baseKey}:${repoId}` : baseKey;
}

/** Read a value; when repoId is set, prefers namespaced storage and migrates from legacy if needed. */
export function readBrowserPref(
  baseKey: string,
  repoId: string | null,
): string | null {
  try {
    const ns = namespacedKey(baseKey, repoId);
    let v = localStorage.getItem(ns);
    if (v === null && repoId) {
      v = localStorage.getItem(baseKey);
      if (v !== null) {
        localStorage.setItem(ns, v);
      }
    }
    return v;
  } catch {
    return null;
  }
}

export function writeBrowserPref(
  baseKey: string,
  repoId: string | null,
  value: string,
): void {
  try {
    localStorage.setItem(namespacedKey(baseKey, repoId), value);
  } catch {
    /* ignore */
  }
}

/** Read legacy global key only (before `/api/repo` returns `repo_id`). */
export function readLegacyBrowserPref(baseKey: string): string | null {
  try {
    return localStorage.getItem(baseKey);
  } catch {
    return null;
  }
}
