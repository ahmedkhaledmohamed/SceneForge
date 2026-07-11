import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, getAuthToken, setAuthToken } from "../api";
import { useIsDemo } from "../DemoContext";
import { toastError, toastOk } from "../components/toast";

export default function Settings() {
  const { prof = "" } = useParams();
  const isDemo = useIsDemo();
  const client = useQueryClient();
  const navigate = useNavigate();
  const token = getAuthToken();

  const { data: profile } = useQuery({
    queryKey: ["profile", prof],
    queryFn: () => api.profile(prof),
    enabled: !isDemo,
  });

  const { data: settings, error: settingsError } = useQuery({
    queryKey: ["settings", prof, token],
    queryFn: () => api.getSettings(prof),
    enabled: !isDemo && !!profile,
    retry: false,
  });

  const [password, setPassword] = useState("");
  const [loginPw, setLoginPw] = useState("");
  const [togetherKey, setTogetherKey] = useState("");
  const [runpodApi, setRunpodApi] = useState("");
  const [runpodEndpoint, setRunpodEndpoint] = useState("");

  const deleteProf = useMutation({
    mutationFn: () => api.deleteProfile(prof),
    onSuccess: () => navigate("/"),
    onError: (e) => toastError(String(e)),
  });
  const doLogout = useMutation({
    mutationFn: () => api.logout(prof),
    onSuccess: () => {
      setAuthToken(null);
      toastOk("logged out");
      client.invalidateQueries({ queryKey: ["settings", prof] });
    },
  });

  const login = useMutation({
    mutationFn: () => api.login(prof, loginPw),
    onSuccess: (r) => {
      setAuthToken(r.token);
      setLoginPw("");
      toastOk("logged in");
      client.invalidateQueries({ queryKey: ["settings", prof] });
    },
    onError: (e) => toastError(String(e)),
  });

  const setPw = useMutation({
    mutationFn: () => api.setPassword(prof, password),
    onSuccess: (r) => {
      setAuthToken(r.token);
      setPassword("");
      toastOk("password set");
      client.invalidateQueries({ queryKey: ["profile", prof] });
    },
    onError: (e) => toastError(String(e)),
  });

  const saveKeys = useMutation({
    mutationFn: () => {
      const keys: Record<string, string> = {};
      if (togetherKey) keys.together = togetherKey;
      if (runpodApi) keys.runpod_api = runpodApi;
      if (runpodEndpoint) keys.runpod_endpoint = runpodEndpoint;
      return api.patchSettings(prof, keys);
    },
    onSuccess: () => {
      setTogetherKey("");
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

  const needsLogin = profile?.has_password && settingsError;

  return (
    <>
      <p><Link to={`/${prof}`}>← {prof}</Link></p>
      <h1>Settings</h1>

      {/* Password section */}
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Password</h2>
        {profile?.has_password ? (
          <>
            <p className="muted">This profile is password-protected.</p>
            {needsLogin ? (
              <form className="row" onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
                <input type="password" value={loginPw}
                       onChange={(e) => setLoginPw(e.target.value)}
                       placeholder="enter password" style={{ width: 200 }} />
                <button type="submit" disabled={login.isPending}>unlock</button>
              </form>
            ) : (
              <div className="row">
                <span className="mono muted">authenticated</span>
                <button className="ghost" onClick={() => doLogout.mutate()}>log out</button>
              </div>
            )}
          </>
        ) : (
          <>
            <p className="muted">No password set. Anyone with access to this machine can use this profile.</p>
            <form className="row" onSubmit={(e) => { e.preventDefault(); setPw.mutate(); }}>
              <input type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)}
                     placeholder="set a password" style={{ width: 200 }} />
              <button type="submit" disabled={setPw.isPending || !password}>set password</button>
            </form>
          </>
        )}
      </div>

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
                    disabled={saveKeys.isPending || (!togetherKey && !runpodApi && !runpodEndpoint)}>
              save keys
            </button>
          </div>
        </div>
      )}

      {!settings && !needsLogin && (
        <p className="muted">Loading settings…</p>
      )}

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
