import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, media, profileMedia } from "../api";
import { useAuth } from "../AuthProvider";
import EmptyState from "../components/EmptyState";
import { SkeletonGrid } from "../components/Skeleton";
import { useProfileScope } from "../hooks";
import { DEMO_PROFILE, DEMO_PROJECTS } from "../demo";
import { useIsDemo } from "../DemoContext";
import { setLastProfile } from "./ProfileList";
import { toastError, toastOk } from "../components/toast";
import type { ProfileDoc } from "../types";
import { timeAgo } from "../util";

function ProfileHeader({ prof, profile }: { prof: string; profile: ProfileDoc }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["profile", prof] });
  const { data: models } = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: Infinity });
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
              <select className="mono" style={{ fontSize: "0.72rem" }}
                value={profile.defaults.image_model}
                onChange={(e) => api.patchProfile(prof, { image_model: e.target.value }).then(refresh)}>
                {Object.entries(models ?? {}).filter(([,m]) => m.kind === "image").map(([k]) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
              <select className="mono" style={{ fontSize: "0.72rem" }}
                value={profile.defaults.video_model}
                onChange={(e) => api.patchProfile(prof, { video_model: e.target.value }).then(refresh)}>
                {Object.entries(models ?? {}).filter(([,m]) => m.kind === "video").map(([k]) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
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

function ImportZipButton({ prof, onImport }: { prof: string; onImport: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const handleFile = async (file: File) => {
    const form = new FormData();
    form.set("file", file);
    try {
      const project = await api.importZip(prof, form);
      toastOk(`Imported "${project.name}"`);
      onImport();
      navigate(`/${prof}/p/${project.slug}`);
    } catch (e) {
      toastError(String(e));
    }
  };

  return (
    <>
      <button className="ghost" onClick={() => fileRef.current?.click()}>
        Import zip
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".zip"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          e.target.value = "";
        }}
      />
    </>
  );
}

export default function ProjectList() {
  const { prof = "" } = useParams();
  const isDemo = useIsDemo();
  useProfileScope(prof);

  const { updatePreferences } = useAuth();
  useEffect(() => {
    if (prof && !isDemo) {
      setLastProfile(prof);
      updatePreferences({ last_profile: prof });
    }
  }, [prof, isDemo]);
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
  const { data: stats } = useQuery({
    queryKey: ["stats", prof],
    queryFn: () => api.profileStats(prof),
    enabled: !isDemo,
  });
  const effectiveProfile = profile ?? (isDemo ? DEMO_PROFILE : undefined);
  const effectiveProjects = projects ?? (isDemo ? DEMO_PROJECTS : undefined);
  const [creating, setCreating] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const navigate = useNavigate();
  const client = useQueryClient();
  const { data: templates } = useQuery({
    queryKey: ["templates", prof],
    queryFn: () => api.templates(prof),
    enabled: !isDemo && showTemplates,
  });

  const invalidateAll = () => {
    client.invalidateQueries({ queryKey: ["projects", prof] });
    client.invalidateQueries({ queryKey: ["stats", prof] });
    client.invalidateQueries({ queryKey: ["profiles"] });
  };

  const create = useMutation({
    mutationFn: (body: Record<string, string>) => api.createProject(prof, body),
    onSuccess: (project: { slug: string }) => {
      invalidateAll();
      navigate(`/${prof}/p/${project.slug}`);
    },
  });
  const createFromTemplate = useMutation({
    mutationFn: ({ template, name }: { template: string; name: string }) =>
      api.createFromTemplate(prof, template, name),
    onSuccess: (project: { slug: string }) => {
      invalidateAll();
      navigate(`/${prof}/p/${project.slug}`);
    },
    onError: (e) => toastError(String(e)),
  });

  return (
    <>
      <h1>{effectiveProfile?.name ?? prof}</h1>
      {effectiveProfile && <ProfileHeader prof={prof} profile={effectiveProfile} />}

      {stats && (
        <div className="row" style={{ gap: 16, margin: "0 0 14px", flexWrap: "wrap" }}>
          <span className="mono muted">{stats.projects} projects</span>
          <span className="mono muted">{stats.images} images</span>
          <span className="mono muted">{stats.clips_completed} clips ({stats.clips_kept} kept)</span>
          {stats.spent_usd > 0 && <span className="mono" style={{ color: "var(--gold)" }}>${stats.spent_usd.toFixed(2)} GPU spend</span>}
          {Object.keys(stats.models_used).length > 0 && (
            <span className="mono muted">
              models: {Object.entries(stats.models_used)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 4)
                .map(([m, n]) => `${m} (${n})`)
                .join(", ")}
            </span>
          )}
        </div>
      )}

      {effectiveProfile && !isDemo && (effectiveProfile.characters.length === 0 || !effectiveProfile.has_keys) && (
        <div className="card" style={{ borderColor: "var(--gold-dim)", marginBottom: 14, padding: "16px 20px" }}>
          <b>Setup checklist</b>
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8, fontSize: "0.88rem" }}>
            <div className="row" style={{ gap: 8 }}>
              <span style={{ color: effectiveProfile.has_keys ? "var(--gold)" : "var(--taupe)", fontSize: "1.1rem" }}>
                {effectiveProfile.has_keys ? "✓" : "○"}
              </span>
              <span className={effectiveProfile.has_keys ? "muted" : ""}>
                {effectiveProfile.has_keys ? "API keys configured" : (
                  <>API keys needed — <Link to={`/${prof}/settings`}>go to Settings</Link></>
                )}
              </span>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <span style={{ color: effectiveProfile.characters.length > 0 ? "var(--gold)" : "var(--taupe)", fontSize: "1.1rem" }}>
                {effectiveProfile.characters.length > 0 ? "✓" : "○"}
              </span>
              <span className={effectiveProfile.characters.length > 0 ? "muted" : ""}>
                {effectiveProfile.characters.length > 0
                  ? `Character added (${effectiveProfile.characters[0].name})`
                  : "Add a character — upload reference photos of your subject above"}
              </span>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <span style={{ color: effectiveProfile.style.anchor ? "var(--gold)" : "var(--taupe)", fontSize: "1.1rem" }}>
                {effectiveProfile.style.anchor ? "✓" : "○"}
              </span>
              <span className={effectiveProfile.style.anchor ? "muted" : ""}>
                {effectiveProfile.style.anchor
                  ? `Style anchor set`
                  : "Set a style anchor — click \"edit style\" above"}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Projects</h2>
        <div className="row">
          {!isDemo && (
            <>
              <button className="ghost" onClick={() => api.backupAll(prof).then(() => toastOk("Full backup downloaded")).catch(e => toastError(String(e)))}>
                Backup all
              </button>
              <ImportZipButton prof={prof} onImport={invalidateAll} />
            </>
          )}
          <button onClick={() => { setShowTemplates(true); setCreating(false); }}>From template</button>
          <button onClick={() => { setCreating(true); setShowTemplates(false); }}>New project</button>
        </div>
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
          {effectiveProfile?.defaults && (
            <div className="muted" style={{ fontSize: "0.72rem", marginTop: 10, lineHeight: 1.8 }}>
              <span className="mono">from profile:</span>{" "}
              image model: <b>{effectiveProfile.defaults.image_model}</b> ·{" "}
              video model: <b>{effectiveProfile.defaults.video_model}</b> ·{" "}
              aspect: <b>{effectiveProfile.defaults.aspect}</b> ·{" "}
              options: <b>{effectiveProfile.defaults.image_options}</b>
            </div>
          )}
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={create.isPending}>Create</button>
            <button type="button" className="ghost" onClick={() => setCreating(false)}>Cancel</button>
            {create.isError && <span className="muted">{String(create.error)}</span>}
          </div>
        </form>
      )}

      {showTemplates && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Start from template</b>
            <button className="ghost" onClick={() => { setShowTemplates(false); setSelectedTemplate(null); }}>cancel</button>
          </div>
          <p className="muted" style={{ margin: "4px 0 10px" }}>Choose a template, then name your project.</p>
          <div className="grid-cards" style={{ marginBottom: 12 }}>
            {templates?.map((t) => (
              <div
                key={t.slug}
                className="card"
                style={{
                  cursor: "pointer",
                  borderColor: selectedTemplate === t.slug ? "var(--gold)" : undefined,
                  background: selectedTemplate === t.slug ? "var(--bg-raised, #2a2520)" : undefined,
                }}
                onClick={() => setSelectedTemplate(t.slug)}
              >
                <b>{t.name}</b>
                <div className="row" style={{ marginTop: 6 }}>
                  <span className="pill">{t.scenes} scenes</span>
                  {t.builtin && <span className="pill muted">built-in</span>}
                </div>
              </div>
            ))}
          </div>
          {selectedTemplate && (
            <form
              className="row"
              onSubmit={(e) => {
                e.preventDefault();
                const name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
                if (name && selectedTemplate) {
                  createFromTemplate.mutate({ template: selectedTemplate, name });
                }
              }}
            >
              <input name="name" required placeholder="Project name" style={{ flex: 1 }} />
              <button type="submit" disabled={createFromTemplate.isPending}>Create</button>
            </form>
          )}
        </div>
      )}

      {isLoading && !isDemo && <SkeletonGrid count={4} />}
      <div className="grid-cards">
        {effectiveProjects?.map((p) => (
          <Link key={p.slug} to={`/${prof}/p/${p.slug}`} className="card" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
            {p.thumbnail && (
              <img
                src={media(prof, p.slug, p.thumbnail)}
                alt=""
                style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 8, flexShrink: 0, border: "1px solid var(--glass-border)" }}
                loading="lazy"
              />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <b>{p.name}</b>
              <div className="muted" style={{ fontSize: "0.85rem" }}>{p.concept || "no concept yet"}</div>
              <div className="row" style={{ marginTop: 8 }}>
                <span className="pill">{p.scenes} scenes</span>
                <span className="pill">{p.clips} clips</span>
                {p.kept > 0 && <span className="pill gold">{p.kept} kept</span>}
                {(p.spent_usd ?? 0) > 0 && <span className="pill">${p.spent_usd!.toFixed(2)}</span>}
              </div>
              {p.updated_at && (
                <div className="mono muted" style={{ fontSize: "0.68rem", marginTop: 6 }}>
                  updated {timeAgo(p.updated_at)}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>
      {effectiveProjects?.length === 0 && !creating && (
        <EmptyState
          title="Start your first project"
          description="Each project is one piece of content — a post, a video, or a look. Start from scratch, use a template, or let the AI Director plan it."
          action="New project"
          onAction={() => setCreating(true)}
        />
      )}
    </>
  );
}
