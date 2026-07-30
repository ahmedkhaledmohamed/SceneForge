import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthProvider";
import { SkeletonGrid } from "../components/Skeleton";
import { timeAgo } from "../util";
import { DEMO_PROFILES } from "../demo";
import { useIsDemo } from "../DemoContext";

export function setLastProfile(slug: string) {
  localStorage.setItem("sf_last_profile", slug);
}

export default function ProfileList() {
  const isDemo = useIsDemo();
  const { preferences, updatePreferences } = useAuth();
  const { data: profiles, isLoading, error } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.profiles,
  });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const isExplicitNav = location.pathname === "/app";

  useEffect(() => {
    if (isExplicitNav || isDemo || isLoading || !profiles) return;
    const lastProfile = preferences.last_profile || localStorage.getItem("sf_last_profile");
    if (lastProfile && profiles.some((p) => p.slug === lastProfile)) {
      navigate(`/${lastProfile}`, { replace: true });
    }
  }, [profiles, isDemo, isLoading, isExplicitNav, preferences]);
  const client = useQueryClient();

  const create = useMutation({
    mutationFn: (name: string) => api.createProfile(name),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ["profiles"] });
      navigate(`/${result.slug}`);
    },
  });

  const dashQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    enabled: !isDemo,
    staleTime: 30000,
  });
  const dash = dashQuery.data;

  return (
    <>
      <h1>Profiles</h1>

      {dash && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 20 }}>
          <div className="card" style={{ padding: 14, textAlign: "center", marginBottom: 0 }}>
            <div className="mono" style={{ fontSize: "1.3rem" }}>{dash.profiles}</div>
            <div className="muted" style={{ fontSize: "0.72rem" }}>Profiles</div>
          </div>
          <div className="card" style={{ padding: 14, textAlign: "center", marginBottom: 0 }}>
            <div className="mono" style={{ fontSize: "1.3rem" }}>{dash.projects}</div>
            <div className="muted" style={{ fontSize: "0.72rem" }}>Projects</div>
          </div>
          <div className="card" style={{ padding: 14, textAlign: "center", marginBottom: 0 }}>
            <div className="mono" style={{ fontSize: "1.3rem", color: "var(--gold)" }}>${dash.total_spend_usd.toFixed(2)}</div>
            <div className="muted" style={{ fontSize: "0.72rem" }}>Total spend</div>
          </div>
        </div>
      )}

      {dash && dash.recent_projects.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ margin: "0 0 10px" }}>Recent projects</h2>
          <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 6 }}>
            {dash.recent_projects.map((rp) => (
              <Link
                key={`${rp.profile}/${rp.slug}`}
                to={`/${rp.profile}/p/${rp.slug}`}
                className="card"
                style={{ flex: "0 0 200px", padding: 12, marginBottom: 0 }}
              >
                {rp.thumbnail && (
                  <img
                    src={`${import.meta.env.VITE_API_BASE ?? "/api"}/profiles/${rp.profile}/projects/${rp.slug}/media/${rp.thumbnail}`}
                    alt=""
                    style={{ width: "100%", height: 80, objectFit: "cover", borderRadius: 6, marginBottom: 8, border: "1px solid var(--glass-border)" }}
                    loading="lazy"
                  />
                )}
                <b style={{ fontSize: "0.85rem" }}>{rp.name}</b>
                <div className="mono muted" style={{ fontSize: "0.62rem", marginTop: 4 }}>
                  {rp.profile} · {timeAgo(rp.updated_at)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <p className="muted">
        A profile is a brand or workspace — its characters, style defaults, and seed
        assets are shared across all projects within it.
      </p>
      {!isDemo && (
        <div className="row" style={{ margin: "14px 0" }}>
          <button onClick={() => setCreating(true)}>New profile</button>
        </div>
      )}

      {creating && !isDemo && (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const name = new FormData(e.currentTarget).get("name") as string;
            if (name?.trim()) create.mutate(name.trim());
          }}
        >
          <label>Profile name</label>
          <input name="name" required placeholder="e.g. GenerationStyled, MiseEnPlace" style={{ width: "100%" }} />
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={create.isPending}>Create</button>
            <button type="button" className="ghost" onClick={() => setCreating(false)}>Cancel</button>
            {create.isError && <span className="muted">{String(create.error)}</span>}
          </div>
        </form>
      )}

      {isLoading && !isDemo && <SkeletonGrid count={3} />}
      {isDemo && (
        <div className="card" style={{ borderColor: "var(--gold-dim, #b06f24)", marginBottom: 14 }}>
          <b>Demo mode</b> — exploring with sample data.
          Run <code>sceneforge studio</code> locally to create real content.
        </div>
      )}
      <div className="grid-cards">
        {(profiles ?? (isDemo ? DEMO_PROFILES : []))?.map((p) => (
          <Link key={p.slug} to={`/${p.slug}`} className="card" style={{ display: "block" }}>
            <b>{p.name}</b>
            <div className="row" style={{ marginTop: 10 }}>
              <span className="pill">{p.projects} projects</span>
              <span className="pill">{p.characters} characters</span>
              {p.seeds > 0 && <span className="pill">{p.seeds} seeds</span>}
              {(p.spent_usd ?? 0) > 0 && <span className="pill gold">${p.spent_usd!.toFixed(2)}</span>}
            </div>
            {p.updated_at && (
              <div className="mono muted" style={{ fontSize: "0.68rem", marginTop: 8 }}>
                updated {timeAgo(p.updated_at)}
              </div>
            )}
          </Link>
        ))}
      </div>
      {!isDemo && profiles?.length === 0 && !creating && (
        <p className="muted">No profiles yet — create one to get started.</p>
      )}
    </>
  );
}
