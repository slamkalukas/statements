import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect } from "react";

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />;
}

export function Loading() {
  return (
    <div className="loading-block">
      <Spinner />
    </div>
  );
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  );
}

export function Toast({ message }) {
  if (!message) return null;
  return <div className="toast">{message}</div>;
}

export function MonthNav({ label, onPrev, onNext, disablePrev, disableNext }) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <button className="btn btn-ghost btn-sm" onClick={onPrev} disabled={disablePrev}>
        <ChevronLeft size={16} />
      </button>
      <span style={{ fontWeight: 600, minWidth: 150, textAlign: "center" }}>{label}</span>
      <button className="btn btn-ghost btn-sm" onClick={onNext} disabled={disableNext}>
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

export function StatusBadge({ status }) {
  const closed = status === "closed";
  return (
    <span className={`tag ${closed ? "private" : "shared"}`}>
      {closed ? "Closed" : "Open"}
    </span>
  );
}
