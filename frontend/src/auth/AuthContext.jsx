import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, onUnauthenticated, refresh, setAccessToken } from "../api/client.js";
import { navigate } from "../lib/router.jsx";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // "loading" until the first refresh attempt settles, so a reload doesn't
  // flash the login screen for someone who's actually signed in
  const [status, setStatus] = useState("loading");
  const [user, setUser] = useState(null);

  const signedIn = useCallback((data) => {
    setAccessToken(data.access_token);
    setUser(data.user);
    setStatus("signed-in");
  }, []);

  const signedOut = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setStatus("signed-out");
  }, []);

  useEffect(() => {
    onUnauthenticated(signedOut);
    refresh().then(signedIn).catch(signedOut);
  }, [signedIn, signedOut]);

  const login = useCallback(
    async (email, password) => signedIn(await api("/api/auth/login", { method: "POST", body: { email, password } })),
    [signedIn],
  );

  const register = useCallback(
    async (email, password) => signedIn(await api("/api/auth/register", { method: "POST", body: { email, password } })),
    [signedIn],
  );

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      signedOut();
      navigate("/", { replace: true });
    }
  }, [signedOut]);

  // pages call this after anything that changes the user (plan, provider)
  const reloadUser = useCallback(async () => setUser(await api("/api/app/me")), []);

  const value = useMemo(
    () => ({ status, user, login, register, logout, reloadUser }),
    [status, user, login, register, logout, reloadUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth needs to be inside <AuthProvider>");
  return ctx;
}
