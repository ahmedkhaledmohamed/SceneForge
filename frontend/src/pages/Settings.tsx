import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthProvider";
import { useIsDemo } from "../DemoContext";
import { toastError, toastOk } from "../components/toast";

export default function Settings() {
  const { prof = "" } = useParams();
  const isDemo = useIsDemo();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();

  const { data: profile } = useQuery({
    queryKey: ["profile", prof],
    queryFn: () => api.profile(prof),
    enabled: !isDemo,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings", prof],
    queryFn: () => api.getSettings(prof),
    enabled: !isDemo && !!profile,
    retry: false,
  });

  const [togetherKey, setTogetherKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [runpodApi, setRunpodApi] = useState("");
  const [runpodEndpoint, setRunpodEndpoint] = useState("");

  const { data: balance } = useQuery({
    queryKey: ["balance", prof],
    queryFn: () => api.getBalance(prof),
    enabled: !isDemo && !!settings,
    retry: false,
    staleTime: 60000,
  });

  const deleteProf = useMutation({
    mutationFn: () => api.deleteProfile(prof),
    onSuccess: () => navigate("/app"),
    onError: (e) => toastError(String(e)),
  });

  const saveKeys = useMutation({
    mutationFn: () => {
      const keys: Record<string, string> = {};
      if (togetherKey) keys.together = togetherKey;
      if (openrouterKey) keys.openrouter = openrouterKey;
      if (runpodApi) keys.runpod_api = runpodApi;
      if (runpodEndpoint) keys.runpod_endpoint = runpodEndpoint;
      return api.patchSettings(prof, keys);
    },
    onSuccess: () => {
      setTogetherKey("");
      setOpenrouterKey("");
      setRunpodApi("");
      setRunpodEndpoint("");
      toastOk("keys saved");
      client.invalidateQueries({ queryKey: ["settings", prof] });
    },
    onError: (e) => toastError(String(e)),
  });

  if (isDemo) {
    return (
      <>
        <p><Link to={`/${prof}`}>← {prof}</Link></p>
        <h1>Settings <span className="pill gold">demo</span></h1>
        <p className="muted">Settings are not available in demo mode.</p>
      </>
    );
  }

  return (
    <>
      <p><Link to={`/${prof}`}>← {prof}</Link></p>
      <h1>Settings</h1>

      {/* Account info */}
      {user && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Account</h2>
          <div className="row" style={{ gap: 12 }}>
            {user.avatar_url && (
              <img src={user.avatar_url} alt="" style={{ width: 36, height: 36, borderRadius: "50%" }} />
            )}
            <div>
              <div><b>{user.name}</b></div>
              <div className="mono muted" style={{ fontSize: "0.78rem" }}>{user.email}</div>
            </div>
            <span className="pill" style={{ marginLeft: "auto" }}>{user.provider}</span>
          </div>
        </div>
      )}

      {/* Account balance */}
      {balance && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Account Status</h2>
          <div className="row" style={{ gap: 24 }}>
            <div>
              <label>Together AI</label>
              {balance.together.status === "active" ? (
                <div className="row" style={{ gap: 8 }}>
                  <span className="pill gold">active</span>
                  <a href={balance.together.dashboard} target="_blank" rel="noreferrer"
                     className="mono muted" style={{ fontSize: "0.72rem" }}>
                    view billing →
                  </a>
                </div>
              ) : balance.together.status === "invalid_key" ? (
                <span className="pill" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>invalid key</span>
              ) : (
                <span className="pill">not configured</span>
              )}
            </div>
            <div>
              <label>RunPod</label>
              {balance.runpod.status === "active" ? (
                <div>
                  <span className="pill gold">
                    ${balance.runpod.credit_balance?.toFixed(2) ?? "?"} credits
                  </span>
                  {balance.runpod.spend_per_hr != null && balance.runpod.spend_per_hr > 0 && (
                    <span className="mono muted" style={{ marginLeft: 8, fontSize: "0.72rem" }}>
                      ${balance.runpod.spend_per_hr.toFixed(4)}/hr active
                    </span>
                  )}
                </div>
              ) : balance.runpod.status === "not_configured" ? (
                <span className="pill">not configured</span>
              ) : (
                <span className="pill" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>error</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* API Keys section */}
      {settings && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>API Keys</h2>
          <p className="muted">Keys are stored in your profile directory. They override global .env settings.</p>

          <label>Together AI</label>
          <div className="row">
            {settings.has_together && (
              <span className="mono muted">{settings.keys.together}</span>
            )}
            <input value={togetherKey}
                   onChange={(e) => setTogetherKey(e.target.value)}
                   placeholder={settings.has_together ? "replace key" : "paste Together API key"}
                   style={{ flex: 1 }} />
          </div>

          <label>OpenRouter (for Seedance 1.5 Pro — cheapest video clips)</label>
          <div className="row">
            <input value={openrouterKey}
                   onChange={(e) => setOpenrouterKey(e.target.value)}
                   placeholder="paste OpenRouter API key"
                   style={{ flex: 1 }} />
          </div>

          <label>RunPod API Key</label>
          <div className="row">
            {settings.has_runpod && (
              <span className="mono muted">{settings.keys.runpod_api}</span>
            )}
            <input value={runpodApi}
                   onChange={(e) => setRunpodApi(e.target.value)}
                   placeholder={settings.has_runpod ? "replace key" : "paste RunPod API key"}
                   style={{ flex: 1 }} />
          </div>

          <label>RunPod Endpoint ID</label>
          <div className="row">
            {settings.keys.runpod_endpoint && (
              <span className="mono muted">{settings.keys.runpod_endpoint}</span>
            )}
            <input value={runpodEndpoint}
                   onChange={(e) => setRunpodEndpoint(e.target.value)}
                   placeholder="endpoint ID"
                   style={{ flex: 1 }} />
          </div>

          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={() => saveKeys.mutate()}
                    disabled={saveKeys.isPending || (!togetherKey && !openrouterKey && !runpodApi && !runpodEndpoint)}>
              save keys
            </button>
          </div>
        </div>
      )}

      {!settings && <p className="muted">Loading settings…</p>}

      {/* Danger zone */}
      <div className="card" style={{ borderColor: "var(--danger, #c44)", marginTop: 24 }}>
        <h2 style={{ marginTop: 0, color: "var(--danger)" }}>Danger zone</h2>
        <p className="muted">Permanently delete this profile and all its projects, images, and clips.</p>
        <button
          className="ghost"
          style={{ color: "var(--danger)" }}
          onClick={() => {
            if (confirm(`Delete profile "${prof}" and ALL its data? This cannot be undone.`))
              deleteProf.mutate();
          }}
        >
          delete profile
        </button>
      </div>
    </>
  );
}
