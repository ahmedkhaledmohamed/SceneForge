import type { HistoryRow, Job, ModelInfo, ProfileDoc, ProfileSummary, Project, ProjectSummary } from "./types";

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
  addSeed: (prof: string, form: FormData) =>
    request(`/profiles/${prof}/seeds`, { method: "POST", body: form }),

  // projects
  projects: (prof: string) => request<ProjectSummary[]>(`/profiles/${prof}/projects`),
  project: (prof: string, slug: string) => request<Project>(p(prof, slug)),
  createProject: (prof: string, body: unknown) =>
    request<Project>(`/profiles/${prof}/projects`, json(body)),
  job: (prof: string, slug: string) => request<Job>(`${p(prof, slug)}/job`),

  addOutfit: (prof: string, slug: string, name: string) =>
    request(`${p(prof, slug)}/outfits`, json({ name })),
  addItem: (prof: string, slug: string, oid: string, form: FormData) =>
    request(`${p(prof, slug)}/outfits/${oid}/items`, { method: "POST", body: form }),
  links: (prof: string, slug: string, oid: string) =>
    request<string>(`${p(prof, slug)}/outfits/${oid}/links`),
  addCharacter: (prof: string, slug: string, form: FormData) =>
    request(`${p(prof, slug)}/characters`, { method: "POST", body: form }),

  addScene: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes`, json(body)),
  scenesFromOutfit: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/from-outfit`, json(body)),
  patchScene: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}`, patch(body)),
  select: (prof: string, slug: string, sid: string, imageIndex: number) =>
    request(`${p(prof, slug)}/scenes/${sid}/select`, json({ image_index: imageIndex })),

  generateImages: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-images`, json(body)),
  regenerateImage: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/regenerate-image`, json(body)),
  takes: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/takes`, json(body)),
  keep: (prof: string, slug: string, sid: string, index: number, kept: boolean) =>
    request(`${p(prof, slug)}/scenes/${sid}/clips/${index}/keep`, json({ kept })),

  export: (prof: string, slug: string) =>
    request<{ dir: string; files: string[] }>(`${p(prof, slug)}/export`, {
      method: "POST",
    }),
  history: (prof: string, slug: string, params = "") =>
    request<HistoryRow[]>(`${p(prof, slug)}/history${params}`),
};

export const media = (prof: string, slug: string, file: string) =>
  `/api/profiles/${prof}/projects/${slug}/media/${file}`;

export const profileMedia = (prof: string, file: string) =>
  `/api/profiles/${prof}/media/${file}`;
