import { Activity, BarChart3, Coins, CreditCard, FolderOpen, History, MessagesSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import Meter from "../components/Meter.jsx";
import UsageChart from "../components/UsageChart.jsx";
import { ago, compact, money, providerLabel } from "../lib/format.js";
import { Link, navigate } from "../lib/router.jsx";

const STATUS_TEXT = { ok: "Answered", fallback: "Fell back", error: "Failed", cancelled: "Stopped" };

function Stat({ icon: Icon, label, value, of, className = "", children }) {
  return (
    <section className={`card stat ${className}`}>
      <span className="k"><Icon size={16} aria-hidden="true" />{label}</span>
      <span className="v">{value}{of && <span className="of"> {of}</span>}</span>
      {children}
    </section>
  );
}

// placeholder blocks shaped like the real page, so nothing jumps when data lands
function DashboardSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading usage">
      <div className="skeleton" style={{ width: 160, height: 34 }} />
      <div className="stats">
        <div className="skeleton stat hero" style={{ minHeight: 190 }} />
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ minHeight: 88 }} />)}
      </div>
      <div className="skeleton" style={{ height: 260 }} />
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    Promise.all([api("/api/billing/me"), api("/api/billing/usage?days=14"), api("/api/app/stats")])
      .then(([billing, usage, stats]) => live && setData({ billing, usage, stats }))
      .catch((e) => live && setError(e));
    return () => {
      live = false;
    };
  }, []);

  if (error) return <div className="page"><p className="notice error">Couldn't load usage: {error.message}</p></div>;
  if (!data) return <DashboardSkeleton />;

  const { billing, usage, stats } = data;
  const { plan } = billing;
  const u = billing.usage;
  const resets = new Date(u.resets_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const total14 = usage.daily.reduce((n, d) => n + d.requests, 0);
  const fresh = usage.recent.length === 0;

  return (
    <div className="page dashboard enter">
      <header className="page-head">
        <div>
          <h1>Usage</h1>
          <p className="muted">
            {plan.name} plan{plan.price_cents ? `, ${money(plan.price_cents)}` : ""}. <Link to="/settings">Change plan</Link>
          </p>
        </div>
      </header>

      <div className="stats">
        <Stat icon={Activity} label="Reviews today" className="hero" value={compact(u.requests_today)}
          of={u.daily_request_limit == null ? "of unlimited" : `of ${compact(u.daily_request_limit)}`}>
          <div className="stat-foot">
            <p className="stat-note">
              {u.daily_request_limit == null
                ? "No daily cap on this plan."
                : `${compact(Math.max(0, u.daily_request_limit - u.requests_today))} left today.`}
            </p>
            <Meter label="Reviews today" used={u.requests_today} limit={u.daily_request_limit} hint={`Resets at ${resets}`} bare />
          </div>
        </Stat>
        <Stat icon={Coins} label="Tokens this month" value={compact(u.tokens_this_month)}
          of={u.monthly_token_limit == null ? "no cap" : `of ${compact(u.monthly_token_limit)}`}>
          <Meter label="Tokens this month" used={u.tokens_this_month} limit={u.monthly_token_limit} bare />
        </Stat>
        <Stat icon={MessagesSquare} label="Conversations" value={stats.sessions} />
        <Stat icon={FolderOpen} label="Guideline files" value={stats.documents} />
        <Stat icon={CreditCard} label="Models" value={plan.can_switch_provider ? "Any" : "Local"}
          of={plan.can_switch_provider ? "configured" : "only"} />
      </div>

      {fresh ? (
        <section className="card getting-started">
          <div>
            <h2>Nothing to chart yet</h2>
            <ol>
              <li><b>Start a review.</b> Paste a diff or use one of the examples.</li>
              <li><b>Add your style guide</b> in Settings so reviews can cite it.</li>
              <li><b>Come back here</b> to see requests, tokens and which model answered.</li>
            </ol>
          </div>
          <button className="primary" onClick={() => navigate("/chat")}>Start a review</button>
        </section>
      ) : (
        <>
          <section className="card panel">
            <div className="panel-head">
              <h2><BarChart3 size={18} aria-hidden="true" /> Last 14 days</h2>
              <span className="muted small num">{total14} requests</span>
            </div>
            <UsageChart days={usage.daily} />
          </section>

          <section className="card panel">
            <div className="panel-head">
              <h2><History size={18} aria-hidden="true" /> Recent requests</h2>
            </div>
            <div className="table-wrap">
              <table className="history">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Model</th>
                    <th className="num">Tokens</th>
                    <th className="num">Time</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.recent.map((r) => (
                    <tr key={r.id} className={r.session_id ? "clickable" : undefined}
                      onClick={() => r.session_id && navigate(`/chat/${r.session_id}`)}
                      onKeyDown={(e) => e.key === "Enter" && r.session_id && navigate(`/chat/${r.session_id}`)}
                      tabIndex={r.session_id ? 0 : undefined}>
                      <td>{ago(r.created_at)}</td>
                      <td>{providerLabel(r.provider)}<span className="model-id">{r.model}</span></td>
                      <td className="num">{compact(r.tokens)}</td>
                      <td className="num">{(r.latency_ms / 1000).toFixed(1)} s</td>
                      <td><span className={`status status-${r.status}`}>{STATUS_TEXT[r.status] ?? r.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
