import { CalendarDays, FileText, FolderOpen, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { EmptyState, Loading, StatusBadge } from "../components/UI";
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

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/dashboard").then(setData);
  }, []);

  if (data === null) return <Loading />;

  const tiles = [
    { label: "Missing documents", value: data.total_missing, icon: TriangleAlert, alert: data.total_missing > 0 },
    { label: "Months tracked", value: data.periods_tracked, icon: CalendarDays },
    { label: "Documents", value: data.total_documents, icon: FileText },
    { label: "Stored", value: formatBytes(data.total_size), icon: FolderOpen },
  ];

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Your monthly bookkeeping archive at a glance.</p>
        </div>
      </div>

      <div className="stat-grid">
        {tiles.map((t) => (
          <div key={t.label} className="card stat">
            <div className="label">
              <t.icon size={15} /> {t.label}
            </div>
            <div className="value" style={t.alert ? { color: "var(--bad)" } : undefined}>
              {t.value}
            </div>
          </div>
        ))}
      </div>

      {data.total_missing > 0 && (
        <div className="callout" style={{ marginTop: 20 }}>
          <TriangleAlert size={16} />
          {data.total_missing} payment{data.total_missing === 1 ? "" : "s"} across{" "}
          {data.months_with_missing} month{data.months_with_missing === 1 ? "" : "s"} still need a
          supporting invoice or bill.
        </div>
      )}
      {data.no_statement > 0 && (
        <div className="callout" style={{ marginTop: 12 }}>
          <TriangleAlert size={16} />
          {data.no_statement} month{data.no_statement === 1 ? "" : "s"} have no bank statement
          imported yet.
        </div>
      )}

      <div className="section-head" style={{ marginTop: 28 }}>
        <h3>Recent months</h3>
      </div>

      {data.recent_periods.length === 0 ? (
        <div className="card card-pad">
          <EmptyState
            title="No months yet"
            hint="Head to Months to create your first one."
            action={
              <button className="btn btn-accent" onClick={() => navigate("/periods")}>
                Go to Months
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
              {data.recent_periods.map((p) => (
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
    </>
  );
}
