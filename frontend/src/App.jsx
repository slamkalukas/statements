import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/UI";
import { useAuth } from "./context/AuthContext";
import Dashboard from "./pages/Dashboard";
import Files from "./pages/Files";
import Login from "./pages/Login";
import PeriodDetail from "./pages/PeriodDetail";
import Periods from "./pages/Periods";
import Settings from "./pages/Settings";
import Travel from "./pages/Travel";

export default function App() {
  const { user, ready } = useAuth();

  if (!ready) return <Loading />;
  if (!user) return <Login />;

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="periods" element={<Periods />} />
          <Route path="periods/:id" element={<PeriodDetail />} />
          <Route path="files" element={<Files />} />
          <Route path="travel" element={<Travel />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
