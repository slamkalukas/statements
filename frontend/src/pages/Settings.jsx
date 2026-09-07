import { FolderOpen, Globe, HardDrive, MapPin, Plane, Plus, Save, Trash2 } from "lucide-react";
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

  const [foreignRates, setForeignRates] = useState(null);
  const [savingForeign, setSavingForeign] = useState(false);

  const [orsConfigured, setOrsConfigured] = useState(null);
  const [orsKey, setOrsKey] = useState("");
  const [savingOrs, setSavingOrs] = useState(false);

  useEffect(() => {
    api.get("/storage").then((s) => {
      setStorage(s);
      setLayout(s.layout);
    }).catch(() => {});
    api.get("/travel/per-diem-rates").then(setRates).catch(() => {});
    api.get("/travel/foreign-per-diem-rates")
      .then((r) => setForeignRates(r.rates))
      .catch(() => setForeignRates([]));
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
        rates: rates.rates.map((r) => ({
          valid_from: r.valid_from || null,
          band1: Number(r.band1) || 0,
          band2: Number(r.band2) || 0,
          band3: Number(r.band3) || 0,
        })),
        domestic_topup: rates.domestic_topup,
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

  const setRateRow = (i, key, value) => setRates({
    ...rates,
    rates: rates.rates.map((r, j) => (j === i ? { ...r, [key]: value } : r)),
  });

  async function saveForeignRates(e) {
    e.preventDefault();
    const rows = foreignRates
      .filter((r) => r.code.trim())
      .map((r) => ({
        code: r.code.trim(),
        name: r.name.trim(),
        rate: Number(r.rate) || 0,
        valid_from: r.valid_from || null,
      }));
    setSavingForeign(true);
    try {
      const saved = await api.patch("/travel/foreign-per-diem-rates", { rates: rows });
      setForeignRates(saved.rates);
      setToast("Foreign per-diem rates saved");
      setTimeout(() => setToast(""), 2200);
    } catch (err) {
      setToast("Failed to save: " + err.message);
      setTimeout(() => setToast(""), 3000);
    } finally {
      setSavingForeign(false);
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
          Add a row when the rates change — each trip uses the bands in force on its own
          date, so a new rate doesn't rewrite earlier months.
        </p>
        {rates ? (
          <form onSubmit={saveRates} className="stack" style={{ gap: 8 }}>
            <div style={{ display: "flex", gap: 6, fontSize: 12 }} className="doc-meta">
              <span style={{ flex: "0 0 140px" }}>Valid from</span>
              <span style={{ flex: 1 }}>5–12 h (€)</span>
              <span style={{ flex: 1 }}>12–18 h (€)</span>
              <span style={{ flex: 1 }}>18 h+ (€)</span>
              <span style={{ flex: "0 0 32px" }} />
            </div>
            {rates.rates.map((row, i) => (
              <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="date" style={{ flex: "0 0 140px" }}
                  title={row.valid_from ? undefined : "Applies to everything before the next row"}
                  value={row.valid_from || ""}
                  onChange={(e) => setRateRow(i, "valid_from", e.target.value)}
                />
                {["band1", "band2", "band3"].map((band) => (
                  <input
                    key={band} type="number" step="0.01" min="0" style={{ flex: 1 }}
                    value={row[band]}
                    onChange={(e) => setRateRow(i, band, e.target.value)}
                  />
                ))}
                <button
                  type="button" className="btn btn-ghost btn-sm" title="Remove"
                  style={{ flex: "0 0 32px" }}
                  disabled={rates.rates.length <= 1}
                  onClick={() => setRates({ ...rates, rates: rates.rates.filter((_, j) => j !== i) })}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <input
                type="checkbox" style={{ width: "auto" }}
                checked={rates.domestic_topup}
                onChange={(e) => setRates({ ...rates, domestic_topup: e.target.checked })}
              />
              Also pay domestic stravné for the Slovak part of a foreign-trip day
            </label>
            <p className="doc-meta">
              Under 5 hours = no per-diem, and the Slovak part of a foreign day only counts
              when it reaches 5 hours on its own — the same hours are never paid twice.
              A trip can still override the amount per leg.
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <button
                type="button" className="btn btn-ghost btn-sm"
                onClick={() => setRates({
                  ...rates,
                  rates: [...rates.rates, { valid_from: "", band1: 0, band2: 0, band3: 0 }],
                })}
              >
                <Plus size={14} /> Add rate change
              </button>
              <button className="btn btn-secondary" type="submit" disabled={savingRates}
                      style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {savingRates ? <Spinner /> : <Save size={14} />} Save rates
              </button>
            </div>
          </form>
        ) : (
          <Spinner />
        )}
      </div>

      <div className="card card-pad" style={{ maxWidth: 620, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
          <Globe size={18} /> Foreign per-diem rates (Zahraničné stravné)
        </h3>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          Basic daily rate per country. A trip marked with a country uses these instead of
          the bands above: 25 % of the rate for up to 6 h abroad that day, 50 % up to 12 h,
          100 % over 12 h — counted per calendar day.
        </p>
        {foreignRates ? (
          <form onSubmit={saveForeignRates} className="stack" style={{ gap: 8 }}>
            {foreignRates.length > 0 && (
              <div style={{ display: "flex", gap: 6, fontSize: 12 }} className="doc-meta">
                <span style={{ flex: "0 0 70px" }}>Code</span>
                <span style={{ flex: 1 }}>Country</span>
                <span style={{ flex: "0 0 100px" }}>€ / day</span>
                <span style={{ flex: "0 0 140px" }}>Valid from</span>
                <span style={{ flex: "0 0 32px" }} />
              </div>
            )}
            {foreignRates.map((row, i) => (
              <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  style={{ flex: "0 0 70px", textTransform: "uppercase" }}
                  placeholder="IT"
                  maxLength={8}
                  value={row.code}
                  onChange={(e) => setForeignRates(
                    foreignRates.map((r, j) => (j === i ? { ...r, code: e.target.value } : r))
                  )}
                />
                <input
                  style={{ flex: 1 }}
                  placeholder="Taliansko"
                  value={row.name}
                  onChange={(e) => setForeignRates(
                    foreignRates.map((r, j) => (j === i ? { ...r, name: e.target.value } : r))
                  )}
                />
                <input
                  type="number" step="0.01" min="0"
                  style={{ flex: "0 0 100px" }}
                  placeholder="45.00"
                  value={row.rate}
                  onChange={(e) => setForeignRates(
                    foreignRates.map((r, j) => (j === i ? { ...r, rate: e.target.value } : r))
                  )}
                />
                <input
                  type="date"
                  style={{ flex: "0 0 140px" }}
                  title="Leave empty to apply from the beginning. Add a second row for the same country when its rate changes."
                  value={row.valid_from || ""}
                  onChange={(e) => setForeignRates(
                    foreignRates.map((r, j) => (j === i ? { ...r, valid_from: e.target.value } : r))
                  )}
                />
                <button
                  type="button" className="btn btn-ghost btn-sm" title="Remove"
                  style={{ flex: "0 0 32px" }}
                  onClick={() => setForeignRates(foreignRates.filter((_, j) => j !== i))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {foreignRates.length === 0 && (
              <p className="doc-meta">
                No countries configured — trips marked as foreign will show €0 until you add one.
              </p>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <button
                type="button" className="btn btn-ghost btn-sm"
                onClick={() => setForeignRates([...foreignRates, { code: "", name: "", rate: "", valid_from: "" }])}
              >
                <Plus size={14} /> Add country
              </button>
              <button className="btn btn-secondary" type="submit" disabled={savingForeign}
                      style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {savingForeign ? <Spinner /> : <Save size={14} />} Save rates
              </button>
            </div>
            <p className="doc-meta">
              Rates are set by an MF SR opatrenie and change during the year. Add a second
              row for the same country with the date the new rate takes effect — earlier
              trips keep reporting the rate that applied when they happened.
            </p>
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
