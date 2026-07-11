import type { Character, ProfileDoc, ProfileSummary, Project, ProjectSummary } from "./types";

const DEMO_CHAR: Character = {
  id: "pchar-1", name: "Mila", description: "brand character doll",
  reference_images: ["refs/characters/pchar-1/front.png", "refs/characters/pchar-1/side.png"],
  main: true,
};

export const DEMO_PROFILES: ProfileSummary[] = [{
  slug: "generation-styled", name: "GenerationStyled",
  characters: 1, seeds: 3, projects: 2,
}];

export const DEMO_PROFILE: ProfileDoc = {
  slug: "generation-styled",
  name: "GenerationStyled",
  style: {
    anchor: "warm golden hour light through windows, muted earth tones, amber, cream",
    suffix: "photorealistic, cinematic composition, vertical framing, no added text, no watermarks",
    mood: "cozy, warm, intimate", palette: "muted earth tones, amber, cream",
    lighting: "warm golden hour light through windows",
  },
  defaults: {
    image_model: "flux-2-pro", final_image_model: "nano-banana-pro",
    video_model: "kling-2.1", aspect: "9:16", image_options: 2,
  },
  characters: [DEMO_CHAR],
  has_password: false,
  has_keys: true,
  seeds: [
    { id: "seed-1", kind: "note", file: null, text: "autumn cafe looks", tags: ["fall", "cozy"], created_at: "2026-07-10T10:00:00Z" },
    { id: "seed-2", kind: "note", file: null, text: "pastel spring series", tags: ["spring"], created_at: "2026-07-10T10:00:00Z" },
    { id: "seed-3", kind: "note", file: null, text: "holiday party outfits", tags: ["winter", "holiday"], created_at: "2026-07-10T10:00:00Z" },
  ],
};

export const DEMO_PROJECTS: ProjectSummary[] = [
  { slug: "spring-cafe-look", name: "Spring Cafe Look", concept: "cozy spring morning cafe outfit", scenes: 2, refs: 4, clips: 4, kept: 2 },
  { slug: "summer-park-set", name: "Summer Park Set", concept: "bright outdoor park outfit styling", scenes: 2, refs: 0, clips: 0, kept: 0 },
];

export const DEMO_PROJECT: Project = {
  slug: "spring-cafe-look",
  profile: "generation-styled",
  name: "Spring Cafe Look",
  concept: "cozy spring morning cafe outfit — linen + knit layers",
  style: {
    anchor: "warm golden hour light through windows, muted earth tones, amber, cream",
    suffix: "photorealistic, cinematic composition, vertical framing, no added text, no watermarks",
  },
  settings: {
    image_model: "flux-2-pro", video_model: "kling-2.1",
    image_options: 2, aspect: "9:16",
  },
  characters: [],
  refs: [],
  scenes: [
    {
      id: "scene-01",
      description: "Mila standing in a sunlit cafe doorway, full outfit visible head to toe",
      pose: "standing, facing the camera, full outfit visible head to toe",
      character_id: "pchar-1", style_override: null,
      refs: [
        { file: "refs/scenes/scene-01/skirt.jpg", role: "garment", label: "Linen midi skirt", url: "https://shop.example/skirt" },
        { file: "refs/scenes/scene-01/cardigan.jpg", role: "garment", label: "Knit cardigan", url: "https://shop.example/cardigan" },
      ],
      images: [
        { file: "images/scene-01/opt-1.png", prompt: "(demo)", model: "flux-2-pro", created_at: "2026-07-10T10:00:00Z", meta: { cost_usd: 0.03 } },
        { file: "images/scene-01/opt-2.png", prompt: "(demo)", model: "flux-2-pro", created_at: "2026-07-10T10:01:00Z", meta: { cost_usd: 0.03 } },
      ],
      selected_image: 0,
      clips: [
        { file: "clips/scene-01/take-01.mp4", prompt: "(demo)", source_image: "images/scene-01/opt-1.png", model: "kling-2.1", status: "completed", duration_s: 5.0, error: null, created_at: "2026-07-10T10:05:00Z", meta: { cost_usd: 0.18 }, take: 1, source_image_index: 0, kept: true },
        { file: "clips/scene-01/take-02.mp4", prompt: "(demo)", source_image: "images/scene-01/opt-1.png", model: "kling-2.1", status: "completed", duration_s: 5.0, error: null, created_at: "2026-07-10T10:06:00Z", meta: { cost_usd: 0.18 }, take: 2, source_image_index: 0, kept: false },
      ],
      prompt_preview: "warm golden hour light through windows, muted earth tones, amber, cream. Mila standing in a sunlit cafe doorway, full outfit visible head to toe. Pose: standing, facing the camera, full outfit visible head to toe. The subject is exactly the character 'Mila' shown in the first 2 reference images: preserve the face, hair, body proportions, and skin tone precisely. The subject is wearing exactly the clothing items shown in the remaining reference images, in order: (1) Linen midi skirt, (2) Knit cardigan. Reproduce every garment faithfully. photorealistic, cinematic composition, vertical framing, no added text, no watermarks.",
    },
    {
      id: "scene-02",
      description: "Mila three-quarter turn, looking over the shoulder, showcasing the outfit from a different angle",
      pose: "three-quarter turn, looking over the shoulder",
      character_id: "pchar-1", style_override: null,
      refs: [
        { file: "refs/scenes/scene-01/skirt.jpg", role: "garment", label: "Linen midi skirt", url: "https://shop.example/skirt" },
        { file: "refs/scenes/scene-01/cardigan.jpg", role: "garment", label: "Knit cardigan", url: "https://shop.example/cardigan" },
      ],
      images: [
        { file: "images/scene-02/opt-1.png", prompt: "(demo)", model: "flux-2-pro", created_at: "2026-07-10T10:02:00Z", meta: { cost_usd: 0.03 } },
        { file: "images/scene-02/opt-2.png", prompt: "(demo)", model: "flux-2-pro", created_at: "2026-07-10T10:03:00Z", meta: { cost_usd: 0.03 } },
      ],
      selected_image: 1,
      clips: [
        { file: "clips/scene-02/take-01.mp4", prompt: "(demo)", source_image: "images/scene-02/opt-2.png", model: "kling-2.1", status: "completed", duration_s: 5.0, error: null, created_at: "2026-07-10T10:07:00Z", meta: { cost_usd: 0.18 }, take: 1, source_image_index: 1, kept: true },
        { file: "clips/scene-02/take-02.mp4", prompt: "(demo)", source_image: "images/scene-02/opt-2.png", model: "kling-2.1", status: "completed", duration_s: 5.0, error: null, created_at: "2026-07-10T10:08:00Z", meta: { cost_usd: 0.18 }, take: 2, source_image_index: 1, kept: false },
      ],
      prompt_preview: "warm golden hour light through windows, muted earth tones, amber, cream. Mila three-quarter turn, looking over the shoulder, showcasing the outfit from a different angle. photorealistic, cinematic composition, vertical framing, no added text, no watermarks.",
    },
  ],
  clips: [
    { id: "clip-01", source_images: ["images/scene-01/opt-1.png"], prompt: "gentle sway", model: "kling-2.1", file: "clips/clip-01.mp4", status: "completed" as const, error: null, duration_s: 5.0, created_at: "2026-07-10T10:05:00Z", meta: { cost_usd: 0.18 }, kept: true },
    { id: "clip-02", source_images: ["images/scene-02/opt-2.png"], prompt: "slow turn", model: "kling-2.1", file: "clips/clip-02.mp4", status: "completed" as const, error: null, duration_s: 5.0, created_at: "2026-07-10T10:07:00Z", meta: { cost_usd: 0.18 }, kept: false },
  ],
  job: null,
  spent_usd: 0.84,
  notes: "",
  profile_characters: [DEMO_CHAR],
};

