import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, media } from "../api";
import JobBanner from "../components/JobBanner";
import Lightbox from "../components/Lightbox";
import { toastError, toastOk } from "../components/toast";
import { DEMO_PROJECT } from "../demo";
import { useIsDemo } from "../DemoContext";
import { useInvalidateProject, useModels, useProject } from "../hooks";
import type { Character, Project, Scene } from "../types";

function ModelPicker({ kind, value, onChange }: {
  kind: "image" | "video"; value: string; onChange: (v: string) => void;
}) {
  const { data: models } = useModels();
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {Object.entries(models ?? {})
        .filter(([, m]) => m.kind === kind)
        .map(([key, m]) => (
          <option key={key} value={key}>
            {key} (${m.price}{m.max_refs ? `, ${m.max_refs} refs` : ""})
          </option>
        ))}
    </select>
  );
}

function CharacterPicker({ characters, value, onChange }: {
  characters: Character[]; value: string; onChange: (v: string) => void;
}) {
  if (characters.length === 0) return null;
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">no character</option>
      {characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name} ({c.id}, {c.reference_images.length} refs){c.main ? " ★" : ""}
        </option>
      ))}
    </select>
  );
}

function SettingsDialog({ prof, slug, project, onClose, refresh }: {
  prof: string; slug: string; project: Project; onClose: () => void; refresh: () => void;
}) {
  const [imageModel, setImageModel] = useState(project.settings.image_model);
  const [videoModel, setVideoModel] = useState(project.settings.video_model);
  const [options, setOptions] = useState(project.settings.image_options);
  const [anchor, setAnchor] = useState(project.style.anchor);
  const [budget, setBudget] = useState(project.budget_usd ?? 0);
  const [autoEnhance, setAutoEnhance] = useState(project.settings.auto_enhance ?? false);

  const save = useMutation({
    mutationFn: () =>
      api.patchProject(prof, slug, {
        image_model: imageModel,
        video_model: videoModel,
        image_options: options,
        anchor,
        budget_usd: budget,
        auto_enhance: autoEnhance,
      }),
    onSuccess: () => { toastOk("settings saved"); onClose(); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  return (
    <dialog open>
      <h2 style={{ marginTop: 0 }}>Project settings</h2>
      <label>Style anchor</label>
      <input value={anchor} onChange={(e) => setAnchor(e.target.value)} style={{ width: "100%" }} />
      <label>Default image model</label>
      <ModelPicker kind="image" value={imageModel} onChange={setImageModel} />
      <label>Default video model</label>
      <ModelPicker kind="video" value={videoModel} onChange={setVideoModel} />
      <label>Image options per scene</label>
      <input type="number" min={1} max={6} value={options}
             onChange={(e) => setOptions(Number(e.target.value))} style={{ width: 60 }} />
      <label>Budget (USD, 0 = unlimited)</label>
      <input type="number" min={0} step={1} value={budget}
             onChange={(e) => setBudget(Number(e.target.value))} style={{ width: 80 }} />
      <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        <input type="checkbox" checked={autoEnhance}
               onChange={(e) => setAutoEnhance(e.target.checked)} />
        Auto-enhance prompts with AI
      </label>
      <span className="muted" style={{ fontSize: "0.72rem" }}>
        Uses LLM to expand scene descriptions before image generation
      </span>
      <div className="row" style={{ marginTop: 14 }}>
        <button onClick={() => save.mutate()} disabled={save.isPending}>save</button>
        <button className="ghost" onClick={onClose}>cancel</button>
      </div>
    </dialog>
  );
}

function RefineDialog({ prof, slug, scene, project, onClose, refresh }: {
  prof: string; slug: string; scene: Scene; project: Project;
  onClose: () => void; refresh: () => void;
}) {
  const [description, setDescription] = useState(scene.description);
  const [pose, setPose] = useState(scene.pose ?? "");
  const [styleOverride, setStyleOverride] = useState(scene.style_override ?? "");
  const [model, setModel] = useState(project.settings.image_model);
  const [options, setOptions] = useState(1);
  const { data: models } = useModels();
  const price = (models?.[model]?.price ?? 0) * options;

  const dirty =
    description !== scene.description ||
    pose !== (scene.pose ?? "") ||
    styleOverride !== (scene.style_override ?? "");

  const save = useMutation({
    mutationFn: () =>
      api.patchScene(prof, slug, scene.id, {
        description,
        pose: pose || null,
        style_override: styleOverride || null,
      }),
    onSuccess: () => { toastOk("scene updated"); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  const enhance = useMutation({
    mutationFn: async () => {
      if (dirty) {
        await api.patchScene(prof, slug, scene.id, {
          description,
          pose: pose || null,
          style_override: styleOverride || null,
        });
      }
      return api.enhancePrompt(prof, slug, scene.id);
    },
    onSuccess: (data) => {
      setDescription(data.enhanced_prompt);
      toastOk("prompt enhanced");
    },
    onError: (e) => toastError(String(e)),
  });

  const regen = useMutation({
    mutationFn: async () => {
      if (dirty) {
        await api.patchScene(prof, slug, scene.id, {
          description,
          pose: pose || null,
          style_override: styleOverride || null,
        });
      }
      return api.regenerateImage(prof, slug, scene.id, { model, options });
    },
    onSuccess: () => { onClose(); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  return (
    <dialog open className="side-panel">
      <h2 style={{ marginTop: 0 }}>Refine {scene.id}</h2>
      <label>Scene description</label>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
        style={{ width: "100%" }}
      />
      <div className="row" style={{ marginTop: 4 }}>
        <button
          className="ghost"
          style={{ fontSize: "0.72rem" }}
          onClick={() => enhance.mutate()}
          disabled={enhance.isPending}
        >
          {enhance.isPending ? "enhancing…" : "✦ enhance with AI"}
        </button>
        {description !== scene.description && (
          <button
            className="ghost"
            style={{ fontSize: "0.72rem" }}
            onClick={() => setDescription(scene.description)}
          >
            revert
          </button>
        )}
      </div>
      <label>Pose / framing</label>
      <input value={pose} onChange={(e) => setPose(e.target.value)} style={{ width: "100%" }} />
      <label>Style override (replaces the project anchor for this scene)</label>
      <input
        value={styleOverride}
        onChange={(e) => setStyleOverride(e.target.value)}
        placeholder={project.style.anchor}
        style={{ width: "100%" }}
      />
      {scene.prompt_preview && (
        <>
          <label>Current full prompt</label>
          <div className="prompt-preview">{scene.prompt_preview}</div>
        </>
      )}
      <label>Model &amp; options</label>
      <div className="row">
        <ModelPicker kind="image" value={model} onChange={setModel} />
        <input
          type="number" min={1} max={4} value={options}
          onChange={(e) => setOptions(Number(e.target.value))}
          style={{ width: 56 }}
        />
      </div>
      <div className="row" style={{ marginTop: 14 }}>
        <button onClick={() => regen.mutate()} disabled={regen.isPending}>
          generate {options} (~${price.toFixed(2)})
        </button>
        {dirty && (
          <button className="ghost" onClick={() => save.mutate()} disabled={save.isPending}>
            save without generating
          </button>
        )}
        <button className="ghost" onClick={onClose}>close</button>
      </div>
    </dialog>
  );
}

function SceneCard({ prof, slug, scene, project, refresh, busy, isFirst, isLast, onMove }: {
  prof: string; slug: string; scene: Scene; project: Project; refresh: () => void; busy: boolean;
  isFirst: boolean; isLast: boolean; onMove: (dir: -1 | 1) => void;
}) {
  const [refineOpen, setRefineOpen] = useState(false);
  const [viewing, setViewing] = useState<number | null>(null);
  const [comparing, setComparing] = useState(false);
  const [copiedLinks, setCopiedLinks] = useState(false);
  const [refDropHighlight, setRefDropHighlight] = useState(false);
  const imgImportRef = useRef<HTMLInputElement>(null);

  const select = useMutation({
    mutationFn: (index: number) => api.select(prof, slug, scene.id, index),
    onSuccess: () => { toastOk("selected"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const importImg = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.set("file", file);
      return api.importImage(prof, slug, scene.id, form);
    },
    onSuccess: () => { toastOk("image imported"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const deleteScene = useMutation({
    mutationFn: () => api.deleteScene(prof, slug, scene.id),
    onSuccess: () => { toastOk("scene deleted"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const addRefsBulk = useMutation({
    mutationFn: (files: FileList) => {
      const form = new FormData();
      for (const f of files) form.append("files", f);
      return api.addSceneRefsBulk(prof, slug, scene.id, form);
    },
    onSuccess: () => { toastOk("refs added"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const deleteRef = useMutation({
    mutationFn: (index: number) => api.deleteSceneRef(prof, slug, scene.id, index),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const { data: sceneModels } = useModels();
  const [sceneModel, setSceneModel] = useState(project.settings.image_model);
  const upgradeScene = useMutation({
    mutationFn: () => api.generateImages(prof, slug, {
      model: "nano-banana-pro",
      options: 1,
      scene_ids: [scene.id],
      force: true,
    }),
    onSuccess: () => { toastOk("upgrading to premium"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const generateScene = useMutation({
    mutationFn: () => api.generateImages(prof, slug, {
      model: sceneModel,
      options: project.settings.image_options,
      scene_ids: [scene.id],
    }),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });

  useEffect(() => {
    if (!comparing) return;
    const handler = (e: KeyboardEvent) => {
      const n = parseInt(e.key);
      if (n >= 1 && n <= scene.images.length) select.mutate(n - 1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [comparing, scene.images.length]);

  const completedTakes = scene.clips.filter((c) => c.status === "completed").length;
  const viewingImage = viewing !== null ? scene.images[viewing] : null;
  const hasRefUrls = scene.refs.some((r) => r.url);

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div className="row" style={{ marginBottom: 4 }}>
            <b>{scene.id}</b>
            {scene.character_id && <span className="pill">{scene.character_id}</span>}
            <span className="pill">{scene.refs.length} refs</span>
            <span className="pill">{scene.images.length} images</span>
          </div>
          <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>{scene.description}</p>
          {scene.pose && <div className="mono muted" style={{ fontSize: "0.72rem" }}>{scene.pose}</div>}
        </div>
        <div className="row">
          <button className="ghost" onClick={() => setRefineOpen(true)}>refine</button>
          {!isFirst && <button className="ghost" onClick={() => onMove(-1)} title="move up">↑</button>}
          {!isLast && <button className="ghost" onClick={() => onMove(1)} title="move down">↓</button>}
          <button
            className="ghost"
            style={{ color: "var(--danger, #c44)" }}
            onClick={() => { if (confirm(`Delete ${scene.id}?`)) deleteScene.mutate(); }}
          >
            ×
          </button>
        </div>
      </div>

      {/* Scene refs: pills + drop zone */}
      <div style={{ marginTop: 6 }}>
        {scene.refs.length > 0 && (
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            {scene.refs.map((ref, i) => (
              <span
                key={i}
                className="pill"
                style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
              >
                {ref.file && (
                  <img
                    src={media(prof, slug, ref.file)}
                    alt=""
                    style={{ width: 18, height: 18, borderRadius: 3, objectFit: "cover" }}
                  />
                )}
                {ref.role}: {ref.label || ref.file.split("/").pop()}
                {ref.url && (
                  <a
                    href={ref.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: "0.65rem" }}
                    title={ref.url}
                  >
                    ↗
                  </a>
                )}
                <button
                  className="ghost"
                  style={{ padding: "0 3px", fontSize: "0.65rem", color: "var(--danger, var(--red, #c44))" }}
                  onClick={() => deleteRef.mutate(i)}
                >
                  ×
                </button>
              </span>
            ))}
            {hasRefUrls && (
              <button
                className="ghost"
                style={{ fontSize: "0.72rem" }}
                onClick={async () => {
                  const text = await api.sceneLinks(prof, slug, scene.id);
                  await navigator.clipboard.writeText(text);
                  setCopiedLinks(true);
                  setTimeout(() => setCopiedLinks(false), 1500);
                }}
              >
                {copiedLinks ? "copied" : "copy links"}
              </button>
            )}
          </div>
        )}
        <div
          style={{
            padding: "8px 12px", borderRadius: 8,
            border: `1px dashed ${refDropHighlight ? "var(--gold)" : "var(--line)"}`,
            textAlign: "center", fontSize: "0.72rem", color: "var(--taupe)",
            cursor: "pointer",
          }}
          onDragOver={(e) => { e.preventDefault(); setRefDropHighlight(true); }}
          onDragLeave={() => setRefDropHighlight(false)}
          onDrop={(e) => {
            e.preventDefault();
            setRefDropHighlight(false);
            if (e.dataTransfer.files.length) addRefsBulk.mutate(e.dataTransfer.files);
          }}
          onClick={() => {
            const input = document.createElement("input");
            input.type = "file"; input.accept = "image/*"; input.multiple = true;
            input.onchange = () => { if (input.files?.length) addRefsBulk.mutate(input.files); };
            input.click();
          }}
        >
          {addRefsBulk.isPending ? "uploading…" : "drop reference images here"}
        </div>
      </div>

      <div className="row" style={{ margin: "8px 0" }}>
        <ModelPicker kind="image" value={sceneModel} onChange={setSceneModel} />
        <button
          onClick={() => generateScene.mutate()}
          disabled={busy || generateScene.isPending}
          style={{ fontSize: "0.78rem" }}
        >
          Generate {project.settings.image_options} images
          {" "}(~${((sceneModels?.[sceneModel]?.price ?? 0) * project.settings.image_options).toFixed(2)})
        </button>
        {scene.images.length > 0 && scene.images.every((img) => img.model !== "nano-banana-pro") && (
          <button className="ghost" style={{ fontSize: "0.72rem" }}
            onClick={() => upgradeScene.mutate()}
            disabled={busy || upgradeScene.isPending}
            title="Regenerate with nano-banana-pro ($0.134) for highest quality"
          >
            ↑ premium (~$0.13)
          </button>
        )}
        <span className="mono muted" style={{ fontSize: "0.68rem" }}>
          {scene.refs.length} refs · {scene.images.length} images
        </span>
      </div>

      {scene.images.length === 0 ? (
        <p className="muted" style={{ margin: "4px 0" }}>
          Add reference images above, then generate.
        </p>
      ) : (() => {
        const lanes = new Map<string, { images: typeof scene.images; indices: number[] }>();
        scene.images.forEach((img, i) => {
          const gid = img.generation_id || "initial";
          if (!lanes.has(gid)) lanes.set(gid, { images: [], indices: [] });
          lanes.get(gid)!.images.push(img);
          lanes.get(gid)!.indices.push(i);
        });
        const laneEntries = [...lanes.entries()].reverse();
        return laneEntries.map(([gid, lane]) => (
          <div key={gid} style={{ marginBottom: 8 }}>
            {laneEntries.length > 1 && (
              <div className="mono muted" style={{ fontSize: "0.65rem", marginBottom: 4 }}>
                {gid === "initial" ? "initial generation" : gid} · {lane.images[0].model}
              </div>
            )}
            <div className="gallery">
              {lane.images.map((img, j) => {
                const globalIdx = lane.indices[j];
                return (
                  <div
                    key={j}
                    className={`thumb${scene.selected_image === globalIdx ? " selected" : ""}${busy ? " busy" : ""}`}
                    onClick={() => setViewing(globalIdx)}
                    role="button"
                    tabIndex={0}
                    title="click to view, then select"
                  >
                    <img src={media(prof, slug, img.file)} alt={`option ${globalIdx + 1}`} loading="lazy" />
                    <div className="cap">
                      {scene.selected_image === globalIdx ? "✓ " : ""}opt {globalIdx + 1} · {img.model}
                      {img.enhanced_prompt && <span style={{ color: "var(--gold)", fontSize: "0.55rem" }}> ✦</span>}
                      <a
                        href={media(prof, slug, img.file)}
                        download
                        onClick={(e) => e.stopPropagation()}
                        className="ghost"
                        style={{ padding: "1px 5px", fontSize: "0.55rem", marginLeft: 2 }}
                        title="download image"
                      >↓</a>
                      <button
                        className="ghost"
                        style={{ padding: "1px 5px", fontSize: "0.55rem", marginLeft: 2 }}
                        onClick={(e) => {
                          e.stopPropagation();
                          api.createClip(prof, slug, {
                            source_images: [img.file],
                            prompt: "",
                            model: project.settings.video_model,
                          }).then(refresh).catch((err) => toastError(String(err)));
                          toastOk("clip created");
                        }}
                      >+ clip</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ));
      })()}

      {scene.clips.length > 0 && (() => {
        const completed = scene.clips.filter((c) => c.status === "completed");
        const best = completed.find((c) => c.kept) ?? completed[completed.length - 1];
        return best ? (
          <div style={{ marginTop: 6 }}>
            <video
              controls
              preload="metadata"
              src={media(prof, slug, best.file)}
              style={{ width: 170, borderRadius: 8, border: "1px solid var(--line)" }}
            />
            <div className="mono muted" style={{ fontSize: "0.65rem" }}>
              {best.kept ? "✓ " : ""}take {best.take ?? "–"} · {best.model}
            </div>
          </div>
        ) : null;
      })()}

      {viewingImage && viewing !== null && (
        <Lightbox
          src={media(prof, slug, viewingImage.file)}
          caption={`opt ${viewing + 1} · ${viewingImage.model}`}
          onClose={() => setViewing(null)}
          actions={
            <>
              <button onClick={() => { select.mutate(viewing); setViewing(null); }}>
                {scene.selected_image === viewing ? "✓ selected" : "select this"}
              </button>
              {scene.selected_image === viewing && (
                <button className="ghost" onClick={() => {
                  api.select(prof, slug, scene.id, null).then(refresh);
                  setViewing(null);
                }}>
                  deselect
                </button>
              )}
              <a href={media(prof, slug, viewingImage.file)} download className="ghost"
                 style={{ display: "inline-block", padding: "7px 14px", borderRadius: 7,
                          border: "1px solid var(--line)", textDecoration: "none" }}>
                download
              </a>
              <button className="ghost" onClick={() => {
                api.createClip(prof, slug, {
                  source_images: [viewingImage.file],
                  prompt: "",
                  model: project.settings.video_model,
                }).then(() => { toastOk("clip created"); refresh(); setViewing(null); })
                  .catch((e) => toastError(String(e)));
              }}>
                + clip
              </button>
              {viewingImage.model !== "nano-banana-pro" && viewingImage.model !== "import" && (
                <button className="ghost" onClick={() => {
                  api.upgradeImage(prof, slug, scene.id, viewing, { model: "nano-banana-pro" })
                    .then(() => { toastOk("upgrading to premium"); refresh(); setViewing(null); })
                    .catch((e) => toastError(String(e)));
                }}>
                  ↑ upgrade ($0.13)
                </button>
              )}
              {viewingImage.upgraded_from && (
                <span className="pill gold" style={{ fontSize: "0.68rem" }}>
                  upgraded from {viewingImage.upgraded_from}
                </span>
              )}
            </>
          }
        />
      )}

      {refineOpen && (
        <RefineDialog
          prof={prof}
          slug={slug}
          scene={scene}
          project={project}
          onClose={() => setRefineOpen(false)}
          refresh={refresh}
        />
      )}
    </div>
  );
}

export default function ProjectBoard() {
  const { prof = "", slug = "" } = useParams();
  const isDemo = useIsDemo();
  const { data: project, isLoading, error } = useProject(prof, slug);
  const refresh = useInvalidateProject(prof, slug);
  const navigate = useNavigate();
  const [imageModel, setImageModel] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);
  const [addingScene, setAddingScene] = useState(false);
  const [activeTab, setActiveTab] = useState<"scenes" | "clips">("scenes");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sceneCharacter, setSceneCharacter] = useState("");
  const [brainstormResults, setBrainstormResults] = useState<string[] | null>(null);
  const [clipCount, setClipCount] = useState(2);
  const [creatingClip, setCreatingClip] = useState(false);
  const [clipStartImage, setClipStartImage] = useState("");
  const [clipEndImage, setClipEndImage] = useState("");
  const [clipPrompt, setClipPrompt] = useState("");
  const [clipModel, setClipModel] = useState("");
  const [clipSeconds, setClipSeconds] = useState(5);
  const [clipShotType, setClipShotType] = useState("");
  const { data: models } = useModels();
  const { data: shotTypes } = useQuery({ queryKey: ["shot-types"], queryFn: api.shotTypes, staleTime: Infinity });

  const generateAll = useMutation({
    mutationFn: () =>
      api.generateImages(prof, slug, {
        model: imageModel ?? project?.settings.image_model,
        options: project?.settings.image_options,
      }),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const batchScenes = useMutation({
    mutationFn: () => {
      const model = imageModel ?? project?.settings.image_model ?? "";
      const price = models?.[model]?.price ?? 0;
      const needed = (project?.scenes ?? []).reduce((sum, s) =>
        sum + Math.max(0, (project?.settings.image_options ?? 1) - s.images.length), 0);
      const est = needed * price;
      if (!window.confirm(
        `Generate images for ${needed > 0 ? `${(project?.scenes ?? []).filter(s => s.images.length < (project?.settings.image_options ?? 1)).length} scenes` : "0 scenes"}. ` +
        `Estimated cost: $${est.toFixed(2)}. Continue?`
      )) throw new Error("cancelled");
      return api.generateAllScenes(prof, slug, {
        model,
        options: project?.settings.image_options,
      });
    },
    onSuccess: () => { toastOk("batch generation started"); refresh(); },
    onError: (e) => { if (String(e) !== "Error: cancelled") toastError(String(e)); },
  });
  const addRef = useMutation({
    mutationFn: (form: FormData) => api.addProjectRef(prof, slug, form),
    onSuccess: () => { toastOk("reference added"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const addScene = useMutation({
    mutationFn: (body: { description: string; pose?: string; character_id?: string }) =>
      api.addScene(prof, slug, body),
    onSuccess: () => { setAddingScene(false); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const runExport = useMutation({
    mutationFn: () => api.export(prof, slug),
    onSuccess: (result) => { setExported(result.dir); toastOk("exported"); },
    onError: (e) => toastError(String(e)),
  });
  const runStitch = useMutation({
    mutationFn: () => api.stitch(prof, slug),
    onSuccess: () => { toastOk("stitching started"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const deleteProject = useMutation({
    mutationFn: () => api.deleteProject(prof, slug),
    onSuccess: () => navigate(`/${prof}`),
    onError: (e) => toastError(String(e)),
  });
  const duplicateProject = useMutation({
    mutationFn: () => {
      const name = prompt("Name for the copy?", `${project?.name ?? ""} copy`);
      if (!name) throw new Error("cancelled");
      return api.duplicateProject(prof, slug, { name });
    },
    onSuccess: (p: Project) => navigate(`/${prof}/p/${p.slug}`),
    onError: (e) => { if (String(e) !== "Error: cancelled") toastError(String(e)); },
  });
  const brainstorm = useMutation({
    mutationFn: () => api.brainstorm(prof, slug, { count: 6 }),
    onSuccess: (data) => setBrainstormResults(data.descriptions),
    onError: (e) => toastError(String(e)),
  });
  const acceptBrainstorm = useMutation({
    mutationFn: (descriptions: string[]) =>
      api.addScenesBulk(prof, slug, { descriptions, character_id: defaultChar || undefined }),
    onSuccess: () => { setBrainstormResults(null); toastOk("scenes added"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const selectAll = useMutation({
    mutationFn: () => api.selectAll(prof, slug),
    onSuccess: (r) => { toastOk(`auto-selected ${r.selected} scenes`); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const takesAll = useMutation({
    mutationFn: () => api.generateTakesAll(prof, slug, {
      model: project?.settings.video_model,
      count: clipCount,
    }),
    onSuccess: () => { toastOk("generating takes for all scenes"); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  if (isLoading && !isDemo) return <p className="muted">Loading…</p>;
  if (!project && !isDemo) return <p className="muted">{String(error ?? "not found")}</p>;
  if (!project && isDemo) {
    const dp = DEMO_PROJECT;
    const gradients = [
      "linear-gradient(135deg, #b8860b 0%, #d4a04a 40%, #f5deb3 100%)",
      "linear-gradient(135deg, #8b6914 0%, #c4923a 40%, #ffe4b5 100%)",
      "linear-gradient(135deg, #a0522d 0%, #cd853f 40%, #ffdead 100%)",
      "linear-gradient(135deg, #996633 0%, #cc9966 40%, #f5e6cc 100%)",
    ];
    return (
      <>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <h1>{dp.name}</h1>
          <span className="pill gold">demo mode</span>
        </div>
        <p className="muted">
          {dp.concept} · <span className="mono">{dp.style.anchor}</span>
          · <span className="mono">${dp.spent_usd.toFixed(2)} GPU spend</span>
        </p>

        <div className="row">
          <span className="mono muted">
            models: {dp.settings.image_model} / {dp.settings.video_model} · {dp.settings.image_options} options/scene
          </span>
        </div>

        <h2>Scenes</h2>
        {dp.scenes.map((scene, si) => (
          <div key={scene.id} className="card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <b>{scene.id}</b> — {scene.description}
                <div className="muted mono" style={{ fontSize: "0.75rem" }}>
                  {[scene.character_id, scene.pose].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div className="row">
                <Link to={`/${prof}/p/${slug}/scenes/${scene.id}/takes`}>
                  <button className="ghost">
                    takes ({scene.clips.filter((c) => c.status === "completed").length})
                  </button>
                </Link>
                <Link to={`/${prof}/p/${slug}/history`}>
                  <button className="ghost">history</button>
                </Link>
              </div>
            </div>
            <div className="gallery">
              {scene.images.map((img, i) => (
                <div key={i} className={`thumb${scene.selected_image === i ? " selected" : ""}`}>
                  <div style={{
                    width: "100%", aspectRatio: "9/16",
                    background: gradients[(si * 2 + i) % gradients.length],
                    borderRadius: 4,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "rgba(0,0,0,0.3)", fontSize: "0.7rem", fontWeight: 700,
                  }}>
                    {img.model}
                  </div>
                  <div className="cap">
                    {scene.selected_image === i ? "✓ " : ""}opt {i + 1} · {img.model} · ${(img.meta.cost_usd as number).toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
            {scene.clips.filter((c) => c.status === "completed").length > 0 && (
              <div className="row" style={{ marginTop: 6, gap: 6 }}>
                {scene.clips.filter((c) => c.status === "completed").map((c, i) => (
                  <span key={i} className={`pill${c.kept ? " gold" : ""}`}>
                    take {c.take} · {c.model}{c.kept ? " ✓" : ""}
                  </span>
                ))}
              </div>
            )}
            {scene.prompt_preview && (
              <div className="prompt-preview">{scene.prompt_preview}</div>
            )}
          </div>
        ))}
      </>
    );
  }

  const proj = project!;
  const busy = proj.job?.status === "running";
  const keptCount = proj.scenes.flatMap((s) => s.clips).filter((c) => c.kept).length;
  const allClipsReady = proj.scenes.length > 0 &&
    proj.scenes.every((s) => s.clips.some((c) => c.status === "completed"));
  const allChars = proj.profile_characters;
  const defaultChar = allChars.find((c) => c.main)?.id ?? allChars[0]?.id ?? "";
  const selectedCount = proj.scenes.filter((s) => s.selected_image !== null).length;
  const unselectedWithImages = proj.scenes.filter((s) => s.selected_image === null && s.images.length > 0).length;
  const imgModelKey = imageModel ?? proj.settings.image_model;
  const imgPrice = models?.[imgModelKey]?.price ?? 0;
  const imagesNeeded = proj.scenes.reduce((sum, s) =>
    sum + Math.max(0, proj.settings.image_options - s.images.length), 0);
  const imgCost = imagesNeeded * imgPrice;
  const vidPrice = models?.[proj.settings.video_model]?.price ?? 0;
  const takesCost = selectedCount * clipCount * vidPrice;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>{proj.name}</h1>
        <div className="row">
          <button className="ghost" onClick={() => setSettingsOpen(true)}>settings</button>
          <button className="ghost" onClick={() => duplicateProject.mutate()}>duplicate</button>
          <button
            className="ghost"
            style={{ color: "var(--red, #c44)" }}
            onClick={() => {
              if (confirm(`Delete project "${proj.name}" and all its files?`))
                deleteProject.mutate();
            }}
          >
            delete project
          </button>
        </div>
      </div>
      <p className="muted">
        {proj.concept} · <span className="mono">{proj.style.anchor}</span>
        {proj.spent_usd > 0 && <> · <span className="mono">${proj.spent_usd.toFixed(2)}{proj.budget_usd > 0 ? ` / $${proj.budget_usd.toFixed(0)} budget` : ""}</span></>}
      </p>
      <JobBanner job={proj.job} onRetry={() => generateAll.mutate()} />

      {(proj.notes || null) && (
        <div className="mono muted" style={{ fontSize: "0.75rem", margin: "6px 0", whiteSpace: "pre-wrap" }}>
          {proj.notes}
        </div>
      )}
      <textarea
        className="mono"
        placeholder="project notes — context, decisions, ideas..."
        defaultValue={proj.notes}
        rows={2}
        style={{ width: "100%", fontSize: "0.75rem", resize: "vertical", marginBottom: 8 }}
        onBlur={(e) => {
          const v = e.target.value;
          if (v !== proj.notes) api.patchProject(prof, slug, { notes: v }).then(refresh);
        }}
      />

      {settingsOpen && (
        <SettingsDialog
          prof={prof}
          slug={slug}
          project={proj}
          onClose={() => setSettingsOpen(false)}
          refresh={refresh}
        />
      )}

      <div className="row" style={{ gap: 0, borderBottom: "1px solid var(--line)", marginBottom: 14 }}>
        <button
          className={activeTab === "scenes" ? "btn" : "ghost"}
          style={{ borderRadius: "7px 7px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("scenes")}
        >
          Scenes ({proj.scenes.length})
        </button>
        <button
          className={activeTab === "clips" ? "btn" : "ghost"}
          style={{ borderRadius: "7px 7px 0 0", borderBottom: "none" }}
          onClick={() => setActiveTab("clips")}
        >
          Clips ({proj.clips.length})
        </button>
      </div>

      {activeTab === "scenes" && <>

      <div className="row" style={{ marginBottom: 10 }}>
        <button className="ghost" onClick={() => setAddingScene(true)}>+ scene</button>
        {proj.concept && (
          <button className="ghost" onClick={() => brainstorm.mutate()} disabled={busy || brainstorm.isPending}>
            {brainstorm.isPending ? "thinking…" : "brainstorm"}
          </button>
        )}
        {imagesNeeded > 0 && (
          <button
            onClick={() => batchScenes.mutate()}
            disabled={busy || batchScenes.isPending}
          >
            Generate all scenes (~${imgCost.toFixed(2)})
          </button>
        )}
      </div>

      {brainstormResults && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Brainstormed scenes</b>
            <button className="ghost" onClick={() => setBrainstormResults(null)}>dismiss</button>
          </div>
          <p className="muted">Edit or remove scenes before adding. Click a scene to edit it.</p>
          {brainstormResults.map((desc, i) => (
            <div key={i} className="row" style={{ marginBottom: 6 }}>
              <input
                value={desc}
                onChange={(e) => {
                  const next = [...brainstormResults];
                  next[i] = e.target.value;
                  setBrainstormResults(next);
                }}
                style={{ flex: 1 }}
              />
              <button
                className="ghost"
                style={{ color: "var(--red, #c44)" }}
                onClick={() => setBrainstormResults(brainstormResults.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </div>
          ))}
          <div className="row" style={{ marginTop: 10 }}>
            <button
              onClick={() => acceptBrainstorm.mutate(brainstormResults.filter((d) => d.trim()))}
              disabled={acceptBrainstorm.isPending}
            >
              add {brainstormResults.filter((d) => d.trim()).length} scenes
            </button>
            <button className="ghost" onClick={() => setBrainstormResults(null)}>cancel</button>
          </div>
        </div>
      )}

      {addingScene && (() => {
        const allImages = proj.scenes.flatMap((s) =>
          s.images.map((img) => ({ file: img.file, scene: s.id, model: img.model }))
        );
        return (
          <form
            className="card"
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              const description = String(data.get("description") ?? "").trim();
              if (!description) return;
              const files = (e.currentTarget.querySelector('input[type="file"]') as HTMLInputElement)?.files;
              const checked = e.currentTarget.querySelectorAll<HTMLInputElement>('input[name="existing_ref"]:checked');
              try {
                const scene = await api.addScene(prof, slug, {
                  description,
                  pose: String(data.get("pose") ?? "") || undefined,
                  character_id: sceneCharacter || undefined,
                }) as { id: string };
                if (files?.length) {
                  const refForm = new FormData();
                  for (const f of files) refForm.append("files", f);
                  await api.addSceneRefsBulk(prof, slug, scene.id, refForm);
                }
                for (const cb of checked) {
                  const refForm = new FormData();
                  refForm.set("role", "style");
                  refForm.set("label", "from " + cb.dataset.scene);
                  const resp = await fetch(media(prof, slug, cb.value));
                  const blob = await resp.blob();
                  refForm.set("file", blob, cb.value.split("/").pop() || "ref.png");
                  await api.addSceneRef(prof, slug, scene.id, refForm);
                }
                setAddingScene(false);
                refresh();
              } catch (err) {
                toastError(String(err));
              }
            }}
          >
            <label>Scene description</label>
            <input name="description" required style={{ width: "100%" }}
                   placeholder="what is this scene? e.g. standing in a sunlit cafe, full outfit visible" />
            <label>Pose / framing (optional)</label>
            <input name="pose" style={{ width: "100%" }}
                   placeholder="e.g. standing, facing camera, head to toe" />
            {allChars.length > 0 && (
              <>
                <label>Character</label>
                <CharacterPicker characters={allChars} value={sceneCharacter} onChange={setSceneCharacter} />
              </>
            )}
            <label>Upload new reference images</label>
            <input type="file" accept="image/*" multiple className="mono" style={{ width: "100%" }} />

            {allImages.length > 0 && (
              <>
                <label>Or use generated images from this project</label>
                <div className="gallery" style={{ maxHeight: 200, overflowY: "auto" }}>
                  {allImages.map((img, i) => (
                    <label key={i} style={{ cursor: "pointer", position: "relative" }}>
                      <input type="checkbox" name="existing_ref" value={img.file}
                             data-scene={img.scene}
                             style={{ position: "absolute", top: 4, left: 4, zIndex: 1 }} />
                      <img src={media(prof, slug, img.file)}
                           alt={`${img.scene} ${img.model}`}
                           style={{ width: 80, borderRadius: 6, border: "1px solid var(--line)" }}
                           loading="lazy" />
                    </label>
                  ))}
                </div>
              </>
            )}
            <div className="row" style={{ marginTop: 10 }}>
              <button type="submit" disabled={addScene.isPending}>add scene</button>
              <button type="button" className="ghost" onClick={() => setAddingScene(false)}>cancel</button>
            </div>
          </form>
        );
      })()}

      {allChars.length > 0 && (
        <p className="muted mono" style={{ marginTop: 10 }}>
          characters: {allChars.map((c) =>
            `${c.main ? "★ " : ""}${c.name} (${c.id}, ${c.reference_images.length} refs)`
          ).join(" · ")}
        </p>
      )}

      {proj.refs.length > 0 && (
        <div className="row" style={{ marginTop: 6, gap: 8, flexWrap: "wrap" }}>
          <span className="mono muted" style={{ fontSize: "0.72rem" }}>refs:</span>
          {proj.refs.map((r, i) => (
            <span key={i} className="pill" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              {r.role}: {r.label || r.file.split("/").pop()}
              <button
                className="ghost"
                style={{ padding: "0 3px", fontSize: "0.65rem", color: "var(--danger)" }}
                onClick={() => api.deleteProjectRef(prof, slug, i).then(refresh)}
              >×</button>
            </span>
          ))}
        </div>
      )}

      {proj.scenes.length === 0 && (
        <div className="card" style={{ borderColor: "var(--gold-dim)", marginTop: 14 }}>
          <b>Getting started</b>
          <p className="muted" style={{ margin: "4px 0" }}>
            1. Click <b>+ scene</b> and describe a visual moment &nbsp; 2. Drop reference images onto the scene card &nbsp;
            3. Click <b>Generate</b> — images appear automatically
          </p>
        </div>
      )}

      <h2>Scenes</h2>
      {proj.scenes.length === 0 && (
        <p className="muted">No scenes yet — hit "+ scene" or "brainstorm scenes" to get started.</p>
      )}
      {proj.scenes.map((scene, idx) => (
        <SceneCard
          key={scene.id}
          prof={prof}
          slug={slug}
          scene={scene}
          project={proj}
          refresh={refresh}
          busy={!!busy}
          isFirst={idx === 0}
          isLast={idx === proj.scenes.length - 1}
          onMove={(dir) => {
            const ids = proj.scenes.map((s) => s.id);
            const j = idx + dir;
            [ids[idx], ids[j]] = [ids[j], ids[idx]];
            api.reorderScenes(prof, slug, ids).then(refresh).catch((e) => toastError(String(e)));
          }}
        />
      ))}

      </>}

      {activeTab === "clips" && <>
      <div className="row" style={{ marginBottom: 10 }}>
        <button className="ghost" onClick={() => setCreatingClip(true)}>+ clip</button>
        <button className="ghost" onClick={() => {
          api.generateAllClips(prof, slug).then(refresh).catch((e) => toastError(String(e)));
        }} disabled={busy || proj.clips.filter((c) => c.status === "pending").length === 0}>
          Generate {proj.clips.filter((c) => c.status === "pending").length} pending
        </button>
      </div>

      {creatingClip && (() => {
        const allImages = proj.scenes.flatMap((s) =>
          s.images.map((img) => ({ file: img.file, scene: s.id }))
        );
        return (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Create clip</h3>
            <label>Start image (required)</label>
            <div className="gallery" style={{ maxHeight: 160, overflowY: "auto" }}>
              {allImages.map((img, i) => (
                <div key={i}
                  className={`thumb${clipStartImage === img.file ? " selected" : ""}`}
                  style={{ width: 80, cursor: "pointer" }}
                  onClick={() => setClipStartImage(img.file)}>
                  <img src={media(prof, slug, img.file)} alt={img.scene} loading="lazy" />
                  <div className="cap">{img.scene}</div>
                </div>
              ))}
            </div>
            <label>End image (optional — AI interpolates between start and end)</label>
            <div className="gallery" style={{ maxHeight: 160, overflowY: "auto" }}>
              <div className={`thumb${!clipEndImage ? " selected" : ""}`}
                   style={{ width: 80, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", height: 100 }}
                   onClick={() => setClipEndImage("")}>
                <span className="muted" style={{ fontSize: "0.7rem" }}>none</span>
              </div>
              {allImages.map((img, i) => (
                <div key={i}
                  className={`thumb${clipEndImage === img.file ? " selected" : ""}`}
                  style={{ width: 80, cursor: "pointer" }}
                  onClick={() => setClipEndImage(img.file)}>
                  <img src={media(prof, slug, img.file)} alt={img.scene} loading="lazy" />
                  <div className="cap">{img.scene}</div>
                </div>
              ))}
            </div>
            <label>Motion prompt</label>
            <input value={clipPrompt} onChange={(e) => setClipPrompt(e.target.value)}
                   placeholder="e.g. gentle sway, slow turn, walk forward"
                   style={{ width: "100%" }} />
            <label>Shot type</label>
            <select value={clipShotType} onChange={(e) => setClipShotType(e.target.value)}
                    style={{ marginBottom: 6 }}>
              <option value="">none</option>
              {Object.entries(shotTypes ?? {}).map(([key, st]) => (
                <option key={key} value={key}>{st.label}</option>
              ))}
            </select>
            {clipShotType && shotTypes?.[clipShotType] && (
              <span className="muted" style={{ fontSize: "0.72rem" }}>
                {shotTypes[clipShotType].description}
              </span>
            )}
            <label>Video model</label>
            <div className="row">
              <select value={clipModel || proj.settings.video_model}
                      onChange={(e) => setClipModel(e.target.value)}>
                <option value="auto">Auto (smart routing)</option>
                {Object.entries(models ?? {})
                  .filter(([, m]) => m.kind === "video")
                  .map(([key, m]) => (
                    <option key={key} value={key}>
                      {key} — ${m.price}/clip{m.supports_i2v ? " · I2V" : ""}
                    </option>
                  ))}
              </select>
              {(clipModel || proj.settings.video_model) === "auto" && clipShotType && shotTypes?.[clipShotType] && (
                <span className="mono muted" style={{ fontSize: "0.68rem" }}>
                  → {shotTypes[clipShotType].recommended_video}
                </span>
              )}
              <label style={{ margin: 0 }}>Length</label>
              <select value={clipSeconds} onChange={(e) => setClipSeconds(Number(e.target.value))}>
                <option value={3}>3s</option>
                <option value={5}>5s</option>
                <option value={7}>7s</option>
                <option value={10}>10s</option>
              </select>
              <span className="mono muted" style={{ fontSize: "0.72rem" }}>
                ~${((models?.[clipModel || proj.settings.video_model]?.price ?? 0) * (clipSeconds / 5)).toFixed(2)}
              </span>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button disabled={!clipStartImage} onClick={() => {
                const sources = [clipStartImage];
                if (clipEndImage) sources.push(clipEndImage);
                api.createClip(prof, slug, {
                  source_images: sources,
                  prompt: clipPrompt,
                  model: clipModel || proj.settings.video_model,
                  seconds: clipSeconds,
                  shot_type: clipShotType || undefined,
                }).then(() => {
                  setCreatingClip(false);
                  setClipStartImage("");
                  setClipEndImage("");
                  setClipPrompt("");
                  setClipModel("");
                  setClipSeconds(5);
                  setClipShotType("");
                  refresh();
                }).catch((e) => toastError(String(e)));
              }}>create clip</button>
              <button className="ghost" onClick={() => setCreatingClip(false)}>cancel</button>
            </div>
          </div>
        );
      })()}

      {proj.clips.length === 0 && !creatingClip && (
        <p className="muted">No clips yet — click "+ clip" or use the "+ clip" button on scene images.</p>
      )}
      {proj.clips.map((clip) => (
        <div key={clip.id} className="card">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{clip.id}</b>
                {clip.shot_type && shotTypes?.[clip.shot_type] && (
                  <span className="pill" style={{
                    borderColor: shotTypes[clip.shot_type].color,
                    color: shotTypes[clip.shot_type].color,
                  }}>{shotTypes[clip.shot_type].label}</span>
                )}
                <span className="pill">{clip.model}</span>
                <span className="pill">{clip.seconds}s</span>
                {clip.source_images.length > 1 && <span className="pill gold">start + end</span>}
                {clip.status === "pending" && <span className="pill">pending</span>}
                {clip.status === "failed" && <span className="pill" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>failed</span>}
                {clip.kept && <span className="pill gold">✓ kept</span>}
                {clip.upgraded_from && (
                  <span className="pill gold" style={{ fontSize: "0.65rem" }}>↑ from {clip.upgraded_from}</span>
                )}
                {typeof clip.meta?.cost_usd === "number" && (
                  <span className="mono muted" style={{ fontSize: "0.72rem" }}>${(clip.meta.cost_usd as number).toFixed(2)}</span>
                )}
              </div>

              {clip.status === "pending" ? (
                <input
                  className="mono"
                  defaultValue={clip.prompt}
                  placeholder="motion prompt (e.g. gentle sway, slow turn)"
                  style={{ width: "100%", fontSize: "0.8rem", marginBottom: 6 }}
                  onBlur={(e) => {
                    if (e.target.value !== clip.prompt)
                      api.patchClip(prof, slug, clip.id, { prompt: e.target.value }).then(refresh);
                  }}
                />
              ) : clip.prompt ? (
                <p className="muted" style={{ margin: "0 0 6px", fontSize: "0.85rem" }}>{clip.prompt}</p>
              ) : null}

              {clip.status === "failed" && clip.error && (
                <p className="muted" style={{ color: "var(--danger)", fontSize: "0.78rem", margin: "0 0 6px" }}>{clip.error}</p>
              )}

              {clip.source_images.length > 0 && (
                <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                  <span className="mono muted" style={{ fontSize: "0.68rem" }}>source:</span>
                  {clip.source_images.map((src, i) => (
                    <img key={i} src={media(prof, slug, src)} alt=""
                         style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4, border: "1px solid var(--line)" }} />
                  ))}
                </div>
              )}

              <div className="row">
                <select
                  className="mono"
                  style={{ fontSize: "0.68rem", padding: "3px 6px", width: "auto" }}
                  value={clip.shot_type || ""}
                  onChange={(e) => api.patchClip(prof, slug, clip.id, { shot_type: e.target.value }).then(refresh).catch((err) => toastError(String(err)))}
                >
                  <option value="">type…</option>
                  {Object.entries(shotTypes ?? {}).map(([key, st]) => (
                    <option key={key} value={key}>{st.label}</option>
                  ))}
                </select>
                {clip.status === "completed" && (
                  <>
                    <button
                      className={clip.kept ? "btn" : "ghost"}
                      onClick={() => api.keepClip(prof, slug, clip.id, !clip.kept).then(refresh).catch((e) => toastError(String(e)))}
                    >
                      {clip.kept ? "✓ kept" : "keep"}
                    </button>
                    <a href={media(prof, slug, clip.file)} download className="ghost"
                       style={{ padding: "7px 14px", borderRadius: 7, border: "1px solid var(--line)", textDecoration: "none" }}>
                      download
                    </a>
                  </>
                )}
                {(clip.status === "completed" || clip.status === "failed") && (
                  <button className="ghost"
                    onClick={() => api.resetClip(prof, slug, clip.id).then(refresh).catch((e) => toastError(String(e)))}>
                    refine
                  </button>
                )}
                {clip.status === "completed" && clip.model !== "seedance-2.0-or" && clip.model !== "seedance-2.0" && (
                  <button className="ghost"
                    onClick={() => api.upgradeClip(prof, slug, clip.id, { model: "seedance-2.0-or" })
                      .then(() => { toastOk("upgrading clip"); refresh(); })
                      .catch((e) => toastError(String(e)))}>
                    ↑ upgrade
                  </button>
                )}
                {clip.status === "pending" && (
                  <button onClick={() => api.generateClip(prof, slug, clip.id).then(refresh).catch((e) => toastError(String(e)))}
                    disabled={busy}>
                    generate
                  </button>
                )}
                <button className="ghost" style={{ color: "var(--danger)" }}
                  onClick={() => { if (confirm(`Delete ${clip.id}?`)) api.deleteClip(prof, slug, clip.id).then(refresh); }}>
                  ×
                </button>
              </div>
            </div>

            {clip.status === "completed" && clip.file && (
              <video controls preload="metadata" src={media(prof, slug, clip.file)}
                     style={{ width: 240, borderRadius: 8, marginLeft: 16,
                              border: clip.kept ? "2px solid var(--gold)" : "1px solid var(--line)" }} />
            )}
          </div>
        </div>
      ))}
      </>}
    </>
  );
}
