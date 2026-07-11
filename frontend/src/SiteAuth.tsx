import { useEffect, useState } from "react";
import { getAuthToken, setAuthToken } from "./api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function checkSiteAuth(): Promise<{ required: boolean }> {
  try {
    const r = await fetch(`${API_BASE}/site-check`);
    return r.ok ? r.json() : { required: false };
  } catch {
    return { required: false };
  }
}

async function siteLogin(password: string): Promise<string> {
  const r = await fetch(`${API_BASE}/site-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!r.ok) throw new Error("Wrong password");
  const data = await r.json();
  return data.token;
}

export default function SiteAuth({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "login" | "ok">("checking");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    checkSiteAuth().then(({ required }) => {
      if (!required) {
        setState("ok");
        return;
      }
      const saved = localStorage.getItem("sf_site_token");
      if (saved) {
        // verify the saved token still works
        fetch(`${API_BASE}/models`, {
          headers: { Authorization: `Bearer ${saved}` },
        }).then((r) => {
          if (r.ok) {
            setAuthToken(saved);
            setState("ok");
          } else {
            localStorage.removeItem("sf_site_token");
            setState("login");
          }
        }).catch(() => setState("login"));
      } else {
        setState("login");
      }
    });
  }, []);

  if (state === "checking") {
    return <div className="shell"><p className="muted">Loading…</p></div>;
  }

  if (state === "login") {
    return (
      <div className="shell" style={{ maxWidth: 400, paddingTop: 80 }}>
        <h1 style={{ textAlign: "center" }}>
          Scene<span style={{ color: "var(--gold)" }}>Forge</span> Studio
        </h1>
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              const token = await siteLogin(password);
              localStorage.setItem("sf_site_token", token);
              setAuthToken(token);
              setState("ok");
            } catch {
              setError("Wrong password");
            }
          }}
        >
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="enter site password"
            autoFocus
            style={{ width: "100%" }}
          />
          {error && <p style={{ color: "var(--danger)", margin: "6px 0 0" }}>{error}</p>}
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit">log in</button>
          </div>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
