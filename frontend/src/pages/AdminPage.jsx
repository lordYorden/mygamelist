import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Library, LogOut, RefreshCcw, Shield, Users } from "lucide-react";

import { Button } from "../components/ui/button";
import { apiJson } from "../lib/api";

const ROLES = ["ADMIN", "MODERATOR", "GAMER"];

export function AdminPage({ user, onLogout }) {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const sortedUsers = useMemo(
    () => [...users].sort((left, right) => left.username.localeCompare(right.username)),
    [users],
  );

  async function loadUsers() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      const data = await apiJson("/api/admin/users");
      setUsers(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await apiJson("/logout", { method: "POST" });
    onLogout();
    navigate("/login", { replace: true });
  }

  async function changeRole(targetUser, role) {
    if (targetUser.role === role) {
      return;
    }
    setError("");
    setNotice("");
    setSavingId(targetUser.id);
    try {
      await apiJson(`/api/admin/users/${targetUser.id}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      await loadUsers();
      setNotice(`${targetUser.username} is now ${role}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingId(null);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  return (
    <main className="mx-auto w-[min(1180px,calc(100vw-32px))] py-7 pb-11">
      <nav className="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <Link className="inline-flex w-fit items-center gap-2.5 text-lg font-extrabold text-foreground hover:no-underline" to="/dashboard">
          <Library size={24} />
          <span>MyGameList</span>
        </Link>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="secondary" size="sm">
            <Link to="/dashboard">
              <ArrowLeft size={16} /> Dashboard
            </Link>
          </Button>
          <Button variant="secondary" size="sm" onClick={logout}>
            <LogOut size={16} /> Log out
          </Button>
        </div>
      </nav>

      <header className="mb-5 flex flex-col justify-between gap-3 border-b pb-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 inline-flex items-center gap-2 text-sm font-bold text-muted-foreground">
            <Shield size={16} /> {user.username}
          </p>
          <h1 className="m-0 flex items-center gap-3 text-3xl font-extrabold tracking-normal">
            <Users size={30} /> Admin
          </h1>
        </div>
        <Button className="w-fit" variant="secondary" size="sm" onClick={loadUsers} disabled={loading}>
          <RefreshCcw size={16} /> Refresh
        </Button>
      </header>

      {error ? (
        <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 font-bold text-destructive">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-md border border-primary/20 bg-accent px-4 py-3 font-bold text-accent-foreground">
          {notice}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-md border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] border-collapse text-left text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-extrabold">User</th>
                <th className="px-4 py-3 font-extrabold">Email</th>
                <th className="px-4 py-3 font-extrabold">Display name</th>
                <th className="px-4 py-3 font-extrabold">Role</th>
                <th className="px-4 py-3 font-extrabold">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-5 text-muted-foreground" colSpan={5}>Loading users...</td>
                </tr>
              ) : sortedUsers.length === 0 ? (
                <tr>
                  <td className="px-4 py-5 text-muted-foreground" colSpan={5}>No users found.</td>
                </tr>
              ) : (
                sortedUsers.map((row) => {
                  const isSelf = row.id === user.id;
                  return (
                    <tr className="border-t" key={row.id}>
                      <td className="px-4 py-3 font-extrabold [overflow-wrap:anywhere]">{row.username}</td>
                      <td className="px-4 py-3 [overflow-wrap:anywhere]">{row.email}</td>
                      <td className="px-4 py-3">{row.displayName || "-"}</td>
                      <td className="px-4 py-3">
                        {isSelf ? (
                          <span className="inline-flex min-h-9 items-center rounded-md border bg-muted px-3 font-bold">
                            {row.role}
                          </span>
                        ) : (
                          <select
                            className="min-h-9 rounded-md border border-input bg-background px-3 font-bold outline-none focus:ring-2 focus:ring-ring disabled:cursor-wait disabled:opacity-70"
                            value={row.role}
                            disabled={savingId === row.id}
                            onChange={(event) => changeRole(row, event.target.value)}
                          >
                            {ROLES.map((role) => (
                              <option key={role} value={role}>{role}</option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(row.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
