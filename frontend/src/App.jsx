import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { apiJson } from "./lib/api";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

function RequireAuth({ ready, user, children }) {
  if (!ready) {
    return <main className="loading-page">Loading...</main>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  async function loadUser() {
    const me = await apiJson("/api/me");
    setUser(me);
    return me;
  }

  useEffect(() => {
    loadUser().catch(() => setUser(null)).finally(() => setReady(true));
  }, []);

  return (
    <Routes>
      <Route path="/" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
      <Route path="/login" element={<LoginPage onAuthenticated={loadUser} />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/dashboard"
        element={
          <RequireAuth ready={ready} user={user}>
            <DashboardPage user={user} onLogout={() => setUser(null)} />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
