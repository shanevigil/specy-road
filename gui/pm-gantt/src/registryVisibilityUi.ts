import type { RegistryVisibilityPayload } from "./types";

export function shouldShowRegistryBanner(
  v: RegistryVisibilityPayload | undefined,
): boolean {
  if (!v) return false;
  return (
    v.on_integration_branch &&
    v.local_registry_entry_count === 0 &&
    v.remote_feature_rm_ref_count > 0
  );
}
