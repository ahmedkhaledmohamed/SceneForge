# SceneForge Feature Execution Plan

20 steps. Each step = one branch → one PR → merge. Execute in order.

---

## Step 1: Prompt Enhancement Layer
**Branch:** `feat/prompt-enhance`

Add an LLM-powered prompt enhancement system. When generating scene images, the user's short description gets auto-enhanced using the scene's refs, style anchor, and character context.

Backend changes:
- In `src/sceneforge/prompts.py`, add `enhance_prompt(project, scene, profile) -> str` that calls the LLM (Together AI, model from `config.DEFAULT_LLM_MODEL` which is already Llama-3.3-70B) with a system prompt like: "You are a prompt engineer for AI image generation. Given a scene description and context, expand it into a detailed, high-quality generation prompt. Keep the user's intent. Add composition, lighting, and detail guidance. Output ONLY the enhanced prompt, nothing else."
- The input to the LLM should include: style anchor, scene description, character description (if any), garment labels from refs, and the current suffix.
- In `src/sceneforge/ops.py`, in the image generation flow, call `enhance_prompt()` before `compose_prompt()`. Store the enhanced prompt in a new field on `ImageArtifact`.
- Add a new API endpoint `POST /profiles/{prof}/projects/{slug}/scenes/{sid}/enhance-prompt` that returns the enhanced prompt as preview without generating.
- In `src/sceneforge/project.py`, add `enhanced_prompt: str = ""` field to `ImageArtifact`.

Frontend changes:
- In `ProjectBoard.tsx`, add an "Enhance" button next to the scene description. When clicked, calls the enhance endpoint, shows the result in an editable textarea. User can accept (replaces description) or discard.
- Show a small "enhanced" pill on images that used an enhanced prompt.
- Add a toggle in project settings: "Auto-enhance prompts" (default off). When on, every generation auto-enhances before sending.

Tests:
- Add `tests/test_prompt_enhance.py` — mock the LLM call, verify the system prompt includes refs and style anchor, verify the enhanced prompt is stored on the artifact.

---

## Step 2: Shot Type Tagging
**Branch:** `feat/shot-types`

Add shot type classification to clips so the system can route to optimal models.

Backend changes:
- In `src/sceneforge/project.py`, add `shot_type: str = ""` field to the `Clip` dataclass. Valid values: "hero", "detail", "transition", "broll", "closeup", "wide", "overhead", "" (unset).
- Add `SHOT_TYPES` constant dict in `src/sceneforge/config.py`: `{"hero": {"label": "Hero shot", "description": "Key product/character moment", "recommended_model": "seedance-2.0-or"}, "detail": {"label": "Detail/Close-up", ...}, "transition": {...}, "broll": {...}}` with recommended models and cost tiers per type.
- In `src/sceneforge/server/api.py`, update the clip create/patch endpoints to accept `shot_type`.
- Add `GET /api/shot-types` endpoint returning the SHOT_TYPES config.

Frontend changes:
- In `ProjectBoard.tsx`, in the clip creation dialog, add a "Shot type" dropdown with the shot types. Default to "" (auto-detect or unset).
- On existing clip cards, show the shot type as a colored pill if set.
- In the clip card actions, add ability to change shot type inline.
- Color-code shot types: hero=gold, detail=blue, transition=gray, broll=green.

Tests:
- Add test for clip creation with shot_type, verify it persists and loads.

---

## Step 3: Smart Model Routing
**Branch:** `feat/smart-routing`

Add an "Auto" model option that picks the best model based on shot type and budget.

Backend changes:
- In `src/sceneforge/config.py`, add a function `recommend_model(shot_type: str, budget_remaining: float | None = None, kind: str = "video") -> str` that maps shot types to recommended models. Logic: hero → seedance-2.0-or, detail → seedance-1.5-pro, transition → kling-2.1, broll → kling-2.1, closeup → seedance-1.5-pro, wide → kling-2.1, overhead → kling-2.1. If budget_remaining is provided and < $1, downgrade to cheapest option (kling-2.1 or runpod-wan-i2v).
- Add "auto" as a virtual model entry in the MODELS dict with kind="video", price=0 (resolved at generation time).
- In `src/sceneforge/ops.py`, when the clip model is "auto", resolve it via `recommend_model()` using the clip's shot_type and project's remaining budget (budget_usd - spent_usd).
- Store the actual resolved model on the clip after generation (not "auto").

