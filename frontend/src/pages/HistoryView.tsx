import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, media } from "../api";

export default function HistoryView() {
  const { slug = "" } = useParams();
  const [type, setType] = useState("");
  const params = type ? `?type=${type}` : "";
  const { data: rows } = useQuery({
    queryKey: ["history", slug, type],
    queryFn: () => api.history(slug, params),
  });

  const spend = rows?.reduce((sum, r) => sum + (r.cost_usd ?? 0), 0) ?? 0;

  return (
    <>
      <p><Link to={`/p/${slug}`}>← board</Link></p>
      <h1>History</h1>
      <div className="row" style={{ margin: "10px 0" }}>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">everything</option>
          <option value="image">images</option>
          <option value="clip">clips</option>
        </select>
        {spend > 0 && <span className="mono muted">tracked GPU spend: ${spend.toFixed(2)}</span>}
      </div>
      <table>
        <thead>
          <tr>
            <th></th><th>Scene</th><th>Model</th><th>Prompt</th><th>Cost</th><th>When</th>
          </tr>
        </thead>
        <tbody>
          {rows?.map((row, i) => (
            <tr key={i}>
              <td>
                {row.type === "image" ? (
                  <img src={media(slug, row.file)} alt="" style={{ width: 44, borderRadius: 4 }} loading="lazy" />
                ) : (
                  <span className="pill">{row.kept ? "clip ✓" : "clip"}</span>
                )}
              </td>
              <td className="mono">{row.scene_id}{row.take ? ` t${row.take}` : ""}</td>
              <td className="mono">{row.model}</td>
              <td className="muted" style={{ maxWidth: 420 }}>{row.prompt}</td>
              <td className="mono">{row.cost_usd ? `$${row.cost_usd.toFixed(3)}` : "–"}</td>
              <td className="mono muted">{row.created_at.slice(0, 16).replace("T", " ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows?.length === 0 && <p className="muted">Nothing generated yet.</p>}
    </>
  );
}
