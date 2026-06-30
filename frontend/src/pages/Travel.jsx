import { Copy, Download, Pencil, Plane, Plus, Route, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, downloadTravelReport } from "../api";
import { EmptyState, Loading, Modal, Spinner, Toast } from "../components/UI";
import { formatAmount, periodLabel } from "../utils";

const TRANSPORTS = ["Auto služobné", "Auto súkromné", "Vlak", "Bus", "Lietadlo", "Taxi", "MHD", "Iné"];

export default function Travel() {
  const [periods, setPeriods] = useState(null);
  const [periodId, setPeriodId] = useState(null);
  const [travels, setTravels] = useState(null);
  const [editing, setEditing] = useState(null);
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
    if (!confirm(`Delete trip ${t.trip_date} (${t.traveller_name})?`)) return;
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
          <EmptyState title="No months yet" hint='Create a month under "Months" first.' />
        </div>
      )}
      {closed && (
        <div className="callout" style={{ marginBottom: 16 }}>
          This month is closed. Reopen it under "Months" to add or change trips.
        </div>
      )}
      {period && travels === null && <Loading />}
      {period && travels && travels.length === 0 && (
        <div className="card card-pad">
          <EmptyState title="No trips this month" hint="Add a trip to start the travel report." />
        </div>
      )}

      {groups.map(([name, trips]) => {
        const totalPd = trips.reduce((s, t) => s + (t.per_diem || 0), 0);
        const totalKm = trips.reduce((s, t) => s + (t.total_km || 0), 0);
        const hasKm = trips.some((t) => t.total_km != null);
        return (
          <div key={name} className="card card-pad" style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Plane size={17} /> {name}
                <span className="doc-meta">
                  · {trips.length} trip{trips.length === 1 ? "" : "s"} · {formatAmount(totalPd)} stravné
                  {hasKm && ` · ${totalKm.toFixed(1)} km`}
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
                    <th>Route / Legs</th>
                    <th>Purpose</th>
                    <th>Times</th>
                    <th className="right">km</th>
                    <th className="right">Stravné</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {trips.map((t) => (
                    <tr key={t.id}>
                      <td className="num">
                        {t.trip_date}
                        {t.end_date && t.end_date !== t.trip_date && (
                          <span className="doc-meta"> → {t.end_date}</span>
                        )}
                      </td>
                      <td>
                        {t.legs.length === 0 && <span className="doc-meta">—</span>}
                        {t.legs.length === 1 && (
                          <span>{t.legs[0].from_place} → {t.legs[0].to_place}</span>
                        )}
                        {t.legs.length > 1 && (
                          <span title={t.legs.map((l) => `${l.from_place}→${l.to_place}`).join(", ")}>
                            {t.legs[0].from_place} → {t.legs[t.legs.length - 1].to_place}
                            <span className="doc-meta"> ({t.legs.length} legs)</span>
                          </span>
                        )}
                      </td>
                      <td>{t.purpose}</td>
                      <td className="num">{fmtTimes(t)}</td>
                      <td className="right num">
                        {t.total_km != null ? t.total_km.toFixed(1) : "—"}
                      </td>
                      <td className="right">
                        <span className="num">{formatAmount(t.per_diem)}</span>
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
  return `${hm(t.depart_time)}–${hm(t.return_arrive_time)}`;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function datesForWeekdays(year, month, picked) {
  const out = [];
  const dt = new Date(year, month - 1, 1);
  const pad = (n) => String(n).padStart(2, "0");
  while (dt.getMonth() === month - 1) {
    const idx = (dt.getDay() + 6) % 7;
    if (picked[idx]) out.push(`${year}-${pad(month)}-${pad(dt.getDate())}`);
    dt.setDate(dt.getDate() + 1);
  }
  return out;
}

function emptyLeg(order_idx = 0) {
  return { from_place: "", to_place: "", transport: "Auto služobné", leg_time: "", expense: "", per_diem: "", order_idx };
}

function TripModal({ period, trip, existing, onClose, onSaved }) {
  const periodId = period.id;
  const [f, setF] = useState(() => ({
    traveller_name: trip?.traveller_name || "",
    traveller_address: trip?.traveller_address || "",
    trip_date: trip?.trip_date || "",
    end_date: trip?.end_date || "",
    purpose: trip?.purpose || "",
    depart_time: (trip?.depart_time || "").slice(0, 5),
    arrive_time: (trip?.arrive_time || "").slice(0, 5),
    return_depart_time: (trip?.return_depart_time || "").slice(0, 5),
    return_arrive_time: (trip?.return_arrive_time || "").slice(0, 5),
  }));
  const [legs, setLegs] = useState(() =>
    trip?.legs?.length
      ? trip.legs.map((l) => ({
          from_place: l.from_place,
          to_place: l.to_place,
          transport: l.transport,
          leg_time: (l.leg_time || "").slice(0, 5),
          expense: l.expense != null ? String(l.expense) : "",
          per_diem: l.per_diem != null ? String(l.per_diem) : "",
          order_idx: l.order_idx,
          _id: l.id,
        }))
      : [emptyLeg(0)]
  );
  const [repeat, setRepeat] = useState(false);
  const [weekdays, setWeekdays] = useState([false, false, false, false, false, false, false]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const repeatDates = useMemo(
    () => (repeat ? datesForWeekdays(period.year, period.month, weekdays) : []),
    [repeat, weekdays, period.year, period.month]
  );

  function onNameBlur() {
    if (f.traveller_address) return;
    const match = existing.find((t) => t.traveller_name === f.traveller_name && t.traveller_address);
    if (match) setF((s) => ({ ...s, traveller_address: match.traveller_address }));
  }

  function addLeg() {
    setLegs((ls) => [...ls, emptyLeg(ls.length)]);
  }

  function removeLeg(idx) {
    setLegs((ls) => ls.filter((_, i) => i !== idx).map((l, i) => ({ ...l, order_idx: i })));
  }

  function setLeg(idx, key, val) {
    setLegs((ls) => ls.map((l, i) => (i === idx ? { ...l, [key]: val } : l)));
  }

  function buildLegs() {
    return legs.map((l, i) => ({
      from_place: l.from_place.trim(),
      to_place: l.to_place.trim(),
      transport: l.transport,
      leg_time: l.leg_time || null,
      expense: l.expense === "" ? null : Number(l.expense),
      per_diem: l.per_diem === "" ? null : Number(l.per_diem),
      order_idx: i,
    }));
  }

  function header() {
    return {
      traveller_name: f.traveller_name.trim(),
      traveller_address: f.traveller_address.trim(),
      purpose: f.purpose.trim(),
      depart_time: f.depart_time || null,
      arrive_time: f.arrive_time || null,
      return_depart_time: f.return_depart_time || null,
      return_arrive_time: f.return_arrive_time || null,
    };
  }

  async function save() {
    if (!f.traveller_name.trim()) { setError("Traveller name is required."); return; }
    setBusy(true); setError("");
    try {
      if (!trip && repeat) {
        if (repeatDates.length === 0) { setError("Pick at least one weekday."); setBusy(false); return; }
        await api.post(`/periods/${periodId}/travels/bulk`, {
          ...header(), trip_date: repeatDates[0], dates: repeatDates, legs: buildLegs(),
        });
        onSaved(`Added ${repeatDates.length} trips`);
        return;
      }
      if (!f.trip_date) { setError("Date is required."); setBusy(false); return; }
      const body = { ...header(), trip_date: f.trip_date, end_date: f.end_date || null, legs: buildLegs() };

      if (trip) {
        // Update header
        await api.patch(`/travels/${trip.id}`, { ...header(), trip_date: f.trip_date, end_date: f.end_date || null });
        // Sync legs: delete removed, add new, update existing
        const existingIds = new Set(trip.legs.map((l) => l.id));
        const keptIds = new Set(legs.filter((l) => l._id).map((l) => l._id));
        for (const id of existingIds) {
          if (!keptIds.has(id)) await api.del(`/travel-legs/${id}`);
        }
        for (let i = 0; i < legs.length; i++) {
          const l = legs[i];
          const legBody = { ...buildLegs()[i] };
          if (l._id) {
            await api.patch(`/travel-legs/${l._id}`, legBody);
          } else {
            await api.post(`/travels/${trip.id}/legs`, legBody);
          }
        }
        onSaved("Trip updated");
      } else {
        await api.post(`/periods/${periodId}/travels`, body);
        onSaved("Trip added");
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title={trip ? "Edit trip" : "Add trip"} onClose={onClose}>
      <div className="stack" style={{ gap: 12 }}>
        {error && <p className="error-text">{error}</p>}

        {/* Header */}
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
            <label>Arrive (príchod dest.)</label>
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

        {/* Legs */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <Route size={14} /> Legs / Stops
            </label>
            <button type="button" className="btn btn-ghost btn-sm" onClick={addLeg}>
              <Plus size={13} /> Add leg
            </button>
          </div>
          <div className="stack" style={{ gap: 8 }}>
            {legs.map((leg, idx) => (
              <div key={idx} className="card" style={{ padding: "10px 12px", background: "var(--surface-2, #f8f8f8)" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
                  <span className="doc-meta" style={{ minWidth: 20 }}>#{idx + 1}</span>
                  <input
                    style={{ flex: 1 }}
                    placeholder="From"
                    value={leg.from_place}
                    onChange={(e) => setLeg(idx, "from_place", e.target.value)}
                  />
                  <span className="doc-meta">→</span>
                  <input
                    style={{ flex: 1 }}
                    placeholder="To"
                    value={leg.to_place}
                    onChange={(e) => setLeg(idx, "to_place", e.target.value)}
                  />
                  {legs.length > 1 && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeLeg(idx)}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <select
                    style={{ flex: "1 1 140px" }}
                    value={leg.transport}
                    onChange={(e) => setLeg(idx, "transport", e.target.value)}
                  >
                    {TRANSPORTS.map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                  <input
                    type="time"
                    style={{ flex: "0 0 110px" }}
                    title="Departure time from this leg's origin"
                    value={leg.leg_time}
                    onChange={(e) => setLeg(idx, "leg_time", e.target.value)}
                  />
                  <input
                    type="number" step="0.01" min="0"
                    style={{ flex: "1 1 90px" }}
                    placeholder="Výdavky €"
                    title="Reimbursable expense (ticket, taxi, etc.)"
                    value={leg.expense}
                    onChange={(e) => setLeg(idx, "expense", e.target.value)}
                  />
                  <input
                    type="number" step="0.01" min="0"
                    style={{ flex: "1 1 90px" }}
                    placeholder="Stravné €"
                    title="Per-diem for this leg (leave blank = auto from total duration)"
                    value={leg.per_diem}
                    onChange={(e) => setLeg(idx, "per_diem", e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="doc-meta" style={{ marginTop: 4 }}>
            Stravné per leg — fill in when rates differ (e.g. SK domestic vs. foreign). Leave blank on all legs to auto-calculate from trip duration.
          </p>
        </div>

        {!trip && (
          <div className="field">
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} style={{ width: "auto" }} />
              Repeat — create on chosen weekdays of {periodLabel(period.year, period.month)}
            </label>
            {repeat && (
              <>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                  {WEEKDAYS.map((d, i) => (
                    <button
                      key={d} type="button"
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