Frontend changes:
- In the clip model picker dropdown, add "Auto (smart routing)" as the first option.
- When "Auto" is selected, show a tooltip/subtitle: "Will pick: {recommended_model} based on shot type".
- After generation, the clip card shows the actual model used, not "auto".

Tests:
- Test recommend_model() with various shot types and budgets.
- Test that "auto" resolves correctly during generation.

---

## Step 4: Draft → Premium Upgrade
**Branch:** `feat/draft-to-premium`

One-click re-generate an image with a better model, or upgrade a clip.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/scenes/{sid}/images/{img_id}/upgrade` that takes an optional `model` param (default: nano-banana-pro for images). It re-generates the same scene with the premium model, adds the result as a new image artifact, and marks it with `upgraded_from: str` field.
- In `src/sceneforge/project.py`, add `upgraded_from: str = ""` to `ImageArtifact`.
- For clips: add `POST /profiles/{prof}/projects/{slug}/clips/{cid}/upgrade` that creates a new clip with the same source_images and prompt but a better model. The new clip gets `upgraded_from` field pointing to the original clip ID.
- Add `upgraded_from: str = ""` to `Clip` dataclass.

Frontend changes:
- On each image in the scene gallery, add an "↑ Upgrade" button (only shown if current model is not already the most expensive).
- Show estimated cost of the upgrade: "Upgrade to nano-banana-pro ($0.134)".
- On clip cards, add "↑ Upgrade" button that creates a new clip with a better model.
- Upgraded artifacts show a small "upgraded from {model}" pill.
- Side-by-side comparison: when an upgraded version exists, show original and upgraded next to each other with model labels.

Tests:
- Test upgrade endpoint creates new artifact with correct model.
- Test upgraded_from field persists.

---

## Step 5: Batch Scene Generation
**Branch:** `feat/batch-scenes`

"Generate all scenes" button with parallel execution and structured progress.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/generate-all-scenes` endpoint. It starts a background job that iterates all scenes missing images and generates them in parallel (using ThreadPoolExecutor, max 3 concurrent).
- In `src/sceneforge/server/jobs.py`, update the Job model to support structured progress: `total: int`, `completed: int`, `current_label: str`, `results: list[dict]` (scene_id, status, cost, error).
- Each scene completion updates the job progress. Partial success is fine — if 4/6 succeed, the 4 are saved and the 2 failures are reported.
- Budget check: before starting, estimate total cost. If it exceeds remaining budget, return an error with the estimate.

Frontend changes:
- In `ProjectBoard.tsx`, add a "Generate all scenes" button in the Scenes tab header (next to "+ Scene").
- Show a confirmation dialog: "Generate images for {n} scenes. Estimated cost: ${estimate}. Continue?"
- During generation, show a progress bar: "3/6 scenes complete" with per-scene status indicators.
- When done, show a summary: "6 scenes generated. 5 succeeded, 1 failed. Total cost: $0.42"
- Failed scenes show an inline error with "Retry" button.

Tests:
- Test batch generation with fake backend, verify progress updates.
- Test partial failure handling.
- Test budget check rejects when over budget.

---

## Step 6: Batch Clip Generation
**Branch:** `feat/batch-clips`

