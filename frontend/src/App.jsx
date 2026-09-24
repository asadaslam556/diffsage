import { AuthProvider, useAuth } from "./auth/AuthContext.jsx";
import { Backdrop } from "./components/Brand.jsx";
import Layout from "./components/Layout.jsx";
import Chat from "./pages/Chat.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import Settings from "./pages/Settings.jsx";
import { Link, match, navigate, usePath } from "./lib/router.jsx";
import { useEffect } from "react";

function Routes() {
  const { status } = useAuth();
  const path = usePath();

  useEffect(() => {
    if (status === "signed-in" && path === "/login") navigate("/chat", { replace: true });
  }, [status, path]);

  if (status === "loading") {
    return (
      <div className="boot" aria-busy="true" aria-label="Loading">
        <div className="skeleton" />
      </div>
    );
  }
  if (status === "signed-out") return <Login />;

  let page;
  let params;
  if (path === "/") page = <Dashboard />;
  else if (path === "/chat") page = <Chat />;
  else if ((params = match("/chat/:id", path))) page = <Chat sessionId={params.id} />;
  else if (path === "/settings") page = <Settings />;
  else if (path === "/login") page = null;
  else
    page = (
      <div className="page lost enter">
        <p className="code">404</p>
        <h1>Nothing lives at this address</h1>
        <p className="muted">
          <code>{path}</code> isn't a page in DiffSage. It may be an old link to a review that was deleted.
        </p>
        <p>
          <Link to="/chat">Go to your reviews</Link>
        </p>
      </div>
    );
  return <Layout>{page}</Layout>;
}

export default function App() {
  return (
    <AuthProvider>
      <Backdrop />
      <Routes />
    </AuthProvider>
  );
}
