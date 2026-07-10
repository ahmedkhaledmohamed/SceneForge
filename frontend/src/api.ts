import type { HistoryRow, Job, ModelInfo, ProfileDoc, ProfileSummary, Project, ProjectSummary } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
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

const patch = (body: unknown): RequestInit => ({
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function p(prof: string, slug: string) {
  return `/profiles/${prof}/projects/${slug}`;
}

export const api = {
  models: () => request<Record<string, ModelInfo>>("/models"),

  // profiles
  profiles: () => request<ProfileSummary[]>("/profiles"),
  createProfile: (name: string) => request<{ slug: string; name: string }>("/profiles", json({ name })),
  profile: (prof: string) => request<ProfileDoc>(`/profiles/${prof}`),
  patchProfile: (prof: string, body: unknown) => request<ProfileDoc>(`/profiles/${prof}`, patch(body)),
  addProfileCharacter: (prof: string, form: FormData) =>
    request(`/profiles/${prof}/characters`, { method: "POST", body: form }),
  addProfileCharacterRef: (prof: string, cid: string, form: FormData) =>
    request(`/profiles/${prof}/characters/${cid}/refs`, { method: "POST", body: form }),
  deleteProfileCharacter: (prof: string, cid: string) =>
    request(`/profiles/${prof}/characters/${cid}`, { method: "DELETE" }),
  addSeed: (prof: string, form: FormData) =>
    request(`/profiles/${prof}/seeds`, { method: "POST", body: form }),

  // projects
  projects: (prof: string) => request<ProjectSummary[]>(`/profiles/${prof}/projects`),
  project: (prof: string, slug: string) => request<Project>(p(prof, slug)),
  createProject: (prof: string, body: unknown) =>
    request<Project>(`/profiles/${prof}/projects`, json(body)),
  job: (prof: string, slug: string) => request<Job>(`${p(prof, slug)}/job`),

  deleteProject: (prof: string, slug: string) =>
    request(`${p(prof, slug)}`, { method: "DELETE" }),
  duplicateProject: (prof: string, slug: string, body: unknown) =>
    request<Project>(`${p(prof, slug)}/duplicate`, json(body)),
  patchProject: (prof: string, slug: string, body: unknown) =>
    request<Project>(`${p(prof, slug)}`, patch(body)),

  addOutfit: (prof: string, slug: string, name: string) =>
    request(`${p(prof, slug)}/outfits`, json({ name })),
  addItem: (prof: string, slug: string, oid: string, form: FormData) =>
    request(`${p(prof, slug)}/outfits/${oid}/items`, { method: "POST", body: form }),
  processOutfit: (prof: string, slug: string, oid: string, body: unknown) =>
    request(`${p(prof, slug)}/outfits/${oid}/process`, json(body)),
  deleteOutfit: (prof: string, slug: string, oid: string) =>
    request(`${p(prof, slug)}/outfits/${oid}`, { method: "DELETE" }),
  deleteItem: (prof: string, slug: string, oid: string, index: number) =>
    request(`${p(prof, slug)}/outfits/${oid}/items/${index}`, { method: "DELETE" }),
  links: (prof: string, slug: string, oid: string) =>
    request<string>(`${p(prof, slug)}/outfits/${oid}/links`),
  addCharacter: (prof: string, slug: string, form: FormData) =>
    request(`${p(prof, slug)}/characters`, { method: "POST", body: form }),

  brainstorm: (prof: string, slug: string, body: unknown) =>
    request<{ descriptions: string[] }>(`${p(prof, slug)}/brainstorm`, json(body)),
  addScenesBulk: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/bulk`, json(body)),
  addScene: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes`, json(body)),
  scenesFromOutfit: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/from-outfit`, json(body)),
  generateTakesAll: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-takes-all`, json(body)),
  deleteScene: (prof: string, slug: string, sid: string) =>
    request(`${p(prof, slug)}/scenes/${sid}`, { method: "DELETE" }),
  patchScene: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}`, patch(body)),
  select: (prof: string, slug: string, sid: string, imageIndex: number) =>
    request(`${p(prof, slug)}/scenes/${sid}/select`, json({ image_index: imageIndex })),

  importImage: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/import-image`, { method: "POST", body: form }),
  importClip: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/import-clip`, { method: "POST", body: form }),

  generateImages: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-images`, json(body)),
  regenerateImage: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/regenerate-image`, json(body)),
  takes: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/takes`, json(body)),
  keep: (prof: string, slug: string, sid: string, index: number, kept: boolean) =>
    request(`${p(prof, slug)}/scenes/${sid}/clips/${index}/keep`, json({ kept })),

  stitch: (prof: string, slug: string) =>
    request(`${p(prof, slug)}/stitch`, { method: "POST" }),
  export: (prof: string, slug: string) =>
    request<{ dir: string; files: string[] }>(`${p(prof, slug)}/export`, {
      method: "POST",
    }),
  history: (prof: string, slug: string, params = "") =>
    request<HistoryRow[]>(`${p(prof, slug)}/history${params}`),
};

export const media = (prof: string, slug: string, file: string) =>
  `${API_BASE}/profiles/${prof}/projects/${slug}/media/${file}`;

export const profileMedia = (prof: string, file: string) =>
  `${API_BASE}/profiles/${prof}/media/${file}`;
