import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, media } from "../api";
import JobBanner from "../components/JobBanner";
import { useInvalidateProject, useModels, useProject } from "../hooks";
import type { Outfit, Project, Scene } from "../types";

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

function OutfitCard({ slug, outfit, refresh }: {
  slug: string; outfit: Outfit; refresh: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);

  const addItem = useMutation({
    mutationFn: (form: FormData) => api.addItem(slug, outfit.id, form),
    onSuccess: refresh,
  });

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>{outfit.name}</b>
        <button
          className="ghost"
          onClick={async () => {
            const text = await api.links(slug, outfit.id);
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "copied" : "copy shop links"}
        </button>
      </div>
      {outfit.items.map((item, i) => (
        <div className="item-row" key={i}>
          {item.image && <img src={media(slug, item.image)} alt="" />}
          {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.name}</a> : <span>{item.name}</span>}
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

function SceneCard({ slug, scene, project, refresh, busy }: {
  slug: string; scene: Scene; project: Project; refresh: () => void; busy: boolean;
}) {
  const [regenOpen, setRegenOpen] = useState(false);
  const [model, setModel] = useState(project.settings.image_model);
  const [pose, setPose] = useState(scene.pose ?? "");

  const select = useMutation({
    mutationFn: (index: number) => api.select(slug, scene.id, index),
    onSuccess: refresh,
  });
  const regen = useMutation({
    mutationFn: async () => {
      if (pose !== (scene.pose ?? "")) await api.patchScene(slug, scene.id, { pose });
      return api.regenerateImage(slug, scene.id, { model, options: 1 });
    },
    onSuccess: () => { setRegenOpen(false); refresh(); },
  });

  const completedTakes = scene.clips.filter((c) => c.status === "completed").length;

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
          <button className="ghost" onClick={() => setRegenOpen(true)} disabled={busy}>
            regenerate…
          </button>
          <Link to={`/p/${slug}/scenes/${scene.id}/takes`}>
            <button className="ghost">
              takes{completedTakes > 0 ? ` (${completedTakes})` : ""}
            </button>
          </Link>
        </div>
      </div>

      <div className="gallery">
        {scene.images.length === 0 && <span className="muted">no images yet</span>}
        {scene.images.map((img, i) => (
          <div
            key={i}
            className={`thumb${scene.selected_image === i ? " selected" : ""}`}
            onClick={() => select.mutate(i)}
            role="button"
            tabIndex={0}
            title={`${img.model} — click to select`}
          >
            <img src={media(slug, img.file)} alt={`option ${i + 1}`} loading="lazy" />
            <div className="cap">
              {scene.selected_image === i ? "✓ " : ""}opt {i + 1} · {img.model}
            </div>
          </div>
        ))}
      </div>

      {regenOpen && (
        <dialog open>
          <h2 style={{ marginTop: 0 }}>Regenerate {scene.id}</h2>
          <label>Pose / framing</label>
          <input value={pose} onChange={(e) => setPose(e.target.value)} style={{ width: "100%" }} />
          <label>Model</label>
          <ModelPicker kind="image" value={model} onChange={setModel} />
          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={() => regen.mutate()} disabled={regen.isPending}>
              generate 1 option
            </button>
            <button className="ghost" onClick={() => setRegenOpen(false)}>close</button>
          </div>
        </dialog>
      )}
    </div>
  );
}

export default function ProjectBoard() {
  const { slug = "" } = useParams();
  const { data: project, isLoading, error } = useProject(slug);
  const refresh = useInvalidateProject(slug);
  const [imageModel, setImageModel] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);

  const generateAll = useMutation({
    mutationFn: () =>
      api.generateImages(slug, {
        model: imageModel ?? project?.settings.image_model,
        options: project?.settings.image_options,
      }),
    onSuccess: refresh,
  });
  const addOutfit = useMutation({
    mutationFn: (name: string) => api.addOutfit(slug, name),
    onSuccess: refresh,
  });
  const outfitScenes = useMutation({
    mutationFn: (outfitId: string) => api.scenesFromOutfit(slug, { outfit_id: outfitId }),
    onSuccess: refresh,
  });
  const addCharacter = useMutation({
    mutationFn: (form: FormData) => api.addCharacter(slug, form),
    onSuccess: refresh,
  });
  const runExport = useMutation({
    mutationFn: () => api.export(slug),
    onSuccess: (result) => setExported(result.dir),
  });

  if (isLoading) return <p className="muted">Loading…</p>;
  if (error || !project) return <p className="muted">{String(error ?? "not found")}</p>;

  const busy = project.job?.status === "running";
  const keptCount = project.scenes.flatMap((s) => s.clips).filter((c) => c.kept).length;

  return (
    <>
      <h1>{project.name}</h1>
      <p className="muted">
        {project.concept} · <span className="mono">{project.style.anchor}</span>
        {project.spent_usd > 0 && <> · <span className="mono">${project.spent_usd.toFixed(2)} GPU spend</span></>}
      </p>
      <JobBanner job={project.job} />

      <div className="row">
        <ModelPicker
          kind="image"
          value={imageModel ?? project.settings.image_model}
          onChange={setImageModel}
        />
        <button onClick={() => generateAll.mutate()} disabled={busy}>
          Generate missing images
        </button>
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
        <button className="ghost" onClick={() => runExport.mutate()} disabled={keptCount === 0}>
          export {keptCount > 0 ? `${keptCount} kept` : ""}
        </button>
        {exported && (
          <span className="mono muted">
            → {exported} · <a href={`/api/projects/${slug}/export.zip`}>zip</a>
          </span>
        )}
      </div>

      {project.characters.length > 0 && (
        <p className="muted mono" style={{ marginTop: 10 }}>
          characters: {project.characters.map((c) => `${c.name} (${c.reference_images.length} refs)`).join(" · ")}
        </p>
      )}

      {project.outfits.length > 0 && <h2>Outfits</h2>}
      {project.outfits.map((outfit) => (
        <div key={outfit.id}>
          <OutfitCard slug={slug} outfit={outfit} refresh={refresh} />
          {!project.scenes.some((s) => s.outfit_id === outfit.id) && (
            <button
              className="ghost"
              style={{ marginBottom: 14 }}
              onClick={() => outfitScenes.mutate(outfit.id)}
            >
              create pose scenes for {outfit.name}
            </button>
          )}
        </div>
      ))}

      <h2>Scenes</h2>
      {project.scenes.length === 0 && (
        <p className="muted">No scenes yet — add an outfit and create its pose scenes, or add scenes via the CLI.</p>
      )}
      {project.scenes.map((scene) => (
        <SceneCard
          key={scene.id}
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
