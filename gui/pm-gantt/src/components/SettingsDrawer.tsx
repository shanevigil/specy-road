import { useEffect, useState } from "react";
import { getSettings, putSettings } from "../api";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SettingsDrawer({ open, onClose }: Props) {
  const [llm, setLlm] = useState<Record<string, string>>({});
  const [git, setGit] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
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
      .catch((e: unknown) => setMsg(String(e)));
  }, [open]);

  if (!open) return null;

  const save = async () => {
    try {
      await putSettings({
        llm: {
          backend: llm.backend || "openai",
          openai_api_key: llm.openai_api_key || "",
          openai_model: llm.openai_model || "",
          openai_base_url: llm.openai_base_url || "",
          azure_endpoint: llm.azure_endpoint || "",
          azure_api_key: llm.azure_api_key || "",
          azure_deployment: llm.azure_deployment || "",
          azure_api_version: llm.azure_api_version || "2024-02-15-preview",
        },
        git_remote: {
          provider: git.provider || "github",
          repo: git.repo || "",
          token: git.token || "",
          base_url: git.base_url || "",
        },
      });
      setMsg("Saved.");
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  return (
    <>
      <div
        className="drawer-backdrop"
        role="presentation"
        onMouseDown={onClose}
      />
      <aside className="drawer" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Settings</h2>
        <p className="outline-meta">
          Stored in ~/.specy-road/gui-settings.json (same as Streamlit PM GUI).
        </p>
        {msg ? <p>{msg}</p> : null}
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
          <input
            value={llm.backend || ""}
            onChange={(e) => setLlm({ ...llm, backend: e.target.value })}
          />
        </label>
        <label>
          OpenAI API key
          <input
            type="password"
            value={llm.openai_api_key || ""}
            onChange={(e) => setLlm({ ...llm, openai_api_key: e.target.value })}
          />
        </label>
        <label>
          Model
          <input
            value={llm.openai_model || ""}
            onChange={(e) => setLlm({ ...llm, openai_model: e.target.value })}
          />
        </label>
        <div className="modal-actions" style={{ marginTop: "1rem" }}>
          <button type="button" onClick={onClose}>
            Close
          </button>
          <button type="button" onClick={save}>
            Save
          </button>
        </div>
      </aside>
    </>
  );
}
