import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getAuthToken, setAuthToken } from "../api";
import { useAuth } from "../AuthProvider";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export default function Login() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<{ google: boolean; github: boolean }>({
    google: false,
    github: false,
  });

  useEffect(() => {
    if (!loading && user) navigate("/app");
  }, [loading, user, navigate]);

  useEffect(() => {
    fetch(`${API_BASE}/auth/providers`)
      .then((r) => r.json())
      .then(setProviders)
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const endpoint = mode === "signup" ? "/auth/signup" : "/auth/login";
      const body = mode === "signup"
        ? { email, password, name: name || email.split("@")[0] }
        : { email, password };
      const r = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        setError(data?.error?.message || data?.detail?.message || "Failed");
        return;
      }
      setAuthToken(data.token);
      window.location.href = "/app";
    } catch {
      setError("Network error");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="shell"><p className="muted">Loading...</p></div>;

  return (
    <div className="shell" style={{ maxWidth: 420, paddingTop: 60 }}>
      <h1 style={{ textAlign: "center", marginBottom: 32 }}>
        Scene<span style={{ color: "var(--gold)" }}>Forge</span> Studio
      </h1>

      {(providers.google || providers.github) && (
        <div style={{ marginBottom: 20 }}>
          {providers.google && (
            <a
              href={`${API_BASE}/auth/google`}
              className="btn"
              style={{
                display: "block",
                textAlign: "center",
                marginBottom: 10,
                background: "var(--surface-2)",
                color: "var(--cream)",
                borderColor: "var(--line)",
              }}
            >
              Continue with Google
            </a>
          )}
          {providers.github && (
            <a
              href={`${API_BASE}/auth/github`}
              className="btn"
              style={{
                display: "block",
                textAlign: "center",
                background: "var(--surface-2)",
                color: "var(--cream)",
                borderColor: "var(--line)",
              }}
            >
              Continue with GitHub
            </a>
          )}
          <div
            style={{
              textAlign: "center",
              margin: "18px 0",
              color: "var(--taupe)",
              fontSize: "0.82rem",
            }}
          >
            or
          </div>
        </div>
      )}

      <div className="row" style={{ gap: 0, marginBottom: 16 }}>
        <button
          className={mode === "login" ? "btn" : "ghost"}
          style={{ flex: 1, borderRadius: "8px 0 0 8px" }}
          onClick={() => setMode("login")}
        >
          Log in
        </button>
        <button
          className={mode === "signup" ? "btn" : "ghost"}
          style={{ flex: 1, borderRadius: "0 8px 8px 0" }}
          onClick={() => setMode("signup")}
        >
          Sign up
        </button>
      </div>

      <form className="card" onSubmit={handleSubmit}>
        {mode === "signup" && (
          <>
            <label>Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="your name"
              style={{ width: "100%" }}
            />
          </>
        )}
        <label>Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          autoFocus
          style={{ width: "100%" }}
        />
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={mode === "signup" ? "at least 8 characters" : "your password"}
          required
          style={{ width: "100%" }}
        />
        {error && (
          <p style={{ color: "var(--danger)", margin: "6px 0 0", fontSize: "0.85rem" }}>
            {error}
          </p>
        )}
        <div className="row" style={{ marginTop: 14 }}>
          <button type="submit" disabled={busy}>
            {busy ? "..." : mode === "login" ? "Log in" : "Create account"}
          </button>
        </div>
      </form>

      <p style={{ textAlign: "center", marginTop: 20, fontSize: "0.82rem" }}>
        <a href="/landing/" style={{ color: "var(--taupe)" }}>
          Back to landing page
        </a>
      </p>
    </div>
  );
}
