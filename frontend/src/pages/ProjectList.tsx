import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function ProjectList() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects,
  });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const client = useQueryClient();

  const create = useMutation({
    mutationFn: (body: Record<string, string>) => api.createProject(body),
    onSuccess: (project: { slug: string }) => {
      client.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/p/${project.slug}`);
    },
  });

  return (
    <>
      <h1>Projects</h1>
      <p className="muted">Each project is one concept — a post, a video, a look.</p>
      <div className="row" style={{ margin: "14px 0" }}>
        <button onClick={() => setCreating(true)}>New project</button>
      </div>

      {creating && (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            create.mutate({
              name: String(data.get("name") ?? ""),
              concept: String(data.get("concept") ?? ""),
              anchor: String(data.get("anchor") ?? ""),
            });
          }}
        >
          <label>Name</label>
          <input name="name" required placeholder="spring looks vol. 3" style={{ width: "100%" }} />
          <label>Concept</label>
          <input name="concept" placeholder="what is this post about?" style={{ width: "100%" }} />
          <label>Style anchor (mood, palette, lighting)</label>
          <input name="anchor" placeholder="soft studio light, muted pastels" style={{ width: "100%" }} />
          <div className="row" style={{ marginTop: 12 }}>
            <button type="submit" disabled={create.isPending}>Create</button>
            <button type="button" className="ghost" onClick={() => setCreating(false)}>Cancel</button>
            {create.isError && <span className="muted">{String(create.error)}</span>}
          </div>
        </form>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      <div className="grid-cards">
        {projects?.map((p) => (
          <Link key={p.slug} to={`/p/${p.slug}`} className="card" style={{ display: "block" }}>
            <b>{p.name}</b>
            <div className="muted" style={{ fontSize: "0.85rem" }}>{p.concept || "no concept yet"}</div>
            <div className="row" style={{ marginTop: 10 }}>
              <span className="pill">{p.scenes} scenes</span>
              <span className="pill">{p.clips} clips</span>
              {p.kept > 0 && <span className="pill gold">{p.kept} kept</span>}
            </div>
          </Link>
        ))}
      </div>
      {projects?.length === 0 && !creating && (
        <p className="muted">No projects yet — create the first one.</p>
      )}
    </>
  );
}
