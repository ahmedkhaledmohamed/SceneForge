import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, media } from "../api";
import JobBanner from "../components/JobBanner";
import { toastError } from "../components/toast";
import { useInvalidateProject, useModels, useProject } from "../hooks";

export default function TakeCompare() {
  const { slug = "", sid = "" } = useParams();
  const { data: project } = useProject(slug);
  const refresh = useInvalidateProject(slug);
  const { data: models } = useModels();
  const [model, setModel] = useState<string | null>(null);
  const [count, setCount] = useState(3);
  const [imageIndex, setImageIndex] = useState<number | null>(null);
  const [motion, setMotion] = useState("");

  const scene = project?.scenes.find((s) => s.id === sid);
  if (!project || !scene) return <p className="muted">Loading…</p>;

  const busy = project.job?.status === "running";
  const videoModel = model ?? project.settings.video_model;
  const price = models?.[videoModel]?.price ?? 0;
  const sourceIndex = imageIndex ?? scene.selected_image ?? 0;

  const generate = useMutation({
    mutationFn: () =>
      api.takes(slug, sid, {
        count,
        model: videoModel,
        image_index: sourceIndex,
        prompt_override: motion || undefined,
      }),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });
  const keep = useMutation({
    mutationFn: ({ index, kept }: { index: number; kept: boolean }) =>
      api.keep(slug, sid, index, kept),
    onSuccess: refresh,
    onError: (e) => toastError(String(e)),
  });

  return (
    <>
      <p><Link to={`/p/${slug}`}>← {project.name}</Link></p>
      <h1>{sid} takes</h1>
      <p className="muted">{scene.description}{scene.pose ? ` — ${scene.pose}` : ""}</p>
      <JobBanner job={project.job} />

      <div className="card">
        <div className="gallery">
          {scene.images.map((img, i) => (
            <div
              key={i}
              className={`thumb${sourceIndex === i ? " selected" : ""}`}
              onClick={() => setImageIndex(i)}
              role="button"
              title="animate this image"
            >
              <img src={media(slug, img.file)} alt={`option ${i + 1}`} />
              <div className="cap">source {i + 1}</div>
            </div>
          ))}
        </div>
        <div className="row">
          <select value={videoModel} onChange={(e) => setModel(e.target.value)}>
            {Object.entries(models ?? {})
              .filter(([, m]) => m.kind === "video")
              .map(([key, m]) => (
                <option key={key} value={key}>{key} (${m.price}/clip)</option>
              ))}
          </select>
          <input
            type="number" min={1} max={6} value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            style={{ width: 60 }}
          />
          <input
            placeholder="motion direction (optional prompt override)"
            value={motion}
            onChange={(e) => setMotion(e.target.value)}
            style={{ flex: 1, minWidth: 220 }}
          />
          <button onClick={() => generate.mutate()} disabled={busy}>
            generate {count} takes (~${(count * price).toFixed(2)})
          </button>
        </div>
      </div>

      <div className="takes">
        {scene.clips.map((clip, index) => (
          <div key={index} className={`take${clip.kept ? " kept" : ""}`}>
            {clip.status === "completed" ? (
              <video controls preload="metadata" src={media(slug, clip.file)} />
            ) : (
              <div className="muted mono">take {clip.take}: {clip.status}</div>
            )}
            <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
              <span className="mono muted">
                take {clip.take ?? "–"}
                {clip.source_image_index != null && ` · src ${clip.source_image_index + 1}`}
                {" · "}{clip.model}
                {typeof clip.meta?.cost_usd === "number" && ` · $${(clip.meta.cost_usd as number).toFixed(2)}`}
              </span>
              {clip.status === "completed" && (
                <button
                  className="ghost"
                  onClick={() => keep.mutate({ index, kept: !clip.kept })}
                >
                  {clip.kept ? "✓ kept" : "keep"}
                </button>
              )}
            </div>
          </div>
        ))}
        {scene.clips.length === 0 && <p className="muted">No takes yet.</p>}
      </div>
    </>
  );
}
