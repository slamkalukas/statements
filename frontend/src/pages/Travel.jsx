import { Copy, Download, Pencil, Plane, Plus, Route, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, downloadAllTravelReportsForYear, downloadTravelReport } from "../api";
import { EmptyState, Loading, Modal, MonthNav, Spinner, Toast } from "../components/UI";
import { SK_MONTHS, formatAmount, getLastVehicleId, rememberVehicleId } from "../utils";

const TRANSPORTS = ["Auto služobné", "Auto súkromné", "Vlak", "Bus", "Lietadlo", "Taxi", "MHD", "Iné"];
// Only a car leg has km worth recording — and only a car's km is looked up.
const CAR_TRANSPORTS = new Set(["Auto služobné", "Auto súkromné"]);

/** Mirrors the backend's is_company_car_transport — a company car goes to the logbook. */
function isCompanyCarTransport(transport) {
  const t = (transport || "").toLowerCase();
  return ["firemn", "služobn", "sluzob"].some((marker) => t.includes(marker));
}

export default function Travel() {
  const [periods, setPeriods] = useState(null);
  const [periodId, setPeriodId] = useState(null);
  const [travels, setTravels] = useState(null);
  const [editing, setEditing] = useState(null);
  const [toast, setToast] = useState("");
  const [vehicles, setVehicles] = useState([]);
  const [foreignRates, setForeignRates] = useState([]);
  const [exportingYear, setExportingYear] = useState(false);

  useEffect(() => {
    api.get("/periods").then((ps) => {
      setPeriods(ps);
      if (ps.length) setPeriodId((cur) => cur ?? ps[0].id);
    });
    api.get("/vehicles").then(setVehicles).catch(() => {});
    api.get("/travel/foreign-per-diem-rates")
      .then((r) => setForeignRates(r.rates))
      .catch(() => {});
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

  async function exportYear() {
    setExportingYear(true);
    try {
      await downloadAllTravelReportsForYear(period.year);
    } catch (e) {
      flash(e.message);
    } finally {
      setExportingYear(false);
    }
  }

  if (periods === null) return <Loading />;

  const periodIdx = periods.findIndex((p) => p.id === periodId);

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Travel</h1>
          <p className="page-sub">Trips (cestovné) per person, per month.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {period && (
            <MonthNav
              label={`${SK_MONTHS[period.month - 1]} ${period.year}`}
              onPrev={() => setPeriodId(periods[periodIdx + 1].id)}
              onNext={() => setPeriodId(periods[periodIdx - 1].id)}
              disablePrev={periodIdx >= periods.length - 1}
              disableNext={periodIdx <= 0}
            />
          )}
          {period && (
            <button className="btn btn-secondary" onClick={exportYear} disabled={exportingYear} title={`Export every person's report for ${period.year} as a zip`}>
              {exportingYear ? <Spinner /> : <Download size={16} />} Export {period.year}
            </button>
          )}
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
        return (
          <div key={name} className="card card-pad" style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Plane size={17} /> {name}
                <span className="doc-meta">
                  · {trips.length} trip{trips.length === 1 ? "" : "s"} · {formatAmount(totalPd)} stravné
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
                    <th>Date &amp; time</th>
                    <th>Route / Legs</th>
                    <th>Purpose</th>
                    <th className="right">Stravné</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {trips.map((t) => (
                    <tr key={t.id}>
                      <td className="num">{fmtTripDateTime(t)}</td>
                      <td>
                        {t.legs.length === 0
                          ? <span className="doc-meta">—</span>
                          : (() => {
                              // Destinations only (drop the trip home), collapsing the
                              // repeats a stay in an already-visited city produces.
                              const dests = [];
                              t.legs.slice(0, -1).forEach((l) => {
                                if (l.to_place && l.to_place !== dests[dests.length - 1]) {
                                  dests.push(l.to_place);
                                }
                              });
                              const label = dests.length
                                ? dests.join(" → ")
                                : (t.legs[t.legs.length - 1].to_place || "—");
                              return <span>{label}</span>;
                            })()
                        }
                        {(() => {
                          const codes = [...new Set(
                            t.legs.map((l) => l.country).filter(Boolean)
                          )];
                          return codes.length ? (
                            <span className="doc-meta" title="Foreign trip — per-diem uses each country's daily rate">
                              {" · "}{codes.join(", ")}
                            </span>
                          ) : null;
                        })()}
                      </td>
                      <td>{t.purpose}</td>
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
          vehicles={vehicles}
          foreignRates={foreignRates}
          onClose={() => setEditing(null)}
          onSaved={(msg) => { setEditing(null); flash(msg); loadTravels(periodId); }}
        />
      )}

      <Toast message={toast} />
    </>
  );
}

function fmtTripDateTime(t) {
  const hm = (s) => (s ? s.slice(0, 5) : "");
  const first = t.legs?.[0];
  const last = t.legs?.[t.legs.length - 1];
  const startTime = hm(first?.depart_time);
  const endTime = hm(last?.arrive_time);
  const startPart = startTime ? `${t.trip_date} ${startTime}` : t.trip_date;

  if (t.end_date && t.end_date !== t.trip_date) {
    const endPart = endTime ? `${t.end_date} ${endTime}` : t.end_date;
    return <>{startPart}<span className="doc-meta"> → {endPart}</span></>;
  }
  return endTime ? <>{startPart}<span className="doc-meta"> – {endTime}</span></> : startPart;
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

function PlaceInput({ value, onChange, readOnly, placeholder, title, style }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  function handleChange(e) {
    const val = e.target.value;
    onChange(val);
    clearTimeout(timer.current);
    if (val.length >= 2) {
      timer.current = setTimeout(async () => {
        try {
          const s = await api.get(`/suggest-places?q=${encodeURIComponent(val)}`);
          setSuggestions(s);
          setOpen(s.length > 0);
        } catch { /* network error — fail silently */ }
      }, 400);
    } else {
      setSuggestions([]);
      setOpen(false);
    }
  }

  function pick(s) {
    onChange(s);
    setSuggestions([]);
    setOpen(false);
  }

  return (
    <div style={{ position: "relative", flex: 1, ...style }}>
      <input
        value={value}
        onChange={handleChange}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        readOnly={readOnly}
        placeholder={placeholder}
        title={title}
        style={{ width: "100%" }}
      />
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 200,
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 6, boxShadow: "0 4px 14px rgba(0,0,0,.15)",
          overflow: "hidden",
        }}>
          {suggestions.map((s, i) => (
            <div
              key={i}
              className="place-suggestion"
              onMouseDown={() => pick(s)}
              title={s}
              style={{
                padding: "7px 10px", cursor: "pointer", fontSize: 13,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}
            >
              {s}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** A day spent in one place: no route, no transport, no km — just where you
 *  were and what you were doing (conference, training, negotiations). */
function StayCard({ leg, idx, trip, tripDate, endDate, inherited, countryOptions, onChange, onRemove }) {
  const multiDay = endDate && endDate !== tripDate;
  return (
    <div
      className="card"
      style={{
        padding: "10px 12px",
        background: "var(--surface-2, #f8f8f8)",
        borderLeft: "3px solid var(--accent, #2a9d6e)",
      }}
    >
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
        <span className="doc-meta" style={{ minWidth: 18, fontSize: 11 }}>#{idx + 1}</span>
        <span className="doc-meta" style={{ fontWeight: 600, whiteSpace: "nowrap" }}>Pobyt</span>
        <PlaceInput
          value={leg.from_place}
          placeholder="Place stayed in"
          onChange={(val) => onChange("from_place", val)}
        />
        <input
          type="date"
          style={{ width: 140 }}
          title="Date of this stay"
          min={tripDate || undefined}
          max={endDate || undefined}
          value={leg.leg_date}
          onChange={(e) => onChange("leg_date", e.target.value)}
        />
        <button type="button" className="btn btn-ghost btn-sm" title="Remove" onClick={onRemove}>
          <Trash2 size={13} />
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <select
          style={{ flex: "0 0 190px" }}
          title="Country you were in that day — defaults to wherever the previous leg arrived"
          value={leg.country}
          onChange={(e) => onChange("country", e.target.value)}
        >
          <option value="">
            {inherited ? `— same as arrival (${inherited}) —` : "— same as arrival (SK) —"}
          </option>
          {countryOptions.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name} ({r.code}) · {r.rate} €/deň
            </option>
          ))}
          {countryOptions.length === 0 && (
            <option value="" disabled>No countries yet — add them in Settings</option>
          )}
          {leg.country && !countryOptions.some((r) => r.code === leg.country) && (
            <option value={leg.country}>{leg.country} — no rate configured</option>
          )}
        </select>
        <input
          style={{ flex: "1 1 220px" }}
          placeholder="What happened here (konferencia, školenie…)"
          value={leg.note}
          onChange={(e) => onChange("note", e.target.value)}
        />
        <div style={{ display: "flex", gap: 4, alignItems: "center", flex: "0 0 auto" }}>
          <input
            type="time" style={{ width: 100 }}
            title="From (optional)"
            value={leg.depart_time}
            onChange={(e) => onChange("depart_time", e.target.value)}
          />
          <span className="doc-meta">–</span>
          <input
            type="time" style={{ width: 100 }}
            title="To (optional)"
            value={leg.arrive_time}
            onChange={(e) => onChange("arrive_time", e.target.value)}
          />
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
        <input
          type="number" step="0.01" min="0"
          style={{ flex: "1 1 100px" }}
          placeholder="Výdavky € (konferenčný poplatok, hotel…)"
          value={leg.expense}
          onChange={(e) => onChange("expense", e.target.value)}
        />
        <input
          type="number" step="0.01" min="0"
          style={{ flex: "1 1 100px" }}
          placeholder="Stravné € (blank = auto)"
          value={leg.per_diem}
          onChange={(e) => onChange("per_diem", e.target.value)}
        />
      </div>
      {!multiDay && !trip && (
        <p className="doc-meta" style={{ marginTop: 4 }}>
          Set an end date on the trip to pick which day this stay falls on.
        </p>
      )}
    </div>
  );
}

function emptyLeg(order_idx, fromPlace = "", toPlace = "") {
  return {
    kind: "travel", note: "", country: "",
    from_place: fromPlace, to_place: toPlace,
    transport: "Auto služobné",
    leg_date: "",
    depart_time: "", arrive_time: "",
    distance_km: "",
    expense: "", per_diem: "",
    order_idx,
  };
}

/** A day spent in one place — conference, training, negotiations — with no travel. */
function emptyStay(order_idx, place = "") {
  return {
    kind: "stay", note: "", country: "",
    from_place: place, to_place: place,
    transport: "",
    leg_date: "",
    depart_time: "", arrive_time: "",
    distance_km: "",
    expense: "", per_diem: "",
    order_idx,
  };
}

function TripModal({ period, trip, existing, vehicles, foreignRates, onClose, onSaved }) {
  const periodId = period.id;
  const [f, setF] = useState(() => ({
    traveller_name: trip?.traveller_name || "",
    traveller_address: trip?.traveller_address || "",
    trip_date: trip?.trip_date || "",
    end_date: trip?.end_date || "",
    purpose: trip?.purpose || "",
    vehicle_id: trip?.vehicle_id ?? getLastVehicleId(vehicles) ?? "",
  }));

  const initLegs = () => {
    if (trip?.legs?.length) {
      return trip.legs.map((l) => ({
        kind: l.kind || "travel",
        note: l.note || "",
        country: l.country || "",
        from_place: l.from_place,
        to_place: l.to_place,
        transport: l.transport,
        leg_date: l.leg_date || "",
        depart_time: (l.depart_time || "").slice(0, 5),
        arrive_time: (l.arrive_time || "").slice(0, 5),
        distance_km: l.distance_km != null ? String(l.distance_km) : "",
        expense: l.expense != null ? String(l.expense) : "",
        per_diem: l.per_diem != null ? String(l.per_diem) : "",
        order_idx: l.order_idx,
        _id: l.id,
      }));
    }
    const addr = trip?.traveller_address || "";
    return [emptyLeg(0, addr, ""), emptyLeg(1, "", addr)];
  };

  const [legs, setLegs] = useState(initLegs);
  const [repeat, setRepeat] = useState(false);
  const [weekdays, setWeekdays] = useState([false, false, false, false, false, false, false]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [calcIdx, setCalcIdx] = useState(null);
  const [calcErrors, setCalcErrors] = useState({});
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  // Keep first leg from_place and last leg to_place in sync with Bydlisko (new trips only)
  useEffect(() => {
    if (trip) return;
    const addr = f.traveller_address;
    setLegs((ls) => {
      if (!ls.length) return ls;
      const updated = ls.map((l) => ({ ...l }));
      const last = updated.length - 1;
      // Stays have no direction — never rewrite their place from Bydlisko.
      if (updated[0].kind !== "stay") updated[0] = { ...updated[0], from_place: addr };
      if (updated[last].kind !== "stay") updated[last] = { ...updated[last], to_place: addr };
      return updated;
    });
  }, [f.traveller_address, trip]);

  const repeatDates = useMemo(
    () => (repeat ? datesForWeekdays(period.year, period.month, weekdays) : []),
    [repeat, weekdays, period.year, period.month]
  );

  // Matched the way the backend decides what syncs to the logbook, so the picker
  // can't hide on a leg the logbook would still pick up.
  const hasCarLeg = useMemo(
    () => legs.some((l) => l.kind !== "stay" && isCompanyCarTransport(l.transport)),
    [legs]
  );

  // A country appears once per historical rate row — the picker wants one entry
  // each, showing the most recent rate.
  const countryOptions = useMemo(() => {
    const byCode = new Map();
    (foreignRates || []).forEach((r) => byCode.set(r.code, r));
    return [...byCode.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [foreignRates]);

  /** Where a stay happens: wherever the last travel leg before it arrived. */
  function inheritedCountry(idx) {
    for (let i = idx - 1; i >= 0; i--) {
      if (legs[i].kind !== "stay") return legs[i].country || "";
    }
    return "";
  }

  function onNameBlur() {
    if (f.traveller_address) return;
    const match = existing.find((t) => t.traveller_name === f.traveller_name && t.traveller_address);
    if (match) setF((s) => ({ ...s, traveller_address: match.traveller_address }));
  }

  function addLeg() {
    setLegs((ls) => {
      const addr = f.traveller_address;
      // Insert before the last (return) leg; last leg always goes back to Bydlisko
      const newLeg = emptyLeg(ls.length - 1, ls[ls.length - 2]?.to_place || "", "");
      const updated = [
        ...ls.slice(0, -1),
        { ...newLeg },
        { ...ls[ls.length - 1], order_idx: ls.length },
      ];
      // Ensure last leg's to_place stays as Bydlisko
      updated[updated.length - 1] = { ...updated[updated.length - 1], to_place: addr };
      return updated.map((l, i) => ({ ...l, order_idx: i }));
    });
  }

  /** A day in one place, inserted before the return leg — same slot as a stop. */
  function addStay() {
    setLegs((ls) => {
      const place = ls[ls.length - 2]?.to_place || ls[0]?.to_place || "";
      const updated = [...ls.slice(0, -1), emptyStay(0, place), ls[ls.length - 1]];
      return updated.map((l, i) => ({ ...l, order_idx: i }));
    });
  }

  function removeLeg(idx) {
    setLegs((ls) => {
      if (ls.filter((l) => l.kind !== "stay").length <= 2 && ls[idx].kind !== "stay") return ls;
      const updated = ls.filter((_, i) => i !== idx).map((l, i) => ({ ...l, order_idx: i }));
      // Re-enforce Bydlisko on first/last — but a stay has no direction to enforce.
      const last = updated.length - 1;
      if (updated[0]?.kind !== "stay") {
        updated[0] = { ...updated[0], from_place: f.traveller_address };
      }
      if (updated[last]?.kind !== "stay") {
        updated[last] = { ...updated[last], to_place: f.traveller_address };
      }
      return updated;
    });
  }

  function setLeg(idx, key, val) {
    setLegs((ls) => ls.map((l, i) => (i === idx ? { ...l, [key]: val } : l)));
  }

  async function calcLegDistance(idx, fromPlace, toPlace) {
    setCalcIdx(idx);
    setCalcErrors((e) => ({ ...e, [idx]: "" }));
    try {
      const res = await api.post("/route-distance", { route: `${fromPlace} > ${toPlace}` });
      setLeg(idx, "distance_km", String(res.km));
    } catch (e) {
      setCalcErrors((errs) => ({ ...errs, [idx]: e.message }));
    } finally {
      setCalcIdx((cur) => (cur === idx ? null : cur));
    }
  }

  // Auto-fill km whenever a leg's from/to/transport combo changes — covers typing,
  // autocomplete picks, and programmatic fills (Bydlisko sync, addLeg carrying over
  // the previous leg's place). Recalculates even if a km value is already set,
  // since that value belongs to whatever address was there before; calcAttempted is
  // seeded from the initial legs so opening an existing trip doesn't immediately
  // re-fetch km for addresses that haven't actually changed, and afterwards prevents
  // re-fetching the same combo on every keystroke of an unrelated field.
  const legSignature = (leg) => `${leg.transport}|${leg.from_place.trim()}|${leg.to_place.trim()}`;
  const calcAttempted = useRef(
    Object.fromEntries(legs.map((leg, idx) => [idx, legSignature(leg)]))
  );
  useEffect(() => {
    const timers = {};
    legs.forEach((leg, idx) => {
      const fromPlace = leg.from_place.trim();
      const toPlace = leg.to_place.trim();
      if (
        leg.kind === "stay" || !CAR_TRANSPORTS.has(leg.transport) ||
        !fromPlace || !toPlace || fromPlace === toPlace
      ) {
        return;
      }
      const sig = legSignature(leg);
      if (calcAttempted.current[idx] === sig) return;
      timers[idx] = setTimeout(() => {
        calcAttempted.current[idx] = sig;
        calcLegDistance(idx, fromPlace, toPlace);
      }, 800);
    });
    return () => Object.values(timers).forEach(clearTimeout);
  }, [legs]);

  function buildLegs() {
    return legs.map((l, i) => ({
      kind: l.kind || "travel",
      note: (l.note || "").trim(),
      country: l.country || "",
      from_place: l.from_place.trim(),
      // A stay has no direction — both ends are the place you stayed in.
      to_place: (l.kind === "stay" ? l.from_place : l.to_place).trim(),
      transport: l.kind === "stay" ? "" : l.transport,
      leg_date: l.leg_date || null,
      depart_time: l.depart_time || null,
      arrive_time: l.arrive_time || null,
      distance_km: l.distance_km === "" ? null : Number(l.distance_km),
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
      vehicle_id: f.vehicle_id ? Number(f.vehicle_id) : null,
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
        await api.patch(`/travels/${trip.id}`, { ...header(), trip_date: f.trip_date, end_date: f.end_date || null });
        const existingIds = new Set(trip.legs.map((l) => l.id));
        const keptIds = new Set(legs.filter((l) => l._id).map((l) => l._id));
        for (const id of existingIds) {
          if (!keptIds.has(id)) await api.del(`/travel-legs/${id}`);
        }
        const builtLegs = buildLegs();
        for (let i = 0; i < legs.length; i++) {
          const l = legs[i];
          if (l._id) await api.patch(`/travel-legs/${l._id}`, builtLegs[i]);
          else await api.post(`/travels/${trip.id}/legs`, builtLegs[i]);
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

  const isFirst = (idx) => idx === 0;
  const isLast = (idx) => idx === legs.length - 1;

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
            <input value={f.traveller_address} onChange={set("traveller_address")} placeholder="Nitra" />
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

        {/* Legs */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <Route size={14} /> Legs
            </label>
            <div style={{ display: "flex", gap: 4 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={addStay} title="A day in one place — conference, training — with no travel">
                <Plus size={13} /> Add stay
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={addLeg}>
                <Plus size={13} /> Add stop
              </button>
            </div>
          </div>
          <div className="stack" style={{ gap: 8 }}>
            {legs.map((leg, idx) => leg.kind === "stay" ? (
              <StayCard
                key={idx}
                leg={leg}
                idx={idx}
                trip={trip}
                tripDate={f.trip_date}
                endDate={f.end_date}
                inherited={inheritedCountry(idx)}
                countryOptions={countryOptions}
                onChange={(key, val) => setLeg(idx, key, val)}
                onRemove={() => removeLeg(idx)}
              />
            ) : (
              <div key={idx} className="card" style={{ padding: "10px 12px", background: "var(--surface-2, #f8f8f8)" }}>
                {/* Route row */}
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
                  <span className="doc-meta" style={{ minWidth: 18, fontSize: 11 }}>#{idx + 1}</span>
                  <PlaceInput
                    value={leg.from_place}
                    readOnly={isFirst(idx) && !trip}
                    placeholder="From"
                    title={isFirst(idx) ? "Auto-filled from Bydlisko" : undefined}
                    onChange={(val) => setLeg(idx, "from_place", val)}
                  />
                  <span className="doc-meta">→</span>
                  <PlaceInput
                    value={leg.to_place}
                    readOnly={isLast(idx) && !trip}
                    placeholder="To"
                    title={isLast(idx) ? "Auto-filled from Bydlisko" : undefined}
                    onChange={(val) => setLeg(idx, "to_place", val)}
                  />
                  {legs.length > 2 && !isFirst(idx) && !isLast(idx) && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeLeg(idx)}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                {/* Times + transport row */}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <select
                    style={{ flex: "1 1 130px" }}
                    value={leg.transport}
                    onChange={(e) => {
                      const transport = e.target.value;
                      setLegs((ls) => ls.map((l, i) => (
                        i === idx
                          // km belongs to a car leg — don't leave one stranded on a flight.
                          ? { ...l, transport, distance_km: CAR_TRANSPORTS.has(transport) ? l.distance_km : "" }
                          : l
                      )));
                    }}
                  >
                    {TRANSPORTS.map((x) => <option key={x} value={x}>{x}</option>)}
                  </select>
                  <select
                    style={{ flex: "1 1 130px" }}
                    title="Country this leg arrives in — sets which per-diem rate applies from here on"
                    value={leg.country}
                    onChange={(e) => setLeg(idx, "country", e.target.value)}
                  >
                    <option value="">— arrives home (SK) —</option>
                    {countryOptions.map((r) => (
                      <option key={r.code} value={r.code}>
                        {r.name} ({r.code}) · {r.rate} €/deň
                      </option>
                    ))}
                    {countryOptions.length === 0 && (
                      <option value="" disabled>No countries yet — add them in Settings</option>
                    )}
                    {leg.country && !countryOptions.some((r) => r.code === leg.country) && (
                      <option value={leg.country}>{leg.country} — no rate configured</option>
                    )}
                  </select>
                  {f.end_date && f.end_date !== f.trip_date && !isFirst(idx) && !isLast(idx) && (
                    <input
                      type="date" style={{ width: 140 }}
                      title="Date of this leg"
                      min={f.trip_date || undefined}
                      max={f.end_date || undefined}
                      value={leg.leg_date}
                      onChange={(e) => setLeg(idx, "leg_date", e.target.value)}
                    />
                  )}
                  <div style={{ display: "flex", gap: 4, alignItems: "center", flex: "0 0 auto" }}>
                    <input
                      type="time" style={{ width: 100 }}
                      title="Departure time"
                      value={leg.depart_time}
                      onChange={(e) => setLeg(idx, "depart_time", e.target.value)}
                    />
                    <span className="doc-meta">–</span>
                    <input
                      type="time" style={{ width: 100 }}
                      title="Arrival time"
                      value={leg.arrive_time}
                      onChange={(e) => setLeg(idx, "arrive_time", e.target.value)}
                    />
                  </div>
                </div>
                {/* Expense + per-diem + km row */}
                <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                  {CAR_TRANSPORTS.has(leg.transport) && (
                    <>
                      <input
                        type="number" step="1" min="0"
                        style={{ flex: "0 0 80px" }}
                        placeholder="km"
                        title="Auto-filled from From/To once both are set"
                        value={leg.distance_km}
                        onChange={(e) => setLeg(idx, "distance_km", e.target.value)}
                      />
                      {calcIdx === idx && <Spinner />}
                      {calcIdx !== idx && calcErrors[idx] && (
                        <span className="doc-meta" style={{ color: "var(--danger, #e53)" }} title={calcErrors[idx]}>
                          km lookup failed
                        </span>
                      )}
                    </>
                  )}
                  <input
                    type="number" step="0.01" min="0"
                    style={{ flex: "1 1 100px" }}
                    placeholder="Výdavky € (ticket, taxi…)"
                    value={leg.expense}
                    onChange={(e) => setLeg(idx, "expense", e.target.value)}
                  />
                  <input
                    type="number" step="0.01" min="0"
                    style={{ flex: "1 1 100px" }}
                    placeholder="Stravné € (blank = auto)"
                    value={leg.per_diem}
                    onChange={(e) => setLeg(idx, "per_diem", e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="doc-meta" style={{ marginTop: 4 }}>
            First leg departs from Bydlisko; last leg returns to Bydlisko. Stravné per leg — fill when rates differ (SK vs. foreign). Leave blank on all legs to auto-calculate from duration.
          </p>
        </div>

        {/* Right below the legs: this only appears once a leg uses a company car,
            so it belongs next to where that transport is chosen. */}
        {hasCarLeg && vehicles.length > 0 && (
          <div className="field">
            <label>Vehicle (Logbook)</label>
            <select
              value={f.vehicle_id}
              onChange={(e) => {
                set("vehicle_id")(e);
                if (e.target.value) rememberVehicleId(Number(e.target.value));
              }}
            >
              <option value="">— auto-select —</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.ecv}{v.manufacturer ? ` · ${v.manufacturer}` : ""}{v.car_model ? ` ${v.car_model}` : ""}
                </option>
              ))}
            </select>
            <span className="doc-meta" style={{ marginTop: 4, display: "block" }}>
              A company-car leg is recorded in the Kniha jázd under this vehicle.
            </span>
          </div>
        )}
        {hasCarLeg && vehicles.length === 0 && (
          <p className="doc-meta">
            A leg uses a company car, but no vehicles are registered — add one under Logbook
            for this trip to appear in the Kniha jázd.
          </p>
        )}

        {!trip && (
          <div className="field">
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} style={{ width: "auto" }} />
              Repeat — create on chosen weekdays of {SK_MONTHS[period.month - 1]} {period.year}
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
