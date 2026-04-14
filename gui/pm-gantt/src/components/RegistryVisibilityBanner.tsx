import { useState } from "react";
import type { RegistryVisibilityPayload } from "../types";
import { shouldShowRegistryBanner } from "../registryVisibilityUi";

const STORAGE_PREFIX = "pmGanttRegistryBannerDismissed:";

function dismissedStorageKey(repoRoot: string): string {
  return `${STORAGE_PREFIX}${repoRoot}`;
}

function readDismissedFromSession(repoRoot: string): boolean {
  if (!repoRoot) return false;
  try {
    return sessionStorage.getItem(dismissedStorageKey(repoRoot)) === "1";
  } catch {
    return false;
  }
}

type Props = {
  repoRoot: string;
  visibility: RegistryVisibilityPayload | undefined;
};

export function RegistryVisibilityBanner({ repoRoot, visibility }: Props) {
  const [dismissed, setDismissed] = useState(() =>
    readDismissedFromSession(repoRoot),
  );

  const show =
    Boolean(repoRoot) &&
    shouldShowRegistryBanner(visibility) &&
    !dismissed;

  if (!show) return null;

  const onDismiss = () => {
    try {
      sessionStorage.setItem(dismissedStorageKey(repoRoot), "1");
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  return (
    <div
      className="registry-visibility-banner"
      role="status"
      aria-live="polite"
    >
      <div className="registry-visibility-banner-body">
        <strong className="registry-visibility-banner-title">
          Registry not visible on this branch
        </strong>
        <p className="registry-visibility-banner-text">
          Active{" "}
          <code className="registry-visibility-banner-code">
            roadmap/registry.yaml
          </code>{" "}
          entries often live only on{" "}
          <code className="registry-visibility-banner-code">feature/rm-*</code>{" "}
          commits until merge. To see the green outline accent and registry-driven
          hints for in-flight work, check out that feature branch, use a second
          git worktree on it, or point this GUI at a clone where that branch is
          checked out. Run <code className="registry-visibility-banner-code">git fetch</code>{" "}
          so remote-tracking refs stay current.
        </p>
      </div>
      <button
        type="button"
        className="registry-visibility-banner-dismiss"
        onClick={onDismiss}
        aria-label="Dismiss registry visibility notice"
      >
        Dismiss
      </button>
    </div>
  );
}
