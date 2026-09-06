import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchBrainstormSession,
  fetchBrainstormSlugs,
  getSettings,
  postBrainstormChat,
  postBrainstormPromote,
  postBrainstormTriage,
  putBrainstormSession,
  PmGuiConcurrencyError,
} from "../api";
import { ideaCounts, promotableCount } from "../brainstormIdeas";
import { hasLlmConfigured } from "../llmConfigured";
import { researchIsComplete } from "../researchProviders";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { BrainstormIdeaList } from "./BrainstormIdeaList";
import { ModalFrame } from "./ModalFrame";
import { ModalPersistStatusFooter } from "./ModalPersistStatusFooter";
import type { ModalRect } from "../modalRect";
import type {
  BrainstormChatMessage,
  BrainstormSession,
} from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Refresh the outline after ideas land in the graph. */
  onPromoted: () => void;
  // Brainstorm sits in the same window stack as the task dialogs, so it takes
  // the same chrome contract they do; see `EditModal` for the counterparts.
  /** Stacking order among open windows. */
  stackZIndex?: number;
  /** Do not dim or block the app when other windows are visible. */
  backdropPassThrough?: boolean;
  /** Only the front window should answer Escape. */
  closeOnEscape?: boolean;
  /** One-time rect for a freshly opened window, offset from the anchor. */
  spawnInitialRect?: ModalRect;
  editTileMode?: boolean;
  tileRect?: ModalRect | null;
  resumeFreeRect?: ModalRect | null;
  onTileToggle?: () => void;
  tileMode?: boolean;
  tileToggleDisabled?: boolean;
  /** Accent the title bar while this is the focused window. */
  titleBarActive?: boolean;
  onActivate?: () => void;
  onRectCommit?: (r: ModalRect) => void;
  minimized?: boolean;
  onMinimize?: () => void;
};

/** Roughly eight lines: enough to review a long message, not enough to bury the chat. */
const COMPOSER_MAX_PX = 160;

const MODE_HELP: Record<string, string> = {
  brainstorm:
    "Diverge: quantity over quality. The assistant is told to question the " +
    "topic first, then generate without ranking.",
  roadmap:
    "Converge: the assistant clusters, flags overlaps with existing nodes, " +
    "and recommends. Accepting is still your call.",
};