"Generate clips for all kept images" with model mixing support.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/generate-all-clips` endpoint. Body: `{ "model": "auto" | specific_model, "seconds": 5, "shot_type_override": null }`.
- For each scene that has kept/selected images but no clips yet, create a clip using the best image as the start frame.
- If model is "auto", use smart routing per clip based on shot type.
- Parallel execution with ThreadPoolExecutor (max 2 concurrent — video gen is slower).
- Structured progress same as batch scenes.

Frontend changes:
- In the Clips tab header, add "Generate clips for all" button.
- Confirmation dialog shows: per-scene breakdown with model selection, total estimated cost.
- Allow overriding model per scene before starting.
- Progress bar with per-clip status.

Tests:
- Test batch clip generation with fake backend.
- Test auto model routing in batch context.

---

## Step 7: Full Pipeline (Generate → Pick → Clip)
**Branch:** `feat/generate-pipeline`

One-click "Produce project" that runs the full pipeline.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/produce` endpoint.
- Pipeline stages: (1) generate images for all scenes missing them, (2) auto-select the best image per scene (first image or highest-resolution), (3) create clips for each scene using the selected image.
- Each stage reports progress. The job tracks which stage it's in.
- In `src/sceneforge/server/jobs.py`, add `stage: str` and `stages: list[str]` fields.

Frontend changes:
- Add a prominent "Produce" button at the top of the project board.
- Shows a pipeline visualization: "Scenes → Images → Clips" with progress per stage.
- Each stage can be expanded to see individual item status.
- At completion, switches to the Clips tab showing all generated clips.

Tests:
- Test full pipeline with fake backend end-to-end.

---

## Step 8: AI Shot List Generator
**Branch:** `feat/shot-list-gen`

Given a concept, AI generates a complete list of scenes with descriptions, compositions, and shot types.

Backend changes:
- In `src/sceneforge/prompts.py`, add `generate_shot_list(concept: str, character_desc: str, num_scenes: int = 8, style_anchor: str = "") -> list[dict]`.
- Calls the LLM with a system prompt: "You are a creative director for social media content. Given a concept, generate a shot list for a photo/video series. For each shot, provide: description (what's in the scene), composition (camera angle, framing), shot_type (hero/detail/transition/broll/closeup/wide/overhead), and a suggested prompt for AI image generation. Output as JSON array."
- Parse the LLM response into structured data.
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/generate-shot-list` endpoint. Body: `{ "concept": "...", "num_scenes": 8 }`. Returns the generated shot list as JSON.
- Add `POST /profiles/{prof}/projects/{slug}/apply-shot-list` endpoint that takes the shot list and creates scenes from it (with descriptions, shot types pre-filled).

Frontend changes:
- In `ProjectBoard.tsx`, add a "Generate shot list" button (visible when project has 0 scenes or in a toolbar).
- Shows a dialog where user enters/edits the concept (pre-filled from project concept).
- Displays the generated shot list as editable cards. User can:
  - Edit any scene description
  - Remove scenes they don't want
  - Reorder scenes
  - Adjust shot types
- "Apply" button creates all scenes from the approved shot list.

Tests:
- Mock LLM, test shot list parsing.
- Test apply-shot-list creates correct scenes.

---

## Step 9: AI Director Mode
**Branch:** `feat/ai-director`

Full automated flow: concept → shot list → generate all → create clips.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/direct` endpoint.
- Combines: generate shot list → apply → generate all scenes → auto-select best images → generate clips.
- This is the "one-button" experience. The job has stages: "Planning", "Generating scenes", "Selecting best", "Generating clips".
- Accepts params: `{ "concept": "...", "num_scenes": 8, "video_model": "auto", "clip_seconds": 5 }`.

Frontend changes:
- Add a "Direct" button or mode toggle at project level.
- When activated, shows a minimal interface: concept input + character selection + style anchor.
- "Action" button starts the full pipeline.
- The UI shows real-time progress through all stages.
- At completion, user reviews the generated clips and keeps/discards.

Tests:
- End-to-end test with fake backends.

---

## Step 10: Project Templates
**Branch:** `feat/project-templates`

Save successful project structures as reusable templates.

Backend changes:
- In `src/sceneforge/project.py`, add a `Template` dataclass: `{ name, concept, style, scenes: list[TemplateScene] }` where TemplateScene has description, shot_type, composition but no generated content.
- In `src/sceneforge/server/api.py`:
  - `POST /profiles/{prof}/projects/{slug}/save-as-template` — extracts the structure (scene descriptions, shot types, style) without generated media.
  - `GET /profiles/{prof}/templates` — list saved templates.
  - `POST /profiles/{prof}/projects/from-template` — creates a new project from a template.
  - `DELETE /profiles/{prof}/templates/{name}` — delete a template.
