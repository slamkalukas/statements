import { BookOpen, Car, ChevronLeft, ChevronRight, Download, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, downloadLogbook } from "../api";
import { EmptyState, Loading, Modal, Spinner, Toast } from "../components/UI";
import { formatAmount } from "../utils";

const FUEL_TYPES = ["Elektro", "Diesel", "Benzín", "Hybrid", "LPG", "Iné"];
const TRIP_TYPES = ["Firemná", "Súkromná"];
const OWNERSHIPS = ["Firemné", "Súkromné"];
const SK_MONTHS = [
  "Január", "Február", "Marec", "Apríl", "Máj", "Jún",
  "Júl", "August", "September", "Október", "November", "December",
];

function fuelUnit(fuelType) {
  return (fuelType || "").toLowerCase().includes("elektr") ? "kWh" : "L";
}

function fmtDt(dt) {
  if (!dt) return "—";
  const d = new Date(dt);
  if (isNaN(d)) return dt;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function toInputDt(dt) {
  if (!dt) return "";
  const d = new Date(dt);
  if (isNaN(d)) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function Logbook() {
  const now = new Date();
  const [vehicles, setVehicles] = useState(null);
  const [vehicleId, setVehicleId] = useState(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [trips, setTrips] = useState(null);
  const [editVehicle, setEditVehicle] = useState(null);
  const [editTrip, setEditTrip] = useState(null);
  const [toast, setToast] = useState("");
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const importRef = useRef(null);

  useEffect(() => {
    api.get("/vehicles").then((vs) => {
      setVehicles(vs);
      if (vs.length) setVehicleId((cur) => cur ?? vs[0].id);
    });
  }, []);

  async function loadTrips(vid = vehicleId, y = year, m = month) {
    if (!vid) return;
    setTrips(null);
    setTrips(await api.get(`/vehicles/${vid}/trips?year=${y}&month=${m}`));
  }
  useEffect(() => { loadTrips(); }, [vehicleId, year, month]);

  const vehicle = vehicles?.find((v) => v.id === vehicleId);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 2400); }

  function prevMonth() {
    if (month === 1) { setYear((y) => y - 1); setMonth(12); }
    else setMonth((m) => m - 1);
  }
  function nextMonth() {
    if (month === 12) { setYear((y) => y + 1); setMonth(1); }
    else setMonth((m) => m + 1);
  }

  async function handleImport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setImporting(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.postForm(`/vehicles/${vehicleId}/trips/import`, form);
      flash(`Imported ${res.imported} trip${res.imported !== 1 ? "s" : ""}${res.skipped ? `, ${res.skipped} skipped` : ""}.`);
      loadTrips();
    } catch (err) {
      flash(err.message);
    } finally {
      setImporting(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try { await downloadLogbook(vehicleId, year, month, vehicle.ecv); }
    catch (e) { flash(e.message); }
    finally { setExporting(false); }
  }

  async function deleteVehicle(v) {
    if (!confirm(`Delete vehicle ${v.ecv}? This cannot be undone.`)) return;
    try {
      await api.del(`/vehicles/${v.id}`);
      flash("Vehicle deleted");
      const vs = await api.get("/vehicles");
      setVehicles(vs);
      setVehicleId(vs.length ? vs[0].id : null);
    } catch (e) { flash(e.message); }
  }

  async function deleteTrip(t) {
    if (!confirm(`Delete trip ${t.journey_number}?`)) return;
    await api.del(`/car-trips/${t.id}`);
    flash("Trip deleted");
    loadTrips();
  }

  const totalKm = (trips || []).reduce((s, t) => s + (t.km || 0), 0);
  const totalCost = (trips || []).reduce((s, t) => s + (t.cost || 0), 0);

  if (vehicles === null) return <Loading />;

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Logbook</h1>
          <p className="page-sub">Kniha jázd — company vehicle usage.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {vehicles.length > 0 && (
            <select value={vehicleId ?? ""} onChange={(e) => setVehicleId(Number(e.target.value))}>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>{v.ecv} — {v.manufacturer} {v.car_model}</option>
              ))}
            </select>
          )}
          <button className="btn btn-primary" onClick={() => setEditVehicle({})}>
            <Plus size={16} /> Add vehicle
          </button>
        </div>
      </div>

      {vehicles.length === 0 && (
        <div className="card card-pad">
          <EmptyState title="No vehicles" hint="Add a company vehicle to start tracking journeys." />
        </div>
      )}

      {vehicle && (
        <>
          {/* Vehicle info strip */}
          <div className="card card-pad" style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <Car size={18} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: "1rem", letterSpacing: "0.04em" }}>{vehicle.ecv}</div>
                  <div className="doc-meta">{vehicle.manufacturer} {vehicle.car_model}</div>
                </div>
              </div>
              <div style={{ borderLeft: "1px solid var(--border)", paddingLeft: 20, display: "flex", gap: 20 }}>
                <div>
                  <div className="doc-meta">Od 1.1.{new Date().getFullYear()}</div>
                  <div style={{ fontWeight: 600 }}>{vehicle.km_ytd != null ? `${vehicle.km_ytd.toLocaleString()} km` : "— km"}</div>
                </div>
                <div>
                  <div className="doc-meta">Celkovo</div>
                  <div style={{ fontWeight: 600 }}>{vehicle.km_total != null ? `${vehicle.km_total.toLocaleString()} km` : "— km"}</div>
                </div>
                {vehicle.fuel_type && (
                  <div>
                    <div className="doc-meta">Palivo</div>
                    <div style={{ fontWeight: 600 }}>{vehicle.fuel_type}</div>
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setEditVehicle(vehicle)}>
                <Pencil size={14} /> Edit
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => deleteVehicle(vehicle)}>
                <Trash2 size={14} />
              </button>
            </div>
          </div>

          {/* Month navigation + actions */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <button className="btn btn-ghost btn-sm" onClick={prevMonth}><ChevronLeft size={16} /></button>
              <span style={{ fontWeight: 600, minWidth: 150, textAlign: "center" }}>
                {SK_MONTHS[month - 1]} {year}
              </span>
              <button className="btn btn-ghost btn-sm" onClick={nextMonth}><ChevronRight size={16} /></button>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                ref={importRef}
                type="file"
                accept=".xlsx"
                style={{ display: "none" }}
                onChange={handleImport}
              />
              <button className="btn btn-secondary btn-sm" onClick={() => importRef.current?.click()} disabled={importing}>
                {importing ? <Spinner /> : <Upload size={14} />} Import xlsx
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleExport} disabled={exporting}>
                {exporting ? <Spinner /> : <Download size={14} />} Export xlsx
              </button>
              <button className="btn btn-primary" onClick={() => setEditTrip({})}>
                <Plus size={16} /> Add trip
              </button>
            </div>
          </div>

          {/* Trips */}
          {trips === null && <Loading />}
          {trips?.length === 0 && (
            <div className="card card-pad">
              <EmptyState title="No trips this month" hint="Add a trip or navigate to another month." icon={BookOpen} />
            </div>
          )}
          {trips?.length > 0 && (
            <div className="card card-pad">
              <div className="table-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Start</th>
                      <th>End</th>
                      <th>Purpose</th>
                      <th>Route</th>
                      <th className="right">km</th>
                      <th>Driver</th>
                      <th>Type</th>
                      <th className="right">Cost</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {trips.map((t) => (
                      <tr key={t.id}>
                        <td className="num" style={{ whiteSpace: "nowrap" }}>{t.journey_number}</td>
                        <td className="num" style={{ whiteSpace: "nowrap" }}>{fmtDt(t.start_dt)}</td>
                        <td className="num" style={{ whiteSpace: "nowrap" }}>{fmtDt(t.end_dt)}</td>
                        <td>{t.purpose}</td>
                        <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t.route}>
                          {t.route || <span className="doc-meta">—</span>}
                        </td>
                        <td className="right num">{t.km ?? "—"}</td>
                        <td>{t.driver_name}</td>
                        <td>{t.trip_type}</td>
                        <td className="right num">{t.cost != null ? formatAmount(t.cost) : "—"}</td>
                        <td className="right">
                          <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                            <button className="btn btn-ghost btn-sm" title="Edit" onClick={() => setEditTrip(t)}>
                              <Pencil size={14} />
                            </button>
                            <button className="btn btn-ghost btn-sm" title="Delete" onClick={() => deleteTrip(t)}>
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ fontWeight: 600 }}>
                      <td colSpan={5} style={{ textAlign: "right", paddingRight: 8 }}>Total</td>
                      <td className="right num">{totalKm}</td>
                      <td colSpan={2} />
                      <td className="right num">{formatAmount(totalCost)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {editVehicle !== null && (
        <VehicleModal
          vehicle={editVehicle.id ? editVehicle : null}
          onClose={() => setEditVehicle(null)}
          onSaved={(v, msg) => {
            flash(msg);
            setEditVehicle(null);
            api.get("/vehicles").then((vs) => {
              setVehicles(vs);
              setVehicleId(v.id);
            });
          }}
        />
      )}

      {editTrip !== null && vehicle && (
        <TripModal
          trip={editTrip.id ? editTrip : null}
          vehicle={vehicle}
          defaultYear={year}
          defaultMonth={month}
          onClose={() => setEditTrip(null)}
          onSaved={(msg) => { setEditTrip(null); flash(msg); loadTrips(); }}
        />
      )}

      <Toast message={toast} />
    </>
  );
}

function VehicleModal({ vehicle, onClose, onSaved }) {
  const [f, setF] = useState({
    ecv: vehicle?.ecv || "",
    vin: vehicle?.vin || "",
    manufacturer: vehicle?.manufacturer || "",
    car_model: vehicle?.car_model || "",
    fuel_type: vehicle?.fuel_type || "Elektro",
    consumption: vehicle?.consumption != null ? String(vehicle.consumption) : "",
    fuel_price: vehicle?.fuel_price != null ? String(vehicle.fuel_price) : "",
    ownership: vehicle?.ownership || "Firemné",
    date_added: vehicle?.date_added || "",
    odometer_base: vehicle?.odometer_base != null ? String(vehicle.odometer_base) : "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const unit = fuelUnit(f.fuel_type);

  async function save() {
    if (!f.ecv.trim()) { setError("EČV is required."); return; }
    setBusy(true); setError("");
    try {
      const body = {
        ...f,
        consumption: f.consumption ? Number(f.consumption) : null,
        fuel_price: f.fuel_price ? Number(f.fuel_price) : null,
        date_added: f.date_added || null,
        odometer_base: f.odometer_base !== "" ? Number(f.odometer_base) : null,
      };
      const v = vehicle
        ? await api.patch(`/vehicles/${vehicle.id}`, body)
        : await api.post("/vehicles", body);
      onSaved(v, vehicle ? "Vehicle updated" : "Vehicle added");
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <Modal title={vehicle ? "Edit vehicle" : "Add vehicle"} onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        {error && <p className="error-text">{error}</p>}
        <div className="row-2">
          <div className="field"><label>EČV</label><input value={f.ecv} onChange={set("ecv")} placeholder="EL036BY" /></div>
          <div className="field"><label>VIN</label><input value={f.vin} onChange={set("vin")} placeholder="LFZA5AE..." /></div>
        </div>
        <div className="row-2">
          <div className="field"><label>Manufacturer</label><input value={f.manufacturer} onChange={set("manufacturer")} placeholder="Leapmotor" /></div>
          <div className="field"><label>Model</label><input value={f.car_model} onChange={set("car_model")} placeholder="B10" /></div>
        </div>
        <div className="row-2">
          <div className="field">
            <label>Fuel type</label>
            <select value={f.fuel_type} onChange={set("fuel_type")}>
              {FUEL_TYPES.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Ownership</label>
            <select value={f.ownership} onChange={set("ownership")}>
              {OWNERSHIPS.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
        </div>
        <div className="row-2">
          <div className="field">
            <label>Consumption ({unit}/100km)</label>
            <input type="number" step="0.1" min="0" value={f.consumption} onChange={set("consumption")} placeholder="17.3" />
          </div>
          <div className="field">
            <label>Fuel price (EUR/{unit})</label>
            <input type="number" step="0.001" min="0" value={f.fuel_price} onChange={set("fuel_price")} placeholder="0.41" />
          </div>
        </div>
        <div className="row-2">
          <div className="field">
            <label>Date added to assets</label>
            <input type="date" value={f.date_added} onChange={set("date_added")} />
          </div>
          <div className="field">
            <label>Starting odometer (km)</label>
            <input type="number" min="0" value={f.odometer_base} onChange={set("odometer_base")} placeholder="0" />
          </div>
        </div>
        <button className="btn btn-primary" disabled={busy} onClick={save}>
          {busy ? <Spinner /> : (vehicle ? "Save changes" : "Add vehicle")}
        </button>
      </div>
    </Modal>
  );
}

function TripModal({ trip, vehicle, defaultYear, defaultMonth, onClose, onSaved }) {
  const unit = fuelUnit(vehicle.fuel_type);
  const pad = (n) => String(n).padStart(2, "0");
  const defaultStart = `${defaultYear}-${pad(defaultMonth)}-01T08:00`;

  const [f, setF] = useState({
    start_dt: trip ? toInputDt(trip.start_dt) : defaultStart,
    end_dt: trip ? toInputDt(trip.end_dt) : "",
    purpose: trip?.purpose || "",
    route: trip?.route || "",
    km: trip?.km != null ? String(trip.km) : "",
    driver_name: trip?.driver_name || "",
    trip_type: trip?.trip_type || "Firemná",
    events: trip?.events || "",
    fuel_price_override: trip?.fuel_price_override != null ? String(trip.fuel_price_override) : "",
  });
  const [busy, setBusy] = useState(false);
  const [calcDist, setCalcDist] = useState(false);
  const [distError, setDistError] = useState("");
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  // Auto-calculate km from route (debounced 800ms)
  useEffect(() => {
    const route = f.route.trim();
    if (route.length < 5 || (!route.includes(">") && !route.includes("→"))) return;
    setDistError("");
    const timer = setTimeout(async () => {
      setCalcDist(true);
      try {
        const res = await api.post("/route-distance", { route });
        setF((s) => ({ ...s, km: String(res.km) }));
      } catch (e) {
        setDistError(e.message);
      } finally {
        setCalcDist(false);
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [f.route]);

  const km = f.km ? Number(f.km) : null;
  const fp = Number(f.fuel_price_override) || Number(vehicle.fuel_price) || 0;
  const cost = km != null && vehicle.consumption && fp
    ? (km * vehicle.consumption / 100 * fp).toFixed(2)
    : null;

  async function save() {
    if (!f.start_dt) { setError("Start date/time is required."); return; }
    setBusy(true); setError("");
    try {
      const body = {
        ...f,
        end_dt: f.end_dt || null,
        km: f.km !== "" ? Number(f.km) : null,
        fuel_price_override: f.fuel_price_override ? Number(f.fuel_price_override) : null,
        events: f.events || null,
      };
      if (trip) {
        await api.patch(`/car-trips/${trip.id}`, body);
        onSaved("Trip updated");
      } else {
        await api.post(`/vehicles/${vehicle.id}/trips`, body);
        onSaved("Trip added");
      }
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <Modal title={trip ? "Edit trip" : "Add trip"} onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        {error && <p className="error-text">{error}</p>}
        <div className="row-2">
          <div className="field"><label>Start (Začiatok)</label><input type="datetime-local" value={f.start_dt} onChange={set("start_dt")} /></div>
          <div className="field"><label>End (Koniec)</label><input type="datetime-local" value={f.end_dt} onChange={set("end_dt")} /></div>
        </div>
        <div className="field"><label>Purpose (Účel jazdy)</label><input value={f.purpose} onChange={set("purpose")} placeholder="Stretnutie s klientom" /></div>
        <div className="field">
          <label>Route (Trasa) — separate cities with &gt;</label>
          <input value={f.route} onChange={set("route")} placeholder="Nitra, SK > Wien, AT > Nitra, SK" />
          {calcDist && <span className="doc-meta" style={{ marginTop: 4, display: "block" }}><Spinner /> Calculating distance…</span>}
          {distError && <span className="doc-meta" style={{ marginTop: 4, display: "block", color: "var(--danger, #e53)" }}>{distError}</span>}
        </div>
        <div className="row-2">
          <div className="field">
            <label>Distance (km)</label>
            <input type="number" min="0" value={f.km} onChange={set("km")} placeholder="auto from route" />
          </div>
          <div className="field">
            <label>Fuel price override (EUR/{unit})</label>
            <input type="number" step="0.001" min="0" value={f.fuel_price_override} onChange={set("fuel_price_override")} placeholder={vehicle.fuel_price ?? ""} />
          </div>
        </div>
        {cost != null && (
          <p className="doc-meta">Cost: <strong>{cost} EUR</strong></p>
        )}
        <div className="row-2">
          <div className="field"><label>Driver (Vodič)</label><input value={f.driver_name} onChange={set("driver_name")} /></div>
          <div className="field">
            <label>Type (Typ jazdy)</label>
            <select value={f.trip_type} onChange={set("trip_type")}>
              {TRIP_TYPES.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
        </div>
        <div className="field"><label>Details</label><input value={f.events} onChange={set("events")} placeholder="Fuel fill-up, toll, parking…" /></div>
        <button className="btn btn-primary" disabled={busy} onClick={save}>
          {busy ? <Spinner /> : (trip ? "Save changes" : "Add trip")}
        </button>
      </div>
    </Modal>
  );
}
