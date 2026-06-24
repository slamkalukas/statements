import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileText,
  FolderSync,
  Link2,
  Lock,
  LockOpen,
  ScanSearch,
  Trash2,
  Unlink,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadDocument } from "../api";
import { EmptyState, Loading, Modal, Spinner, StatusBadge, Toast } from "../components/UI";
import { KIND_LABELS, KINDS, formatAmount, formatBytes, periodLabel } from "../utils";

export default function PeriodDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [period, setPeriod] = useState(null);
  const [lines, setLines] = useState(null);
  const [docs, setDocs] = useState(null);
  const [toast, setToast] = useState("");
  const [attachLine, setAttachLine] = useState(null);

  async function load() {
    const [periods, ls, ds] = await Promise.all([
      api.get("/periods"),
      api.get(`/periods/${id}/lines`),
      api.get(`/periods/${id}/documents`),
    ]);
    setPeriod(periods.find((p) => String(p.id) === String(id)) || null);
    setLines(ls);
    setDocs(ds);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function flash(msg) {
    setToast(msg);
    setTimeout(() => setToast(""), 2400);
  }

  if (period === null || lines === null || docs === null) return <Loading />;
  const closed = period.status === "closed";

  async function toggleStatus() {
    await api.post(`/periods/${period.id}/${closed ? "reopen" : "close"}`);
    flash(closed ? "Month reopened" : "Month closed");
    load();
  }

  async function unlink(line) {
    await api.post(`/lines/${line.id}/unlink`);
    flash("Unlinked");
    load();
  }

  async function autoMatch() {
    const r = await api.post(`/periods/${id}/auto-match`, {});
    const ocr = r.ocr > 0 ? ` (${r.ocr} via OCR)` : "";
    if (r.matched > 0) {
      flash(`Paired ${r.matched} payment${r.matched === 1 ? "" : "s"}${r.ambiguous ? `, ${r.ambiguous} ambiguous` : ""} · ${r.still_missing} still missing${ocr}`);
    } else if (r.scanned > 0) {
      flash(`Scanned ${r.scanned} document${r.scanned === 1 ? "" : "s"}${ocr} — no new unambiguous matches`);
    } else {
      flash("Nothing to match — no unpaired documents found");
    }
    load();
  }

  async function removeDoc(doc) {
    if (!confirm(`Delete "${doc.original_filename}"? This removes the file from disk.`)) return;
    await api.del(`/documents/${doc.id}`);
    flash("Document deleted");
    load();
  }

  async function deleteMonth() {
    if (!confirm(`Delete ${periodLabel(period.year, period.month)}?`)) return;
    try {
      await api.del(`/periods/${period.id}`);
      navigate("/periods");
    } catch (err) {
      flash(err.message);
    }
  }

  const outgoing = lines.filter((l) => l.amount < 0);
  const missing = outgoing.filter((l) => l.document_id == null);
  const empty = docs.length === 0 && lines.length === 0;

  return (
    <>
      <Link to="/periods" className="back-link">
        <ArrowLeft size={15} /> All months
      </Link>

      <div className="section-head">
        <div>
          <h1 className="page-title">{periodLabel(period.year, period.month)}</h1>
          <p className="page-sub">
            {period.has_statement
              ? `${outgoing.length} payment${outgoing.length === 1 ? "" : "s"} · ${missing.length} missing a document`
              : "No statement imported yet"}
            {period.note ? ` · ${period.note}` : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <StatusBadge status={period.status} />
          <button className="btn" onClick={toggleStatus}>
            {closed ? <LockOpen size={15} /> : <Lock size={15} />}
            {closed ? "Reopen" : "Close month"}
          </button>
        </div>
      </div>

      {closed && (
        <div className="callout" style={{ marginBottom: 16 }}>
          <Lock size={16} />
          This month is closed. Reopen it to import, attach, or remove anything.
        </div>
      )}

      {/* ---- Reconciliation: the primary view ---- */}
      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <div className="card-head" style={{ marginBottom: 14 }}>
          <h3>Reconciliation</h3>
          {period.has_statement &&
            (missing.length === 0 ? (
              <span className="tag shared">
                <CheckCircle2 size={13} /> All payments documented
              </span>
            ) : (
              <span className="tag warn">
                <AlertCircle size={13} /> {missing.length} missing
              </span>
            ))}
        </div>

        {!period.has_statement ? (
          <StatementImport periodId={period.id} disabled={closed} onDone={(r) => { flash(`Imported ${r.imported} transactions (${r.format})`); load(); }} />
        ) : (
          <>
            <ReconcileTable
              outgoing={outgoing}
              closed={closed}
              onAttach={(line) => setAttachLine(line)}
              onUnlink={unlink}
              onDownload={(docId, name) => downloadDocument(docId, name)}
            />
            {!closed && (
              <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
                {missing.length > 0 && (
                  <button className="btn btn-accent btn-sm" onClick={autoMatch} title="Scan unpaired documents and pair them to payments by amount">
                    <ScanSearch size={14} /> Scan &amp; auto-match
                  </button>
                )}
                <StatementImport
                  periodId={period.id}
                  disabled={closed}
                  compact
                  onDone={(r) => { flash(`Imported ${r.imported} new (${r.duplicates} dup)`); load(); }}
                />
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={async () => {
                    if (!confirm("Clear all parsed statement lines for this month? Uploaded files stay.")) return;
                    await api.del(`/periods/${period.id}/lines`);
                    flash("Statement cleared");
                    load();
                  }}
                >
                  <Trash2 size={14} /> Clear statement
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* ---- All documents ---- */}
      <DocumentsCard
        period={period}
        docs={docs}
        closed={closed}
        onUploaded={(doc) => { flash(uploadMessage(doc)); load(); }}
        onDownload={(docId, name) => downloadDocument(docId, name)}
        onDelete={removeDoc}
      />

      {empty && !closed && (
        <div style={{ marginTop: 16 }}>
          <button className="btn btn-danger" onClick={deleteMonth}>
            <Trash2 size={15} /> Delete this empty month
          </button>
        </div>
      )}

      {attachLine && (
        <AttachModal
          line={attachLine}
          periodId={period.id}
          documents={docs}
          onClose={() => setAttachLine(null)}
          onDone={() => { setAttachLine(null); flash("Document attached"); load(); }}
        />
      )}

      <Toast message={toast} />
    </>
  );
}

function uploadMessage(doc) {
  if (doc && doc.extracted_via && doc.amount != null) {
    const how = doc.extracted_via === "ocr" ? "OCR" : "the file";
    return `Uploaded · read ${formatAmount(doc.amount)} via ${how}`;
  }
  return "Uploaded";
}

function ExtractBadge({ via }) {
  if (!via) return null;
  // How the amount/date were read off the file.
  const ocr = via === "ocr";
  return (
    <span
      className="tag"
      title={ocr ? "Amount/date read by OCR (scanned document)" : "Amount/date read from the file's text"}
      style={{ marginLeft: 8, fontSize: 11, padding: "1px 7px", verticalAlign: "middle" }}
    >
      <ScanSearch size={11} /> {ocr ? "OCR" : "auto-read"}
    </span>
  );
}

function Amount({ value }) {
  return (
    <span className="num" style={{ color: value < 0 ? "var(--bad)" : "var(--ok)" }}>
      {value < 0 ? "−" : "+"}
      {formatAmount(Math.abs(value))}
    </span>
  );
}

function ReconcileTable({ outgoing, closed, onAttach, onUnlink, onDownload }) {
  if (outgoing.length === 0) {
    return <EmptyState title="No outgoing payments" hint="This statement has no payments that need a document." />;
  }
  // Missing first, so the work to do is at the top.
  const sorted = [...outgoing].sort((a, b) => (a.document_id == null ? 0 : 1) - (b.document_id == null ? 0 : 1));
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th>Date</th>
            <th>Payee / description</th>
            <th className="right">Amount</th>
            <th>Document</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((l) => (
            <tr key={l.id}>
              <td className="num">{l.txn_date}</td>
              <td>
                <div style={{ fontWeight: 600 }}>{l.payee || l.description || "—"}</div>
                {l.payee && l.description && <div className="doc-meta">{l.description}</div>}
              </td>
              <td className="right">
                <Amount value={l.amount} />
              </td>
              <td>
                {l.document_id ? (
                  <button className="tag shared" style={{ border: "none", cursor: "pointer" }} onClick={() => onDownload(l.document_id, l.document_filename)}>
                    <CheckCircle2 size={13} /> {l.document_filename}
                  </button>
                ) : (
                  <span className="tag warn">
                    <AlertCircle size={13} /> Missing
                  </span>
                )}
              </td>
              <td className="right">
                {!closed &&
                  (l.document_id ? (
                    <button className="btn btn-ghost btn-sm" title="Unlink" onClick={() => onUnlink(l)}>
                      <Unlink size={15} />
                    </button>
                  ) : (
                    <button className="btn btn-sm" onClick={() => onAttach(l)}>
                      <Link2 size={14} /> Attach
                    </button>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatementImport({ periodId, disabled, compact, onDone }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    const file = ref.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.postForm(`/periods/${periodId}/statement`, fd);
      if (ref.current) ref.current.value = "";
      onDone(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (compact) {
    return (
      <>
        <input ref={ref} type="file" style={{ display: "none" }} onChange={submit} disabled={disabled} />
        <button className="btn btn-sm" disabled={disabled || busy} onClick={() => ref.current?.click()}>
          {busy ? <Spinner /> : <Upload size={14} />} Re-import statement
        </button>
        {error && <span className="error-text">{error}</span>}
      </>
    );
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="muted" style={{ margin: 0 }}>
        Upload this month's bank statement — its transactions become the checklist. Tatra
        CAMT.053 XML, George (SLSP) JSON, and generic CSV are detected automatically.
      </p>
      {error && <p className="error-text">{error}</p>}
      <div className="dropzone">
        <input ref={ref} type="file" disabled={disabled} onChange={submit} />
      </div>
      {busy && <Spinner />}
    </div>
  );
}

function AttachModal({ line, periodId, documents, onClose, onDone }) {
  const target = Math.abs(line.amount);
  const unlinked = documents.filter((d) => d.linked_line_count === 0);
  const suggested = useMemo(
    () => unlinked.filter((d) => d.amount != null && Math.abs(d.amount - target) < 0.005),
    [unlinked, target]
  );
  const others = unlinked.filter((d) => !suggested.includes(d));

  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function link(docId) {
    setBusy(true);
    setError("");
    try {
      await api.post(`/lines/${line.id}/link`, { document_id: docId });
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  async function uploadNew() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", "invoice");
    fd.append("amount", target.toFixed(2));
    fd.append("line_id", String(line.id));
    try {
      await api.postForm(`/periods/${periodId}/documents`, fd);
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Attach a document" onClose={onClose}>
      <div className="stack" style={{ gap: 14 }}>
        <div className="muted">
          {line.payee || line.description || "Payment"} ·{" "}
          <span className="num">{formatAmount(target)}</span> · {line.txn_date}
        </div>
        {error && <p className="error-text">{error}</p>}

        {suggested.length > 0 && (
          <div>
            <h4 style={{ marginBottom: 8 }}>Suggested (same amount)</h4>
            {suggested.map((d) => (
              <div key={d.id} className="doc-row">
                <div className="doc-icon"><FileText size={18} /></div>
                <div className="doc-main">
                  <div className="doc-name">{d.original_filename}</div>
                  <div className="doc-meta">{KIND_LABELS[d.kind]} · {formatBytes(d.size_bytes)}</div>
                </div>
                <button className="btn btn-accent btn-sm" disabled={busy} onClick={() => link(d.id)}>
                  <Link2 size={14} /> Link
                </button>
              </div>
            ))}
          </div>
        )}

        {others.length > 0 && (
          <div>
            <h4 style={{ marginBottom: 8 }}>Other unlinked documents</h4>
            {others.map((d) => (
              <div key={d.id} className="doc-row">
                <div className="doc-icon"><FileText size={18} /></div>
                <div className="doc-main">
                  <div className="doc-name">{d.original_filename}</div>
                  <div className="doc-meta">
                    {KIND_LABELS[d.kind]}
                    {d.amount != null ? ` · ${formatAmount(d.amount)}` : ""}
                  </div>
                </div>
                <button className="btn btn-sm" disabled={busy} onClick={() => link(d.id)}>
                  <Link2 size={14} /> Link
                </button>
              </div>
            ))}
          </div>
        )}

        <div>
          <h4 style={{ marginBottom: 8 }}>Or upload a new invoice</h4>
          <input ref={fileRef} type="file" />
          <button className="btn btn-accent" style={{ marginTop: 10 }} disabled={busy} onClick={uploadNew}>
            {busy ? <Spinner /> : <Upload size={16} />} Upload &amp; link
          </button>
        </div>
      </div>
    </Modal>
  );
}

function DocumentsCard({ period, docs, closed, onUploaded, onDownload, onDelete }) {
  const grouped = KINDS.map((kind) => ({ kind, items: docs.filter((d) => d.kind === kind) })).filter(
    (g) => g.items.length > 0
  );
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");

  async function syncFolder() {
    setSyncing(true);
    setSyncMsg("");
    try {
      const r = await api.post(`/periods/${period.id}/sync`, {});
      if (r.imported === 0) {
        setSyncMsg(`All ${r.scanned} file${r.scanned === 1 ? "" : "s"} already tracked.`);
      } else {
        const ocr = r.ocr > 0 ? `, ${r.ocr} via OCR` : "";
        const paired = r.matched > 0 ? ` · paired ${r.matched} payment${r.matched === 1 ? "" : "s"}` : "";
        setSyncMsg(`Synced ${r.imported} new file${r.imported === 1 ? "" : "s"}${ocr}${paired}.`);
        onUploaded();
      }
    } catch (err) {
      setSyncMsg(err.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="doc-grid">
      <div className="card card-pad">
        <h3 style={{ marginBottom: 4 }}>Add a document</h3>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          Stored on the host folder under {period.year}/{String(period.month).padStart(2, "0")}/.
        </p>
        {!closed && (
          <div style={{ marginBottom: 16 }}>
            <button
              className="btn btn-secondary"
              onClick={syncFolder}
              disabled={closed || syncing}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {syncing ? <Spinner /> : <FolderSync size={15} />}
              Sync from folder
            </button>
            {syncMsg && <p className="doc-meta" style={{ marginTop: 6 }}>{syncMsg}</p>}
          </div>
        )}
        <UploadForm periodId={period.id} disabled={closed} onUploaded={onUploaded} />
      </div>

      <div className="card card-pad">
        <h3 style={{ marginBottom: 16 }}>Documents</h3>
        {docs.length === 0 ? (
          <EmptyState title="No files yet" hint="Upload invoices, receipts, or other supporting documents." />
        ) : (
          grouped.map((g) => (
            <div key={g.kind} className="kind-group">
              <h4>{KIND_LABELS[g.kind]}</h4>
              {g.items.map((d) => (
                <div key={d.id} className="doc-row">
                  <div className="doc-icon"><FileText size={18} /></div>
                  <div className="doc-main">
                    <div className="doc-name">
                      {d.original_filename}
                      <ExtractBadge via={d.extracted_via} />
                    </div>
                    <div className="doc-meta">
                      {formatBytes(d.size_bytes)}
                      {d.doc_date ? ` · ${d.doc_date}` : ""}
                      {d.amount != null ? ` · ${formatAmount(d.amount)}` : ""}
                      {d.linked_line_count > 0 ? ` · linked` : ""}
                    </div>
                  </div>
                  <div className="doc-actions">
                    <button className="btn btn-ghost btn-sm" title="Download" onClick={() => onDownload(d.id, d.original_filename)}>
                      <Download size={16} />
                    </button>
                    {!closed && (
                      <button className="btn btn-ghost btn-sm" title="Delete" onClick={() => onDelete(d)}>
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function UploadForm({ periodId, disabled, onUploaded }) {
  const fileRef = useRef(null);
  const [kind, setKind] = useState("invoice");
  const [note, setNote] = useState("");
  const [docDate, setDocDate] = useState("");
  const [amount, setAmount] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setBusy(true);
    setError("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    if (note) fd.append("note", note);
    if (docDate) fd.append("doc_date", docDate);
    if (amount) fd.append("amount", amount);
    try {
      const doc = await api.postForm(`/periods/${periodId}/documents`, fd);
      setNote("");
      setDocDate("");
      setAmount("");
      setFileName("");
      if (fileRef.current) fileRef.current.value = "";
      onUploaded(doc);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="stack" style={{ gap: 14 }}>
      {error && <p className="error-text">{error}</p>}
      <div className="field">
        <label htmlFor="kind">Type</label>
        <select id="kind" value={kind} onChange={(e) => setKind(e.target.value)} disabled={disabled}>
          {KINDS.map((k) => (
            <option key={k} value={k}>{KIND_LABELS[k]}</option>
          ))}
        </select>
      </div>
      <div className="row-2">
        <div className="field">
          <label htmlFor="dd">Document date</label>
          <input id="dd" type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} disabled={disabled} />
        </div>
        <div className="field">
          <label htmlFor="amt">Amount</label>
          <input id="amt" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="helps matching" disabled={disabled} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="dn">Note</label>
        <input id="dn" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" disabled={disabled} />
      </div>
      <div className="field">
        <label htmlFor="file">File</label>
        <input id="file" ref={fileRef} type="file" disabled={disabled} onChange={(e) => setFileName(e.target.files?.[0]?.name || "")} />
        {fileName && <span className="doc-meta">{fileName}</span>}
      </div>
      <button className="btn btn-accent" type="submit" disabled={disabled || busy}>
        {busy ? <Spinner /> : <Upload size={16} />} Upload
      </button>
    </form>
  );
}