- Templates stored as JSON files in `{profile_root}/templates/{name}.json`.
- Include 3 built-in templates: "Product lookbook" (10 scenes), "Day in the life" (8 scenes), "Character series" (6 scenes).

Frontend changes:
- In the "New project" flow, add "Start from template" option alongside blank project.
- Template picker shows built-in + saved templates with scene count preview.
- On a project page, add "Save as template" in a menu/dropdown.
- Templates page accessible from profile header.

Tests:
- Test save/load template round-trip.
- Test create project from template.

---

## Step 11: Sequence Builder
**Branch:** `feat/sequence-builder`

Arrange kept clips in timeline order and preview the sequence.

Backend changes:
- In `src/sceneforge/project.py`, add `sequence: list[str] = field(default_factory=list)` to Project — an ordered list of clip IDs representing the final sequence.
- In `src/sceneforge/server/api.py`:
  - `GET /profiles/{prof}/projects/{slug}/sequence` — returns the ordered sequence with clip details.
  - `PUT /profiles/{prof}/projects/{slug}/sequence` — body is `{ "clip_ids": ["clip-01", "clip-03", "clip-02"] }`.
  - `POST /profiles/{prof}/projects/{slug}/sequence/render` — stitches the clips in sequence order using ffmpeg into one video file.
- In `src/sceneforge/stitch.py`, update the stitch function to accept an ordered list of clip paths and concatenate them.

Frontend changes:
- Add a third tab: "Sequence" (alongside Scenes and Clips).
- Shows kept clips as draggable cards in a horizontal timeline.
- Drag to reorder. Visual preview of each clip as thumbnail.
- "Preview" button plays clips in sequence (HTML5 video elements playing sequentially).
- "Render" button stitches into one downloadable video.
- Show total duration and estimated render time.

Tests:
- Test sequence ordering persists.
- Test stitch with multiple clips.

---

## Step 12: Platform-Aware Export
**Branch:** `feat/platform-export`

Auto-format exports for TikTok, Reels, Shorts, Pinterest.

