export interface ImageArtifact {
  file: string;
  prompt: string;
  model: string;
  created_at: string;
  meta: Record<string, unknown>;
  generation_id?: string;
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
  outfit_id: string | null;
  style_override: string | null;
  images: ImageArtifact[];
  selected_image: number | null;
  clips: ClipArtifact[];
  prompt_preview?: string | null;
}

export interface ClothingItem {
  name: string;
  url: string | null;
  image: string | null;
}

export interface Outfit {
  id: string;
  name: string;
  items: ClothingItem[];
}

export interface Character {
  id: string;
  name: string;
  description: string;
  reference_images: string[];
  main?: boolean;
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
  };
  characters: Character[];
  outfits: Outfit[];
  scenes: Scene[];
  job: Job | null;
  spent_usd: number;
  notes: string;
  profile_characters: Character[];
}

export interface ProjectSummary {
  slug: string;
  name: string;
  concept: string;
  scenes: number;
  outfits: number;
  clips: number;
  kept: number;
}

export interface ProfileSummary {
  slug: string;
  name: string;
  characters: number;
  seeds: number;
  projects: number;
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
  has_password: boolean;
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
}

export interface ModelInfo {
  kind: "image" | "video";
  price: number;
  max_refs?: number;
  supports_i2v?: boolean | null;
  notes?: string;
}

export interface HistoryRow {
  type: "image" | "clip";
  scene_id: string;
  outfit_id: string | null;
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
