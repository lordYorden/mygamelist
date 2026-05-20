import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";

import { AuthShell } from "../components/layout/AuthShell";
import { FormField } from "../components/auth/FormField";
import { Alert, AlertDescription, AlertIcon } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import { Label } from "../components/ui/label";
import { apiJson } from "../lib/api";

export function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    username: "",
    email: "",
    displayName: "",
    password: "",
    confirmPassword: "",
    termsAccepted: true,
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  function update(event) {
    const { name, value, checked, type } = event.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setSubmitting(true);
    try {
      await apiJson("/api/register", {
        method: "POST",
        body: JSON.stringify({
          username: form.username,
          email: form.email,
          display_name: form.displayName || null,
          password: form.password,
          confirm_password: form.confirmPassword,
          terms_accepted: form.termsAccepted,
        }),
      });
      setMessage("Account created. Redirecting to login...");
      window.setTimeout(() => navigate("/login"), 800);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="Create your account"
      title="Start your game list"
      description="Your first account becomes the administrator; later users join as gamers."
    >
      <Card>
        <CardHeader>
          <CardTitle><UserPlus size={20} /> Register</CardTitle>
          <CardDescription>Passwords are hashed with salted Argon2i before storage.</CardDescription>
        </CardHeader>
        <CardContent>
          <form id="register-form" className="stack" onSubmit={submit}>
            <FormField id="username" label="Username" value={form.username} onChange={update} autoComplete="username" required />
            <FormField id="email" label="Email" type="email" value={form.email} onChange={update} autoComplete="email" required />
            <FormField id="displayName" label="Display name" value={form.displayName} onChange={update} autoComplete="nickname" />
            <FormField id="password" label="Password" type="password" value={form.password} onChange={update} autoComplete="new-password" required />
            <FormField id="confirmPassword" label="Confirm password" type="password" value={form.confirmPassword} onChange={update} autoComplete="new-password" required />
            <div className="check-row">
              <Checkbox id="termsAccepted" name="termsAccepted" checked={form.termsAccepted} onChange={update} />
              <Label htmlFor="termsAccepted">I agree to the terms of service</Label>
            </div>
            {message && (
              <Alert variant="success">
                <AlertIcon variant="success" />
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertIcon />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </form>
        </CardContent>
        <CardFooter>
          <Button form="register-form" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating..." : "Create account"}
          </Button>
          <p className="form-link">
            Already registered? <Link to="/login">Log in</Link>
          </p>
        </CardFooter>
      </Card>
    </AuthShell>
  );
}
