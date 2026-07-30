export default function EmptyState({
  title,
  description,
  action,
  onAction,
}: {
  title: string;
  description: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div
      className="card"
      style={{
        textAlign: "center",
        padding: "40px 24px",
        borderStyle: "dashed",
      }}
    >
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      <p className="muted" style={{ margin: "0 auto 16px", maxWidth: "40ch", fontSize: "0.88rem" }}>
        {description}
      </p>
      {action && onAction && (
        <button onClick={onAction}>{action}</button>
      )}
    </div>
  );
}
