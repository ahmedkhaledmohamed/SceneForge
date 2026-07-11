import type { HistoryRow, Job, ModelInfo, ProfileDoc, ProfileSummary, Project, ProjectSummary } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

let _authToken: string | null = localStorage.getItem("sf_token");

export function setAuthToken(token: string | null) {
  _authToken = token;
  if (token) localStorage.setItem("sf_token", token);
  else localStorage.removeItem("sf_token");
}

export function getAuthToken() { return _authToken; }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (_authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${_authToken}`);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body?.error?.message ?? message;
    } catch {
      /* not json */
    }
    if (response.status === 401) {
      try {
        const body = await response.clone().json();
        if (body?.error?.code === "site_auth") {
          localStorage.removeItem("sf_site_token");
          window.location.reload();
          throw new Error("Session expired — reloading");
        }
      } catch { /* not json or not site_auth */ }
      setAuthToken(null);
    }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("json")) return response.json() as Promise<T>;
  if (contentType.includes("text/plain")) return response.text() as Promise<T>;
  throw new Error("API returned non-JSON response — is the backend running?");
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
  deleteProfile: (prof: string) => request(`/profiles/${prof}`, { method: "DELETE" }),
  login: (prof: string, password: string) =>
    request<{ token: string }>(`/profiles/${prof}/login`, json({ password })),
  logout: (prof: string) =>
    request(`/profiles/${prof}/logout`, { method: "POST" }),
  setPassword: (prof: string, password: string) =>
    request<{ token: string }>(`/profiles/${prof}/set-password`, json({ password })),
  getSettings: (prof: string) =>
    request<{ keys: { together: string; runpod_api: string; runpod_endpoint: string }; has_together: boolean; has_runpod: boolean }>(`/profiles/${prof}/settings`),
  patchSettings: (prof: string, keys: Record<string, string>) =>
    request(`/profiles/${prof}/settings`, patch({ keys })),
  addProfileCharacter: (prof: string, form: FormData) =>
    request(`/profiles/${prof}/characters`, { method: "POST", body: form }),
  addProfileCharacterRef: (prof: string, cid: string, form: FormData) =>
    request(`/profiles/${prof}/characters/${cid}/refs`, { method: "POST", body: form }),
  deleteProfileCharacter: (prof: string, cid: string) =>
    request(`/profiles/${prof}/characters/${cid}`, { method: "DELETE" }),
  profileStats: (prof: string) =>
    request<{
      projects: number; scenes: number; images: number;
      clips_completed: number; clips_kept: number; spent_usd: number;
      models_used: Record<string, number>;
    }>(`/profiles/${prof}/stats`),
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
  addItemsBulk: (prof: string, slug: string, oid: string, form: FormData) =>
    request(`${p(prof, slug)}/outfits/${oid}/items/bulk`, { method: "POST", body: form }),
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
  reorderScenes: (prof: string, slug: string, sceneIds: string[]) =>
    request(`${p(prof, slug)}/scenes/reorder`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_ids: sceneIds }),
    }),
  deleteScene: (prof: string, slug: string, sid: string) =>
    request(`${p(prof, slug)}/scenes/${sid}`, { method: "DELETE" }),
  patchScene: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}`, patch(body)),
  selectAll: (prof: string, slug: string) =>
    request<{ selected: number }>(`${p(prof, slug)}/select-all`, { method: "POST" }),
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
