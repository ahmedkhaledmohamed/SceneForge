import { useCallback, useEffect, useRef, useState } from "react";

interface MaskEditorProps {
  imageUrl: string;
  onApply: (maskBlob: Blob) => void;
  onCancel: () => void;
  busy?: boolean;
}

export default function MaskEditor({ imageUrl, onApply, onCancel, busy }: MaskEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const maskRef = useRef<HTMLCanvasElement>(null);
  const [painting, setPainting] = useState(false);
  const [brushSize, setBrushSize] = useState(30);
  const [erasing, setErasing] = useState(false);
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const maxW = Math.min(560, window.innerWidth - 60);
      const scale = maxW / img.width;
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      setImgSize({ w, h });

      const canvas = canvasRef.current;
      const mask = maskRef.current;
      if (!canvas || !mask) return;
      canvas.width = w;
      canvas.height = h;
      mask.width = img.width;
      mask.height = img.height;

      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, w, h);

      const mctx = mask.getContext("2d")!;
      mctx.fillStyle = "#000";
      mctx.fillRect(0, 0, img.width, img.height);
    };
    img.src = imageUrl;
  }, [imageUrl]);

  const draw = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!painting) return;
      const canvas = canvasRef.current;
      const mask = maskRef.current;
      if (!canvas || !mask) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const scaleX = mask.width / canvas.width;
      const scaleY = mask.height / canvas.height;

      // Draw on visible canvas (semi-transparent overlay)
      const ctx = canvas.getContext("2d")!;
      ctx.globalCompositeOperation = erasing ? "destination-out" : "source-over";
      ctx.fillStyle = erasing ? "rgba(0,0,0,1)" : "rgba(0, 212, 255, 0.35)";
      ctx.beginPath();
      ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = "source-over";

      // Draw on mask canvas (white = edit area)
      const mctx = mask.getContext("2d")!;
      mctx.fillStyle = erasing ? "#000" : "#fff";
      mctx.beginPath();
      mctx.arc(x * scaleX, y * scaleY, (brushSize / 2) * scaleX, 0, Math.PI * 2);
      mctx.fill();
    },
    [painting, brushSize, erasing],
  );

  const clearMask = () => {
    const canvas = canvasRef.current;
    const mask = maskRef.current;
    if (!canvas || !mask) return;

    // Redraw image
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const ctx = canvas.getContext("2d")!;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = imageUrl;

    // Clear mask to black
    const mctx = mask.getContext("2d")!;
    mctx.fillStyle = "#000";
    mctx.fillRect(0, 0, mask.width, mask.height);
  };

  const handleApply = () => {
    const mask = maskRef.current;
    if (!mask) return;
    mask.toBlob((blob) => {
      if (blob) onApply(blob);
    }, "image/png");
  };

  return (
    <div
      className="lightbox"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ maxWidth: 600, width: "100%" }}>
        <div style={{ position: "relative" }}>
          <canvas
            ref={canvasRef}
            style={{
              width: imgSize.w || 560,
              borderRadius: 10,
              cursor: erasing ? "crosshair" : "cell",
              border: "1px solid var(--glass-border)",
              display: "block",
            }}
            onMouseDown={() => setPainting(true)}
            onMouseUp={() => setPainting(false)}
            onMouseLeave={() => setPainting(false)}
            onMouseMove={draw}
          />
          <canvas ref={maskRef} style={{ display: "none" }} />
        </div>

        <div className="row" style={{ marginTop: 12, justifyContent: "space-between" }}>
          <div className="row" style={{ gap: 10 }}>
            <button
              className={erasing ? "ghost" : ""}
              onClick={() => setErasing(false)}
              style={{ fontSize: "0.76rem" }}
            >
              Paint
            </button>
            <button
              className={erasing ? "" : "ghost"}
              onClick={() => setErasing(true)}
              style={{ fontSize: "0.76rem" }}
            >
              Erase
            </button>
            <button className="ghost" onClick={clearMask} style={{ fontSize: "0.76rem" }}>
              Clear
            </button>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <span className="mono muted" style={{ fontSize: "0.68rem" }}>brush</span>
            <input
              type="range"
              min={5}
              max={80}
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              style={{ width: 100 }}
            />
            <span className="mono muted" style={{ fontSize: "0.68rem" }}>{brushSize}px</span>
          </div>
        </div>

        <div className="row" style={{ marginTop: 12, justifyContent: "flex-end", gap: 10 }}>
          <button className="ghost" onClick={onCancel}>Cancel</button>
          <button onClick={handleApply} disabled={busy}>
            {busy ? "Applying..." : "Apply edit"}
          </button>
        </div>

        <p className="muted" style={{ fontSize: "0.72rem", marginTop: 8, textAlign: "center" }}>
          Paint over the area you want to change. The painted region will be regenerated.
        </p>
      </div>
    </div>
  );
}
