import { Link, useNavigate } from "react-router-dom";
import { Camera, Library, LogOut, Settings, ShieldCheck, Upload, Users } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { apiJson } from "../lib/api";

export function DashboardPage({ user, onLogout }) {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [profilePictureUrl, setProfilePictureUrl] = useState(user.profilePictureUrl);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);

  async function logout() {
    await apiJson("/logout", { method: "POST" });
    onLogout();
    navigate("/login", { replace: true });
  }

  async function uploadProfilePicture(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setUploadError("");
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setUploadError("Choose a JPG, PNG, or WEBP image.");
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setUploadError("Profile picture must be 2 MB or smaller.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setUploading(true);
      const updatedUser = await apiJson("/api/me/profile-picture", {
        method: "POST",
        body: formData,
      });
      const nextUrl = updatedUser.profilePictureUrl
        ? `${updatedUser.profilePictureUrl}?v=${Date.now()}`
        : null;
      setProfilePictureUrl(nextUrl);
    } catch (error) {
      setUploadError(error.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
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
          <Button asChild variant="secondary" size="sm">
            <Link to="/settings">
              <Settings size={16} /> Settings
            </Link>
          </Button>
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
            <div className="mb-5 flex flex-col gap-3 border-b pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <div className="grid h-16 w-16 shrink-0 place-items-center overflow-hidden rounded-full border bg-muted text-muted-foreground">
                  {profilePictureUrl ? (
                    <img className="h-full w-full object-cover" src={profilePictureUrl} alt="" />
                  ) : (
                    <Camera size={24} />
                  )}
                </div>
                <div>
                  <p className="m-0 font-extrabold">Profile picture</p>
                  <p className="m-0 text-sm text-muted-foreground">JPG, PNG, or WEBP up to 2 MB.</p>
                </div>
              </div>
              <div className="flex flex-col items-start gap-2 sm:items-end">
                <input
                  ref={fileInputRef}
                  className="hidden"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={uploadProfilePicture}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={uploading}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload size={16} /> {uploading ? "Uploading..." : "Upload"}
                </Button>
                {uploadError ? <p className="m-0 max-w-64 text-sm text-destructive">{uploadError}</p> : null}
              </div>
            </div>
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
