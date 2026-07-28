import { useQuery } from "@tanstack/react-query";
import { Navigate, NavLink, Route, Routes, useParams } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./AuthProvider";
import { Toaster } from "./components/toast";
import Analytics from "./pages/Analytics";
import HistoryView from "./pages/HistoryView";
import Login from "./pages/Login";
import ProfileList from "./pages/ProfileList";
import ProjectBoard from "./pages/ProjectBoard";
import ProjectList from "./pages/ProjectList";
import Settings from "./pages/Settings";
import TakeCompare from "./pages/TakeCompare";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="shell"><p className="muted">Loading...</p></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function ProfileSwitcher({ currentProf }: { currentProf?: string }) {
  const { user } = useAuth();
  const { data: profiles } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.profiles,
    enabled: !!user,
    staleTime: 30000,
  });

  if (!profiles || profiles.length <= 1) return null;

  return (
    <select
      value={currentProf || ""}
      onChange={(e) => {
        if (e.target.value) window.location.href = `/${e.target.value}`;
        else window.location.href = "/app";
      }}
      style={{
        background: "var(--surface-2, #2b241d)",
        color: "var(--cream)",
        border: "1px solid var(--line)",
        borderRadius: 6,
        padding: "3px 8px",
        fontSize: "0.78rem",
        fontFamily: "var(--font-mono)",
      }}
    >
      <option value="">All profiles</option>
      {profiles.map((p) => (
        <option key={p.slug} value={p.slug}>{p.name}</option>
      ))}
    </select>
  );
}

function TopBar() {
  const { prof, slug } = useParams();
  const { user, logout } = useAuth();
  return (
    <header className="topbar">
      <NavLink className="mark" to="/app">
        Scene<span>Forge</span> Studio
      </NavLink>
      <nav>
        <ProfileSwitcher currentProf={prof} />
        {prof && (
          <>
            <NavLink to={`/${prof}/settings`}>
              settings
            </NavLink>
            <NavLink to={`/${prof}/analytics`}>
              analytics
            </NavLink>
          </>
        )}
        {prof && slug && (
          <>
            <NavLink to={`/${prof}/p/${slug}`} end>
              Board
            </NavLink>
            <NavLink to={`/${prof}/p/${slug}/history`}>History</NavLink>
          </>
        )}
        {user && (
          <button
            onClick={logout}
            className="ghost"
            style={{ padding: "2px 8px", fontSize: "0.78rem" }}
          >
            {user.name || user.email} · logout
          </button>
        )}
      </nav>
    </header>
  );
}

function WithBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <TopBar />
      {children}
      <Toaster />
    </div>
  );
}

function AuthRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <WithBar>{children}</WithBar>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/demo" element={<WithBar><ProfileList /></WithBar>} />
      <Route path="/demo/:prof" element={<WithBar><ProjectList /></WithBar>} />
      <Route path="/demo/:prof/p/:slug" element={<WithBar><ProjectBoard /></WithBar>} />
      <Route path="/demo/:prof/p/:slug/scenes/:sid/takes" element={<WithBar><TakeCompare /></WithBar>} />
      <Route path="/demo/:prof/p/:slug/history" element={<WithBar><HistoryView /></WithBar>} />
      <Route path="/" element={<AuthRoute><ProfileList /></AuthRoute>} />
      <Route path="/app" element={<AuthRoute><ProfileList /></AuthRoute>} />
      <Route path="/:prof" element={<AuthRoute><ProjectList /></AuthRoute>} />
      <Route path="/:prof/settings" element={<AuthRoute><Settings /></AuthRoute>} />
      <Route path="/:prof/analytics" element={<AuthRoute><Analytics /></AuthRoute>} />
      <Route path="/:prof/p/:slug" element={<AuthRoute><ProjectBoard /></AuthRoute>} />
      <Route path="/:prof/p/:slug/scenes/:sid/takes" element={<AuthRoute><TakeCompare /></AuthRoute>} />
      <Route path="/:prof/p/:slug/history" element={<AuthRoute><HistoryView /></AuthRoute>} />
    </Routes>
  );
}
