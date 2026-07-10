import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, profileMedia } from "../api";
import { DEMO_PROFILE, DEMO_PROJECTS } from "../demo";
import { useIsDemo } from "../DemoContext";
import { toastError, toastOk } from "../components/toast";
import type { ProfileDoc } from "../types";

function ProfileHeader({ prof, profile }: { prof: string; profile: ProfileDoc }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["profile", prof] });
  const [editingStyle, setEditingStyle] = useState(false);
  const [anchor, setAnchor] = useState(profile.style.anchor);

  const addChar = useMutation({
    mutationFn: (form: FormData) => api.addProfileCharacter(prof, form),
    onSuccess: () => { toastOk("character added"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const deleteChar = useMutation({
    mutationFn: (cid: string) => api.deleteProfileCharacter(prof, cid),
    onSuccess: () => { toastOk("character removed"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const addRef = useMutation({
    mutationFn: ({ cid, form }: { cid: string; form: FormData }) =>
      api.addProfileCharacterRef(prof, cid, form),
    onSuccess: () => { toastOk("ref added"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const patchStyle = useMutation({
    mutationFn: () => api.patchProfile(prof, { anchor }),
    onSuccess: () => { toastOk("style updated"); setEditingStyle(false); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        {editingStyle ? (
          <div className="row" style={{ flex: 1 }}>
            <input value={anchor} onChange={(e) => setAnchor(e.target.value)}
                   style={{ flex: 1 }} placeholder="style anchor" />
            <button onClick={() => patchStyle.mutate()} disabled={patchStyle.isPending}>save</button>
            <button className="ghost" onClick={() => setEditingStyle(false)}>cancel</button>
          </div>
        ) : (
          <>
            <div>
              <span className="mono muted">style: </span>
              {profile.style.anchor || <em className="muted">none set</em>}
            </div>
            <div className="row">
              <button className="ghost" onClick={() => { setAnchor(profile.style.anchor); setEditingStyle(true); }}>
                edit style
              </button>
              <span className="mono muted">
                {profile.defaults.image_model} / {profile.defaults.video_model}
              </span>
            </div>
          </>
        )}
      </div>
      {profile.characters.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <span className="mono muted">characters: </span>
          {profile.characters.map((c) => (
            <span key={c.id} className="row" style={{ display: "inline-flex", gap: 4, marginRight: 8, marginBottom: 4 }}>
              <span className="pill">
                {c.name} ({c.reference_images.length} refs){c.main ? " ★" : ""}
              </span>
              <label className="ghost" style={{ cursor: "pointer", fontSize: "0.7rem", padding: "2px 4px" }}>
                +ref
                <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const form = new FormData();
                    form.set("files", file);
                    addRef.mutate({ cid: c.id, form });
                  }
                  e.target.value = "";
                }} />
              </label>
              <button
                className="ghost"
                style={{ padding: "0 4px", fontSize: "0.7rem", color: "var(--red, #c44)" }}
                onClick={() => { if (confirm(`Remove character "${c.name}"?`)) deleteChar.mutate(c.id); }}
              >×</button>
            </span>
          ))}
        </div>
      )}
      {profile.seeds.length > 0 && (
        <div className="gallery" style={{ marginTop: 8 }}>
          {profile.seeds.filter((s) => s.file).map((s) => (
            <img key={s.id} src={profileMedia(prof, s.file!)} alt="" style={{ width: 48, borderRadius: 4 }} />
          ))}
          {profile.seeds.filter((s) => s.kind === "note").map((s) => (
            <span key={s.id} className="pill">{s.text}</span>
          ))}
        </div>
      )}
      <form
        className="row"
        style={{ marginTop: 10 }}
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          addChar.mutate(form);
          e.currentTarget.reset();
        }}
      >
        <input name="name" placeholder="character name" style={{ width: 130 }} />
        <input name="files" type="file" accept="image/*" multiple className="mono" style={{ width: 170 }} />
        <button className="ghost" disabled={addChar.isPending}>+ profile character</button>
      </form>
    </div>
  );
}

export default function ProjectList() {
  const { prof = "" } = useParams();
  const isDemo = useIsDemo();
  const { data: profile } = useQuery({
    queryKey: ["profile", prof],
    queryFn: () => api.profile(prof),
    enabled: !isDemo,
  });
  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects", prof],
    queryFn: () => api.projects(prof),
    enabled: !isDemo,
  });
  const effectiveProfile = profile ?? (isDemo ? DEMO_PROFILE : undefined);
  const effectiveProjects = projects ?? (isDemo ? DEMO_PROJECTS : undefined);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const client = useQueryClient();

  const create = useMutation({
    mutationFn: (body: Record<string, string>) => api.createProject(prof, body),
    onSuccess: (project: { slug: string }) => {
      client.invalidateQueries({ queryKey: ["projects", prof] });
      navigate(`/${prof}/p/${project.slug}`);
    },
  });

  return (
    <>
      <h1>{effectiveProfile?.name ?? prof}</h1>
      {effectiveProfile && <ProfileHeader prof={prof} profile={effectiveProfile} />}

      {effectiveProfile && effectiveProfile.characters.length === 0 && !isDemo && (
        <div className="card" style={{ borderColor: "var(--gold-dim)", marginBottom: 14 }}>
          <b>Add your character first</b>
          <p className="muted" style={{ margin: "4px 0" }}>
            Upload reference photos of your character doll above — these will be used in
            every project to keep the character consistent. After that, create your first project.
          </p>
        </div>
      )}

      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Projects</h2>
        <button onClick={() => setCreating(true)}>New project</button>
      </div>
      <p className="muted">Each project is one concept — a post, a video, a look.</p>

      {creating && (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            create.mutate({
              name: String(data.get("name") ?? ""),
              concept: String(data.get("concept") ?? ""),
              anchor: String(data.get("anchor") ?? ""),
            });
          }}
        >
          <label>Name</label>
          <input name="name" required placeholder="spring looks vol. 3" style={{ width: "100%" }} />
          <label>Concept</label>
          <input name="concept" placeholder="what is this post about?" style={{ width: "100%" }} />
          <label>Style anchor (overrides profile default)</label>
          <input name="anchor" placeholder={effectiveProfile?.style.anchor || "soft studio light, muted pastels"} style={{ width: "100%" }} />
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={create.isPending}>Create</button>
            <button type="button" className="ghost" onClick={() => setCreating(false)}>Cancel</button>
            {create.isError && <span className="muted">{String(create.error)}</span>}
          </div>
        </form>
      )}

      {isLoading && !isDemo && <p className="muted">Loading…</p>}
      <div className="grid-cards">
        {effectiveProjects?.map((p) => (
          <Link key={p.slug} to={`/${prof}/p/${p.slug}`} className="card" style={{ display: "block" }}>
            <b>{p.name}</b>
            <div className="muted" style={{ fontSize: "0.85rem" }}>{p.concept || "no concept yet"}</div>
            <div className="row" style={{ marginTop: 10 }}>
              <span className="pill">{p.scenes} scenes</span>
              <span className="pill">{p.clips} clips</span>
              {p.kept > 0 && <span className="pill gold">{p.kept} kept</span>}
            </div>
          </Link>
        ))}
      </div>
      {effectiveProjects?.length === 0 && !creating && (
        <p className="muted">No projects yet — create the first one.</p>
      )}
    </>
  );
}
