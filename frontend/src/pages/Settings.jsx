import { useState } from "react";
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
