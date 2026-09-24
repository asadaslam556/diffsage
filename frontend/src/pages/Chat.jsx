import { ArrowRight, ArrowUp, Bot, CircleAlert, Cpu, FileCode2, GitPullRequest, History, LoaderCircle, Plus, Search, ShieldAlert, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { streamChat } from "../api/sse.js";
import Markdown from "../components/Markdown.jsx";
import { ago, fmt, providerLabel } from "../lib/format.js";
import { Link, navigate } from "../lib/router.jsx";

let localId = 0;
const nextId = () => `local-${++localId}`;

// one-click examples for an empty conversation
const STARTERS = [
  {
    icon: GitPullRequest,
    title: "Review a diff",
    hint: "A small patch with a resource leak",
    text: "```diff\n-def load_rows(path):\n-    f = open(path)\n-    rows = f.readlines()\n-    return [r.strip() for r in rows]\n+def load_rows(path):\n+    f = open(path)\n+    rows = [r.strip() for r in f.readlines() if r]\n+    return rows\n```",
  },
  {
    icon: ShieldAlert,
    title: "Hunt for security bugs",
    hint: "SQL built with string formatting",
    text: "```python\ndef find_user(db, email):\n    query = f\"SELECT * FROM users WHERE email = '{email}'\"\n    return db.execute(query).fetchone()\n```",
  },
  {
    icon: FileCode2,
    title: "Check a React hook",
    hint: "An effect with a missing cleanup",
    text: "```jsx\nfunction useClock() {\n  const [now, setNow] = useState(Date.now());\n  useEffect(() => {\n    setInterval(() => setNow(Date.now()), 1000);\n  }, []);\n  return now;\n}\n```",
  },
];

// what to tell people when the server refuses before streaming starts
function refusalText(err) {
  switch (err.code) {
    case "daily_limit_reached":
    case "monthly_tokens_reached":
      return { text: err.message, action: { to: "/settings", label: "See plans" } };
    case "provider_not_in_plan":
      return { text: err.message, action: { to: "/settings", label: "Change provider or plan" } };
    case "rate_limited":
      return { text: "You're sending requests faster than the limit allows. Wait a few seconds and try again." };
    default:
      return { text: err.message };
  }
}

const TOOL_LABELS = { search_guidelines: "Searched your guidelines", get_past_reviews: "Looked at earlier reviews" };

function ToolNote({ tool }) {
  const Icon = tool.name === "get_past_reviews" ? History : Search;
  let state = "…";
  if (tool.done) state = tool.ok ? "" : " (failed)";
  return (
    <li className={`tool ${tool.done ? "done" : "running"} ${tool.ok === false ? "failed" : ""}`}>
      {tool.done ? <Icon size={14} aria-hidden="true" /> : <LoaderCircle size={14} className="spin" aria-hidden="true" />}
      <span>{TOOL_LABELS[tool.name] ?? tool.name}{state}</span>
      {tool.done && tool.preview && <span className="tool-preview">{tool.preview}</span>}
    </li>
  );
}

function AssistantMessage({ m }) {
  return (
    <article className={`msg assistant card ${m.streaming ? "streaming" : ""}`} aria-busy={m.streaming || undefined}>
      <header className="msg-meta">
        <span className="who-said">
          <span className="bot"><Bot size={15} aria-hidden="true" /></span>
          {m.provider ? providerLabel(m.provider) : "Reviewer"}
        </span>
        {m.model && <span className="model-id">{m.model}</span>}
        {m.latency_ms != null && <span className="num">{(m.latency_ms / 1000).toFixed(1)} s</span>}
        {m.tokens != null && <span className="num">{fmt.format(m.tokens)} tokens</span>}
      </header>
      {m.fallback && (
        <p className="notice fallback" role="status">
          <CircleAlert size={16} aria-hidden="true" />
          <span>{providerLabel(m.fallback.from)} didn't answer ({m.fallback.reason}), so {providerLabel(m.fallback.to)} took over.</span>
        </p>
      )}
      {m.tools?.length > 0 && <ul className="tools">{m.tools.map((t) => <ToolNote key={t.id} tool={t} />)}</ul>}
      {m.content && <Markdown text={m.content} />}
      {!m.content && m.streaming && !m.error && (
        <p className="thinking"><span className="dots" aria-hidden="true"><i /><i /><i /></span> Reading your code…</p>
      )}
      {m.status === "cancelled" && (
        <p className="notice">{m.content ? "Stopped. What's above is all it wrote." : "Stopped before it wrote anything."}</p>
      )}
      {m.error && <p className="notice error" role="alert"><CircleAlert size={16} aria-hidden="true" /> {m.error}</p>}
    </article>
  );
}

export default function Chat({ sessionId }) {
  const [sessions, setSessions] = useState([]);
  const [messages, setMessages] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [profile, setProfile] = useState("code_reviewer");
  const [providerInfo, setProviderInfo] = useState(null);
  const [maxChars, setMaxChars] = useState(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [refusal, setRefusal] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const abortRef = useRef(null);
  const streamSessionRef = useRef(null); // session the live stream belongs to
  const threadEndRef = useRef(null);
  const inputRef = useRef(null);
  const stickToBottom = useRef(true);

  const loadSessions = useCallback(() => api("/api/app/sessions").then(setSessions).catch(() => {}), []);

  useEffect(() => {
    loadSessions();
    api("/api/agent/profiles").then(setProfiles).catch(() => {});
    api("/api/agent/providers").then(setProviderInfo).catch(() => {});
    api("/api/billing/me").then((b) => setMaxChars(b.plan.max_input_chars)).catch(() => {});
  }, [loadSessions]);

  // load the conversation from the URL, unless it's the one we're streaming into
  useEffect(() => {
    setRefusal(null);
    setLoadError(null);
    if (sessionId && sessionId === streamSessionRef.current) return undefined;
    // Leaving a conversation mid-stream: stop it and detach it, otherwise the
    // remaining tokens would get written into whatever we show next. The server
    // still saves what was written so far as a "cancelled" reply.
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (!sessionId) {
      setMessages([]);
      return undefined;
    }
    let live = true;
    api(`/api/app/sessions/${sessionId}`)
      .then((s) => {
        if (!live) return;
        setProfile(s.profile);
        setMessages(s.messages);
      })
      .catch((e) => live && setLoadError(e.status === 404 ? "That conversation doesn't exist." : e.message));
    return () => {
      live = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (stickToBottom.current) threadEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEffect(() => {
    const onScroll = () => {
      const gap = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      stickToBottom.current = gap < 120; // stop auto-scrolling if they scrolled up to read
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  async function send(e) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setRefusal(null);
    setInput("");
    setStreaming(true);
    stickToBottom.current = true;
    streamSessionRef.current = sessionId ?? null;

    const assistant = { id: nextId(), role: "assistant", content: "", streaming: true, tools: [] };
    setMessages((prev) => [...prev, { id: nextId(), role: "user", content: text }, assistant]);

    const controller = new AbortController();
    abortRef.current = controller;
    // only patch the thread while this stream is still the attached one
    const patchLast = (fn) => {
      if (abortRef.current !== controller) return;
      setMessages((prev) => {
        if (!prev.length) return prev;
        const copy = prev.slice();
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });
    };

    try {
      await streamChat({
        message: text,
        sessionId,
        profile,
        signal: controller.signal,
        onEvent(name, data) {
          switch (name) {
            case "meta":
              if (!sessionId) {
                streamSessionRef.current = data.session_id;
                navigate(`/chat/${data.session_id}`, { replace: true });
                loadSessions(); // so the new conversation shows up in the list straight away
              }
              break;
            case "provider":
              patchLast((m) => ({ ...m, provider: data.provider, model: data.model }));
              break;
            case "fallback":
              patchLast((m) => ({ ...m, fallback: data }));
              break;
            case "tool_start":
              patchLast((m) => ({ ...m, tools: [...m.tools, { ...data, done: false }] }));
              break;
            case "tool_end":
              patchLast((m) => ({ ...m, tools: m.tools.map((t) => (t.id === data.id ? { ...t, ...data, done: true } : t)) }));
              break;
            case "token":
              patchLast((m) => ({ ...m, content: m.content + data.text }));
              break;
            case "error":
              patchLast((m) => ({ ...m, streaming: false, status: "error", error: data.message }));
              break;
            case "done":
              patchLast((m) => ({
                ...m, streaming: false, status: data.status, provider: data.provider, model: data.model,
                latency_ms: data.latency_ms, tokens: data.input_tokens + data.output_tokens,
              }));
              break;
            default:
              break;
          }
        },
      });
      patchLast((m) => (m.streaming ? { ...m, streaming: false, error: m.error ?? "The connection closed early." } : m));
    } catch (err) {
      if (err.name === "AbortError") {
        patchLast((m) => ({ ...m, streaming: false, status: "cancelled" }));
      } else if (err.status >= 400) {
        // refused before any streaming: take the message back out and put the text back
        if (abortRef.current === controller) setMessages((prev) => prev.slice(0, -2));
        setInput(text);
        setRefusal(refusalText(err));
      } else {
        patchLast((m) => ({ ...m, streaming: false, status: "error", error: err.message }));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      streamSessionRef.current = null;
      setStreaming(false);
      loadSessions();
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(e);
  }

  function applyStarter(text) {
    setInput(text);
    inputRef.current?.focus();
  }

  const activeProfile = profiles.find((p) => p.name === profile);
  // a saved choice whose API key has since been removed would just fall back, so say so
  const chosen = providerInfo?.providers?.find((p) => p.name === providerInfo.selected);
  const provider = chosen?.configured ? chosen.name : providerInfo?.default;
  const tooLong = maxChars != null && input.length > maxChars;

  return (
    <div className="chat">
      <aside className="sessions" aria-label="Conversations">
        <button className="new-review primary" onClick={() => navigate("/chat")} disabled={streaming && !sessionId}>
          <Plus size={16} aria-hidden="true" /> New review
        </button>
        <h2>Recent reviews</h2>
        {sessions.length === 0 ? (
          <p className="empty small">Your reviews will be listed here.</p>
        ) : (
          <ol>
            {sessions.map((s) => (
              <li key={s.id}>
                <Link to={`/chat/${s.id}`} className={s.id === sessionId ? "active" : undefined}
                  aria-current={s.id === sessionId ? "page" : undefined}>
                  <span className="s-title">{s.title}</span>
                  <span className="s-when">{ago(s.updated_at)}</span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </aside>

      <section className="thread-col">
        <div className="thread" aria-live="polite">
          {loadError && <p className="notice error"><CircleAlert size={16} aria-hidden="true" /> {loadError}</p>}
          {!loadError && messages.length === 0 && (
            <div className="blank enter">
              <span className="model-chip">
                <Cpu size={14} aria-hidden="true" /> Answering with {providerLabel(provider ?? "ollama")}
              </span>
              <h1>{activeProfile?.title ?? "Code review"}</h1>
              <p className="lede">{activeProfile?.description ?? "Paste a diff, a file or a snippet and get a review."}</p>
              {providerInfo && !providerInfo.can_switch && (
                <p className="muted small"><Link to="/settings">Claude, OpenAI and DeepSeek are on Pro.</Link></p>
              )}
              {profile === "code_reviewer" && (
                <ul className="starters" aria-label="Examples to try">
                  {STARTERS.map(({ icon: Icon, title, hint, text }) => (
                    <li key={title}>
                      <button type="button" className="starter" onClick={() => applyStarter(text)}>
                        <span className="ico"><Icon size={18} aria-hidden="true" /></span>
                        <span>
                          <strong>{title}</strong>
                          <span className="hint">{hint}</span>
                        </span>
                        <ArrowRight size={16} className="go" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {messages.map((m) =>
            m.role === "user" ? (
              <article key={m.id} className="msg user">
                <pre className="user-text">{m.content}</pre>
              </article>
            ) : (
              <AssistantMessage key={m.id} m={m} />
            ),
          )}
          <div ref={threadEndRef} />
        </div>

        <div className="composer-wrap">
          <form className="composer glass" onSubmit={send}>
            {refusal && (
              <p className="notice error" role="alert">
                <CircleAlert size={16} aria-hidden="true" />
                <span>{refusal.text} {refusal.action && <Link to={refusal.action.to}>{refusal.action.label}</Link>}</span>
              </p>
            )}
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={activeProfile?.input_hint ?? "Paste code or a diff."}
              spellCheck={false}
              rows={5}
              aria-label="Code or question"
            />
            <div className="composer-bar">
              <select value={profile} onChange={(e) => setProfile(e.target.value)} disabled={streaming || messages.length > 0}
                aria-label="Assistant type" title={messages.length > 0 ? "Start a new review to switch" : undefined}>
                {(profiles.length ? profiles : [{ name: "code_reviewer", title: "Code review" }]).map((p) => (
                  <option key={p.name} value={p.name}>{p.title}</option>
                ))}
              </select>
              <span className={`count ${tooLong ? "over" : ""}`}>
                {fmt.format(input.length)}{maxChars ? ` / ${fmt.format(maxChars)}` : ""}
              </span>
              <span className="kbd" aria-hidden="true">Ctrl + Enter</span>
              {streaming ? (
                <button type="button" className="stop" onClick={() => abortRef.current?.abort()}>
                  <Square size={14} aria-hidden="true" /> Stop
                </button>
              ) : (
                <button className="primary" disabled={!input.trim() || tooLong} title="Ctrl/⌘ + Enter">
                  <ArrowUp size={16} aria-hidden="true" /> Review
                </button>
              )}
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}
