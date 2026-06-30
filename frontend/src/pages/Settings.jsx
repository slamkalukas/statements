import { FolderOpen, HardDrive, MapPin, Plane, Save } from "lucide-react";
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

  const [rates, setRates] = useState(null);
  const [savingRates, setSavingRates] = useState(false);

  const [orsConfigured, setOrsConfigured] = useState(null);
  const [orsKey, setOrsKey] = useState("");
  const [savingOrs, setSavingOrs] = useState(false);

  useEffect(() => {
    api.get("/storage").then((s) => {
      setStorage(s);
      setLayout(s.layout);
    }).catch(() => {});
    api.get("/travel/per-diem-rates").then(setRates).catch(() => {});
    api.get("/travel/routing-key").then((r) => setOrsConfigured(r.configured)).catch(() => {});
  }, []);

  async function saveOrsKey(e) {
    e.preventDefault();
    if (!orsKey.trim()) return;
    setSavingOrs(true);
    try {
      const r = await api.patch("/travel/routing-key", { key: orsKey.trim() });
      setOrsConfigured(r.configured);
      setOrsKey("");
      setToast("Routing API key saved");
      setTimeout(() => setToast(""), 2200);
    } catch (err) {
      setToast("Failed to save: " + err.message);
      setTimeout(() => setToast(""), 3000);
    } finally {
      setSavingOrs(false);
    }
  }

  async function saveRates(e) {
    e.preventDefault();
    setSavingRates(true);
    try {
      const saved = await api.patch("/travel/per-diem-rates", {
        band1: Number(rates.band1), band2: Number(rates.band2), band3: Number(rates.band3),
      });
      setRates(saved);
      setToast("Per-diem rates saved");
      setTimeout(() => setToast(""), 2200);
    } catch (err) {
      setToast("Failed to save: " + err.message);
      setTimeout(() => setToast(""), 3000);
    } finally {
      setSavingRates(false);
    }
  }

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

      <div className="card card-pad" style={{ maxWidth: 620, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
          <Plane size={18} /> Travel per-diem rates (Stravné)
        </h3>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          Meal-allowance bands used to auto-calculate a trip's per-diem from its duration.
        </p>
        {rates ? (
          <form onSubmit={saveRates} className="stack" style={{ gap: 12 }}>
            <div className="row-2">
              <div className="field">
                <label>5–12 hours (€)</label>
                <input type="number" step="0.01" value={rates.band1}
                       onChange={(e) => setRates({ ...rates, band1: e.target.value })} />
              </div>
              <div className="field">
                <label>12–18 hours (€)</label>
                <input type="number" step="0.01" value={rates.band2}
                       onChange={(e) => setRates({ ...rates, band2: e.target.value })} />
              </div>
            </div>
            <div className="field" style={{ maxWidth: 280 }}>
              <label>Over 18 hours (€)</label>
              <input type="number" step="0.01" value={rates.band3}
                     onChange={(e) => setRates({ ...rates, band3: e.target.value })} />
            </div>
            <p className="doc-meta">Under 5 hours = no per-diem. A trip can still override the amount individually.</p>
            <button className="btn btn-secondary" type="submit" disabled={savingRates}
                    style={{ display: "flex", alignItems: "center", gap: 6, maxWidth: 160 }}>
              {savingRates ? <Spinner /> : <Save size={14} />} Save rates
            </button>
          </form>
        ) : (
          <Spinner />
        )}
      </div>

      <div className="card card-pad" style={{ maxWidth: 620, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
          <MapPin size={18} /> Routing (km calculation)
        </h3>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          OpenRouteService API key for auto-calculating trip distance and drive time.
          The key is stored in the database and never shown again.
        </p>
        <div className="stack" style={{ gap: 12 }}>
          <div className="path-row">
            <div className="label">Status</div>
            {orsConfigured === null ? (
              <Spinner />
            ) : orsConfigured ? (
              <span style={{ color: "var(--success, green)", fontWeight: 600 }}>Configured</span>
            ) : (
              <span className="doc-meta">Not set — routing will be skipped</span>
            )}
          </div>
          <form onSubmit={saveOrsKey}>
            <div className="path-row" style={{ alignItems: "flex-end" }}>
              <div className="label" style={{ flexShrink: 0 }}>{orsConfigured ? "Replace key" : "Enter key"}</div>
              <div style={{ flex: 1, display: "flex", gap: 8 }}>
                <input
                  type="password"
                  value={orsKey}
                  onChange={(e) => setOrsKey(e.target.value)}
                  placeholder="Paste ORS API key…"
                  autoComplete="off"
                  style={{ flex: 1 }}
                />
                <button
                  className="btn btn-secondary"
                  type="submit"
                  disabled={savingOrs || !orsKey.trim()}
                  style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}
                >
                  {savingOrs ? <Spinner /> : <Save size={14} />}
                  Save
                </button>
              </div>
            </div>
          </form>
        </div>
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
