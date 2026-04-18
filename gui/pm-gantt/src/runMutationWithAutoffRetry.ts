import { PmGuiConcurrencyError } from "./api";

/**
 * Run a roadmap-mutating fetch with one transparent retry on a "retryable"
 * 412.
 *
 * The server's lenient concurrency guard (enabled by
 * ``SPECY_ROAD_GUI_PM_AUTO_RETRY_AUTOFF=1``) returns 412 with
 * ``retryable: true`` when the only delta between the client's token and
 * the on-disk fingerprint is the auto-FF / auto-fetch the GET endpoints
 * ran on behalf of the same session. In that case the on-disk state is
 * canonical, so we refresh the snapshot once (which writes the fresh
 * fingerprint into ``lastFingerprintRef``) and re-run the same mutation.
 *
 * If the retry also fails — or the original failure is not retryable —
 * the caller's banner path runs.
 *
 * Pure function (no React state); intentionally testable in isolation.
 *
 * @returns ``"ok"`` on success, ``"conflict"`` when the conflict was not
 *   recoverable, or rethrows non-PmGuiConcurrencyError errors.
 */
export async function runMutationWithAutoffRetry(
  mutation: () => Promise<void>,
  loadSnapshot: () => Promise<void>,
): Promise<"ok" | "conflict"> {
  let attempted = false;
  while (true) {
    try {
      await mutation();
      return "ok";
    } catch (e: unknown) {
      if (!(e instanceof PmGuiConcurrencyError)) throw e;
      if (e.retryable && !attempted) {
        attempted = true;
        await loadSnapshot();
        continue;
      }
      // Either non-retryable, or we already retried once.
      await loadSnapshot();
      return "conflict";
    }
  }
}
