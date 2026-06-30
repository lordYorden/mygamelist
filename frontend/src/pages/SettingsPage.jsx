import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Library, LogOut, PlugZap, RefreshCcw, Send, Settings, Trash2, Users } from "lucide-react";

import { Alert, AlertDescription, AlertIcon } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { apiJson } from "../lib/api";

export function SettingsPage({ user, onLogout }) {
  const navigate = useNavigate();
  const [webhooks, setWebhooks] = useState([]);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadWebhooks() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      setWebhooks(await apiJson("/api/webhooks"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function createWebhook(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSaving(true);
    try {
      const webhook = await apiJson("/api/webhooks", {
        method: "POST",
        body: JSON.stringify({ title, url }),
      });
      setWebhooks((current) => [webhook, ...current]);
      setTitle("");
      setUrl("");
      setNotice("Webhook saved.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function testWebhook(webhook) {
    setError("");
    setNotice("");
    setBusyId(webhook.id);
    try {
      const result = await apiJson(`/api/webhooks/${webhook.id}/test`, { method: "POST" });
      const status = result.targetStatus === null ? "no response" : `HTTP ${result.targetStatus}`;
      setNotice(`${result.message}: ${status}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteWebhook(webhook) {
    setError("");
    setNotice("");
    setBusyId(webhook.id);
    try {
      await apiJson(`/api/webhooks/${webhook.id}`, { method: "DELETE" });
      setWebhooks((current) => current.filter((item) => item.id !== webhook.id));
      setNotice("Webhook deleted.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function logout() {
    await apiJson("/logout", { method: "POST" });
    onLogout();
    navigate("/login", { replace: true });
  }

  useEffect(() => {
    loadWebhooks();
  }, []);

  return (
    <main className="mx-auto w-[min(1120px,calc(100vw-32px))] py-7 pb-11">
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

      <header className="mb-5 flex flex-col justify-between gap-3 border-b pb-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-2 inline-flex items-center gap-2 text-sm font-bold text-muted-foreground">
            <Settings size={16} /> {user.username}
          </p>
          <h1 className="m-0 flex items-center gap-3 text-3xl font-extrabold tracking-normal">
            <PlugZap size={30} /> Settings
          </h1>
        </div>
        <Button className="w-fit" variant="secondary" size="sm" onClick={loadWebhooks} disabled={loading}>
          <RefreshCcw size={16} /> Refresh
        </Button>
      </header>

      {error ? (
        <Alert className="mb-4">
          <AlertIcon />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {notice ? (
        <Alert className="mb-4" variant="success">
          <AlertIcon variant="success" />
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[minmax(300px,0.72fr)_minmax(0,1.28fr)]">
        <Card className="max-w-none self-start">
          <CardHeader>
            <CardTitle><Send size={20} /> New webhook</CardTitle>
            <CardDescription>Register a notification endpoint for account events.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-3" onSubmit={createWebhook}>
              <div className="grid gap-1.5">
                <Label htmlFor="webhook-title">Title</Label>
                <Input
                  id="webhook-title"
                  placeholder="Slack alerts"
                  value={title}
                  maxLength={80}
                  required
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="webhook-url">Callback URL</Label>
                <Input
                  id="webhook-url"
                  type="url"
                  placeholder="https://hooks.slack.com/services/..."
                  value={url}
                  maxLength={2048}
                  required
                  onChange={(event) => setUrl(event.target.value)}
                />
              </div>
              <Button type="submit" disabled={saving}>
                <PlugZap size={16} /> {saving ? "Saving..." : "Save webhook"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="max-w-none">
          <CardHeader>
            <CardTitle><PlugZap size={20} /> Notification webhooks</CardTitle>
            <CardDescription>{webhooks.length} registered endpoint{webhooks.length === 1 ? "" : "s"}.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3">
              {loading ? (
                <p className="m-0 text-sm text-muted-foreground">Loading webhooks...</p>
              ) : webhooks.length === 0 ? (
                <p className="m-0 text-sm text-muted-foreground">No webhooks registered.</p>
              ) : (
                webhooks.map((webhook) => (
                  <div className="grid gap-3 rounded-md border bg-background p-3 md:grid-cols-[minmax(0,1fr)_auto]" key={webhook.id}>
                    <div className="min-w-0">
                      <p className="m-0 font-extrabold [overflow-wrap:anywhere]">{webhook.title}</p>
                      <p className="m-0 mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm">{webhook.url}</p>
                      <p className="m-0 mt-1 text-sm text-muted-foreground">
                        Added {new Date(webhook.createdAt).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
                      <Button
                        className="w-fit"
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={busyId === webhook.id}
                        onClick={() => testWebhook(webhook)}
                      >
                        <Send size={16} /> Test
                      </Button>
                      <Button
                        className="w-fit"
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={busyId === webhook.id}
                        onClick={() => deleteWebhook(webhook)}
                      >
                        <Trash2 size={16} /> Delete
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
