export interface SceneRef {
  file: string;
  role: string;
  label: string;
  url: string | null;
}

export interface ImageArtifact {
  file: string;
  prompt: string;
  model: string;
  created_at: string;
  meta: Record<string, unknown>;
  generation_id?: string;
  enhanced_prompt?: string;
  upgraded_from?: string;
  inpainted_from?: string;
}

export interface ClipArtifact {
  file: string;
  prompt: string;
  source_image: string | null;
  model: string;
  status: "pending" | "completed" | "failed";
  duration_s: number | null;
  error: string | null;
  created_at: string;
  meta: Record<string, unknown>;
  take: number | null;
  source_image_index: number | null;
  kept: boolean;
}

export interface Scene {
  id: string;
  description: string;
  pose: string | null;
  character_id: string | null;
  style_override: string | null;
  refs: SceneRef[];
  images: ImageArtifact[];
  selected_image: number | null;
  clips: ClipArtifact[];
  prompt_preview?: string | null;
}

export interface Character {
  id: string;
  name: string;
  description: string;
  reference_images: string[];
  main?: boolean;
}

export interface ReferenceImage {
  file: string;
  role: string;
  label: string;
}

export interface ProjectClip {
  id: string;
  source_images: string[];
  prompt: string;
  model: string;
  seconds: number;
  file: string;
  status: "pending" | "completed" | "failed";
  error: string | null;
  duration_s: number | null;
  created_at: string;
  meta: Record<string, unknown>;
  kept: boolean;
  shot_type?: string;
  upgraded_from?: string;
  audio_file?: string;
  audio_type?: string;
}

export interface AudioTypeInfo {
  label: string;
  description: string;
}

export interface ShotTypeInfo {
  label: string;
  description: string;
  color: string;
  recommended_video: string;
}

export interface ShotListItem {
  description: string;
  composition: string;
  shot_type: string;
  prompt: string;
}

export interface ConsistencyResult {
  score: number;
  outliers: { scene_id: string; similarity: number }[];
  images_scored: number;
}

export interface Asset {
  id: string;
  file: string;
  tags: string[];
  label: string;
  role: string;
  url: string;
  created_at: string;
  projects_used: string[];
}

export interface SavedPrompt {
  id: string;
  text: string;
  tags: string[];
  model: string;
  created_at: string;
  times_used: number;
}

export interface CaptionResult {
  caption: string;
  hashtags: string[];
  cta: string;
}

export interface Project {
  slug: string;
  profile: string;
  name: string;
  concept: string;
  style: { anchor: string; suffix: string };
  settings: {
    image_model: string;
    video_model: string;
    image_options: number;
    aspect: string;
    auto_enhance?: boolean;
  };
  characters: Character[];
  refs: ReferenceImage[];
  scenes: Scene[];
  clips: ProjectClip[];
  sequence: string[];
  captions: Record<string, CaptionResult>;
  job: Job | null;
  spent_usd: number;
  notes: string;
  budget_usd: number;
  profile_characters: Character[];
}

export interface ProjectSummary {
  slug: string;
  name: string;
  concept: string;
  scenes: number;
  refs: number;
  clips: number;
  kept: number;
  thumbnail?: string | null;
  spent_usd?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ProfileSummary {
  slug: string;
  name: string;
  characters: number;
  seeds: number;
  projects: number;
  spent_usd?: number;
  updated_at?: string | null;
}

export interface ProfileDoc {
  slug: string;
  name: string;
  style: { anchor: string; suffix: string; mood: string; palette: string; lighting: string };
  defaults: {
    image_model: string;
    final_image_model: string;
    video_model: string;
    aspect: string;
    image_options: number;
  };
  characters: Character[];
  seeds: Seed[];
  has_keys: boolean;
}

export interface Seed {
  id: string;
  kind: "image" | "clip" | "note";
  file: string | null;
  text: string | null;
  tags: string[];
  created_at: string;
}

export interface Job {
  name: string | null;
  status: "running" | "done" | "failed" | "idle";
  log: string[];
  total: number;
  completed: number;
  current: string;
}

export interface ModelInfo {
  kind: "image" | "video";
  price: number;
  max_refs?: number;
  supports_i2v?: boolean | null;
  notes?: string;
}

export interface PlatformSpec {
  label: string;
  aspect: string;
  max_duration: number;
  width: number;
  height: number;
  codec: string;
}

export interface ModelStats {
  images: number;
  clips: number;
  clips_kept: number;
  clips_failed: number;
  keep_rate: number;
  success_rate: number;
  spend_usd: number;
  cost_per_kept: number | null;
}

export interface ProfileAnalytics {
  projects: number;
  total_images: number;
  total_clips: number;
  total_kept: number;
  total_spend_usd: number;
  avg_cost_per_kept: number | null;
  best_value_model: string | null;
  models: Record<string, ModelStats>;
  spend_trend: { week: string; spend_usd: number }[];
}

export interface ProjectAnalytics {
  total_images: number;
  total_clips: number;
  total_kept: number;
  total_spend_usd: number;
  avg_cost_per_kept: number | null;
  models: Record<string, ModelStats>;
}

export interface DashboardData {
  profiles: number;
  projects: number;
  total_spend_usd: number;
  recent_projects: {
    profile: string;
    slug: string;
    name: string;
    concept: string;
    thumbnail: string | null;
    updated_at: string;
    spent_usd: number;
  }[];
}

export interface HistoryRow {
  type: "image" | "clip";
  scene_id: string;
  file: string;
  prompt: string;
  model: string;
  status?: string;
  take?: number | null;
  kept?: boolean;
  cost_usd: number | null;
  references?: string[];
  created_at: string;
}
