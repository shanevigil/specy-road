import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  fetchWorkspaceFiles,
  uploadSharedFile,
  type WorkspaceFileEntry,
} from "../api";
import { ModalFrame } from "./ModalFrame";

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SharedDocsDrawer({ open, onClose }: Props) {
  const [files, setFiles] = useState<WorkspaceFileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [subpath, setSubpath] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const subId = useId();

  const refresh = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const r = await fetchWorkspaceFiles("shared");
      setFiles(r.files);
    } catch (e: unknown) {
      setMsg(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  const onPickFile = () => fileInputRef.current?.click();

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files;
    if (!list?.length) return;
    const f = list[0];
    if (!f) return;
    setUploading(true);
    setMsg(null);
    try {
      await uploadSharedFile(f, subpath.trim() || undefined);
      setMsg(`Uploaded: ${f.name}`);
      window.setTimeout(() => setMsg(null), 3500);
      await refresh();
    } catch (err: unknown) {
      setMsg(String(err));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  if (!open) return null;

  return (
    <ModalFrame
      title="Shared docs"
      titleId="shared-docs-title"
      onClose={onClose}
      storageKey="shared-docs"
      footer={msg ? <span>{msg}</span> : null}
      bodyClassName="modal-body--workspace modal-body--shared-docs"
    >
      <p className="outline-meta">
        Upload files into the repo <code>shared/</code> tree (contracts, assets,
        etc.). Paths stay under <code>shared/</code> only.
      </p>
      <div className="workspace-toolbar">
        <label className="workspace-subpath-label" htmlFor={subId}>
          Subfolder under <code>shared/</code> (optional)
        </label>
        <input
          id={subId}
          type="text"
          className="workspace-subpath-input"
          placeholder="e.g. contracts"
          value={subpath}
          onChange={(e) => setSubpath(e.target.value)}
          disabled={uploading}
        />
        <input
          ref={fileInputRef}
          type="file"
          className="workspace-file-input-hidden"
          onChange={(e) => void onFileChange(e)}
        />
        <button
          type="button"
          className="workspace-upload-btn"
          disabled={uploading}
          onClick={onPickFile}
        >
          {uploading ? "Uploading…" : "Upload file"}
        </button>
      </div>
      {loading ? <p>Loading…</p> : null}
      <div className="workspace-file-table-wrap">
        <table className="workspace-file-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Path</th>
              <th className="workspace-col-size">Size</th>
            </tr>
          </thead>
          <tbody>
            {files.length === 0 && !loading ? (
              <tr>
                <td colSpan={3} className="workspace-empty">
                  No files yet — upload one above.
                </td>
              </tr>
            ) : (
              files.map((f) => (
                <tr key={f.path}>
                  <td>{f.name}</td>
                  <td>
                    <code className="workspace-path-code">{f.path}</code>
                  </td>
                  <td className="workspace-col-size">{fmtBytes(f.bytes)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </ModalFrame>
  );
}
