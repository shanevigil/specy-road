import { FileChangedOnDiskError, PmGuiConcurrencyError } from "./api";

/**
 * One save at a time for an open task dialog (title, gate status, acceptance
 * criteria, planning sheet).
 *
 * The dialog used to autosave from three independent effects that each
 * re-armed whenever the roadmap refreshed. A refresh while a title PATCH
 * was in flight sent a second PATCH for the same rename, the two collided
 * on the server, and sheet text typed meanwhile went to the old path or
 * was overwritten by the reload, with no error shown.
 *
 * This queue keeps the wanted and the saved value of each field, debounces
 * edits, and runs at most one request at a time in a fixed order: title,
 * gate status, acceptance, then the sheet. A title save is followed by re-reading the
 * sheet path (a title change renames the sheet) and a roadmap refresh (new
 * mutation fingerprint) before any sheet save goes out. A value already
 * requested is never requested again, so re-renders cannot duplicate a save.
 * A failed save stays reported until the user edits that field again.
 */

export type SaveKind = "title" | "status" | "acceptance" | "sheet";

export type SaveStatus =
  | { state: "idle" }
  | { state: "saving" }
  | { state: "saved" }
  | { state: "error"; message: string };

export type SaveSnapshot = {
  title: string;
  status: string;
  /** Criteria joined by newlines (the PATCH value). */
  acceptance: string;
  path: string | null;
  content: string;
};

export type SaveQueueDeps = {
  patchNode: (pairs: { key: string; value: string }[]) => Promise<void>;
  /** Re-read this node's sheet path (after a rename) and prime its content hash. */
  resolveSheetPath: () => Promise<string | null>;
  saveSheet: (path: string, content: string) => Promise<void>;
  /** Reload the roadmap snapshot; refreshes the mutation fingerprint. */
  refresh: () => Promise<void>;
  onStatus: (s: SaveStatus) => void;
  onSheetPathAdopted: (path: string | null) => void;
};

export const SAVE_DEBOUNCE_MS: Record<SaveKind, number> = {
  title: 500,
  status: 500,
  acceptance: 500,
  sheet: 600,
};

const ORDER: SaveKind[] = ["title", "status", "acceptance", "sheet"];

const LABEL: Record<SaveKind, string> = {
  title: "Title",
  status: "Gate status",
  acceptance: "Acceptance",
  sheet: "Planning sheet",
};

/** Footer text for a save that did not reach disk. */
export function describeSaveFailure(kind: SaveKind, e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const msg = raw.trim().replace(/[.\s]+$/, "") || "unknown error";
  if (e instanceof FileChangedOnDiskError) return `${LABEL[kind]} not saved: ${msg}.`;
  const hint =
    kind === "sheet"
      ? "Your text is still in the editor; edit it again to retry, or copy it before closing."
      : "Edit it again to retry.";
  return `${LABEL[kind]} not saved: ${msg}. ${hint}`;
}

type Wanted = Record<SaveKind, string | null>;

export class EditModalSaveQueue {
  private readonly deps: SaveQueueDeps;
  private saved: SaveSnapshot;
  private wanted: Wanted = { title: null, status: null, acceptance: null, sheet: null };
  private readonly failed = new Map<SaveKind, { value: string; message: string }>();
  private readonly timers = new Map<SaveKind, ReturnType<typeof setTimeout>>();
  private running: Promise<void> | null = null;

  constructor(deps: SaveQueueDeps, initial: SaveSnapshot) {
    this.deps = deps;
    this.saved = { ...initial };
  }

  get sheetPath(): string | null {
    return this.saved.path;
  }

  /** Values loaded from disk: nothing pending, no reported failure. */
  reset(s: SaveSnapshot): void {
    for (const k of ORDER) this.cancelTimer(k);
    this.saved = { ...s };
    this.wanted = { title: null, status: null, acceptance: null, sheet: null };
    this.failed.clear();
  }

  /** The sheet was (re)loaded from disk at ``path``. */
  resetSheet(path: string | null, content: string): void {
    this.cancelTimer("sheet");
    this.saved = { ...this.saved, path, content };
    this.wanted.sheet = null;
    this.failed.delete("sheet");
  }

  /** The sheet moved on disk (rename elsewhere); unsaved text goes to ``path``. */
  adoptSheetPath(path: string | null): void {
    this.saved = { ...this.saved, path };
  }

  hasUnsavedSheet(): boolean {
    return this.wanted.sheet !== null && this.wanted.sheet !== this.saved.content;
  }

  /** ``blocked``: the title is invalid (taken or blank); drop any pending title save. */
  setTitle(value: string, blocked = false): void {
    if (blocked || !value.trim()) {
      this.cancelTimer("title");
      this.wanted.title = null;
      this.failed.delete("title");
      this.emitSettled();
      return;
    }
    this.request("title", value);
  }

  setStatus(value: string): void {
    this.request("status", value);
  }

