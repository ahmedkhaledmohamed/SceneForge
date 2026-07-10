import { useEffect } from "react";

export default function Lightbox({ src, caption, onClose, actions }: {
  src: string;
  caption: string;
  onClose: () => void;
  actions?: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-modal="true">
      <div className="lightbox-inner" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={caption} />
        <div className="lightbox-bar">
          <span className="mono muted" style={{ flex: 1 }}>{caption}</span>
          {actions}
          <button className="ghost" onClick={onClose}>close</button>
        </div>
      </div>
    </div>
  );
}
