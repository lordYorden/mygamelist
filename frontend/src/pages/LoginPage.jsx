import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";

import { AuthShell } from "../components/layout/AuthShell";
import { FormField } from "../components/auth/FormField";
import { Alert, AlertDescription, AlertIcon } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
import { apiJson, loginBody } from "../lib/api";

export function LoginPage({ onAuthenticated }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  function update(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await apiJson("/login", {
        method: "POST",
        body: loginBody(form),
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      await onAuthenticated();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Secure BFF login"
      title="Welcome back"
      description="Sign in through the BFF session flow. The browser receives only the protected session cookie."
    >
      <Card>
        <CardHeader>
          <CardTitle><LogIn size={20} /> Log in</CardTitle>
          <CardDescription>Use your username or email address.</CardDescription>
        </CardHeader>
        <CardContent>
          <form id="login-form" className="stack" onSubmit={submit}>
            <FormField
              id="username"
              label="Email or username"
              value={form.username}
              onChange={update}
              autoComplete="username"
              required
            />
            <FormField
              id="password"
              label="Password"
              type="password"
              value={form.password}
              onChange={update}
              autoComplete="current-password"
              required
            />
            {error && (
              <Alert variant="destructive">
                <AlertIcon />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </form>
        </CardContent>
        <CardFooter>
          <Button form="login-form" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign in"}
          </Button>
          <p className="form-link">
            New here? <Link to="/register">Create an account</Link>
          </p>
        </CardFooter>
      </Card>
    </AuthShell>
  );
}