  /** ``value``: the criteria joined by newlines (acceptanceEdit). */
  setAcceptance(value: string): void {
    this.request("acceptance", value);
  }

  setContent(value: string): void {
    this.request("sheet", value);
  }

  /** Send every debounced edit now (dialog closing). */
  flush(): Promise<void> {
    for (const k of ORDER) this.cancelTimer(k);
    return this.kick();
  }

  /** Resolves when no request is in flight. */
  whenIdle(): Promise<void> {
    return this.running ?? Promise.resolve();
  }

  private savedOf(kind: SaveKind): string | null {
    if (kind === "title") return this.saved.title;
    if (kind === "status") return this.saved.status;
    if (kind === "acceptance") return this.saved.acceptance;
    return this.saved.content;
  }

  private setSaved(kind: SaveKind, value: string): void {
    if (kind === "title") this.saved.title = value;
    else if (kind === "status") this.saved.status = value;
    else if (kind === "acceptance") this.saved.acceptance = value;
    else this.saved.content = value;
    if (this.wanted[kind] === value) this.wanted[kind] = null;
  }

  private request(kind: SaveKind, value: string): void {
    if (this.wanted[kind] === value) return;
    if (this.wanted[kind] === null && value === this.savedOf(kind)) return;
    this.wanted[kind] = value;
    this.failed.delete(kind);
    this.cancelTimer(kind);
    this.timers.set(
      kind,
      setTimeout(() => {
        this.timers.delete(kind);
        void this.kick();
      }, SAVE_DEBOUNCE_MS[kind]),
    );
    this.deps.onStatus({ state: "saving" });
  }

  private cancelTimer(kind: SaveKind): void {
    const t = this.timers.get(kind);
    if (t !== undefined) clearTimeout(t);
    this.timers.delete(kind);
  }

  private isPending(kind: SaveKind): boolean {
    if (this.timers.has(kind)) return false;
    const w = this.wanted[kind];
    if (w === null || w === this.savedOf(kind)) return false;
    if (kind === "sheet" && !this.saved.path) return false;
    return this.failed.get(kind)?.value !== w;
  }

  private nextKind(): SaveKind | null {
    return ORDER.find((k) => this.isPending(k)) ?? null;
  }

  private kick(): Promise<void> {
    if (!this.running) {
      this.running = this.pump().finally(() => {
        this.running = null;
        if (this.nextKind()) void this.kick();
      });
    }
    return this.running;
  }

  private async pump(): Promise<void> {
    for (let kind = this.nextKind(); kind; kind = this.nextKind()) {
      const value = this.wanted[kind] as string;
      this.deps.onStatus({ state: "saving" });
      try {
        await this.runStep(kind, value);
      } catch (e: unknown) {
        this.failed.set(kind, { value, message: describeSaveFailure(kind, e) });
      }
    }
    this.emitSettled(true);
  }

  /** One transparent retry after a 412: our own earlier save, or another tab, moved the token. */
  private async withRetry(send: () => Promise<void>): Promise<void> {
    try {
      await send();
    } catch (e: unknown) {
      if (!(e instanceof PmGuiConcurrencyError)) throw e;
      await this.deps.refresh();
      await send();
    }
  }

  private async runStep(kind: SaveKind, value: string): Promise<void> {
    if (kind === "sheet") {
      const path = this.saved.path as string;
      await this.withRetry(() => this.deps.saveSheet(path, value));
      this.setSaved(kind, value);
      void this.deps.refresh().catch(() => undefined);
      return;
    }
    await this.withRetry(() => this.deps.patchNode([{ key: kind, value }]));
    this.setSaved(kind, value);
    if (kind === "title") await this.adoptRenamedSheet();
    // The PATCH moved the mutation fingerprint; the next save needs the new one.
    await this.deps.refresh().catch(() => undefined);
  }

  private async adoptRenamedSheet(): Promise<void> {
    let path: string | null;
    try {
      path = await this.deps.resolveSheetPath();
    } catch (e: unknown) {
      // Without the new path a sheet save would recreate the old file: hold it.
      if (this.hasUnsavedSheet()) {
        const held = this.wanted.sheet as string;
        this.failed.set("sheet", { value: held, message: describeSaveFailure("sheet", e) });
      }
      return;
    }
    if (path !== this.saved.path) {
      this.saved = { ...this.saved, path };
      this.deps.onSheetPathAdopted(path);
    }
  }

  private emitSettled(fromPump = false): void {
    if (this.failed.size > 0) {
      const message = ORDER.map((k) => this.failed.get(k)?.message)
        .filter(Boolean)
        .join(" ");
      this.deps.onStatus({ state: "error", message });
      return;
    }
    const busy =
      this.timers.size > 0 ||
      (!fromPump && this.running !== null) ||
      this.nextKind() !== null;
    this.deps.onStatus(busy ? { state: "saving" } : { state: "saved" });
  }
}
