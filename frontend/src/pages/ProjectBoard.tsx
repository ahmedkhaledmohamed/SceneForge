import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, exportForPlatform, media } from "../api";
import EmptyState from "../components/EmptyState";
import JobBanner from "../components/JobBanner";
import Lightbox from "../components/Lightbox";
import { SkeletonProjectBoard } from "../components/Skeleton";
import { toastError, toastOk } from "../components/toast";
import { DEMO_PROJECT } from "../demo";
import { useIsDemo } from "../DemoContext";
import { useInvalidateProject, useModels, useProject } from "../hooks";
import type { Character, Project, SavedPrompt, Scene, ShotListItem } from "../types";

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

function AssetPicker({ prof, slug, sceneId, onAdd }: {
  prof: string; slug: string; sceneId: string; onAdd: () => void;
}) {
  const [roleFilter, setRoleFilter] = useState("");
  const assetsQuery = useQuery({
    queryKey: ["assets", prof, roleFilter],
    queryFn: () => api.assets(prof, undefined, roleFilter || undefined),
  });
  const assets = assetsQuery.data ?? [];

  const addFromAsset = async (aid: string) => {
    try {
      await api.refFromAsset(prof, slug, sceneId, aid);
      toastOk("Added from library");
      onAdd();
    } catch (e) {
      toastError(String(e));
    }
  };

  const roles = ["garment", "style", "background", "prop", "other"];

  return (
    <div style={{ padding: "8px 0", marginBottom: 6 }}>
      <div className="row" style={{ gap: 6, marginBottom: 8 }}>
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} style={{ fontSize: "0.78rem" }}>
          <option value="">All roles</option>
          {roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      {assets.length === 0 && (
        <p className="muted" style={{ fontSize: "0.78rem", margin: 0 }}>
          No assets in library. Upload assets from the profile page.
        </p>
      )}
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        {assets.map((asset) => (
          <div
            key={asset.id}
            style={{ cursor: "pointer", textAlign: "center" }}
            onClick={() => addFromAsset(asset.id)}
            title={`${asset.label} — click to add`}
          >
            <img
              src={`${import.meta.env.VITE_API_BASE ?? "/api"}/profiles/${prof}/media/${asset.file}`}
              alt={asset.label}
              style={{ width: 60, height: 60, objectFit: "cover", borderRadius: 6, border: "1px solid var(--line)" }}
            />
            <div className="mono muted" style={{ fontSize: "0.62rem", maxWidth: 60, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {asset.label}
            </div>
          </div>
        ))}
      </div>
    </div>
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
  const [showAssetPicker, setShowAssetPicker] = useState(false);
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
            <button
              className="ghost"
              style={{ fontSize: "0.72rem" }}
              onClick={() => setShowAssetPicker(!showAssetPicker)}
            >
              {showAssetPicker ? "close library" : "from library"}
            </button>
          </div>
        )}
        {showAssetPicker && (
          <AssetPicker prof={prof} slug={slug} sceneId={scene.id} onAdd={() => { setShowAssetPicker(false); refresh(); }} />
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
  const [activeTab, setActiveTab] = useState<"scenes" | "clips" | "sequence">("scenes");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sceneCharacter, setSceneCharacter] = useState("");
  const [promptLibOpen, setPromptLibOpen] = useState(false);
  const { data: profileDoc } = useQuery({
    queryKey: ["profile", prof],
    queryFn: () => api.profile(prof),
    enabled: !isDemo && !!prof,
    staleTime: 60000,
  });
  const [consistencyScore, setConsistencyScore] = useState<{score: number; outliers: {scene_id: string; similarity: number}[]} | null>(null);
  const [scoringBusy, setScoringBusy] = useState(false);
  const [brainstormResults, setBrainstormResults] = useState<string[] | null>(null);
  const [shotListResults, setShotListResults] = useState<ShotListItem[] | null>(null);
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
  const queryClient = useQueryClient();
  const deleteProject = useMutation({
    mutationFn: () => api.deleteProject(prof, slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stats", prof] });
      queryClient.invalidateQueries({ queryKey: ["projects", prof] });
      navigate(`/${prof}`);
    },
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
  const saveAsTemplate = useMutation({
    mutationFn: () => {
      const name = prompt("Template name?", project?.name ?? "");
      if (!name) throw new Error("cancelled");
      return api.saveAsTemplate(prof, slug, name);
    },
    onSuccess: (r) => toastOk(`saved template "${r.name}" (${r.scenes} scenes)`),
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
  const shotList = useMutation({
    mutationFn: () => api.generateShotList(prof, slug, { num_scenes: 8 }),
    onSuccess: (data) => setShotListResults(data.shots),
    onError: (e) => toastError(String(e)),
  });
  const applyShotList = useMutation({
    mutationFn: (shots: ShotListItem[]) =>
      api.applyShotList(prof, slug, {
        shots,
        character_id: defaultChar || undefined,
      }),
    onSuccess: () => { setShotListResults(null); toastOk("scenes added from shot list"); refresh(); },
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

  if (isLoading && !isDemo) return <SkeletonProjectBoard />;
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
          <button className="ghost" onClick={() => saveAsTemplate.mutate()}>save as template</button>
          <button className="ghost" onClick={() => duplicateProject.mutate()}>duplicate</button>
          <button className="ghost" onClick={() => api.backupProject(prof, slug).then(() => toastOk("Backup downloaded")).catch(e => toastError(String(e)))}>backup zip</button>
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
        {" · "}<span className="mono" style={{ color: "var(--gold)" }}>${proj.spent_usd.toFixed(2)} spent{proj.budget_usd > 0 ? ` / $${proj.budget_usd.toFixed(0)} budget` : ""}</span>
        {consistencyScore && (() => {
          const s = consistencyScore.score;
          const color = s > 0.8 ? "var(--green, #4a4)" : s > 0.6 ? "var(--gold, #daa520)" : "var(--danger, #c44)";
          return (
            <> · <span className="pill" style={{ background: color, color: "#fff", fontSize: "0.72rem" }}>
              consistency {(s * 100).toFixed(0)}%
            </span>
            {consistencyScore.outliers.length > 0 && (
              <span className="muted" style={{ fontSize: "0.72rem" }}>
                {" "}({consistencyScore.outliers.length} outlier{consistencyScore.outliers.length !== 1 ? "s" : ""})
              </span>
            )}
            </>
          );
        })()}
      </p>
      <div className="row" style={{ marginBottom: 8, gap: 8 }}>
        {proj.scenes.filter(s => s.selected_image != null).length >= 2 && (
          <button
            className="ghost"
            style={{ fontSize: "0.78rem" }}
            disabled={scoringBusy}
            onClick={async () => {
              setScoringBusy(true);
              try {
                const result = await api.scoreConsistency(prof, slug);
                setConsistencyScore(result);
                toastOk(`Consistency: ${(result.score * 100).toFixed(0)}%`);
              } catch (e) {
                toastError(String(e));
              } finally {
                setScoringBusy(false);
              }
            }}
          >
            {scoringBusy ? "Scoring..." : "Check consistency"}
          </button>
        )}
      </div>
      <JobBanner job={proj.job} onRetry={() => generateAll.mutate()} />

      {profileDoc && !profileDoc.has_keys && (
        <div className="card" style={{ borderColor: "var(--danger)", padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <b style={{ color: "var(--danger)" }}>API key required</b>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.82rem" }}>
              Add a Together AI key in Settings before generating images or clips.
            </p>
          </div>
          <Link to={`/${prof}/settings`} style={{ flexShrink: 0 }}>
            <button>Go to Settings</button>
          </Link>
        </div>
      )}

      {proj.concept && proj.scenes.length === 0 && (
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", borderRadius: 8,
          background: "var(--bg-raised, #2a2520)",
          border: "1px solid var(--gold-dim, #665c3a)",
          marginBottom: 12,
        }}>
          <button
            style={{ fontWeight: 600, fontSize: "0.9rem" }}
            disabled={busy}
            onClick={() => {
              const numScenes = 8;
              const opts = proj.settings.image_options;
              const estImgCost = numScenes * opts * (models?.[proj.settings.image_model]?.price ?? 0);
              const estVidCost = numScenes * (models?.[proj.settings.video_model]?.price ?? 0);
              const estTotal = estImgCost + estVidCost;
              if (!window.confirm(
                `AI Director will:\n` +
                `  - Plan ${numScenes} scenes from your concept\n` +
                `  - Generate ${numScenes * opts} image(s)\n` +
                `  - Auto-select and generate ${numScenes} clip(s)\n\n` +
                `Estimated cost: ~$${estTotal.toFixed(2)}\n\nContinue?`
              )) return;
              api.direct(prof, slug, {
                num_scenes: numScenes,
                image_model: proj.settings.image_model,
                video_model: proj.settings.video_model,
                seconds: 5,
                character_id: defaultChar || undefined,
              }).then(() => { toastOk("director started"); refresh(); })
                .catch((e) => toastError(String(e)));
            }}
          >
            Direct
          </button>
          <span className="mono muted" style={{ fontSize: "0.72rem" }}>
            AI plans scenes, generates images &amp; clips from your concept
          </span>
        </div>
      )}

      {proj.scenes.length > 0 && (() => {
        const imgNeeded = proj.scenes.reduce((sum, s) =>
          sum + Math.max(0, proj.settings.image_options - s.images.length), 0);
        const completedSources = new Set(
          proj.clips.filter((c) => c.status === "completed").flatMap((c) => c.source_images)
        );
        const clipsNeeded = proj.scenes.filter((s) => {
          const selImg = s.selected_image !== null ? s.images[s.selected_image!]?.file : s.images[0]?.file;
          return selImg ? !completedSources.has(selImg) : imgNeeded > 0;
        }).length;
        const estImgCost = imgNeeded * (models?.[proj.settings.image_model]?.price ?? 0);
        const estVidCost = clipsNeeded * (models?.[proj.settings.video_model]?.price ?? 0);
        const estTotal = estImgCost + estVidCost;
        return (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 14px", borderRadius: 8,
            background: "var(--bg-raised, #2a2520)",
            border: "1px solid var(--gold-dim, #665c3a)",
            marginBottom: 12,
          }}>
            <button
              style={{ fontWeight: 600, fontSize: "0.9rem" }}
              disabled={busy}
              onClick={() => {
                if (!window.confirm(
                  `Produce full pipeline:\n` +
                  `  - Generate ${imgNeeded} image(s)\n` +
                  `  - Auto-select unselected scenes\n` +
                  `  - Generate ~${clipsNeeded} clip(s)\n\n` +
                  `Estimated cost: ~$${estTotal.toFixed(2)}\n\nContinue?`
                )) return;
                api.produce(prof, slug, {
                  image_model: proj.settings.image_model,
                  video_model: proj.settings.video_model,
                  seconds: 5,
                }).then(() => { toastOk("produce started"); refresh(); })
                  .catch((e) => toastError(String(e)));
              }}
            >
              Produce (~${estTotal.toFixed(2)})
            </button>
            <span className="mono muted" style={{ fontSize: "0.72rem" }}>
              {imgNeeded > 0 ? `${imgNeeded} images` : "images done"}
              {" + "}
              {clipsNeeded > 0 ? `${clipsNeeded} clips` : "clips done"}
            </span>
          </div>
        );
      })()}

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

      <div className="tab-bar">
        <button
          className={activeTab === "scenes" ? "active" : ""}
          onClick={() => setActiveTab("scenes")}
        >
          Scenes ({proj.scenes.length})
        </button>
        <button
          className={activeTab === "clips" ? "active" : ""}
          onClick={() => setActiveTab("clips")}
        >
          Clips ({proj.clips.length})
        </button>
        <button
          className={activeTab === "sequence" ? "active" : ""}
          onClick={() => setActiveTab("sequence")}
        >
          Sequence ({proj.sequence.length})
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
        {proj.concept && (
          <button className="ghost" onClick={() => shotList.mutate()} disabled={busy || shotList.isPending}>
            {shotList.isPending ? "generating…" : "shot list"}
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
        <button className="ghost" onClick={() => setPromptLibOpen(!promptLibOpen)}>
          {promptLibOpen ? "close prompts" : "prompt library"}
        </button>
      </div>

      {promptLibOpen && (
        <PromptLibrary prof={prof} />
      )}

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

      {shotListResults && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Shot list ({shotListResults.length} shots)</b>
            <button className="ghost" onClick={() => setShotListResults(null)}>dismiss</button>
          </div>
          <p className="muted">Review, edit, reorder, or remove shots. Click "apply" to create scenes.</p>
          {shotListResults.map((shot, i) => (
            <div key={i} className="card" style={{ marginBottom: 8, padding: "8px 12px" }}>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                <div className="row" style={{ gap: 6, alignItems: "center" }}>
                  <span style={{
                    fontSize: 11, fontWeight: 600, textTransform: "uppercase",
                    padding: "1px 6px", borderRadius: 4,
                    background: "var(--surface, #333)", color: "var(--fg, #eee)",
                  }}>
                    {shot.shot_type}
                  </span>
                  {i > 0 && (
                    <button className="ghost" style={{ fontSize: 11, padding: "0 4px" }}
                      onClick={() => {
                        const next = [...shotListResults];
                        [next[i - 1], next[i]] = [next[i], next[i - 1]];
                        setShotListResults(next);
                      }}>↑</button>
                  )}
                  {i < shotListResults.length - 1 && (
                    <button className="ghost" style={{ fontSize: 11, padding: "0 4px" }}
                      onClick={() => {
                        const next = [...shotListResults];
                        [next[i], next[i + 1]] = [next[i + 1], next[i]];
                        setShotListResults(next);
                      }}>↓</button>
                  )}
                </div>
                <button
                  className="ghost"
                  style={{ color: "var(--red, #c44)" }}
                  onClick={() => setShotListResults(shotListResults.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </div>
              <input
                value={shot.description}
                onChange={(e) => {
                  const next = [...shotListResults];
                  next[i] = { ...next[i], description: e.target.value };
                  setShotListResults(next);
                }}
                style={{ width: "100%", marginBottom: 4 }}
                placeholder="Description"
              />
              <div className="row" style={{ gap: 8 }}>
                <input
                  value={shot.composition}
                  onChange={(e) => {
                    const next = [...shotListResults];
                    next[i] = { ...next[i], composition: e.target.value };
                    setShotListResults(next);
                  }}
                  style={{ flex: 1 }}
                  placeholder="Composition"
                />
                <select
                  value={shot.shot_type}
                  onChange={(e) => {
                    const next = [...shotListResults];
                    next[i] = { ...next[i], shot_type: e.target.value };
                    setShotListResults(next);
                  }}
                  style={{ width: 120 }}
                >
                  {["hero", "detail", "transition", "broll", "wide", "overhead"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            </div>
          ))}
          <div className="row" style={{ marginTop: 10 }}>
            <button
              onClick={() => applyShotList.mutate(shotListResults.filter((s) => s.description.trim()))}
              disabled={applyShotList.isPending}
            >
              apply {shotListResults.filter((s) => s.description.trim()).length} shots
            </button>
            <button className="ghost" onClick={() => setShotListResults(null)}>cancel</button>
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
        <EmptyState
          title="Add your first scene"
          description="Each scene is a visual moment. Add reference images (garment photos, props), write a description, and generate AI images."
          action="+ scene"
          onAction={() => setAddingScene(true)}
        />
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
        {(() => {
          const completedSources = new Set(
            proj.clips.filter((c) => c.status === "completed").flatMap((c) => c.source_images)
          );
          const eligible = proj.scenes.filter(
            (s) => s.selected_image !== null && s.images[s.selected_image!] &&
              !completedSources.has(s.images[s.selected_image!].file)
          );
          const batchCost = eligible.length * vidPrice;
          return eligible.length > 0 ? (
            <button
              onClick={() => {
                if (!window.confirm(
                  `Create and generate clips for ${eligible.length} scene(s). ` +
                  `Estimated cost: ~$${batchCost.toFixed(2)}. Continue?`
                )) return;
                api.generateAllClipsBatch(prof, slug, {
                  model: proj.settings.video_model,
                  seconds: 5,
                }).then(() => { toastOk("batch clip generation started"); refresh(); })
                  .catch((e) => toastError(String(e)));
              }}
              disabled={busy}
            >
              Generate clips for {eligible.length} scenes (~${batchCost.toFixed(2)})
            </button>
          ) : null;
        })()}
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
          {clip.status === "completed" && (
            <ClipAudioSection prof={prof} slug={slug} clip={clip} refresh={refresh} />
          )}
        </div>
      ))}
      </>}

      {activeTab === "sequence" && <>
      <SequenceTab prof={prof} slug={slug} project={proj} refresh={refresh} busy={!!busy} />
      </>}
    </>
  );
}

function ClipAudioSection({ prof, slug, clip, refresh }: {
  prof: string; slug: string; clip: { id: string; audio_file?: string; audio_type?: string }; refresh: () => void;
}) {
  const [audioType, setAudioType] = useState(clip.audio_type || "ambient");
  const fileRef = useRef<HTMLInputElement>(null);

  const hasAudio = !!clip.audio_file;

  const handleUpload = async (file: File) => {
    const form = new FormData();
    form.set("file", file);
    form.set("audio_type", audioType);
    try {
      await api.addClipAudio(prof, slug, clip.id, form);
      toastOk("Audio attached");
      refresh();
    } catch (e) {
      toastError(String(e));
    }
  };

  const handleMerge = async () => {
    try {
      await api.mergeClipAudio(prof, slug, clip.id);
      toastOk("Audio merged into clip");
      refresh();
    } catch (e) {
      toastError(String(e));
    }
  };

  const handleRemove = async () => {
    try {
      await api.removeClipAudio(prof, slug, clip.id);
      toastOk("Audio removed");
      refresh();
    } catch (e) {
      toastError(String(e));
    }
  };

  return (
    <div style={{ padding: "6px 16px 0", fontSize: "0.78rem" }}>
      <div className="row" style={{ gap: 6 }}>
        {hasAudio ? (
          <>
            <span className="pill" style={{ fontSize: "0.7rem" }}>
              {clip.audio_type}: {clip.audio_file?.split("/").pop()}
            </span>
            <button className="ghost" style={{ fontSize: "0.72rem" }} onClick={handleMerge}>
              Merge into clip
            </button>
            <button className="ghost" style={{ fontSize: "0.72rem", color: "var(--danger, #c44)" }} onClick={handleRemove}>
              Remove audio
            </button>
          </>
        ) : (
          <>
            <select value={audioType} onChange={(e) => setAudioType(e.target.value)} style={{ fontSize: "0.72rem" }}>
              <option value="ambient">Ambient</option>
              <option value="music">Music</option>
              <option value="voiceover">Voiceover</option>
            </select>
            <button className="ghost" style={{ fontSize: "0.72rem" }} onClick={() => fileRef.current?.click()}>
              Add audio
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*,.mp3,.wav,.m4a,.mp4"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}


function PromptLibrary({ prof }: { prof: string }) {
  const [filterTag, setFilterTag] = useState("");
  const [newText, setNewText] = useState("");
  const [newTags, setNewTags] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const promptsQuery = useQuery({
    queryKey: ["prompts", prof, filterTag],
    queryFn: () => api.prompts(prof, filterTag || undefined),
  });
  const prompts = promptsQuery.data ?? [];

  const allTags = [...new Set(prompts.flatMap((p) => p.tags))].sort();

  const savePrompt = useMutation({
    mutationFn: () =>
      api.savePrompt(prof, {
        text: newText.trim(),
        tags: newTags.split(",").map((t) => t.trim()).filter(Boolean),
        model: "",
      }),
    onSuccess: () => {
      toastOk("Prompt saved");
      setNewText("");
      setNewTags("");
      promptsQuery.refetch();
    },
    onError: (e) => toastError(String(e)),
  });

  const deletePrompt = useMutation({
    mutationFn: (pid: string) => api.deletePrompt(prof, pid),
    onSuccess: () => { toastOk("Deleted"); promptsQuery.refetch(); },
    onError: (e) => toastError(String(e)),
  });

  const usePrompt = async (pid: string) => {
    try {
      const result = await api.usePrompt(prof, pid);
      await navigator.clipboard.writeText(result.text);
      setCopied(pid);
      setTimeout(() => setCopied(null), 2000);
      toastOk("Copied to clipboard — paste into scene description");
      promptsQuery.refetch();
    } catch (e) {
      toastError(String(e));
    }
  };

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <b>Prompt Library</b>
        {allTags.length > 0 && (
          <select value={filterTag} onChange={(e) => setFilterTag(e.target.value)}>
            <option value="">All tags</option>
            {allTags.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
      </div>

      {prompts.length === 0 && (
        <p className="muted" style={{ fontSize: "0.82rem" }}>
          No saved prompts yet. Save prompts you want to reuse.
        </p>
      )}

      {prompts.map((prompt) => (
        <div key={prompt.id} className="card" style={{ padding: "8px 12px", marginBottom: 8 }}>
          <p style={{ margin: "0 0 6px", fontSize: "0.85rem" }}>{prompt.text}</p>
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            {prompt.tags.map((t) => (
              <span key={t} className="pill" style={{ fontSize: "0.72rem" }}>{t}</span>
            ))}
            <span className="mono muted" style={{ fontSize: "0.72rem", marginLeft: "auto" }}>
              used {prompt.times_used}x
            </span>
            <button
              className="ghost"
              style={{ fontSize: "0.78rem" }}
              onClick={() => usePrompt(prompt.id)}
            >
              {copied === prompt.id ? "Copied!" : "Use"}
            </button>
            <button
              className="ghost"
              style={{ fontSize: "0.78rem", color: "var(--danger, #c44)" }}
              onClick={() => deletePrompt.mutate(prompt.id)}
            >
              x
            </button>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
        <input
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          placeholder="Prompt text..."
          style={{ width: "100%", marginBottom: 6 }}
        />
        <div className="row" style={{ gap: 8 }}>
          <input
            value={newTags}
            onChange={(e) => setNewTags(e.target.value)}
            placeholder="Tags (comma-separated)"
            style={{ flex: 1 }}
          />
          <button
            onClick={() => savePrompt.mutate()}
            disabled={!newText.trim() || savePrompt.isPending}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}


function SequenceTab({ prof, slug, project, refresh, busy }: {
  prof: string; slug: string; project: Project; refresh: () => void; busy: boolean;
}) {
  const [localSeq, setLocalSeq] = useState<string[]>(project.sequence);
  const [rendering, setRendering] = useState(false);
  const [exporting, setExporting] = useState(false);
  const seqQuery = useQuery({
    queryKey: ["sequence", prof, slug],
    queryFn: () => api.getSequence(prof, slug),
  });
  const platformsQuery = useQuery({
    queryKey: ["platforms"],
    queryFn: () => api.platforms(),
  });

  useEffect(() => {
    setLocalSeq(project.sequence);
  }, [project.sequence]);

  const completedClips = project.clips.filter((c) => c.status === "completed");
  const clipsById = Object.fromEntries(completedClips.map((c) => [c.id, c]));
  const inSequence = new Set(localSeq);
  const available = completedClips.filter((c) => !inSequence.has(c.id));

  const saveSeq = useMutation({
    mutationFn: (ids: string[]) => api.setSequence(prof, slug, ids),
    onSuccess: () => { toastOk("sequence saved"); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  const doRender = useMutation({
    mutationFn: () => api.renderSequence(prof, slug),
    onSuccess: () => { toastOk("rendering started"); setRendering(true); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  const moveItem = (index: number, dir: -1 | 1) => {
    const next = [...localSeq];
    const j = index + dir;
    [next[index], next[j]] = [next[j], next[index]];
    setLocalSeq(next);
    saveSeq.mutate(next);
  };

  const addToSequence = (clipId: string) => {
    const next = [...localSeq, clipId];
    setLocalSeq(next);
    saveSeq.mutate(next);
  };

  const removeFromSequence = (index: number) => {
    const next = localSeq.filter((_, i) => i !== index);
    setLocalSeq(next);
    saveSeq.mutate(next);
  };

  const handlePlatformExport = async (platform: string) => {
    setExporting(true);
    try {
      await exportForPlatform(prof, slug, platform);
      toastOk(`exported for ${platform}`);
    } catch (e) {
      toastError(String(e));
    } finally {
      setExporting(false);
    }
  };

  const totalDuration = localSeq.reduce((sum, cid) => {
    const clip = clipsById[cid];
    return sum + (clip?.duration_s ?? 0);
  }, 0);

  return (
    <>
      <div className="row" style={{ marginBottom: 10, justifyContent: "space-between" }}>
        <span className="mono muted">
          {localSeq.length} clip{localSeq.length !== 1 ? "s" : ""} · {totalDuration.toFixed(1)}s total
        </span>
        <div className="row" style={{ gap: 8 }}>
          <button
            onClick={() => doRender.mutate()}
            disabled={busy || doRender.isPending || localSeq.length === 0}
          >
            Render sequence
          </button>
          <select
            value=""
            disabled={exporting || busy}
            onChange={(e) => {
              if (e.target.value) handlePlatformExport(e.target.value);
            }}
            style={{ minWidth: 140 }}
          >
            <option value="">{exporting ? "Exporting..." : "Export for..."}</option>
            {Object.entries(platformsQuery.data ?? {}).map(([key, spec]) => (
              <option key={key} value={key}>
                {spec.label} ({spec.width}x{spec.height}, {spec.max_duration}s max)
              </option>
            ))}
          </select>
        </div>
      </div>

      {localSeq.length === 0 && (
        <p className="muted">
          No clips in sequence yet. Add completed clips from below.
        </p>
      )}

      {localSeq.map((cid, idx) => {
        const clip = clipsById[cid];
        if (!clip) return null;
        return (
          <div key={`${cid}-${idx}`} className="card" style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 12px" }}>
            <span className="mono" style={{ width: 24, textAlign: "center", fontSize: "0.85rem", color: "var(--taupe)" }}>
              {idx + 1}
            </span>
            {clip.file && (
              <video
                preload="metadata"
                src={media(prof, slug, clip.file)}
                style={{ width: 100, borderRadius: 6, border: "1px solid var(--line)" }}
              />
            )}
            <div style={{ flex: 1 }}>
              <div className="row" style={{ marginBottom: 4 }}>
                <b>{clip.id}</b>
                <span className="pill">{clip.model}</span>
                {clip.duration_s && <span className="mono muted" style={{ fontSize: "0.72rem" }}>{clip.duration_s.toFixed(1)}s</span>}
                {clip.kept && <span className="pill gold">kept</span>}
              </div>
              {clip.prompt && <p className="muted" style={{ margin: 0, fontSize: "0.78rem" }}>{clip.prompt}</p>}
            </div>
            <div className="row" style={{ gap: 4 }}>
              {idx > 0 && (
                <button className="ghost" onClick={() => moveItem(idx, -1)} title="move up">^</button>
              )}
              {idx < localSeq.length - 1 && (
                <button className="ghost" onClick={() => moveItem(idx, 1)} title="move down">v</button>
              )}
              <button
                className="ghost"
                style={{ color: "var(--danger, #c44)" }}
                onClick={() => removeFromSequence(idx)}
                title="remove from sequence"
              >
                x
              </button>
            </div>
          </div>
        );
      })}

      {available.length > 0 && (
        <>
          <h3 style={{ marginTop: 16 }}>Available clips</h3>
          {available.map((clip) => (
            <div key={clip.id} className="card" style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 12px", opacity: 0.8 }}>
              {clip.file && (
                <video
                  preload="metadata"
                  src={media(prof, slug, clip.file)}
                  style={{ width: 80, borderRadius: 6, border: "1px solid var(--line)" }}
                />
              )}
              <div style={{ flex: 1 }}>
                <div className="row" style={{ marginBottom: 4 }}>
                  <b>{clip.id}</b>
                  <span className="pill">{clip.model}</span>
                  {clip.duration_s && <span className="mono muted" style={{ fontSize: "0.72rem" }}>{clip.duration_s.toFixed(1)}s</span>}
                  {clip.kept && <span className="pill gold">kept</span>}
                </div>
              </div>
              <button className="ghost" onClick={() => addToSequence(clip.id)}>
                + add
              </button>
            </div>
          ))}
        </>
      )}

      <CaptionSection prof={prof} slug={slug} project={project} refresh={refresh} busy={busy} />
      <LinkCardSection prof={prof} slug={slug} project={project} busy={busy} />
    </>
  );
}


function LinkCardSection({ prof, slug, project, busy }: {
  prof: string; slug: string; project: Project; busy: boolean;
}) {
  const [generating, setGenerating] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [linksCopied, setLinksCopied] = useState(false);

  const hasProductRefs = project.scenes.some((s) => s.refs.some((r) => r.url));

  const handleGenerateCard = async () => {
    setGenerating(true);
    try {
      await api.generateLinkCard(prof, slug);
      toastOk("Link card downloaded");
      setShowPreview(true);
    } catch (e) {
      toastError(String(e));
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyLinks = async () => {
    try {
      const text = await api.getLinksText(prof, slug);
      await navigator.clipboard.writeText(text);
      setLinksCopied(true);
      setTimeout(() => setLinksCopied(false), 2000);
    } catch (e) {
      toastError(String(e));
    }
  };

  const handleDownloadOverlay = async () => {
    try {
      await api.generateLinksOverlay(prof, slug);
      toastOk("Links overlay downloaded");
    } catch (e) {
      toastError(String(e));
    }
  };

  if (!hasProductRefs) return null;

  return (
    <>
      <h3 style={{ marginTop: 24 }}>Shop Links</h3>
      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <button
          onClick={handleGenerateCard}
          disabled={busy || generating}
        >
          {generating ? "Generating..." : "Generate link card"}
        </button>
        <button className="ghost" onClick={handleCopyLinks}>
          {linksCopied ? "Copied!" : "Copy link list"}
        </button>
        <button className="ghost" onClick={handleDownloadOverlay}>
          Download overlay (.srt)
        </button>
      </div>
      {showPreview && (
        <div className="card" style={{ padding: 12 }}>
          <img
            src={api.getLinkCardPreview(prof, slug)}
            alt="Link card preview"
            style={{ maxWidth: "100%", borderRadius: 6 }}
            onError={() => setShowPreview(false)}
          />
        </div>
      )}
    </>
  );
}


function CaptionSection({ prof, slug, project, refresh, busy }: {
  prof: string; slug: string; project: Project; refresh: () => void; busy: boolean;
}) {
  const [platform, setPlatform] = useState("instagram");
  const [tone, setTone] = useState("playful");
  const [editedCaption, setEditedCaption] = useState("");
  const [editedHashtags, setEditedHashtags] = useState<string[]>([]);
  const [editedCta, setEditedCta] = useState("");
  const [activePlatform, setActivePlatform] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const captions = project.captions ?? {};
  const platforms = ["instagram", "tiktok", "youtube", "pinterest"];
  const tones = ["playful", "professional", "casual", "minimal"];

  // Sync local state when a caption is loaded or generated
  useEffect(() => {
    if (activePlatform && captions[activePlatform]) {
      const c = captions[activePlatform];
      setEditedCaption(c.caption);
      setEditedHashtags(c.hashtags);
      setEditedCta(c.cta);
    }
  }, [activePlatform, captions]);

  // Show first available caption on mount
  useEffect(() => {
    if (!activePlatform) {
      const first = Object.keys(captions)[0];
      if (first) setActivePlatform(first);
    }
  }, [captions, activePlatform]);

  const generate = useMutation({
    mutationFn: () => api.generateCaption(prof, slug, { platform, tone }),
    onSuccess: (data) => {
      toastOk(`${platform} caption generated`);
      setActivePlatform(platform);
      setEditedCaption(data.caption);
      setEditedHashtags(data.hashtags);
      setEditedCta(data.cta);
      refresh();
    },
    onError: (e) => toastError(String(e)),
  });

  const deleteCaption = useMutation({
    mutationFn: (p: string) => api.deleteCaption(prof, slug, p),
    onSuccess: (_data, p) => {
      toastOk(`${p} caption deleted`);
      if (activePlatform === p) {
        setActivePlatform(null);
        setEditedCaption("");
        setEditedHashtags([]);
        setEditedCta("");
      }
      refresh();
    },
    onError: (e) => toastError(String(e)),
  });

  const removeHashtag = (index: number) => {
    setEditedHashtags((prev) => prev.filter((_, i) => i !== index));
  };

  const copyToClipboard = async () => {
    const hashtags = editedHashtags.map((h) => `#${h}`).join(" ");
    const text = [editedCaption, "", hashtags, editedCta ? `\n${editedCta}` : ""]
      .filter(Boolean)
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toastError("Failed to copy");
    }
  };

  return (
    <>
      <h3 style={{ marginTop: 24 }}>Caption</h3>

      <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
          {platforms.map((p) => (
            <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
          ))}
        </select>
        <select value={tone} onChange={(e) => setTone(e.target.value)}>
          {tones.map((t) => (
            <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
          ))}
        </select>
        <button
          onClick={() => generate.mutate()}
          disabled={busy || generate.isPending || !project.concept}
          title={!project.concept ? "Set a concept first" : ""}
        >
          {generate.isPending ? "Generating..." : "Generate caption"}
        </button>
      </div>

      {Object.keys(captions).length > 0 && (
        <div className="row" style={{ gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          {Object.keys(captions).map((p) => (
            <button
              key={p}
              className={activePlatform === p ? "btn" : "ghost"}
              onClick={() => setActivePlatform(p)}
              style={{ fontSize: "0.82rem" }}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      )}

      {activePlatform && captions[activePlatform] && (
        <div className="card" style={{ padding: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <b style={{ textTransform: "capitalize" }}>{activePlatform}</b>
            <div className="row" style={{ gap: 6 }}>
              <button
                className="ghost"
                onClick={copyToClipboard}
                style={{ fontSize: "0.82rem" }}
              >
                {copied ? "Copied!" : "Copy to clipboard"}
              </button>
              <button
                className="ghost"
                style={{ color: "var(--danger, #c44)", fontSize: "0.82rem" }}
                onClick={() => deleteCaption.mutate(activePlatform)}
              >
                Delete
              </button>
            </div>
          </div>

          <textarea
            value={editedCaption}
            onChange={(e) => setEditedCaption(e.target.value)}
            rows={4}
            style={{ width: "100%", resize: "vertical", marginBottom: 8 }}
          />

          <div style={{ marginBottom: 8 }}>
            <span className="muted" style={{ fontSize: "0.78rem", marginBottom: 4, display: "block" }}>
              Hashtags
            </span>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {editedHashtags.map((tag, i) => (
                <span
                  key={`${tag}-${i}`}
                  className="pill"
                  style={{ cursor: "pointer" }}
                  onClick={() => removeHashtag(i)}
                  title="Click to remove"
                >
                  #{tag} x
                </span>
              ))}
            </div>
          </div>

          {editedCta && (
            <div>
              <span className="muted" style={{ fontSize: "0.78rem", marginBottom: 4, display: "block" }}>
                CTA
              </span>
              <input
                type="text"
                value={editedCta}
                onChange={(e) => setEditedCta(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>
          )}
        </div>
      )}
    </>
  );
}
