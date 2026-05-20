import { Link, useNavigate } from "react-router-dom";
import { Library, LogOut, ShieldCheck } from "lucide-react";

import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { apiJson } from "../lib/api";

export function DashboardPage({ user, onLogout }) {
  const navigate = useNavigate();

  async function logout() {
    await apiJson("/logout", { method: "POST" });
    onLogout();
    navigate("/login", { replace: true });
  }

  return (
    <main className="app-shell">
      <nav className="topbar">
        <Link className="brand-link compact" to="/dashboard">
          <Library size={24} />
          <span>MyGameList</span>
        </Link>
        <Button variant="secondary" size="sm" onClick={logout}>
          <LogOut size={16} /> Log out
        </Button>
      </nav>
      <section className="dashboard-grid">
        <Card>
          <CardHeader>
            <CardTitle><ShieldCheck size={20} /> Dashboard</CardTitle>
            <CardDescription>Signed in as {user.displayName || user.username}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="details-list">
              <div><dt>Username</dt><dd>{user.username}</dd></div>
              <div><dt>Email</dt><dd>{user.email}</dd></div>
              <div><dt>Role</dt><dd>{user.role}</dd></div>
            </dl>
          </CardContent>
        </Card>
        <Card className="feature-card">
          <CardHeader>
            <CardTitle>Next feature slice</CardTitle>
            <CardDescription>Game list endpoints can now follow the protected BFF proxy pattern.</CardDescription>
          </CardHeader>
        </Card>
      </section>
    </main>
  );
}
