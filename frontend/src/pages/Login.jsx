import { useState } from "react";
import { Spinner } from "../components/UI";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <aside className="login-aside">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div className="brand-name">Statements</div>
        </div>
        <div>
          <div className="big">
            Every month,
            <br />
            <em>filed</em> and
            <br />
            <em>findable</em>.
          </div>
          <div className="login-ledger">
            <div className="lrow">
              <span>Bank statement</span>
              <span>one place</span>
            </div>
            <div className="lrow">
              <span>Invoices & receipts</span>
              <span>by month</span>
            </div>
            <div className="lrow">
              <span>Files on your disk</span>
              <span>you own them</span>
            </div>
          </div>
        </div>
        <div style={{ color: "#7c8492", fontSize: 12 }}>
          A tidy monthly archive of your bank statements and supporting documents.
        </div>
      </aside>

      <div className="login-main">
        <div className="login-card">
          <h1 className="page-title">Welcome back</h1>
          <p className="page-sub">Sign in with your email and password.</p>

          {error && (
            <p className="error-text" style={{ marginTop: 12 }}>
              {error}
            </p>
          )}

          <form onSubmit={submit} className="stack" style={{ gap: 12, marginTop: 16 }}>
            <div className="field">
              <label htmlFor="em">Email</label>
              <input
                id="em"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                autoComplete="email"
                required
              />
            </div>
            <div className="field">
              <label htmlFor="pw">Password</label>
              <input
                id="pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
            </div>
            <button className="btn btn-accent" disabled={busy} type="submit">
              {busy ? <Spinner /> : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
