import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "../api";

const AuthContext = createContext(null);
const USER_KEY = "statements.user";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function verify() {
      if (getToken()) {
        try {
          const me = await api.get("/auth/me");
          setUser(me);
          localStorage.setItem(USER_KEY, JSON.stringify(me));
        } catch {
          // token invalid; clear
        }
      }
      setReady(true);
    }
    verify();
    const onLogout = () => doLogout();
    window.addEventListener("statements:logout", onLogout);
    return () => window.removeEventListener("statements:logout", onLogout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(email, password) {
    const { token, user: u } = await api.post("/auth/login", { email, password });
    setToken(token);
    setUser(u);
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    return u;
  }

  function doLogout() {
    setToken(null);
    localStorage.removeItem(USER_KEY);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, logout: doLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
