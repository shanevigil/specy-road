import { useEffect, useRef, useState } from "react";
import { getSettings, putSettings, testLlmSettings } from "../api";
import { ModalFrame } from "./ModalFrame";

type Props = {
  open: boolean;
  onClose: () => void;
};

const BACKENDS = ["openai", "azure", "compatible", "anthropic"] as const;

function normalizeBackend(raw: string): string {
  const l = raw.trim().toLowerCase();
  return BACKENDS.includes(l as (typeof BACKENDS)[number]) ? l : "openai";
}

function buildLlmPayload(llm: Record<string, string>) {
  return {
    backend: normalizeBackend(llm.backend || "openai"),
    openai_api_key: llm.openai_api_key || "",
    openai_model: llm.openai_model || "",
    openai_base_url: llm.openai_base_url || "",
    azure_endpoint: llm.azure_endpoint || "",
    azure_api_key: llm.azure_api_key || "",
    azure_deployment: llm.azure_deployment || "",
    azure_api_version: llm.azure_api_version || "2024-02-15-preview",
    anthropic_api_key: llm.anthropic_api_key || "",
    anthropic_model: llm.anthropic_model || "",
  };
}

export function SettingsDrawer({ open, onClose }: Props) {
  const [llm, setLlm] = useState<Record<string, string>>({});
  const [git, setGit] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const skipAutosave = useRef(true);

  useEffect(() => {
    if (!open) return;
    skipAutosave.current = true;
    /* eslint-disable react-hooks/set-state-in-effect -- reset when opening */
    setMsg(null);
    setPersistMsg(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    getSettings()
      .then((s) => {
        const l = (s.llm as Record<string, unknown>) || {};
        const g = (s.git_remote as Record<string, unknown>) || {};
        setLlm(
          Object.fromEntries(
            Object.entries(l).map(([k, v]) => [k, v == null ? "" : String(v)]),
          ),
        );
        setGit(
          Object.fromEntries(
            Object.entries(g).map(([k, v]) => [k, v == null ? "" : String(v)]),
          ),
        );
      })
      .catch((e: unknown) => setMsg(String(e)))
      .finally(() => {
        queueMicrotask(() => {
          skipAutosave.current = false;
        });
      });
  }, [open]);

  useEffect(() => {
    if (!open || skipAutosave.current) return;
    /* eslint-disable-next-line react-hooks/set-state-in-effect -- autosave status */
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      putSettings({
        llm: buildLlmPayload(llm),
        git_remote: {
          provider: git.provider || "github",
          repo: git.repo || "",
          token: git.token || "",
          base_url: git.base_url || "",
        },
      })
        .then(() => {
          setPersistMsg("Saved.");
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setMsg(String(e));
          setPersistMsg(null);
        });
    }, 800);
    return () => window.clearTimeout(t);
  }, [llm, git, open]);

  if (!open) return null;

  const backend = normalizeBackend(llm.backend || "openai");

  const testLlm = async () => {
    setMsg(null);
    try {
      const out = await testLlmSettings(buildLlmPayload(llm));
      setMsg(out.message || "LLM endpoint responded.");
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const footer = (
    <>
      <span>{persistMsg || msg}</span>
      <div className="modal-footer-actions">
        <button type="button" onClick={() => void testLlm()}>
          Test LLM
        </button>
      </div>
    </>
  );

  return (
    <ModalFrame
      title="Settings"
      titleId="settings-title"
      onClose={onClose}
      storageKey="settings"
      footer={footer}
    >
      <p className="outline-meta">
        Stored in ~/.specy-road/gui-settings.json (same as Streamlit PM GUI).
        API keys are stored with simple obfuscation on disk, not plain text.
        Changes save automatically.
      </p>
      <h3>Git remote</h3>
      <label>
        Provider
        <select
          value={git.provider || "github"}
          onChange={(e) => setGit({ ...git, provider: e.target.value })}
        >
          <option value="github">github</option>
          <option value="gitlab">gitlab</option>
          <option value="custom">custom (GitLab)</option>
        </select>
      </label>
      <label>
        Repo (owner/name)
        <input
          value={git.repo || ""}
          onChange={(e) => setGit({ ...git, repo: e.target.value })}
        />
      </label>
      <label>
        Token
        <input
          type="password"
          value={git.token || ""}
          onChange={(e) => setGit({ ...git, token: e.target.value })}
          autoComplete="off"
        />
      </label>
      <label>
        Base URL (GitLab)
        <input
          value={git.base_url || ""}
          onChange={(e) => setGit({ ...git, base_url: e.target.value })}
          placeholder="https://gitlab.com"
        />
      </label>
      <h3>LLM (optional)</h3>
      <label>
        Backend
        <select
          value={backend}
          onChange={(e) => setLlm({ ...llm, backend: e.target.value })}
        >
          <option value="openai">openai</option>
          <option value="azure">azure</option>
          <option value="compatible">compatible (OpenAI-compatible API)</option>
          <option value="anthropic">anthropic (Claude)</option>
        </select>
      </label>
      {backend === "azure" ? (
        <>
          <label>
            Azure endpoint
            <input
              value={llm.azure_endpoint || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_endpoint: e.target.value })
              }
            />
          </label>
          <label>
            Azure API key
            <input
              type="password"
              value={llm.azure_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Deployment name
            <input
              value={llm.azure_deployment || ""}
              onChange={(e) =>
                setLlm({ ...llm, azure_deployment: e.target.value })
              }
            />
          </label>
          <label>
            API version
            <input
              value={llm.azure_api_version || "2024-02-15-preview"}
              onChange={(e) =>
                setLlm({ ...llm, azure_api_version: e.target.value })
              }
            />
          </label>
        </>
      ) : null}
      {backend === "anthropic" ? (
        <>
          <label>
            Anthropic API key
            <input
              type="password"
              value={llm.anthropic_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, anthropic_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Model
            <input
              value={llm.anthropic_model || ""}
              onChange={(e) =>
                setLlm({ ...llm, anthropic_model: e.target.value })
              }
              placeholder="claude-sonnet-4-20250514"
            />
          </label>
        </>
      ) : null}
      {backend === "openai" || backend === "compatible" ? (
        <>
          <label>
            API key
            <input
              type="password"
              value={llm.openai_api_key || ""}
              onChange={(e) =>
                setLlm({ ...llm, openai_api_key: e.target.value })
              }
              autoComplete="off"
            />
          </label>
          <label>
            Model
            <input
              value={llm.openai_model || ""}
              onChange={(e) =>
                setLlm({ ...llm, openai_model: e.target.value })
              }
              placeholder="gpt-4o-mini"
            />
          </label>
          {backend === "compatible" ? (
            <label>
              Base URL
              <input
                value={llm.openai_base_url || ""}
                onChange={(e) =>
                  setLlm({ ...llm, openai_base_url: e.target.value })
                }
              />
            </label>
          ) : null}
        </>
      ) : null}
    </ModalFrame>
  );
}
