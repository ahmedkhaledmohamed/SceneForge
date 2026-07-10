import type { HistoryRow, Job, ModelInfo, Project, ProjectSummary } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
    } catch {
      /* not json */
    }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") ?? "";
  return (contentType.includes("json")
    ? response.json()
    : response.text()) as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  models: () => request<Record<string, ModelInfo>>("/models"),
  projects: () => request<ProjectSummary[]>("/projects"),
  project: (slug: string) => request<Project>(`/projects/${slug}`),
  createProject: (body: unknown) => request<Project>("/projects", json(body)),
  job: (slug: string) => request<Job>(`/projects/${slug}/job`),

  addOutfit: (slug: string, name: string) =>
    request(`/projects/${slug}/outfits`, json({ name })),
  addItem: (slug: string, oid: string, form: FormData) =>
    request(`/projects/${slug}/outfits/${oid}/items`, { method: "POST", body: form }),
  links: (slug: string, oid: string) =>
    request<string>(`/projects/${slug}/outfits/${oid}/links`),
  addCharacter: (slug: string, form: FormData) =>
    request(`/projects/${slug}/characters`, { method: "POST", body: form }),

  addScene: (slug: string, body: unknown) =>
    request(`/projects/${slug}/scenes`, json(body)),
  scenesFromOutfit: (slug: string, body: unknown) =>
    request(`/projects/${slug}/scenes/from-outfit`, json(body)),
  patchScene: (slug: string, sid: string, body: unknown) =>
    request(`/projects/${slug}/scenes/${sid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  select: (slug: string, sid: string, imageIndex: number) =>
    request(`/projects/${slug}/scenes/${sid}/select`, json({ image_index: imageIndex })),

  generateImages: (slug: string, body: unknown) =>
    request(`/projects/${slug}/generate-images`, json(body)),
  regenerateImage: (slug: string, sid: string, body: unknown) =>
    request(`/projects/${slug}/scenes/${sid}/regenerate-image`, json(body)),
  takes: (slug: string, sid: string, body: unknown) =>
    request(`/projects/${slug}/scenes/${sid}/takes`, json(body)),
  keep: (slug: string, sid: string, index: number, kept: boolean) =>
    request(`/projects/${slug}/scenes/${sid}/clips/${index}/keep`, json({ kept })),

  export: (slug: string) =>
    request<{ dir: string; files: string[] }>(`/projects/${slug}/export`, {
      method: "POST",
    }),
  history: (slug: string, params = "") =>
    request<HistoryRow[]>(`/projects/${slug}/history${params}`),
};

export const media = (slug: string, file: string) =>
  `/api/projects/${slug}/media/${file}`;
