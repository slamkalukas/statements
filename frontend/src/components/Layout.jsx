import { CalendarDays, LayoutDashboard, LogOut, Menu, Settings as SettingsIcon } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/periods", label: "Months", icon: CalendarDays },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">S</div>
          <div className="brand-name">Statements</div>
        </div>
        <nav className="nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          Signed in as {user?.email}
          <br />
          Statements v1.0
        </div>
      </aside>

      <div className={`backdrop ${open ? "show" : ""}`} onClick={() => setOpen(false)} />

      <div className="main">
        <header className="header">
          <button
            className="menu-btn"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            <Menu size={18} />
          </button>
          <div className="spacer" />
          <div className="user-chip">
            <div className="avatar">{(user?.email || "?")[0].toUpperCase()}</div>
            <div className="meta">
              <div className="nm">Admin</div>
              <div className="em">{user?.email}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout} title="Log out">
            <LogOut size={16} />
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
