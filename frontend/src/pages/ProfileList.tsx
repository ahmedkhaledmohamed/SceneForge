import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { DEMO_PROFILES } from "../demo";
import { useIsDemo } from "../DemoContext";

export function setLastProfile(slug: string) {
  localStorage.setItem("sf_last_profile", slug);
}

export default function ProfileList() {
  const isDemo = useIsDemo();
  const { data: profiles, isLoading, error } = useQuery({
    queryKey: ["profiles"],
    queryFn: api.profiles,
  });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (isDemo || isLoading || !profiles) return;
    const last = localStorage.getItem("sf_last_profile");
    if (last && profiles.some((p) => p.slug === last)) {
      navigate(`/${last}`, { replace: true });
    }
  }, [profiles, isDemo, isLoading]);
  const client = useQueryClient();

  const create = useMutation({
    mutationFn: (name: string) => api.createProfile(name),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ["profiles"] });
      navigate(`/${result.slug}`);
    },
  });

  return (
    <>
      <h1>Profiles</h1>
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

      {isLoading && !isDemo && <p className="muted">Loading…</p>}
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
            </div>
          </Link>
        ))}
      </div>
      {!isDemo && profiles?.length === 0 && !creating && (
        <p className="muted">No profiles yet — create one to get started.</p>
      )}
    </>
  );
}
