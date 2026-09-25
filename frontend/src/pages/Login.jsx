import { CircleAlert, Eye, EyeOff, GitCompareArrows, KeyRound, LibraryBig, LoaderCircle, Mail, Waypoints } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import { Wordmark } from "../components/Brand.jsx";
import TiltCard from "../components/TiltCard.jsx";

// three.js is ~130 kB gzipped; only the sign-in page needs it
const HeroScene = lazy(() => import("../components/HeroScene.jsx"));

const FallbackOrb = () => (
  <div className="hero-fallback" aria-hidden="true">
    <div className="orb" />
  </div>
);

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const signingIn = mode === "signin";
  const emailBad = emailTouched && email !== "" && !EMAIL.test(email.trim());
  const pwShort = !signingIn && password.length > 0 && password.length < 8;

  async function submit(e) {
    e.preventDefault();
    setEmailTouched(true);
    if (!EMAIL.test(email.trim())) return;
    setError(null);
    setBusy(true);
    try {
      await (signingIn ? login : register)(email.trim(), password);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-pitch enter">
        <p className="wordmark big">
          <Wordmark />
        </p>
        <div className="hero-3d">
          <Suspense fallback={<FallbackOrb />}>
            <HeroScene />
          </Suspense>
        </div>
        <h1>A second pair of eyes on every diff.</h1>
        <p className="lede">
          Paste a diff or a file and read the review as it's written. DiffSage runs on a model on your own machine, and
          checks your team's style guide before it tells you anything.
        </p>
        <ul className="facts-inline">
          <li><GitCompareArrows size={17} aria-hidden="true" /><span><b>Streams as it reviews.</b> Issues arrive ranked blocker to nit, with fixes.</span></li>
          <li><LibraryBig size={17} aria-hidden="true" /><span><b>Knows your conventions.</b> Upload a style guide and it gets cited.</span></li>
          <li><Waypoints size={17} aria-hidden="true" /><span><b>Any model.</b> Local by default, Claude, DeepSeek or OpenAI when you add a key, with automatic fallback.</span></li>
        </ul>
      </section>

      <TiltCard as="form" className="auth-form" onSubmit={submit} noValidate max={3}>
        <h2>{signingIn ? "Sign in" : "Create your account"}</h2>
        <p className="sub">{signingIn ? "Pick up where your last review left off." : "The Free plan covers 25 reviews a day. No card needed."}</p>
        <label>
          Email
          <span className="field">
            <Mail size={16} aria-hidden="true" />
            <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setEmailTouched(true)} aria-invalid={emailBad || undefined}
              aria-describedby={emailBad ? "email-hint" : undefined} placeholder="you@company.dev" required autoFocus />
          </span>
          {emailBad && <span id="email-hint" className="field-hint bad">That doesn't look like an email address.</span>}
        </label>
        <label>
          Password
          <span className="field">
            <KeyRound size={16} aria-hidden="true" />
            <input type={showPw ? "text" : "password"} autoComplete={signingIn ? "current-password" : "new-password"}
              value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required
              aria-invalid={pwShort || undefined} aria-describedby={signingIn ? undefined : "pw-hint"} />
            <button type="button" className="reveal" onClick={() => setShowPw((v) => !v)}
              aria-label={showPw ? "Hide password" : "Show password"}>
              {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </span>
          {!signingIn && <span id="pw-hint" className={`field-hint ${pwShort ? "bad" : ""}`}>At least 8 characters.</span>}
        </label>
        {error && <p className="form-error" role="alert"><CircleAlert size={16} aria-hidden="true" /> {error}</p>}
        <button className="primary" disabled={busy || !email || password.length < (signingIn ? 1 : 8)}>
          {busy && <LoaderCircle size={16} className="spin" aria-hidden="true" />}
          {busy ? (signingIn ? "Signing in" : "Creating account") : signingIn ? "Sign in" : "Create account"}
        </button>
        <p className="switch">
          {signingIn ? "New here?" : "Already have an account?"}{" "}
          <button type="button" className="linkish" onClick={() => { setMode(signingIn ? "signup" : "signin"); setError(null); }}>
            {signingIn ? "Create an account" : "Sign in instead"}
          </button>
        </p>
      </TiltCard>
    </div>
  );
}
