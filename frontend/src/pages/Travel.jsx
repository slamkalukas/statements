import { Copy, Download, Pencil, Plane, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, downloadTravelReport } from "../api";
import { EmptyState, Loading, Modal, Spinner, Toast } from "../components/UI";
import { formatAmount, periodLabel } from "../utils";

const TRANSPORTS = ["Auto služobné", "Auto súkromné", "Vlak", "Bus", "Lietadlo", "MHD"];

export default function Travel() {
  const [periods, setPeriods] = useState(null);
  const [periodId, setPeriodId] = useState(null);
  const [travels, setTravels] = useState(null);
  const [editing, setEditing] = useState(null); // trip object, or {} for new, or null
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.get("/periods").then((ps) => {
      setPeriods(ps);
      if (ps.length) setPeriodId((cur) => cur ?? ps[0].id);
    });
  }, []);

  async function loadTravels(pid) {
    setTravels(null);
    setTravels(await api.get(`/periods/${pid}/travels`));
  }
  useEffect(() => {
    if (periodId) loadTravels(periodId);
  }, [periodId]);

  function flash(msg) {
    setToast(msg);
    setTimeout(() => setToast(""), 2400);
  }

  const period = periods?.find((p) => p.id === periodId);
  const closed = period?.status === "closed";

  const groups = useMemo(() => {
    const g = new Map();
    (travels || []).forEach((t) => {
      const key = t.traveller_name || "(no name)";
      if (!g.has(key)) g.set(key, []);
      g.get(key).push(t);
    });
    return [...g.entries()];
  }, [travels]);

  async function removeTrip(t) {
    if (!confirm(`Delete the trip ${t.trip_date} (${t.traveller_name})?`)) return;
    await api.del(`/travels/${t.id}`);
    flash("Trip deleted");
    loadTravels(periodId);
  }

  async function duplicateTrip(t) {
    await api.post(`/travels/${t.id}/duplicate`, {});
    flash("Trip duplicated");
    loadTravels(periodId);
  }

  if (periods === null) return <Loading />;

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Travel</h1>
          <p className="page-sub">Trips (cestovné) per person, per month.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={periodId ?? ""}
            onChange={(e) => setPeriodId(Number(e.target.value))}
            disabled={periods.length === 0}
          >
            {periods.map((p) => (
              <option key={p.id} value={p.id}>{periodLabel(p.year, p.month)}</option>
            ))}
          </select>
          {!closed && period && (
            <button className="btn btn-primary" onClick={() => setEditing({})}>
              <Plus size={16} /> Add trip
            </button>
          )}
        </div>
      </div>

      {periods.length === 0 && (
        <div className="card card-pad">
          <EmptyState title="No months yet" hint="Create a month under “Months” first — travel is organized by the same months." />
        </div>
      )}

      {closed && (
        <div className="callout" style={{ marginBottom: 16 }}>
          This month is closed. Reopen it under “Months” to add or change trips.
        </div>
      )}

      {period && travels === null && <Loading />}

      {period && travels && travels.length === 0 && (
        <div className="card card-pad">
          <EmptyState title="No trips this month" hint="Add a trip to start the travel report." />
        </div>
      )}

      {groups.map(([name, trips]) => {
        const total = trips.reduce((s, t) => s + (t.per_diem || 0), 0);
        const totalKm = trips.reduce((s, t) => s + (t.distance_km != null ? t.distance_km * 2 : 0), 0);
        const hasKm = trips.some((t) => t.distance_km != null);
        return (
          <div key={name} className="card card-pad" style={{ marginBottom: 16 }}>
            <div className="card-head" style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Plane size={17} /> {name}
                <span className="doc-meta">
                  · {trips.length} trip{trips.length === 1 ? "" : "s"} · {formatAmount(total)} stravné
                  {hasKm && ` · ${totalKm.toFixed(1)} km celkom`}
                </span>
              </h3>
              <button className="btn btn-secondary btn-sm" onClick={() => downloadTravelReport(periodId, name)}>
                <Download size={14} /> Export xlsx
              </button>
            </div>
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Route</th>
                    <th>Purpose</th>
                    <th>Times</th>
                    <th>Transport</th>
                    <th className="right">km (tam+sp.)</th>
                    <th className="right">Stravné</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {trips.map((t) => (
                    <tr key={t.id}>
                      <td className="num">
                        {t.trip_date}
                        {t.end_date && t.end_date !== t.trip_date && <span className="doc-meta"> → {t.end_date}</span>}
                      </td>
                      <td>{t.from_place} → {t.to_place}</td>
                      <td>{t.purpose}</td>
                      <td className="num">{fmtTimes(t)}</td>
                      <td>{t.transport}</td>
                      <td className="right num">
                        {t.distance_km != null ? (
                          <span title={`${t.duration_min != null ? t.duration_min + " min one-way" : ""}`}>
                            {(t.distance_km * 2).toFixed(1)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="right">
                        <span className="num">{formatAmount(t.per_diem)}</span>
                        {t.per_diem_override != null && <span className="doc-meta" title="Manual override"> ✎</span>}
                      </td>
                      <td className="right">
                        {!closed && (
                          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                            <button className="btn btn-ghost btn-sm" title="Duplicate" onClick={() => duplicateTrip(t)}>
                              <Copy size={15} />
                            </button>
                            <button className="btn btn-ghost btn-sm" title="Edit" onClick={() => setEditing(t)}>
                              <Pencil size={15} />
                            </button>
                            <button className="btn btn-ghost btn-sm" title="Delete" onClick={() => removeTrip(t)}>
                              <Trash2 size={15} />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      {editing && period && (
        <TripModal
          period={period}
          trip={editing.id ? editing : null}
          existing={travels || []}
          onClose={() => setEditing(null)}
          onSaved={(msg) => { setEditing(null); flash(msg); loadTravels(periodId); }}
        />
      )}

      <Toast message={toast} />
    </>
  );
}

function fmtTimes(t) {
  const hm = (s) => (s ? s.slice(0, 5) : "—");
  return `${hm(t.depart_time)}–${hm(t.arrive_time)} / ${hm(t.return_depart_time)}–${hm(t.return_arrive_time)}`;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function datesForWeekdays(year, month, picked) {
  const out = [];
  const dt = new Date(year, month - 1, 1);
  const pad = (n) => String(n).padStart(2, "0");
  while (dt.getMonth() === month - 1) {
    const idx = (dt.getDay() + 6) % 7; // Mon=0 … Sun=6
    if (picked[idx]) out.push(`${year}-${pad(month)}-${pad(dt.getDate())}`);
    dt.setDate(dt.getDate() + 1);
  }
  return out;
}

function TripModal({ period, trip, existing, onClose, onSaved }) {
  const periodId = period.id;
  const [f, setF] = useState(() => ({
    traveller_name: trip?.traveller_name || "",
    traveller_address: trip?.traveller_address || "",
    trip_date: trip?.trip_date || "",
    end_date: trip?.end_date || "",
    from_place: trip?.from_place || "",
    to_place: trip?.to_place || "",
    purpose: trip?.purpose || "",
    depart_time: (trip?.depart_time || "").slice(0, 5),
    arrive_time: (trip?.arrive_time || "").slice(0, 5),
    return_depart_time: (trip?.return_depart_time || "").slice(0, 5),
    return_arrive_time: (trip?.return_arrive_time || "").slice(0, 5),
    transport: trip?.transport || "Auto služobné",
    per_diem_override: trip?.per_diem_override != null ? String(trip.per_diem_override) : "",
  }));
  const [repeat, setRepeat] = useState(false);
  const [weekdays, setWeekdays] = useState([false, false, false, false, false, false, false]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const repeatDates = useMemo(
    () => (repeat ? datesForWeekdays(period.year, period.month, weekdays) : []),
    [repeat, weekdays, period.year, period.month]
  );

  // Prefill the home address from an earlier trip by the same traveller.
  function onNameBlur() {
    if (f.traveller_address) return;
    const match = existing.find((t) => t.traveller_name === f.traveller_name && t.traveller_address);
    if (match) setF((s) => ({ ...s, traveller_address: match.traveller_address }));
  }

  function template() {
    return {
      traveller_name: f.traveller_name.trim(),
      traveller_address: f.traveller_address.trim(),
      from_place: f.from_place.trim(),
      to_place: f.to_place.trim(),
      purpose: f.purpose.trim(),
      depart_time: f.depart_time || null,
      arrive_time: f.arrive_time || null,
      return_depart_time: f.return_depart_time || null,
      return_arrive_time: f.return_arrive_time || null,
      transport: f.transport.trim(),
      per_diem_override: f.per_diem_override === "" ? null : Number(f.per_diem_override),
    };
  }

  async function save() {
    if (!f.traveller_name.trim()) {
      setError("Traveller name is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (!trip && repeat) {
        if (repeatDates.length === 0) {
          setError("Pick at least one weekday to repeat on.");
          setBusy(false);
          return;
        }
        await api.post(`/periods/${periodId}/travels/bulk`, {
          ...template(), trip_date: repeatDates[0], dates: repeatDates,
        });
        onSaved(`Added ${repeatDates.length} trips`);
        return;
      }
      if (!f.trip_date) {
        setError("Date is required.");
        setBusy(false);
        return;
      }
      const body = { ...template(), trip_date: f.trip_date, end_date: f.end_date || null };
      if (trip) await api.patch(`/travels/${trip.id}`, body);
      else await api.post(`/periods/${periodId}/travels`, body);
      onSaved(trip ? "Trip updated" : "Trip added");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title={trip ? "Edit trip" : "Add trip"} onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        {error && <p className="error-text">{error}</p>}
        <div className="row-2">
          <div className="field">
            <label>Traveller</label>
            <input value={f.traveller_name} onChange={set("traveller_name")} onBlur={onNameBlur} placeholder="Meno a priezvisko" />
          </div>
          <div className="field">
            <label>Home address (Bydlisko)</label>
            <input value={f.traveller_address} onChange={set("traveller_address")} />
          </div>
        </div>
        {!repeat && (
          <div className="row-2">
            <div className="field">
              <label>Start date</label>
              <input type="date" value={f.trip_date} onChange={set("trip_date")} />
            </div>
            <div className="field">
              <label>End date (multi-day, optional)</label>
              <input type="date" value={f.end_date} onChange={set("end_date")} min={f.trip_date || undefined} />
            </div>
          </div>
        )}
        <div className="row-2">
          <div className="field">
            <label>Transport</label>
            <select value={f.transport} onChange={set("transport")}>
              {TRANSPORTS.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div className="field" />
        </div>
        <div className="row-2">
          <div className="field">
            <label>From (home)</label>
            <input value={f.from_place} onChange={set("from_place")} placeholder="Nitra" />
          </div>
          <div className="field">
            <label>Destination</label>
            <input value={f.to_place} onChange={set("to_place")} placeholder="Trnava" />
          </div>
        </div>
        <div className="field">
          <label>Purpose (Účel cesty)</label>
          <input value={f.purpose} onChange={set("purpose")} />
        </div>
        <div className="row-2">
          <div className="field">
            <label>Depart (odchod)</label>
            <input type="time" value={f.depart_time} onChange={set("depart_time")} />
          </div>
          <div className="field">
            <label>Arrive (príchod)</label>
            <input type="time" value={f.arrive_time} onChange={set("arrive_time")} />
          </div>
        </div>
        <div className="row-2">
          <div className="field">
            <label>Return depart</label>
            <input type="time" value={f.return_depart_time} onChange={set("return_depart_time")} />
          </div>
          <div className="field">
            <label>Return arrive (home)</label>
            <input type="time" value={f.return_arrive_time} onChange={set("return_arrive_time")} />
          </div>
        </div>
        <div className="field">
          <label>Per-diem override (€)</label>
          <input type="number" step="0.01" value={f.per_diem_override} onChange={set("per_diem_override")}
                 placeholder="auto from duration" />
          <span className="doc-meta">Leave blank to auto-calculate from the trip duration.</span>
        </div>

        {!trip && (
          <div className="field">
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} style={{ width: "auto" }} />
              Repeat — create the same trip on chosen weekdays of {periodLabel(period.year, period.month)}
            </label>
            {repeat && (
              <>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                  {WEEKDAYS.map((d, i) => (
                    <button
                      key={d}
                      type="button"
                      className={`btn btn-sm ${weekdays[i] ? "btn-accent" : "btn-ghost"}`}
                      onClick={() => setWeekdays((w) => w.map((v, j) => (j === i ? !v : v)))}
                    >
                      {d}
                    </button>
                  ))}
                </div>
                <span className="doc-meta" style={{ marginTop: 6 }}>
                  {repeatDates.length} trip{repeatDates.length === 1 ? "" : "s"} will be created.
                </span>
              </>
            )}
          </div>
        )}

        <button className="btn btn-primary" disabled={busy} onClick={save}>
          {busy ? <Spinner /> : (trip ? "Save changes" : (repeat ? `Add ${repeatDates.length} trips` : "Add trip"))}
        </button>
      </div>
    </Modal>
  );
}
