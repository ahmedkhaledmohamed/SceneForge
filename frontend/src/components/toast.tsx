import { useEffect, useState } from "react";

type Toast = { id: number; message: string; kind: "error" | "ok" };

let push: ((t: Omit<Toast, "id">) => void) | null = null;
let nextId = 1;

export function toastError(message: string) {
  push?.({ message, kind: "error" });
}
export function toastOk(message: string) {
  push?.({ message, kind: "ok" });
}

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    push = (t) => {
      const toast = { ...t, id: nextId++ };
      setToasts((cur) => [...cur, toast]);
      setTimeout(
        () => setToasts((cur) => cur.filter((x) => x.id !== toast.id)),
        t.kind === "error" ? 6000 : 2500,
      );
    };
    return () => {
      push = null;
    };
  }, []);

  return (
    <div className="toaster" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
