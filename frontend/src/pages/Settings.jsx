import { FolderOpen, HardDrive, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner, Toast } from "../components/UI";
import { useAuth } from "../context/AuthContext";

export default function Settings() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const [storage, setStorage] = useState(null);
  const [layout, setLayout] = useState("");
  const [savingLayout, setSavingLayout] = useState(false);

  useEffect(() => {
    api.get("/storage").then((s) => {
      setStorage(s);
      setLayout(s.layout);
    }).catch(() => {});
  }, []);

  async function saveLayout(e) {
    e.preventDefault();
    setSavingLayout(true);
    try {
      const updated = await api.patch("/storage", { layout });
      setStorage(updated);
      setLayout(updated.layout);
      setToast("Layout saved");
      setTimeout(() => setToast(""), 2200);
    } catch (err) {
      setToast("Failed to save: " + err.message);
      setTimeout(() => setToast(""), 3000);
    } finally {
      setSavingLayout(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setToast("Password changed");
      setTimeout(() => setToast(""), 2200);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">Signed in as {user?.email}</p>
        </div>
      </div>

      <div className="card card-pad" style={{ maxWidth: 620, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
          <FolderOpen size={18} /> Documents folder
        </h3>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          Where your uploaded statements and invoices are stored on disk.
        </p>
        {storage ? (
          <div className="stack" style={{ gap: 16 }}>
            <div className="path-row">
              <div className="label">
                <HardDrive size={14} /> Host folder
              </div>
              <code className="path">{storage.host_path}</code>
              <span className="doc-meta">
                Fixed by the <code>DOCUMENTS_DIR_HOST</code> volume mount in docker-compose
                (restart to change).
              </span>
            </div>
            <div className="path-row">
              <div className="label">In container</div>
              <code className="path">{storage.container_path}</code>
            </div>

            <form onSubmit={saveLayout}>
              <div className="path-row" style={{ alignItems: "flex-end" }}>
                <div className="label" style={{ flexShrink: 0 }}>Layout</div>
                <div style={{ flex: 1, display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    value={layout}
                    onChange={(e) => setLayout(e.target.value)}
                    style={{ flex: 1, fontFamily: "monospace", fontSize: 13 }}
                    placeholder="{YYYY}/{MM}"
                  />
                  <button
                    className="btn btn-secondary"
                    type="submit"
                    disabled={savingLayout || layout === storage.layout || !layout.trim()}
                    style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {savingLayout ? <Spinner /> : <Save size={14} />}
                    Save
                  </button>
                </div>
              </div>
              <p className="doc-meta" style={{ marginTop: 6 }}>
                Default subfolder for each month, under the host folder. Placeholders:{" "}
                <code>{"{YYYY}"}</code> <code>{"{MM}"}</code> — e.g. <code>{"{YYYY}/{MM}"}</code> →{" "}
                <code>2026/06</code>, or <code>{"#{YYYY}/Vydavky"}</code>. Affects new uploads and
                sync for months without a custom folder; files already stored stay put.
              </p>
            </form>

            <div className="doc-meta">Per-file upload limit: {storage.max_upload_mb} MB.</div>
          </div>
        ) : (
          <Spinner />
        )}
      </div>

      <div className="card card-pad" style={{ maxWidth: 460 }}>
        <h3 style={{ marginBottom: 16 }}>Change password</h3>
        <form onSubmit={submit} className="stack" style={{ gap: 14 }}>
          {error && <p className="error-text">{error}</p>}
          <div className="field">
            <label htmlFor="cur">Current password</label>
            <input
              id="cur"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="new">New password</label>
            <input
              id="new"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? <Spinner /> : "Update password"}
          </button>
        </form>
      </div>

      <Toast message={toast} />
    </>
  );
}
