import { useModels } from "../hooks";

export function ModelPills({ kind, value, onChange }: {
  kind: "image" | "video" | "inpaint";
  value: string;
  onChange: (v: string) => void;
}) {
  const { data: models } = useModels();
  const entries = Object.entries(models ?? {}).filter(([, m]) => m.kind === kind);

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {entries.map(([key, m]) => (
        <button
          key={key}
          className={value === key ? "" : "ghost"}
          onClick={() => onChange(key)}
          style={{
            fontSize: "0.72rem",
            padding: "5px 12px",
            borderRadius: 20,
            whiteSpace: "nowrap",
          }}
          title={m.notes ?? ""}
        >
          {key}
          <span className="muted" style={{ marginLeft: 4, fontSize: "0.64rem" }}>
            ${m.price}
          </span>
          {m.max_refs ? (
            <span className="muted" style={{ marginLeft: 2, fontSize: "0.58rem" }}>
              {m.max_refs}refs
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function CostBadge({ model, count = 1 }: { model: string; count?: number }) {
  const { data: models } = useModels();
  const price = models?.[model]?.price ?? 0;
  const total = price * count;
  if (total === 0) return null;
  return (
    <span className="mono" style={{ fontSize: "0.72rem", color: "var(--gold)" }}>
      ~${total.toFixed(2)}
    </span>
  );
}
