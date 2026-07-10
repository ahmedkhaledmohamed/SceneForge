import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, media } from "../api";
import JobBanner from "../components/JobBanner";
import Lightbox from "../components/Lightbox";
import { toastError, toastOk } from "../components/toast";
import { useInvalidateProject, useModels, useProject } from "../hooks";
import type { Character, Outfit, Project, Scene } from "../types";

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

function OutfitCard({ prof, slug, outfit, allChars, busy, refresh }: {
  prof: string; slug: string; outfit: Outfit; allChars: Character[];
  busy: boolean; refresh: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);

  const addItem = useMutation({
    mutationFn: (form: FormData) => api.addItem(prof, slug, outfit.id, form),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const deleteItem = useMutation({
    mutationFn: (index: number) => api.deleteItem(prof, slug, outfit.id, index),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const deleteOutfit = useMutation({
    mutationFn: () => api.deleteOutfit(prof, slug, outfit.id),
    onSuccess: () => { toastOk("outfit deleted"); refresh(); },
    onError: (e) => toastError(String(e)),
  });
  const processOutfit = useMutation({
    mutationFn: () => {
      const charId = allChars.find((c) => c.main)?.id ?? allChars[0]?.id;
      return api.processOutfit(prof, slug, outfit.id, { character_id: charId });
    },
    onSuccess: () => { toastOk("processing outfit — scenes + images"); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>{outfit.name}</b>
        <div className="row">
          <button
            className="ghost"
            onClick={async () => {
              const text = await api.links(prof, slug, outfit.id);
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? "copied" : "copy links"}
          </button>
          <button
            className="ghost"
            onClick={() => processOutfit.mutate()}
            disabled={busy || processOutfit.isPending}
          >
            {outfit.items.length > 0 ? "process" : "needs items"}
          </button>
          <button
            className="ghost"
            style={{ color: "var(--red, #c44)" }}
            onClick={() => { if (confirm(`Delete outfit "${outfit.name}"?`)) deleteOutfit.mutate(); }}
          >
            delete
          </button>
        </div>
      </div>
      {outfit.items.map((item, i) => (
        <div className="item-row" key={i}>
          {item.image && <img src={media(prof, slug, item.image)} alt="" />}
          {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.name}</a> : <span>{item.name}</span>}
          <button
            className="ghost"
            style={{ marginLeft: "auto", fontSize: "0.8rem", color: "var(--red, #c44)" }}
            onClick={() => deleteItem.mutate(i)}
            title="remove item"
          >
            ×
          </button>
        </div>
      ))}
      <form
        className="row"
        style={{ marginTop: 10 }}
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          const file = fileRef.current?.files?.[0];
          if (file) form.set("image", file);
          addItem.mutate(form);
          e.currentTarget.reset();
        }}
      >
        <input name="name" placeholder="item name" required style={{ width: 140 }} />
        <input name="url" placeholder="shop URL" style={{ width: 170 }} />
        <input ref={fileRef} type="file" accept="image/*" className="mono" style={{ width: 180 }} />
        <button className="ghost" disabled={addItem.isPending}>add item</button>
      </form>
    </div>
  );
}

function SettingsDialog({ prof, slug, project, onClose, refresh }: {
  prof: string; slug: string; project: Project; onClose: () => void; refresh: () => void;
}) {
  const [imageModel, setImageModel] = useState(project.settings.image_model);
  const [videoModel, setVideoModel] = useState(project.settings.video_model);
  const [options, setOptions] = useState(project.settings.image_options);
  const [anchor, setAnchor] = useState(project.style.anchor);

  const save = useMutation({
    mutationFn: () =>
      api.patchProject(prof, slug, {
        image_model: imageModel,
        video_model: videoModel,
        image_options: options,
        anchor,
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
    <dialog open>
      <h2 style={{ marginTop: 0 }}>Refine {scene.id}</h2>
      <label>Scene description</label>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        style={{ width: "100%" }}
      />
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

function SceneCard({ prof, slug, scene, project, refresh, busy }: {
  prof: string; slug: string; scene: Scene; project: Project; refresh: () => void; busy: boolean;
}) {
  const [refineOpen, setRefineOpen] = useState(false);
  const [viewing, setViewing] = useState<number | null>(null);
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

  const completedTakes = scene.clips.filter((c) => c.status === "completed").length;
  const viewingImage = viewing !== null ? scene.images[viewing] : null;

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <b>{scene.id}</b> — {scene.description}
          <div className="muted mono">
            {[scene.outfit_id, scene.character_id, scene.pose].filter(Boolean).join(" · ")}
          </div>
        </div>
        <div className="row">
          <button className="ghost" onClick={() => setRefineOpen(true)}>
            refine…
          </button>
          <Link to={`/${prof}/p/${slug}/scenes/${scene.id}/takes`}>
            <button className="ghost">
              takes{completedTakes > 0 ? ` (${completedTakes})` : ""}
            </button>
          </Link>
          <input
            ref={imgImportRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importImg.mutate(file);
              e.target.value = "";
            }}
          />
          <button className="ghost" onClick={() => imgImportRef.current?.click()}>
            import
          </button>
          <button
            className="ghost"
            style={{ color: "var(--red, #c44)" }}
            onClick={() => { if (confirm(`Delete ${scene.id}?`)) deleteScene.mutate(); }}
          >
            ×
          </button>
        </div>
      </div>

      <div className="gallery">
        {scene.images.length === 0 && (
          <span className="muted">
            no images yet — use "refine…" or the generate button above
          </span>
        )}
        {scene.images.map((img, i) => (
          <div
            key={i}
            className={`thumb${scene.selected_image === i ? " selected" : ""}${busy ? " busy" : ""}`}
            onClick={() => setViewing(i)}
            role="button"
            tabIndex={0}
            title="view full size"
          >
            <img src={media(prof, slug, img.file)} alt={`option ${i + 1}`} loading="lazy" />
            <div className="cap">
              {scene.selected_image === i ? "✓ " : ""}opt {i + 1} · {img.model}
            </div>
          </div>
        ))}
      </div>

      {viewingImage && viewing !== null && (
        <Lightbox
          src={media(prof, slug, viewingImage.file)}
          caption={`opt ${viewing + 1} · ${viewingImage.model}`}
          onClose={() => setViewing(null)}
          actions={
            <button
              onClick={() => { select.mutate(viewing); setViewing(null); }}
            >
              {scene.selected_image === viewing ? "✓ selected" : "select this"}
            </button>
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
  const { data: project, isLoading, error } = useProject(prof, slug);
  const refresh = useInvalidateProject(prof, slug);
  const navigate = useNavigate();
  const [imageModel, setImageModel] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);
  const [addingScene, setAddingScene] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sceneCharacter, setSceneCharacter] = useState("");
  const [brainstormResults, setBrainstormResults] = useState<string[] | null>(null);

  const generateAll = useMutation({
    mutationFn: () =>
      api.generateImages(prof, slug, {
        model: imageModel ?? project?.settings.image_model,
        options: project?.settings.image_options,
      }),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const addOutfit = useMutation({
    mutationFn: (name: string) => api.addOutfit(prof, slug, name),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const outfitScenes = useMutation({
    mutationFn: ({ outfitId, characterId }: { outfitId: string; characterId?: string }) =>
      api.scenesFromOutfit(prof, slug, {
        outfit_id: outfitId,
        character_id: characterId || undefined,
      }),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const addCharacter = useMutation({
    mutationFn: (form: FormData) => api.addCharacter(prof, slug, form),
    onSuccess: () => { toastOk("character added"); refresh(); },
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
  const takesAll = useMutation({
    mutationFn: () => api.generateTakesAll(prof, slug, {
      model: project?.settings.video_model,
      count: 2,
    }),
    onSuccess: () => { toastOk("generating takes for all scenes"); refresh(); },
    onError: (e) => toastError(String(e)),
  });

  if (isLoading) return <p className="muted">Loading…</p>;
  if (error || !project) return <p className="muted">{String(error ?? "not found")}</p>;

  const { data: models } = useModels();
  const busy = project.job?.status === "running";
  const keptCount = project.scenes.flatMap((s) => s.clips).filter((c) => c.kept).length;
  const allClipsReady = project.scenes.length > 0 &&
    project.scenes.every((s) => s.clips.some((c) => c.status === "completed"));
  const allChars = [...project.profile_characters, ...project.characters];
  const defaultChar = allChars.find((c) => c.main)?.id ?? allChars[0]?.id ?? "";
  const selectedCount = project.scenes.filter((s) => s.selected_image !== null).length;
  const imgModelKey = imageModel ?? project.settings.image_model;
  const imgPrice = models?.[imgModelKey]?.price ?? 0;
  const imagesNeeded = project.scenes.reduce((sum, s) =>
    sum + Math.max(0, project.settings.image_options - s.images.length), 0);
  const imgCost = imagesNeeded * imgPrice;
  const vidPrice = models?.[project.settings.video_model]?.price ?? 0;
  const takesCost = selectedCount * 2 * vidPrice;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>{project.name}</h1>
        <div className="row">
          <button className="ghost" onClick={() => setSettingsOpen(true)}>settings</button>
          <button className="ghost" onClick={() => duplicateProject.mutate()}>duplicate</button>
          <button
            className="ghost"
            style={{ color: "var(--red, #c44)" }}
            onClick={() => {
              if (confirm(`Delete project "${project.name}" and all its files?`))
                deleteProject.mutate();
            }}
          >
            delete project
          </button>
        </div>
      </div>
      <p className="muted">
        {project.concept} · <span className="mono">{project.style.anchor}</span>
        {project.spent_usd > 0 && <> · <span className="mono">${project.spent_usd.toFixed(2)} GPU spend</span></>}
      </p>
      <JobBanner job={project.job} />

      {settingsOpen && (
        <SettingsDialog
          prof={prof}
          slug={slug}
          project={project}
          onClose={() => setSettingsOpen(false)}
          refresh={refresh}
        />
      )}

      <div className="row">
        <ModelPicker
          kind="image"
          value={imageModel ?? project.settings.image_model}
          onChange={setImageModel}
        />
        <button onClick={() => generateAll.mutate()} disabled={busy || imagesNeeded === 0}>
          Generate {imagesNeeded} images{imgCost > 0 ? ` (~$${imgCost.toFixed(2)})` : ""}
        </button>
        <button className="ghost" onClick={() => setAddingScene(true)}>+ scene</button>
        {project.concept && (
          <button className="ghost" onClick={() => brainstorm.mutate()} disabled={busy || brainstorm.isPending}>
            {brainstorm.isPending ? "thinking…" : "brainstorm scenes"}
          </button>
        )}
        <button
          className="ghost"
          onClick={() => {
            const name = prompt("Outfit name?");
            if (name) addOutfit.mutate(name);
          }}
        >
          + outfit
        </button>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            addCharacter.mutate(form);
            e.currentTarget.reset();
          }}
        >
          <input name="name" placeholder="character name" style={{ width: 130 }} />
          <input name="files" type="file" accept="image/*" multiple className="mono" style={{ width: 170 }} />
          <button className="ghost" disabled={addCharacter.isPending}>+ character</button>
        </form>
      </div>

      <div className="row" style={{ marginTop: 8 }}>
        <button className="ghost" onClick={() => takesAll.mutate()} disabled={busy || selectedCount === 0}>
          generate takes ({selectedCount} scenes{takesCost > 0 ? `, ~$${takesCost.toFixed(2)}` : ""})
        </button>
        <button className="ghost" onClick={() => runStitch.mutate()} disabled={busy || !allClipsReady}>
          stitch final video
        </button>
        <button className="ghost" onClick={() => runExport.mutate()} disabled={keptCount === 0}>
          export {keptCount > 0 ? `${keptCount} kept` : ""}
        </button>
        {exported && (
          <span className="mono muted">
            → {exported} · <a href={`${(import.meta.env.VITE_API_BASE ?? "/api")}/profiles/${prof}/projects/${slug}/export.zip`}>download zip</a>
          </span>
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

      {addingScene && (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            const description = String(data.get("description") ?? "").trim();
            if (!description) return;
            addScene.mutate({
              description,
              pose: String(data.get("pose") ?? "") || undefined,
              character_id: sceneCharacter || undefined,
            });
          }}
        >
          <label>Scene description</label>
          <input name="description" required style={{ width: "100%" }}
                 placeholder="a single visual moment, describable in one image" />
          <label>Pose / framing (optional)</label>
          <input name="pose" style={{ width: "100%" }} />
          {allChars.length > 0 && (
            <>
              <label>Character</label>
              <CharacterPicker characters={allChars} value={sceneCharacter} onChange={setSceneCharacter} />
            </>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <button type="submit" disabled={addScene.isPending}>add scene</button>
            <button type="button" className="ghost" onClick={() => setAddingScene(false)}>cancel</button>
          </div>
        </form>
      )}

      {allChars.length > 0 && (
        <p className="muted mono" style={{ marginTop: 10 }}>
          characters: {allChars.map((c) =>
            `${c.main ? "★ " : ""}${c.name} (${c.id}, ${c.reference_images.length} refs)`
          ).join(" · ")}
        </p>
      )}

      {project.outfits.length > 0 && <h2>Outfits</h2>}
      {project.outfits.map((outfit) => (
        <div key={outfit.id}>
          <OutfitCard prof={prof} slug={slug} outfit={outfit} allChars={allChars} busy={!!busy} refresh={refresh} />
          {!project.scenes.some((s) => s.outfit_id === outfit.id) && (
            <div className="row" style={{ marginBottom: 14 }}>
              {allChars.length > 1 ? (
                <>
                  <CharacterPicker characters={allChars} value={defaultChar} onChange={() => {}} />
                  <button
                    className="ghost"
                    onClick={() => {
                      const charSelect = document.querySelector(`[data-outfit-char="${outfit.id}"]`) as HTMLSelectElement | null;
                      outfitScenes.mutate({
                        outfitId: outfit.id,
                        characterId: charSelect?.value || defaultChar,
                      });
                    }}
                  >
                    create pose scenes
                  </button>
                </>
              ) : (
                <button
                  className="ghost"
                  onClick={() => outfitScenes.mutate({
                    outfitId: outfit.id,
                    characterId: defaultChar || undefined,
                  })}
                >
                  create pose scenes for {outfit.name}
                  {defaultChar && ` (${allChars.find((c) => c.id === defaultChar)?.name})`}
                </button>
              )}
            </div>
          )}
        </div>
      ))}

      <h2>Scenes</h2>
      {project.scenes.length === 0 && (
        <p className="muted">No scenes yet — hit "+ scene", or add an outfit and create its pose scenes.</p>
      )}
      {project.scenes.map((scene) => (
        <SceneCard
          key={scene.id}
          prof={prof}
          slug={slug}
          scene={scene}
          project={project}
          refresh={refresh}
          busy={!!busy}
        />
      ))}
    </>
  );
}
