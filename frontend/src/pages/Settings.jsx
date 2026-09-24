import { Check, CircleAlert, Cpu, CreditCard, FileText, Layers, LoaderCircle, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import TiltCard from "../components/TiltCard.jsx";
import { ago, compact, fmt, providerLabel } from "../lib/format.js";

const HEALTH_TEXT = {
  ok: "Reachable",
  degraded: "Needs attention",
  down: "Not reachable",
  not_configured: "No API key",
};

function Feedback({ msg }) {
  if (!msg) return null;
  return (
    <p className={msg.error ? "form-error" : "form-ok"} role="status">
      {msg.error ? <CircleAlert size={16} aria-hidden="true" /> : <Check size={16} aria-hidden="true" />} {msg.text}
    </p>
  );
}

function ProviderSection({ onChanged }) {
  const [info, setInfo] = useState(null);
  const [choice, setChoice] = useState("");
  const [msg, setMsg] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const data = await api("/api/agent/providers");
    setInfo(data);
    // a saved model that has since lost its API key can't be used, so show the
    // server default as the active choice and say why, instead of a disabled tile
    // that looks selected
    const saved = data.providers.find((p) => p.name === data.selected);
    setChoice(saved && saved.configured && saved.allowed_on_plan ? saved.name : "");
  }, []);

  useEffect(() => {
    load().catch((e) => setMsg({ error: true, text: e.message }));
  }, [load]);

  async function save() {
    setSaving(true);
    setMsg(null);
    try {
      await api("/api/app/me", { method: "PATCH", body: { preferred_provider: choice || null } });
      await Promise.all([load(), onChanged()]);
      setMsg({ text: choice ? `Reviews now go to ${providerLabel(choice)}.` : "Reviews use the server default again." });
    } catch (e) {
      setMsg({ error: true, text: e.message });
    } finally {
      setSaving(false);
    }
  }

  const savedChoice = info?.providers.find((p) => p.name === info.selected);
  const stale = Boolean(info?.selected) && !(savedChoice?.configured && savedChoice?.allowed_on_plan);

  if (!info) {
    return (
      <section className="card panel">
        <h2><Cpu size={18} aria-hidden="true" /> Model</h2>
        {msg ? <Feedback msg={msg} /> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  return (
    <section className="card panel">
      <div className="panel-head">
        <h2><Cpu size={18} aria-hidden="true" /> Model</h2>
        {!info.can_switch && <span className="muted small">Choosing a model is on Pro and Team</span>}
      </div>
      <p className="muted small">
        If the model you pick fails or times out, the review falls back to {providerLabel(info.fallback)} automatically.
      </p>
      {stale && (
        <p className="notice fallback" role="status">
          <CircleAlert size={16} aria-hidden="true" />
          <span>
            You picked {providerLabel(info.selected)}, but it has no API key on this server any more, so reviews use the
            server default. Choose again and save to update it.
          </span>
        </p>
      )}
      <fieldset className="choices" disabled={!info.can_switch || saving}>
        <legend className="sr-only">Model for reviews</legend>
        <label className={`choice ${choice === "" ? "on" : ""}`}>
          <input type="radio" name="provider" value="" checked={choice === ""} onChange={() => setChoice("")} />
          <span className="choice-main">
            <span className="choice-title">Server default</span>
            <span className="model-id">{providerLabel(info.default)}</span>
          </span>
        </label>
        {info.providers.map((p) => {
          const usable = p.allowed_on_plan && p.configured;
          const health = p.health?.status ?? (p.configured ? null : "not_configured");
          return (
            <label key={p.name} className={`choice ${choice === p.name ? "on" : ""} ${usable ? "" : "off"}`}>
              <input type="radio" name="provider" value={p.name} checked={choice === p.name}
                onChange={() => setChoice(p.name)} disabled={!usable} />
              <span className="choice-main">
                <span className="choice-title">{providerLabel(p.name)}</span>
                <span className="model-id">{p.model}</span>
              </span>
              {health && <span className={`health h-${health}`}>{HEALTH_TEXT[health] ?? health}</span>}
            </label>
          );
        })}
      </fieldset>
      {info.can_switch && (
        <div className="row-actions">
          <button className="primary" onClick={save} disabled={saving || (!stale && choice === (info.selected ?? ""))}>
            {saving && <LoaderCircle size={16} className="spin" aria-hidden="true" />}
            {saving ? "Saving" : "Save model"}
          </button>
        </div>
      )}
      <Feedback msg={msg} />
    </section>
  );
}

function PlanSection({ user, onChanged }) {
  const [plans, setPlans] = useState([]);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    api("/api/billing/plans").then(setPlans).catch((e) => setMsg({ error: true, text: e.message }));
  }, []);

  async function choose(id) {
    setBusy(id);
    setMsg(null);
    try {
      await api("/api/billing/plan", { method: "POST", body: { plan_id: id } });
      await onChanged();
      setMsg({ text: `You're on ${plans.find((p) => p.id === id)?.name} now.` });
    } catch (e) {
      setMsg({ error: true, text: e.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card panel">
      <div className="panel-head"><h2><CreditCard size={18} aria-hidden="true" /> Plan</h2></div>
      <div className="plans">
        {plans.map((p) => {
          const current = p.id === user.plan_id;
          return (
            <TiltCard key={p.id} className={`plan ${current ? "current" : ""} ${p.id === "pro" ? "recommended" : ""}`} max={5}>
              <div className="plan-name">
                {p.name}
                {p.id === "pro" && !current && <span className="plan-flag">Recommended</span>}
              </div>
              <div className="plan-price lift">
                {p.price_cents ? `$${(p.price_cents / 100).toFixed(0)}` : "$0"} <small>a month</small>
              </div>
              <ul>
                <li><Check size={14} aria-hidden="true" />{p.daily_request_limit == null ? "Unlimited reviews" : `${fmt.format(p.daily_request_limit)} reviews a day`}</li>
                <li><Check size={14} aria-hidden="true" />{p.monthly_token_limit == null ? "No token cap" : `${compact(p.monthly_token_limit)} tokens a month`}</li>
                <li><Check size={14} aria-hidden="true" />{p.can_switch_provider ? "Any configured model" : "Local model only"}</li>
                <li><Check size={14} aria-hidden="true" />Up to {compact(p.max_input_chars)} characters per review</li>
              </ul>
              <div className="plan-foot">
                {current ? (
                  <span className="plan-current"><Check size={15} aria-hidden="true" /> Your plan</span>
                ) : (
                  <button className={p.id === "pro" ? "primary" : undefined} onClick={() => choose(p.id)} disabled={busy !== null}>
                    {busy === p.id && <LoaderCircle size={16} className="spin" aria-hidden="true" />}
                    {busy === p.id ? "Switching" : `Switch to ${p.name}`}
                  </button>
                )}
              </div>
            </TiltCard>
          );
        })}
      </div>
      <p className="muted small">Plan changes take effect straight away in this build. A production deployment would take you through checkout first.</p>
      <Feedback msg={msg} />
    </section>
  );
}

function GuidelinesSection() {
  const [docs, setDocs] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [confirming, setConfirming] = useState(null); // id of the file whose Remove was clicked once
  const fileRef = useRef(null);

  const load = useCallback(() => api("/api/app/documents").then(setDocs), []);
  useEffect(() => {
    load().catch((e) => setMsg({ error: true, text: e.message }));
  }, [load]);

  async function upload(file) {
    if (!file) return;
    setMsg(null);
    if (file.size > 200_000) {
      setMsg({ error: true, text: `${file.name} is ${compact(file.size)} bytes; the limit is 200k. Split it into smaller files.` });
      return;
    }
    setBusy(true);
    try {
      const content = await file.text();
      const doc = await api("/api/app/documents", { method: "POST", body: { filename: file.name, content } });
      await load();
      setMsg({ text: `Indexed ${doc.filename} (${doc.chunk_count} sections).` });
    } catch (err) {
      setMsg({ error: true, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(doc) {
    setConfirming(null);
    try {
      await api(`/api/app/documents/${doc.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setMsg({ error: true, text: err.message });
    }
  }

  return (
    <section className="card panel">
      <div className="panel-head">
        <h2><Layers size={18} aria-hidden="true" /> Team guidelines</h2>
      </div>
      <p className="muted small">
        Style guides, conventions, a CONTRIBUTING file. The reviewer searches these before it writes and cites them when they apply.
      </p>
      <button type="button" className={`dropzone ${over ? "over" : ""}`} onClick={() => fileRef.current?.click()} disabled={busy}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files?.[0]); }}>
        {busy ? <LoaderCircle size={22} className="spin" aria-hidden="true" /> : <Upload size={22} aria-hidden="true" />}
        <strong>{busy ? "Indexing the file" : "Drop a file here, or click to choose one"}</strong>
        <span className="small">Markdown, text or code, up to 200 kB</span>
      </button>
      <input ref={fileRef} type="file" hidden accept=".md,.txt,.rst,.py,.js,.ts,.json,.yaml,.yml,.toml,text/*"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; upload(f); }} />
      {docs && docs.length === 0 && <p className="empty">No files yet. Reviews use general best practice until you add one.</p>}
      {docs && docs.length > 0 && (
        <ul className="docs">
          {docs.map((d) => (
            <li key={d.id}>
              <FileText size={16} aria-hidden="true" />
              <span>
                <span className="doc-name">{d.filename}</span>
                <span className="doc-meta">{fmt.format(d.char_count)} characters, added {ago(d.created_at)}</span>
              </span>
              {confirming === d.id ? (
                <span className="confirm" role="group" aria-label={`Remove ${d.filename}?`}>
                  Reviews will stop citing it.
                  <button className="small danger-text" onClick={() => remove(d)}>Remove</button>
                  <button className="small ghost" onClick={() => setConfirming(null)}>Keep</button>
                </span>
              ) : (
                <button className="small ghost" onClick={() => setConfirming(d.id)}>Remove</button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Feedback msg={msg} />
    </section>
  );
}

export default function Settings() {
  const { user, reloadUser } = useAuth();
  // bumping the key remounts the model section so it re-reads what the plan allows
  const [planVersion, setPlanVersion] = useState(0);
  const planChanged = async () => {
    await reloadUser();
    setPlanVersion((v) => v + 1);
  };
  return (
    <div className="page settings enter">
      <header className="page-head">
        <div>
          <h1>Settings</h1>
          <p className="muted">Signed in as {user.email}</p>
        </div>
      </header>
      <ProviderSection key={planVersion} onChanged={reloadUser} />
      <PlanSection user={user} onChanged={planChanged} />
      <GuidelinesSection />
    </div>
  );
}
