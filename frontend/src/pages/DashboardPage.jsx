import { Link, useNavigate } from "react-router-dom";
import { Library, LogOut, ShieldCheck, Users } from "lucide-react";

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
    <main className="mx-auto w-[min(1120px,calc(100vw-32px))] py-7 pb-11">
      <nav className="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <Link className="inline-flex w-fit items-center gap-2.5 text-lg font-extrabold text-foreground hover:no-underline" to="/dashboard">
          <Library size={24} />
          <span>MyGameList</span>
        </Link>
        <div className="flex flex-wrap gap-2">
          {user.role === "ADMIN" ? (
            <Button asChild variant="secondary" size="sm">
              <Link to="/admin">
                <Users size={16} /> Admin
              </Link>
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" onClick={logout}>
            <LogOut size={16} /> Log out
          </Button>
        </div>
      </nav>
      <section className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(280px,0.7fr)]">
        <Card className="max-w-none">
          <CardHeader>
            <CardTitle><ShieldCheck size={20} /> Dashboard</CardTitle>
            <CardDescription>Signed in as {user.displayName || user.username}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-2.5">
              <div className="grid gap-1 border-b pb-2.5 sm:flex sm:justify-between sm:gap-4"><dt className="text-muted-foreground">Username</dt><dd className="m-0 [overflow-wrap:anywhere] font-extrabold">{user.username}</dd></div>
              <div className="grid gap-1 border-b pb-2.5 sm:flex sm:justify-between sm:gap-4"><dt className="text-muted-foreground">Email</dt><dd className="m-0 [overflow-wrap:anywhere] font-extrabold">{user.email}</dd></div>
              <div className="grid gap-1 border-b pb-2.5 sm:flex sm:justify-between sm:gap-4"><dt className="text-muted-foreground">Role</dt><dd className="m-0 [overflow-wrap:anywhere] font-extrabold">{user.role}</dd></div>
            </dl>
          </CardContent>
        </Card>
        <Card className="min-h-44 max-w-none">
          <CardHeader>
            <CardTitle>{user.role === "ADMIN" ? "Admin access" : "Next feature slice"}</CardTitle>
            <CardDescription>
              {user.role === "ADMIN"
                ? "User management is available from the admin panel."
                : "Game list endpoints can now follow the protected BFF proxy pattern."}
            </CardDescription>
          </CardHeader>
        </Card>
      </section>
    </main>
  );
}