Backend changes:
- In `src/sceneforge/config.py`, add `PLATFORMS` dict:
  ```
  { "tiktok": { "aspect": "9:16", "max_duration": 60, "resolution": "1080x1920" },
    "reels": { "aspect": "9:16", "max_duration": 90, "resolution": "1080x1920" },
    "shorts": { "aspect": "9:16", "max_duration": 60, "resolution": "1080x1920" },
    "pinterest": { "aspect": "2:3", "max_duration": 60, "resolution": "1000x1500" } }
  ```
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/export/{platform}`.
  - Takes the rendered sequence (or individual clips).
  - Re-encodes via ffmpeg to match platform specs (resolution, codec, duration trim).
  - Returns the formatted file for download.
- For Pinterest: also export a static thumbnail (best frame extraction).

Frontend changes:
- In the Sequence tab, add "Export for..." dropdown with platform options.
- Each option shows the target specs (resolution, max duration, aspect ratio).
- If the sequence exceeds max duration, show a warning with option to trim.
- Download button per platform.

Tests:
- Test platform config resolution.
- Test ffmpeg re-encoding with fake video.

---

## Step 13: Caption & Copy Generation
**Branch:** `feat/caption-gen`

AI-generated captions, hashtags, and product descriptions.

Backend changes:
- In `src/sceneforge/prompts.py`, add `generate_caption(project, platform: str = "instagram") -> dict` that calls the LLM with scene descriptions, product refs (labels + URLs), and platform context.
- Returns: `{ "caption": "...", "hashtags": ["...", "..."], "cta": "Shop the look: [link]" }`.
- In `src/sceneforge/server/api.py`:
  - `POST /profiles/{prof}/projects/{slug}/generate-caption` — body: `{ "platform": "instagram", "tone": "playful" }`.
  - Returns generated caption with hashtags.
- Store generated captions in project: add `captions: dict[str, dict] = field(default_factory=dict)` to Project (keyed by platform).

Frontend changes:
- In the Sequence tab (or a new "Publish" section), add "Generate caption" button per platform.
- Shows editable caption preview with hashtags as pills (removable).
- "Copy to clipboard" button for the final caption.
- Tone selector: playful, professional, casual, minimal.

Tests:
- Mock LLM, test caption includes product refs.

---

## Step 14: Shop Link Cards
**Branch:** `feat/shop-links`

Generate visual product link cards for exports.

Backend changes:
- In `src/sceneforge/server/api.py`, add `POST /profiles/{prof}/projects/{slug}/link-card`.
  - Collects all scene refs that have URLs.
  - Generates a "shop the look" card image using PIL/Pillow: product thumbnails in a grid with labels and short URLs.
  - Returns the image as a downloadable PNG.
- Add `POST /profiles/{prof}/projects/{slug}/links-overlay` that generates a text overlay file (SRT-style or ASS subtitle) with product names timed to appear during their scene's clip.

Frontend changes:
- In the Sequence/Export area, add "Generate link card" button.
- Preview the generated card before downloading.
- "Copy link list" button that formats all URLs as a plain text list (for link-in-bio or caption).

Tests:
- Test link card generation with refs that have URLs.

---

## Step 15: Prompt Library
**Branch:** `feat/prompt-library`

Save, tag, and reuse successful prompts.

Backend changes:
- In `src/sceneforge/profile.py`, add a `SavedPrompt` dataclass: `{ id, text, tags: list[str], model, created, times_used: int }`.
- Add `saved_prompts: list[SavedPrompt]` to Profile.
- In `src/sceneforge/server/api.py`:
  - `GET /profiles/{prof}/prompts` — list all saved prompts, filterable by tag.
  - `POST /profiles/{prof}/prompts` — save a new prompt with tags.
  - `DELETE /profiles/{prof}/prompts/{pid}` — delete.
  - `POST /profiles/{prof}/prompts/{pid}/use` — increment usage counter, return the prompt text.
- When generating a scene image, if the resulting image is "kept", auto-suggest saving the prompt.

Frontend changes:
- In project board, add a "Prompt library" button/panel that slides in.
- Shows saved prompts with tags, usage count, and a "Use" button that pastes into the current scene description.
- On scene image cards that are kept, show "Save prompt" action.
- Tag editor: add/remove tags on prompts.
- Search/filter by tag.

Tests:
- Test CRUD for saved prompts.
- Test usage counter increment.

---

## Step 16: Asset Library
**Branch:** `feat/asset-library`

Profile-level tagged assets reusable across projects.

Backend changes:
- In `src/sceneforge/profile.py`, add `Asset` dataclass: `{ id, file, tags: list[str], label, role, url, created, projects_used: list[str] }`.
- Add `assets: list[Asset]` to Profile.
- In `src/sceneforge/server/api.py`:
  - `GET /profiles/{prof}/assets` — list all assets, filterable by tag/role.
  - `POST /profiles/{prof}/assets` — upload with tags and role.
  - `DELETE /profiles/{prof}/assets/{aid}`.
  - `POST /profiles/{prof}/projects/{slug}/scenes/{sid}/refs/from-asset/{aid}` — add an asset as a scene ref (copies or symlinks the file).
- When adding a scene ref, offer "From library" as an option alongside file upload.

Frontend changes:
- New "Library" section accessible from profile header.
- Grid view of all assets with thumbnails, tags as pills.
- Drag assets from library onto scene cards to add as refs.
- "Add to library" button on scene ref pills.
- Tag-based search and role filter (garment, prop, background, style).

Tests:
- Test asset CRUD and tag filtering.
- Test asset-to-ref flow.

---

## Step 17: Generation Analytics
**Branch:** `feat/gen-analytics`

Cost, quality, and model performance dashboards.

Backend changes:
- In `src/sceneforge/server/api.py`, add analytics endpoints:
  - `GET /profiles/{prof}/analytics` — aggregate stats across all projects:
    - Total spend by model, by month
    - Keep rate per model (kept clips / total clips)
    - Average cost per kept clip (the real metric)
    - Generation success rate per model
    - Spend trend (last 4 weeks)
  - `GET /profiles/{prof}/projects/{slug}/analytics` — per-project breakdown.
- Compute from existing data: iterate all projects, scenes, clips, image artifacts.

Frontend changes:
- New "Analytics" page accessible from profile header.
- Cards: total spend, average cost per post, best-value model.
- Charts: spend over time (bar chart), model usage distribution (pie), keep rate by model (bar).
- Per-project: cost breakdown, generation timeline.
- Use simple CSS-based charts (no chart library dependency) — horizontal bar charts and simple stats cards.

Tests:
- Test analytics computation with mock project data.

---

## Step 18: Style Consistency Scoring
**Branch:** `feat/style-scoring`

CLIP-based visual similarity scoring across scenes.

Backend changes:
- Add `src/sceneforge/backends/clip_scorer.py`:
  - Uses CLIP ViT-B/32 model via Together AI's embedding endpoint (or a lightweight local model).
  - `score_consistency(images: list[Path]) -> float` — average pairwise cosine similarity.
  - `find_outliers(images: list[Path], threshold: float = 0.7) -> list[int]` — indices of images that are below threshold similarity to the group.
- In `src/sceneforge/server/api.py`:
  - `POST /profiles/{prof}/projects/{slug}/score-consistency` — scores all kept/selected scene images.
  - Returns: `{ "score": 0.85, "outliers": [{ "scene_id": "...", "similarity": 0.62 }] }`.

Frontend changes:
- In project board header, add a "Consistency" badge showing the score (green >0.8, yellow 0.6-0.8, red <0.6).
- Outlier scenes highlighted with a warning indicator.
- "Check consistency" button to run scoring on demand.

Tests:
- Mock CLIP embeddings, test pairwise similarity computation.
- Test outlier detection.

---

## Step 19: Audio Layer
**Branch:** `feat/audio-layer`

Ambient sound and music generation for clips.

Backend changes:
- In `src/sceneforge/config.py`, add audio models to MODELS dict (e.g., Together AI audio models or a free SFX library).
- In `src/sceneforge/project.py`, add `audio_file: str = ""` and `audio_type: str = ""` to Clip (types: "ambient", "music", "voiceover", "none").
- In `src/sceneforge/server/api.py`:
  - `POST /profiles/{prof}/projects/{slug}/clips/{cid}/generate-audio` — generates ambient audio matching the scene description. Body: `{ "type": "ambient", "prompt": "café ambiance, gentle background chatter" }`.
  - Uses ffmpeg to merge audio with the clip video.
- Alternatively, integrate with a free SFX API or use the OpenRouter audio generation (Seedance 1.5 Pro supports_audio).

Frontend changes:
- On clip cards, add an "Audio" section.
- "Add audio" button with type selector (ambient, music, voiceover).
- Audio prompt input (pre-filled from scene description).
- Preview audio independently, then "Apply to clip" to merge.
- Mute/unmute toggle on clip preview.

Tests:
- Test audio merge with ffmpeg.
- Test audio file storage on clip.

---

## Step 20: Data Backup & Export
**Branch:** `feat/backup-export`

Full project zip export/import for portability and backup.

Backend changes:
- In `src/sceneforge/server/api.py`:
  - `GET /profiles/{prof}/projects/{slug}/export-zip` — creates a zip containing: project.json, all ref images, all generated images (kept only), all kept clips, and a manifest.json with metadata.
  - `POST /profiles/{prof}/import-zip` — uploads a zip file, creates a new project from it. Validates the manifest, copies media files, creates the project.json.
  - `GET /profiles/{prof}/export-all` — exports ALL projects as a single zip (for full backup).
- Use Python's zipfile module with streaming (ZipFile in memory or temp file).
- Include a `manifest.json` in the zip with: version, export_date, profile_name, project stats.

Frontend changes:
- In project board menu, add "Export as zip" option.
- Shows export progress (for large projects with many clips).
- In profile header, add "Backup all" button.
- In "New project" flow, add "Import from zip" option alongside blank/template.
- Drag-and-drop zip file onto the project list page to import.

Tests:
- Test zip export contains correct files.
- Test zip import creates valid project.
- Test round-trip: export → import → compare.