export const DEMO_HISTORY = [
  { type: "image" as const, scene_id: "scene-01", file: "images/scene-01/opt-1.png", prompt: "(demo) warm golden hour light, Mila in cafe doorway", model: "flux-2-pro", cost_usd: 0.03, created_at: "2026-07-10T10:00:00Z" },
  { type: "image" as const, scene_id: "scene-01", file: "images/scene-01/opt-2.png", prompt: "(demo) warm golden hour light, Mila in cafe doorway", model: "flux-2-pro", cost_usd: 0.03, created_at: "2026-07-10T10:01:00Z" },
  { type: "image" as const, scene_id: "scene-02", file: "images/scene-02/opt-1.png", prompt: "(demo) warm golden hour, Mila three-quarter turn", model: "flux-2-pro", cost_usd: 0.03, created_at: "2026-07-10T10:02:00Z" },
  { type: "image" as const, scene_id: "scene-02", file: "images/scene-02/opt-2.png", prompt: "(demo) warm golden hour, Mila three-quarter turn", model: "flux-2-pro", cost_usd: 0.03, created_at: "2026-07-10T10:03:00Z" },
  { type: "clip" as const, scene_id: "scene-01", file: "clips/scene-01/take-01.mp4", prompt: "(demo)", model: "kling-2.1", status: "completed", take: 1, kept: true, cost_usd: 0.18, created_at: "2026-07-10T10:05:00Z" },
  { type: "clip" as const, scene_id: "scene-01", file: "clips/scene-01/take-02.mp4", prompt: "(demo)", model: "kling-2.1", status: "completed", take: 2, kept: false, cost_usd: 0.18, created_at: "2026-07-10T10:06:00Z" },
  { type: "clip" as const, scene_id: "scene-02", file: "clips/scene-02/take-01.mp4", prompt: "(demo)", model: "kling-2.1", status: "completed", take: 1, kept: true, cost_usd: 0.18, created_at: "2026-07-10T10:07:00Z" },
  { type: "clip" as const, scene_id: "scene-02", file: "clips/scene-02/take-02.mp4", prompt: "(demo)", model: "kling-2.1", status: "completed", take: 2, kept: false, cost_usd: 0.18, created_at: "2026-07-10T10:08:00Z" },
];

export const DEMO_MODELS = {
  "flux-schnell": { kind: "image" as const, price: 0.003, notes: "fast drafts" },
  "flux-2-pro": { kind: "image" as const, price: 0.03, max_refs: 8, notes: "multi-ref drafts" },
  "nano-banana-pro": { kind: "image" as const, price: 0.134, max_refs: 14, notes: "best garment fidelity" },
  "seedance-2.0": { kind: "video" as const, price: 0.80, supports_i2v: true, notes: "most realistic" },
  "kling-2.1": { kind: "video" as const, price: 0.18, supports_i2v: true, notes: "cheapest I2V" },
};
