import { Gauge, LogOut, MessagesSquare, Settings2 } from "lucide-react";
import { useAuth } from "../auth/AuthContext.jsx";
import { Link, usePath } from "../lib/router.jsx";
import { Wordmark } from "./Brand.jsx";

const NAV = [
  { to: "/chat", label: "Reviews", icon: MessagesSquare, match: (p) => p.startsWith("/chat") },
  { to: "/", label: "Usage", icon: Gauge, match: (p) => p === "/" },
  { to: "/settings", label: "Settings", icon: Settings2, match: (p) => p.startsWith("/settings") },
];

const PLAN_NAMES = { free: "Free plan", pro: "Pro plan", team: "Team plan" };

export default function Layout({ children }) {
  const path = usePath();
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className="rail">
        <Link to="/chat" className="wordmark" aria-label="DiffSage home">
          <Wordmark />
        </Link>
        <nav aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, match }) => (
            <Link key={to} to={to} className={match(path) ? "active" : undefined}
              aria-current={match(path) ? "page" : undefined} aria-label={label}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="who">
          <div className="top">
            <span className="avatar" aria-hidden="true">{user?.email?.[0]?.toUpperCase()}</span>
            <span className="id">
              <span className="email" title={user?.email}>{user?.email}</span>
              <span className="plan-tag">{PLAN_NAMES[user?.plan_id] ?? user?.plan_id}</span>
            </span>
          </div>
          <button className="ghost signout" onClick={logout} aria-label="Sign out">
            <LogOut size={16} aria-hidden="true" /> <span>Sign out</span>
          </button>
        </div>
      </aside>
      <main className="main" id="main" tabIndex={-1}>{children}</main>
    </div>
  );
}
