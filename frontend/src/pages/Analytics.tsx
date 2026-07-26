import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ background: "var(--line)", borderRadius: 4, height: 18, flex: 1 }}>
      <div style={{ background: color, borderRadius: 4, height: "100%", width: `${pct}%`, minWidth: pct > 0 ? 2 : 0 }} />
    </div>
  );
}

export default function Analytics() {
  const { prof = "" } = useParams();
  const { data, isLoading, error } = useQuery({
    queryKey: ["analytics", prof],
    queryFn: () => api.profileAnalytics(prof),
  });

  if (isLoading) return <p className="muted">Loading analytics...</p>;
  if (error) return <p style={{ color: "var(--danger)" }}>Error: {String(error)}</p>;
  if (!data) return null;

  const models = Object.entries(data.models);
  const maxSpend = Math.max(...models.map(([, s]) => s.spend_usd), 0.01);
  const maxClips = Math.max(...models.map(([, s]) => s.clips), 1);

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <h2>Analytics</h2>
        <Link to={`/${prof}`} className="ghost" style={{ fontSize: "0.82rem" }}>
          back to projects
        </Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>${data.total_spend_usd.toFixed(2)}</div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Total spend</div>
        </div>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>
            {data.avg_cost_per_kept != null ? `$${data.avg_cost_per_kept.toFixed(2)}` : "—"}
          </div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Avg cost per kept clip</div>
        </div>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>
            {data.best_value_model ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Best value model</div>
        </div>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>{data.projects}</div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Projects</div>
        </div>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>{data.total_images}</div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Images generated</div>
        </div>
        <div className="card" style={{ padding: 16, textAlign: "center" }}>
          <div className="mono" style={{ fontSize: "1.4rem" }}>
            {data.total_kept}/{data.total_clips}
          </div>
          <div className="muted" style={{ fontSize: "0.78rem" }}>Clips kept / total</div>
        </div>
      </div>

      {data.spend_trend.length > 0 && (
        <>
          <h3>Spend trend (last 4 weeks)</h3>
          <div style={{ marginBottom: 24 }}>
            {data.spend_trend.map((w) => (
              <div key={w.week} className="row" style={{ gap: 8, marginBottom: 4 }}>
                <span className="mono muted" style={{ width: 70, fontSize: "0.78rem" }}>{w.week}</span>
                <Bar value={w.spend_usd} max={Math.max(...data.spend_trend.map((x) => x.spend_usd))} color="var(--gold, #daa520)" />
                <span className="mono" style={{ width: 60, textAlign: "right", fontSize: "0.78rem" }}>${w.spend_usd.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <h3>Model performance</h3>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--line)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Model</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Images</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Clips</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Kept</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Keep %</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Success %</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>Spend</th>
              <th style={{ textAlign: "right", padding: "6px 8px" }}>$/kept</th>
              <th style={{ padding: "6px 8px", width: "30%" }}>Spend</th>
            </tr>
          </thead>
          <tbody>
            {models.map(([model, stats]) => (
              <tr key={model} style={{ borderBottom: "1px solid var(--line)" }}>
                <td style={{ padding: "6px 8px" }}><span className="pill">{model}</span></td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">{stats.images}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">{stats.clips}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">{stats.clips_kept}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">{(stats.keep_rate * 100).toFixed(0)}%</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">{(stats.success_rate * 100).toFixed(0)}%</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">${stats.spend_usd.toFixed(2)}</td>
                <td style={{ textAlign: "right", padding: "6px 8px" }} className="mono">
                  {stats.cost_per_kept != null ? `$${stats.cost_per_kept.toFixed(2)}` : "—"}
                </td>
                <td style={{ padding: "6px 8px" }}>
                  <Bar value={stats.spend_usd} max={maxSpend} color="var(--gold, #daa520)" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
