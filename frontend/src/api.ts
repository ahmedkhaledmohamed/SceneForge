import type { CaptionResult, HistoryRow, Job, ModelInfo, PlatformSpec, ProfileDoc, ProfileSummary, Project, ProjectSummary, ShotListItem, ShotTypeInfo } from "./types";

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
  shotTypes: () => request<Record<string, ShotTypeInfo>>("/shot-types"),
  platforms: () => request<Record<string, PlatformSpec>>("/platforms"),

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
  getBalance: (prof: string) =>
    request<{
      together: { status: string; dashboard?: string };
      runpod: { status: string; credit_balance?: number; spend_per_hr?: number };
    }>(`/profiles/${prof}/balance`),
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

  // templates
  templates: (prof: string) =>
    request<{ name: string; slug: string; scenes: number; builtin: boolean }[]>(
      `/profiles/${prof}/templates`),
  saveAsTemplate: (prof: string, slug: string, name: string) =>
    request<{ slug: string; name: string; scenes: number }>(
      `${p(prof, slug)}/save-as-template`, json({ name })),
  createFromTemplate: (prof: string, template: string, name: string) =>
    request<Project>(`/profiles/${prof}/projects/from-template`,
      json({ template, name })),
  deleteTemplate: (prof: string, name: string) =>
    request(`/profiles/${prof}/templates/${name}`, { method: "DELETE" }),

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

  addProjectRef: (prof: string, slug: string, form: FormData) =>
    request(`${p(prof, slug)}/refs`, { method: "POST", body: form }),
  deleteProjectRef: (prof: string, slug: string, index: number) =>
    request(`${p(prof, slug)}/refs/${index}`, { method: "DELETE" }),

  enhancePrompt: (prof: string, slug: string, sid: string) =>
    request<{ enhanced_prompt: string; original: string }>(
      `${p(prof, slug)}/scenes/${sid}/enhance-prompt`, { method: "POST" }),
  brainstorm: (prof: string, slug: string, body: unknown) =>
    request<{ descriptions: string[] }>(`${p(prof, slug)}/brainstorm`, json(body)),
  generateShotList: (prof: string, slug: string, body: unknown) =>
    request<{ shots: ShotListItem[] }>(`${p(prof, slug)}/generate-shot-list`, json(body)),
  applyShotList: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/apply-shot-list`, json(body)),
  addScenesBulk: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/bulk`, json(body)),
  addScene: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes`, json(body)),
  addSceneRef: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/refs`, { method: "POST", body: form }),
  addSceneRefsBulk: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/refs/bulk`, { method: "POST", body: form }),
  deleteSceneRef: (prof: string, slug: string, sid: string, index: number) =>
    request(`${p(prof, slug)}/scenes/${sid}/refs/${index}`, { method: "DELETE" }),
  sceneLinks: (prof: string, slug: string, sid: string) =>
    request<string>(`${p(prof, slug)}/scenes/${sid}/links`),
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
  select: (prof: string, slug: string, sid: string, imageIndex: number | null) =>
    request(`${p(prof, slug)}/scenes/${sid}/select`, json({ image_index: imageIndex })),

  importImage: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/import-image`, { method: "POST", body: form }),
  importClip: (prof: string, slug: string, sid: string, form: FormData) =>
    request(`${p(prof, slug)}/scenes/${sid}/import-clip`, { method: "POST", body: form }),

  upgradeImage: (prof: string, slug: string, sid: string, imgIdx: number, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/images/${imgIdx}/upgrade`, json(body)),
  upgradeClip: (prof: string, slug: string, cid: string, body: unknown) =>
    request(`${p(prof, slug)}/clips/${cid}/upgrade`, json(body)),
  generateImages: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-images`, json(body)),
  generateAllScenes: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-all-scenes`, json(body)),
  regenerateImage: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/regenerate-image`, json(body)),
  takes: (prof: string, slug: string, sid: string, body: unknown) =>
    request(`${p(prof, slug)}/scenes/${sid}/takes`, json(body)),
  keep: (prof: string, slug: string, sid: string, index: number, kept: boolean) =>
    request(`${p(prof, slug)}/scenes/${sid}/clips/${index}/keep`, json({ kept })),

  createClip: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/clips`, json(body)),
  generateClip: (prof: string, slug: string, cid: string) =>
    request(`${p(prof, slug)}/clips/${cid}/generate`, { method: "POST" }),
  generateAllClips: (prof: string, slug: string) =>
    request(`${p(prof, slug)}/clips/generate-all`, { method: "POST" }),
  generateAllClipsBatch: (prof: string, slug: string, body: unknown) =>
    request(`${p(prof, slug)}/generate-all-clips-batch`, json(body)),
  patchClip: (prof: string, slug: string, cid: string, body: unknown) =>
    request(`${p(prof, slug)}/clips/${cid}`, patch(body)),
  resetClip: (prof: string, slug: string, cid: string) =>
    request(`${p(prof, slug)}/clips/${cid}/reset`, { method: "POST" }),
  deleteClip: (prof: string, slug: string, cid: string) =>
    request(`${p(prof, slug)}/clips/${cid}`, { method: "DELETE" }),
  keepClip: (prof: string, slug: string, cid: string, kept: boolean) =>
    request(`${p(prof, slug)}/clips/${cid}/keep`, json({ kept })),
  produce: (prof: string, slug: string, body: unknown) =>
    request<{ started: string; estimate: { images: number; clips: number; cost_usd: number } }>(
      `${p(prof, slug)}/produce`, json(body)),
  direct: (prof: string, slug: string, body: unknown) =>
    request<{ started: string; estimate: { num_scenes: number; images: number; clips: number; cost_usd: number } }>(
      `${p(prof, slug)}/direct`, json(body)),
  // captions
  generateCaption: (prof: string, slug: string, body: { platform: string; tone: string }) =>
    request<CaptionResult>(`${p(prof, slug)}/generate-caption`, json(body)),
  getCaptions: (prof: string, slug: string) =>
    request<Record<string, CaptionResult>>(`${p(prof, slug)}/captions`),
  deleteCaption: (prof: string, slug: string, platform: string) =>
    request(`${p(prof, slug)}/captions/${platform}`, { method: "DELETE" }),

  // sequence
  getSequence: (prof: string, slug: string) =>
    request<{ sequence: { id: string; file: string; model: string; duration_s: number | null; kept: boolean; status: string }[]; total_duration: number }>(
      `${p(prof, slug)}/sequence`),
  setSequence: (prof: string, slug: string, clipIds: string[]) =>
    request(`${p(prof, slug)}/sequence`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_ids: clipIds }),
    }),
  renderSequence: (prof: string, slug: string) =>
    request(`${p(prof, slug)}/sequence/render`, { method: "POST" }),

  stitch: (prof: string, slug: string) =>
    request(`${p(prof, slug)}/stitch`, { method: "POST" }),
  export: (prof: string, slug: string) =>
    request<{ dir: string; files: string[] }>(`${p(prof, slug)}/export`, {
      method: "POST",
    }),
  history: (prof: string, slug: string, params = "") =>
    request<HistoryRow[]>(`${p(prof, slug)}/history${params}`),
};

export async function exportForPlatform(prof: string, slug: string, platform: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (_authToken) headers["Authorization"] = `Bearer ${_authToken}`;
  const response = await fetch(
    `${API_BASE}/profiles/${prof}/projects/${slug}/export/${platform}`,
    { method: "POST", headers },
  );
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body?.error?.message ?? body?.detail?.message ?? message;
    } catch { /* not json */ }
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename=(.+)/);
  const filename = match ? match[1] : `${slug}-${platform}.mp4`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const media = (prof: string, slug: string, file: string) =>
  `${API_BASE}/profiles/${prof}/projects/${slug}/media/${file}`;

export const profileMedia = (prof: string, file: string) =>
  `${API_BASE}/profiles/${prof}/media/${file}`;
