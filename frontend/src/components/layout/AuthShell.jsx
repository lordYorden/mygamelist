import { Gamepad2 } from "lucide-react";
import { Link } from "react-router-dom";

export function AuthShell({ children, eyebrow, title, description }) {
  return (
    <main className="auth-shell">
      <section className="auth-intro" aria-label="MyGameList">
        <Link className="brand-link" to="/">
          <Gamepad2 size={30} />
          <span>MyGameList</span>
        </Link>
        <div className="intro-copy">
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </section>
      <section className="auth-panel">{children}</section>
    </main>
  );
}
