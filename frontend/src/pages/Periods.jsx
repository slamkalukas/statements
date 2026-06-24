import { AlertCircle, CheckCircle2, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { EmptyState, Loading, Modal, StatusBadge } from "../components/UI";
import { formatBytes, periodLabel } from "../utils";

function reconcileBadge(p) {
  if (!p.has_statement) return <span className="tag">No statement</span>;
  if (p.missing_count > 0)
    return (
      <span className="tag warn">
        <AlertCircle size={13} /> {p.missing_count} missing
      </span>
    );
  return (
    <span className="tag shared">
      <CheckCircle2 size={13} /> Complete
    </span>
  );
}

export default function Periods() {
  const navigate = useNavigate();
  const [periods, setPeriods] = useState(null);
  const [adding, setAdding] = useState(false);

  async function load() {
    setPeriods(await api.get("/periods"));
  }
  useEffect(() => {
    load();
  }, []);

  if (periods === null) return <Loading />;

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Months</h1>
          <p className="page-sub">Each month holds its bank statement and supporting documents.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setAdding(true)}>
          <Plus size={16} /> Add month
        </button>
      </div>

      {periods.length === 0 ? (
        <div className="card card-pad">
          <EmptyState
            title="No months yet"
            hint="Create your first month to start filing statements and invoices."
            action={
              <button className="btn btn-accent" onClick={() => setAdding(true)}>
                <Plus size={16} /> Add month
              </button>
            }
          />
        </div>
      ) : (
        <div className="card table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Month</th>
                <th>Status</th>
                <th>Reconciliation</th>
                <th className="right">Documents</th>
                <th className="right">Size</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((p) => (
                <tr key={p.id} className="clickable" onClick={() => navigate(`/periods/${p.id}`)}>
                  <td style={{ fontWeight: 600 }}>{periodLabel(p.year, p.month)}</td>
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td>{reconcileBadge(p)}</td>
                  <td className="right">{p.document_count}</td>
                  <td className="right">{formatBytes(p.total_size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {adding && (
        <AddMonthModal
          onClose={() => setAdding(false)}
          onCreated={(p) => {
            setAdding(false);
            navigate(`/periods/${p.id}`);
          }}
        />
      )}
    </>
  );
}

function AddMonthModal({ onClose, onCreated }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const p = await api.post("/periods", { year: Number(year), month: Number(month), note });
      onCreated(p);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Add a month"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-accent" onClick={submit} disabled={busy} form="add-month">
            Create
          </button>
        </>
      }
    >
      <form id="add-month" onSubmit={submit} className="stack" style={{ gap: 14 }}>
        {error && <p className="error-text">{error}</p>}
        <div className="row-2">
          <div className="field">
            <label htmlFor="yr">Year</label>
            <input
              id="yr"
              type="number"
              min="1970"
              max="2200"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="mo">Month</label>
            <select id="mo" value={month} onChange={(e) => setMonth(e.target.value)}>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {periodLabel(2000, m).split(" ")[0]}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="nt">Note (optional)</label>
          <input
            id="nt"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. VAT return month"
          />
        </div>
      </form>
    </Modal>
  );
}
