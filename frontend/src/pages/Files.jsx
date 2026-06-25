import { ChevronRight, Download, FileText, Folder, HardDrive } from "lucide-react";
import { useEffect, useState } from "react";
import { api, downloadFile } from "../api";
import { EmptyState, Loading } from "../components/UI";
import { formatBytes } from "../utils";

export default function Files() {
  const [path, setPath] = useState("");
  const [listing, setListing] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setListing(null);
    setError("");
    api.get(`/files?path=${encodeURIComponent(path)}`)
      .then(setListing)
      .catch((e) => setError(e.message));
  }, [path]);

  // Breadcrumb segments built from the current path.
  const segments = path ? path.split("/") : [];
  const crumbs = segments.map((seg, i) => ({
    label: seg,
    path: segments.slice(0, i + 1).join("/"),
  }));

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="page-title">Files</h1>
          <p className="page-sub">Browse the documents folder.</p>
        </div>
      </div>

      <div className="breadcrumb" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4, marginBottom: 14 }}>
        <button className="crumb" onClick={() => setPath("")} title="Documents root">
          <HardDrive size={14} /> documents
        </button>
        {crumbs.map((c) => (
          <span key={c.path} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <ChevronRight size={14} style={{ opacity: 0.5 }} />
            <button className="crumb" onClick={() => setPath(c.path)}>{c.label}</button>
          </span>
        ))}
      </div>

      <div className="card card-pad">
        {error ? (
          <p className="error-text">{error}</p>
        ) : !listing ? (
          <Loading />
        ) : listing.entries.length === 0 ? (
          <EmptyState title="Empty folder" hint="No files or subfolders here yet." />
        ) : (
          <div className="file-list">
            {listing.entries.map((e) =>
              e.is_dir ? (
                <button key={e.path} className="file-row as-button" onClick={() => setPath(e.path)}>
                  <div className="doc-icon"><Folder size={18} /></div>
                  <div className="doc-main">
                    <div className="doc-name">{e.name}</div>
                    <div className="doc-meta">{e.child_count} item{e.child_count === 1 ? "" : "s"}</div>
                  </div>
                  <ChevronRight size={16} style={{ opacity: 0.5 }} />
                </button>
              ) : (
                <div key={e.path} className="file-row">
                  <div className="doc-icon"><FileText size={18} /></div>
                  <div className="doc-main">
                    <div className="doc-name">{e.name}</div>
                    <div className="doc-meta">
                      {formatBytes(e.size_bytes)}
                      {e.modified ? ` · ${e.modified.replace("T", " ")}` : ""}
                    </div>
                  </div>
                  <button
                    className="btn btn-ghost btn-sm"
                    title="Download"
                    onClick={() => downloadFile(e.path, e.name)}
                  >
                    <Download size={16} />
                  </button>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </>
  );
}
