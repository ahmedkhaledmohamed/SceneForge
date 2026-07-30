# Image Editing / Inpainting Plan for SceneForge

## Problem
When a generated image is 90% right but one detail is wrong (wrong shoe color, bad hand, garment texture off), the only option is full regeneration. This wastes money and loses the good parts. Higgsfield has inline editing tools. SceneForge needs at minimum: region selection + regeneration (inpainting).

## Approach: Together AI Inpainting via FLUX.1-Fill

Together AI supports inpainting via the FLUX.1-Fill-dev model ($0.05/image) — you send an image + a mask (black = keep, white = edit) + a prompt describing what to put in the masked region. This is the simplest path: no new providers, same API key, same backend pattern.

## Implementation Plan

### Step 1: Canvas mask editor component
**Branch:** `feat/mask-editor`

New React component `MaskEditor.tsx` — opens in a modal over a generated image. User draws on the image to create a mask:
- Paint brush tool (adjustable radius) 
- Eraser to undo mask regions
- Clear all / invert
- The mask is a canvas overlay rendered as a semi-transparent red/pink layer
- Export as PNG (white where painted, black where untouched)

No backend changes. Pure frontend component.

### Step 2: Inpainting backend
**Branch:** `feat/inpainting-backend`

- Add `flux-fill` model to `config.py` MODELS dict (kind: "inpaint", price: $0.05)
- Add `src/sceneforge/backends/inpaint.py` — calls Together AI's image endpoint with `image` + `mask` + `prompt` params
- Add `POST /profiles/{prof}/projects/{slug}/scenes/{sid}/images/{idx}/inpaint` endpoint:
  - Accepts: mask image (PNG upload), prompt (text), model (default flux-fill)
  - Sends original image + mask + prompt to Together AI
  - Saves result as a new image artifact with `inpainted_from` field
  - Returns the new image
- Add `inpainted_from: str = ""` to `ImageArtifact` dataclass

### Step 3: Inpaint UI integration
**Branch:** `feat/inpaint-ui`

- On each image in the scene gallery, add an "Edit" button (next to Upgrade)
- Clicking "Edit" opens the MaskEditor modal with the image loaded
- User paints the region they want to change
- Text field below for the edit prompt (e.g. "white sneakers instead of brown")
- "Apply" button sends mask + prompt to the inpaint endpoint
- Result appears as a new image option in the scene
- Original image preserved — inpainting is non-destructive

### Step 4: Quick edit presets
**Branch:** `feat/edit-presets`

Common edit operations as one-click buttons (no mask drawing needed):
- "Fix hands" — auto-masks hand regions using a simple heuristic or full-image prompt
- "Change background" — auto-masks everything except the subject
- "Enhance face" — auto-masks face region
These use predefined prompts + automatic mask generation.

## Cost
- Inpainting: $0.05 per edit (FLUX.1-Fill-dev on Together AI)
- Much cheaper than full regeneration ($0.03-0.134 for a new image)
- Show cost on the "Apply" button

## Alternative: Gemini/Imagen Edit
Google's Gemini models support image editing via natural language ("change the shoes to white"). This would be even simpler — no mask needed, just a text instruction. But it requires a Gemini API key (separate from Together AI). Could be added as a second editing backend later.

## Dependencies
- Together AI FLUX.1-Fill-dev model (already available on their API)
- HTML5 Canvas for mask drawing (no new npm deps)
- No new Python deps

## Estimated effort
- Step 1 (mask editor): ~200 lines of React
- Step 2 (backend): ~100 lines of Python
- Step 3 (UI integration): ~50 lines in ProjectBoard
- Step 4 (presets): stretch goal, ~100 lines

Total: 4 PRs, ~450 lines of code.
