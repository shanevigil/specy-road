import { describe, expect, it, vi } from "vitest";

import { PmGuiConcurrencyError } from "./api";
import { runMutationWithAutoffRetry } from "./runMutationWithAutoffRetry";

describe("runMutationWithAutoffRetry", () => {
  it("returns ok when the mutation succeeds first try (no retry, no snapshot)", async () => {
    const mutation = vi.fn(async () => undefined);
    const loadSnapshot = vi.fn(async () => undefined);
    const out = await runMutationWithAutoffRetry(mutation, loadSnapshot);
    expect(out).toBe("ok");
    expect(mutation).toHaveBeenCalledTimes(1);
    expect(loadSnapshot).toHaveBeenCalledTimes(0);
  });

  it("transparently retries once when the 412 is retryable, then succeeds", async () => {
    const mutation = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(
        new PmGuiConcurrencyError("stale", 412, 12345, true),
      )
      .mockResolvedValueOnce(undefined);
    const loadSnapshot = vi.fn(async () => undefined);

    const out = await runMutationWithAutoffRetry(mutation, loadSnapshot);

    expect(out).toBe("ok");
    expect(mutation).toHaveBeenCalledTimes(2);
    // Snapshot must be refreshed BEFORE the retry so the next mutation
    // attaches the fresh fingerprint via lastFingerprintRef.
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
  });

  it("returns conflict for non-retryable 412 (banner path)", async () => {
    const mutation = vi
      .fn<() => Promise<void>>()
      .mockRejectedValue(
        new PmGuiConcurrencyError("stale", 412, 99999, false),
      );
    const loadSnapshot = vi.fn(async () => undefined);

    const out = await runMutationWithAutoffRetry(mutation, loadSnapshot);

    expect(out).toBe("conflict");
    // No retry attempted on non-retryable conflicts.
    expect(mutation).toHaveBeenCalledTimes(1);
    // Snapshot still refreshes so the user sees the latest data behind the banner.
    expect(loadSnapshot).toHaveBeenCalledTimes(1);
  });

  it("returns conflict for 428 (header missing — never retryable)", async () => {
    const mutation = vi
      .fn<() => Promise<void>>()
      .mockRejectedValue(new PmGuiConcurrencyError("missing", 428));
    const loadSnapshot = vi.fn(async () => undefined);
    const out = await runMutationWithAutoffRetry(mutation, loadSnapshot);
    expect(out).toBe("conflict");
    expect(mutation).toHaveBeenCalledTimes(1);
  });

  it("caps at one retry: a second retryable 412 still surfaces as conflict", async () => {
    const mutation = vi
      .fn<() => Promise<void>>()
      .mockRejectedValue(
        new PmGuiConcurrencyError("stale-twice", 412, 0, true),
      );
    const loadSnapshot = vi.fn(async () => undefined);

    const out = await runMutationWithAutoffRetry(mutation, loadSnapshot);

    expect(out).toBe("conflict");
    expect(mutation).toHaveBeenCalledTimes(2); // original + 1 retry, then stop
    expect(loadSnapshot).toHaveBeenCalledTimes(2); // pre-retry refresh + final refresh
  });

  it("rethrows non-PmGuiConcurrencyError errors", async () => {
    const mutation = vi
      .fn<() => Promise<void>>()
      .mockRejectedValue(new Error("network down"));
    const loadSnapshot = vi.fn(async () => undefined);

    await expect(
      runMutationWithAutoffRetry(mutation, loadSnapshot),
    ).rejects.toThrow(/network down/);
    expect(loadSnapshot).toHaveBeenCalledTimes(0);
  });
});
