import { describe, expect, it } from "vitest";
import { shouldShowRegistryBanner } from "./registryVisibilityUi";

describe("shouldShowRegistryBanner", () => {
  it("returns false when payload missing", () => {
    expect(shouldShowRegistryBanner(undefined)).toBe(false);
  });

  it("returns true on integration branch with empty registry and remote feature refs", () => {
    expect(
      shouldShowRegistryBanner({
        on_integration_branch: true,
        local_registry_entry_count: 0,
        remote_feature_rm_ref_count: 1,
      }),
    ).toBe(true);
  });

  it("returns false when local registry has entries", () => {
    expect(
      shouldShowRegistryBanner({
        on_integration_branch: true,
        local_registry_entry_count: 1,
        remote_feature_rm_ref_count: 3,
      }),
    ).toBe(false);
  });

  it("returns false when not on integration branch", () => {
    expect(
      shouldShowRegistryBanner({
        on_integration_branch: false,
        local_registry_entry_count: 0,
        remote_feature_rm_ref_count: 2,
      }),
    ).toBe(false);
  });

  it("returns false when no remote feature refs", () => {
    expect(
      shouldShowRegistryBanner({
        on_integration_branch: true,
        local_registry_entry_count: 0,
        remote_feature_rm_ref_count: 0,
      }),
    ).toBe(false);
  });
});
