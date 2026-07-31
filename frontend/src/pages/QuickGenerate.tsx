import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, media } from "../api";
import { CostBadge, ModelPills } from "../components/ModelPills";
import { toastError, toastOk } from "../components/toast";
import { useModels } from "../hooks";

export default function QuickGenerate() {
  const { prof = "" } = useParams();
  const [mode, setMode] = useState<"image" | "video">("image");
  const [model, setModel] = useState("flux-schnell");
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { data: models } = useModels();

  // Switch default model when mode changes
  useEffect(() => {
    if (mode === "image") setModel("flux-schnell");
    else setModel("kling-2.1");
  }, [mode]);

  const resultsQuery = useQuery({
    queryKey: ["quick-results", prof],
    queryFn: () => api.quickResults(prof),
    refetchInterval: generating ? 2000 : false,
  });

  const results = resultsQuery.data;

  const handleGenerate = async () => {
    if (!prompt.trim() && mode === "image") {
      toastError("Enter a prompt");
      return;
    }
    if (mode === "video" && !file) {
      toastError("Upload a start image for video");
      return;
    }
    setGenerating(true);
    try {
      const form = new FormData();
      form.set("prompt", prompt);
      form.set("model", model);
      form.set("mode", mode);
      if (file) form.set("file", file);
      await api.quickGenerate(prof, form);
      toastOk("Generating...");
      // Poll results via refetchInterval
      setTimeout(() => {
        resultsQuery.refetch();
        setGenerating(false);
      }, 3000);
    } catch (e) {
      toastError(String(e));
      setGenerating(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleGenerate();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 80px)" }}>
      {/* Results area */}
      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 200 }}>
        <h1>Quick Generate</h1>
        <p className="muted" style={{ marginBottom: 20 }}>
          Generate images or videos without creating a project. Results can be saved to any project later.
        </p>

        {/* Image results */}
        {results && results.images.length > 0 && (
          <>
            <h2>Images</h2>
            <div className="gallery">
              {results.images.map((img, i) => (
                <div key={`${img.scene_id}-${i}`} className="thumb">
                  <img
                    src={media(prof, "_quick", img.file)}
                    alt={img.prompt}
                    loading="lazy"
                  />
                  <div className="cap">
                    {img.model} · ${(img.cost_usd ?? 0).toFixed(3)}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Video results */}
        {results && results.clips.length > 0 && (
          <>
            <h2>Videos</h2>
            <div className="takes">
              {results.clips.map((clip) => (
                <div key={clip.id} className="take">
                  <video
                    controls
                    preload="metadata"
                    src={media(prof, "_quick", clip.file)}
                    style={{ width: "100%", borderRadius: 10 }}
                  />
                  <div className="cap" style={{ fontSize: "0.68rem", color: "var(--taupe)", padding: 4 }}>
                    {clip.model} · {clip.duration_s?.toFixed(1)}s · ${(clip.cost_usd ?? 0).toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {results && results.images.length === 0 && results.clips.length === 0 && !generating && (
          <div style={{ textAlign: "center", padding: "80px 0 60px", color: "var(--taupe)" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16, opacity: 0.3 }}>&#9670;</div>
            <h2 style={{ color: "var(--cream)", marginBottom: 8 }}>Start creating</h2>
            <p style={{ maxWidth: "40ch", margin: "0 auto", lineHeight: 1.6 }}>
              Type a prompt below, pick a model, and hit Generate.<br />
              Upload a reference image for multi-ref composition,<br />
              or switch to Video mode to animate an image.
            </p>
            <div className="mono" style={{ marginTop: 16, fontSize: "0.72rem", opacity: 0.5 }}>
              Cmd+Enter to generate
            </div>
          </div>
        )}

        {generating && (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--gold)" }}>
            <div className="skeleton" style={{ width: 190, height: 280, margin: "0 auto", borderRadius: 10 }} />
            <p className="mono" style={{ marginTop: 12, fontSize: "0.78rem" }}>Generating...</p>
          </div>
        )}
      </div>

      {/* Prompt bar — pinned at bottom */}
      <div style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        background: "rgba(10, 10, 15, 0.85)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderTop: "1px solid var(--glass-border)",
        padding: "16px 24px 20px",
        zIndex: 20,
      }}>
        <div style={{ maxWidth: 1160, margin: "0 auto" }}>
          {/* Mode toggle + model pills */}
          <div className="row" style={{ marginBottom: 10, justifyContent: "space-between" }}>
            <div className="row" style={{ gap: 0 }}>
              <button
                className={mode === "image" ? "" : "ghost"}
                style={{ borderRadius: "20px 0 0 20px", fontSize: "0.72rem" }}
                onClick={() => setMode("image")}
              >
                Image
              </button>
              <button
                className={mode === "video" ? "" : "ghost"}
                style={{ borderRadius: "0 20px 20px 0", fontSize: "0.72rem" }}
                onClick={() => setMode("video")}
              >
                Video
              </button>
            </div>

            <ModelPills kind={mode === "image" ? "image" : "video"} value={model} onChange={setModel} />
          </div>

          {/* Upload area + prompt + generate */}
          <div className="row" style={{ gap: 10 }}>
            {/* File upload */}
            <button
              className="ghost"
              onClick={() => fileRef.current?.click()}
              style={{ flexShrink: 0, fontSize: "0.72rem", padding: "8px 12px" }}
              title={mode === "image" ? "Add reference image (optional)" : "Start image (required)"}
            >
              {file ? file.name.slice(0, 15) : (mode === "image" ? "+ ref" : "+ image")}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />

            {/* Prompt */}
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={mode === "image"
                ? "Describe the scene you want to generate..."
                : "Describe the motion (e.g. gentle wind, camera pan)..."}
              rows={1}
              style={{
                flex: 1,
                resize: "none",
                fontSize: "0.88rem",
                padding: "10px 14px",
                minHeight: 40,
                maxHeight: 80,
              }}
            />

            {/* Generate button */}
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{ flexShrink: 0, padding: "10px 20px", fontSize: "0.85rem" }}
            >
              {generating ? "..." : "Generate"}
              {!generating && (
                <span style={{ marginLeft: 6 }}>
                  <CostBadge model={model} />
                </span>
              )}
            </button>
          </div>

          <div className="mono muted" style={{ fontSize: "0.62rem", marginTop: 6, textAlign: "right" }}>
            Cmd+Enter to generate
          </div>
        </div>
      </div>
    </div>
  );
}