export function BrainstormDrawer({
  open,
  onClose,
  onPromoted,
  stackZIndex,
  backdropPassThrough,
  closeOnEscape,
  spawnInitialRect,
  editTileMode = false,
  tileRect = null,
  resumeFreeRect = null,
  onTileToggle,
  tileMode = false,
  tileToggleDisabled = false,
  titleBarActive,
  onActivate,
  onRectCommit,
  minimized = false,
  onMinimize,
}: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [session, setSession] = useState<BrainstormSession | null>(null);
  const [slugs, setSlugs] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [under, setUnder] = useState("");
  const [messages, setMessages] = useState<BrainstormChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const llm = (settings?.llm ?? {}) as Record<string, unknown>;
  const research = (settings?.research ?? null) as Record<
    string,
    unknown
  > | null;
  const llmReady = hasLlmConfigured(llm);
  // Not just "has a key": SearXNG has none, and the key field is named the
  // same for every provider now.
  const researchOn =
    Boolean(research?.enabled) &&
    researchIsComplete((research ?? {}) as Record<string, string>);

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof PmGuiConcurrencyError) {
        void onConcurrencyConflict();
        setMsg("Roadmap changed elsewhere; refreshed. Retry.");
        return;
      }
      setMsg(String(e instanceof Error ? e.message : e));
    },
    [onConcurrencyConflict],
  );

  useEffect(() => {
    if (!open) return;
    /* eslint-disable-next-line @eslint-react/set-state-in-effect -- reset on open */
    setMsg(null);
    const load = async () => {
      try {
        const [found, s] = await Promise.all([
          fetchBrainstormSlugs(),
          getSettings(),
        ]);
        setSlugs(found);
        setSettings(s);
        if (found.length > 0) {
          const loaded = await fetchBrainstormSession(found[0]);
          setSession(loaded);
          setTopic(loaded.topic);
          setUnder(loaded.under ?? "");
        }
      } catch (e: unknown) {
        fail(e);
      }
    };
    void load();
  }, [open, fail]);

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Grow the composer with what is typed, and shrink it back once the draft is
  // sent. Capped so a long paste cannot squeeze out the conversation above it;
  // past the cap the textarea scrolls instead.
  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_PX)}px`;
  }, [draft, open]);

  const openSession = async (slug: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const loaded = await fetchBrainstormSession(slug);
      setSession(loaded);
      setTopic(loaded.topic);
      setUnder(loaded.under ?? "");
      setMessages([]);
    } catch (e: unknown) {
      fail(e);
    }
    setBusy(false);
  };

  const saveSession = async (mode?: "brainstorm" | "roadmap") => {
    setBusy(true);
    setMsg(null);
    try {
      const saved = await putBrainstormSession({
        slug: session?.slug,
        topic,
        under: under.trim() || null,
        mode: mode ?? session?.mode ?? "brainstorm",
      });
      setSession(saved);
      setSlugs((prev) =>
        prev.includes(saved.slug) ? prev : [...prev, saved.slug].sort(),
      );
    } catch (e: unknown) {
      fail(e);
    }
    setBusy(false);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || !session || busy) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setDraft("");
    setBusy(true);
    setMsg(null);
    try {
      const reply = await postBrainstormChat({
        slug: session.slug,
        messages: next,
        llm,
        research,
      });
      setMessages(reply.messages);
      setSession(reply.session);
      const notes: string[] = [];
      if (reply.ideas.length > 0) {
        notes.push(`Captured ${reply.ideas.length} idea(s).`);
      }
      if (reply.searched.length > 0) {
        notes.push(`Searched: ${reply.searched.join("; ")}`);
      }
      setMsg(notes.length > 0 ? notes.join(" ") : null);
    } catch (e: unknown) {
      fail(e);
    }
    setBusy(false);
  };

  const triage = async (ideaId: string, status: string) => {
    if (!session) return;
    setBusy(true);
    try {
      setSession(
        await postBrainstormTriage({
          slug: session.slug,
          idea_id: ideaId,
          status,
        }),
      );
    } catch (e: unknown) {
      fail(e);
    }
    setBusy(false);
  };

  const promote = async (dryRun: boolean) => {
    if (!session) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await postBrainstormPromote({
        slug: session.slug,
        dry_run: dryRun,
      });
      setSession(r.session);
      const listed = r.promoted
        .map((p) => `${p.node_id} ${p.title}`)
        .join(", ");
      setMsg(
        r.promoted.length === 0
          ? "Nothing accepted to promote yet."
          : `${dryRun ? "Would add" : "Added"}: ${listed}`,
      );
      if (!dryRun && r.promoted.length > 0) onPromoted();
    } catch (e: unknown) {
      fail(e);
    }
    setBusy(false);
  };

  if (!open) return null;

  const counts = session ? ideaCounts(session.ideas) : null;
  const ready = session != null && llmReady;
  const promotable = session ? promotableCount(session.ideas) : 0;

  const titleBarAction =
    onTileToggle != null ? (
      <button
        type="button"
        className="modal-titlebar-tile-btn"
        aria-pressed={tileMode}
        disabled={tileToggleDisabled}
        title={
          tileMode
            ? "Restore windows to their positions before tiling"
            : "Tile open windows left to right"
        }
        aria-label={tileMode ? "Untile windows" : "Tile windows"}
        onClick={(e) => {
          e.stopPropagation();
          onTileToggle();
        }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {tileMode ? "Untile" : "Tile"}
      </button>
    ) : null;

  return (
    <ModalFrame
      title="Brainstorm"
      titleId="brainstorm-title"
      onClose={onClose}
      storageKey="brainstorm"
      bodyClassName="modal-body--brainstorm"
      initialRectOverride={spawnInitialRect}
      forcedRect={editTileMode && tileRect ? tileRect : null}
      resumeFreeRect={resumeFreeRect}
      suppressPositionPersist={editTileMode}
      titleBarActive={titleBarActive}
      onActivate={onActivate}
      onRectCommit={onRectCommit}
      titleBarAction={titleBarAction}
      zIndex={stackZIndex}
      backdropPassThrough={backdropPassThrough}
      closeOnEscape={closeOnEscape && !minimized}
      taskWindowChrome
      minimized={minimized}
      onMinimize={onMinimize}
      maximizeConstrained={editTileMode && Boolean(tileRect)}
      footer={
        <div className="brainstorm-footer">
          <ModalPersistStatusFooter msg={msg} persistMsg={busy ? "Working…" : ""} />
          {/* Rendered disabled rather than omitted before a session exists, so
              the footer keeps one height and the body below does not jump. */}
          <button
            type="button"
            disabled={!session || busy || promotable === 0}
            onClick={() => void promote(true)}
          >
            Preview promotion
          </button>
          <button
            type="button"
            disabled={!session || busy || promotable === 0}
            onClick={() => void promote(false)}
          >
            {promotable > 0 ? `Promote ${promotable} to roadmap` : "Promote to roadmap"}
          </button>
        </div>
      }
    >
      <section className="brainstorm-setup">
        <label>
          Topic
          <input
            type="text"
            value={topic}
            placeholder="How do we expand payments?"
            onChange={(e) => setTopic(e.target.value)}
          />
        </label>
        <label>
          Anchor node
          <input
            type="text"
            value={under}
            placeholder="M3 (blank = roadmap root)"
            onChange={(e) => setUnder(e.target.value)}
          />
        </label>
        <button type="button" disabled={busy} onClick={() => void saveSession()}>
          {session ? "Update session" : "Start session"}
        </button>
        {slugs.length > 1 ? (
          <label>
            Session
            <select
              value={session?.slug ?? ""}
              onChange={(e) => void openSession(e.target.value)}
            >
              {slugs.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </section>

      {!llmReady ? (
        <p className="brainstorm-warning">
          No model configured. Open Settings and set up an LLM backend before
          chatting.
        </p>
      ) : null}
      {!researchOn ? (
        <p className="outline-meta">
          Web search is off, so the assistant answers from the repository and
          its own knowledge. Configure it in Settings → Research.
        </p>
      ) : null}

      {session ? (
        <>
          <div className="brainstorm-modes">
            {(["brainstorm", "roadmap"] as const).map((m) => (
              <button
                key={m}
                type="button"
                disabled={busy}
                aria-pressed={session.mode === m}
                className={
                  session.mode === m ? "brainstorm-mode is-active" : "brainstorm-mode"
                }
                onClick={() => void saveSession(m)}
              >
                {m === "brainstorm" ? "Brainstorm" : "Roadmap"}
              </button>
            ))}
            <span className="outline-meta">{MODE_HELP[session.mode]}</span>
          </div>

          <div className="brainstorm-transcript" ref={transcriptRef}>
            {messages.length === 0 ? (
              <p className="outline-meta">
                {session.mode === "brainstorm"
                  ? "Say hello to begin. The assistant will question the topic before generating."
                  : "Ask the assistant to assess the ideas captured so far."}
              </p>
            ) : null}
            {messages.map((m, i) => (
              <div
                key={`${m.role}-${String(i)}`}
                className={`brainstorm-turn brainstorm-turn--${m.role}`}
              >
                {m.content}
              </div>
            ))}
          </div>

          <div className="brainstorm-compose">
            <textarea
              ref={composerRef}
              value={draft}
              rows={1}
              disabled={!ready || busy}
              placeholder="Message the assistant…  (Shift+Enter for a new line)"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" || e.shiftKey) return;
                // An IME uses Enter to accept the highlighted candidate, so
                // sending on it would post the sentence half-written.
                if (e.nativeEvent.isComposing) return;
                e.preventDefault();
                void send();
              }}
            />
            <button type="button" disabled={!ready || busy} onClick={() => void send()}>
              {busy ? "Working…" : "Send"}
            </button>
          </div>

          <section className="brainstorm-ideas">
            <h3>
              Ideas{" "}
              {counts ? (
                <span className="outline-meta">
                  {session.ideas.length} total · {counts.accepted} accepted ·{" "}
                  {counts.rejected} rejected · {counts.promoted} on the roadmap
                </span>
              ) : null}
            </h3>
            <BrainstormIdeaList
              ideas={session.ideas}
              busy={busy}
              onTriage={(id, status) => void triage(id, status)}
            />
          </section>
        </>
      ) : null}
    </ModalFrame>
  );
}
