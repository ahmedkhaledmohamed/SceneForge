# SceneForge

[![CI](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml)

**Local-first AI video production.** Concept to finished short-form video in one tool:

```
profile → project → outfit + items → scenes → image options → select → video takes → export
```

Built for a real content creator's workflow: shoppable outfit posts where a consistent character doll wears photographed clothing items, multiple clips are compared, and the best takes are exported to CapCut with shop links.

## Studio

The daily-driver interface. Run locally — it serves a React SPA backed by a FastAPI JSON API:

```bash
pip install -e .
sceneforge studio        # http://127.0.0.1:8000 (~/SceneForge as home)
```

Everything is **profile-scoped**: a profile is a brand/workspace with global characters, style defaults, and seeds shared across all projects within it.

### The workflow

1. **Create a profile** — name your brand, set a style anchor, add your character doll with reference images
2. **New project** — one project per post/video, inherits profile defaults
3. **Add outfit + items** — clothing pieces with product photos and shop URLs
4. **Process outfit** — one click: creates pose scenes, generates multi-reference images (character + garment refs), auto-selects the first option
5. **Refine** — swap models, edit descriptions, regenerate individual scenes with prompt preview
6. **Generate takes** — batch video clips for all scenes, compare, mark keepers
7. **Export** — kept takes + links.txt in a CapCut-ready folder, or download as zip
8. **Stitch** — optional: speed-adjusted crossfade final cut

### Key features

- **Multi-reference image composition** — character identity refs + outfit item photos → dressed character (FLUX.2-pro $0.03 drafts, Nano Banana Pro $0.134 premium)
- **LLM brainstorm** — describe the concept, the AI suggests scene descriptions
- **Cost tracking** — every artifact records its GPU cost; buttons show estimated totals before you commit
- **Profile characters** — `pchar-*` IDs resolve across all projects; identity refs update globally
- **Import existing assets** — bring in images and clips from your library
- **Scene reorder** — order determines stitch output
- **Duplicate project** — copy settings + scenes without generated media

## Models

Pick per operation with model dropdowns, see prices live:

| Key | Kind | Price | Refs | Notes |
|---|---|---|---|---|
| `flux-schnell` | image | $0.003 | – | fast drafts (default) |
| `flux-dev` | image | $0.025 | – | higher quality |
| `flux-2-pro` | image | $0.03 | 8 | multi-reference drafts |
| `nano-banana-pro` | image | $0.134 | 14 | best garment fidelity + character consistency |
| `seedance-2.0` | video | $0.80/clip | – | most realistic I2V (default) |
| `veo-3.0-fast` | video | $0.40/clip | – | mid-price |
| `kling-2.1` | video | $0.18/clip | – | cheapest hosted I2V |
| `runpod-flux` / `runpod-wan-i2v` | both | ~$0.03/~$0.10 | – | self-hosted GPU, 720p Wan2.2-TI2V-5B (see runpod-worker/) |
| `fake-image` / `fake-video` | test | $0 | 14 | ffmpeg-generated, powers the test suite |

## Architecture

```
src/sceneforge/
├── cli.py              typer CLI (create/add-scenes/generate/select/stitch/studio)
├── profile.py          profile data model (SCENEFORGE_HOME layout)
├── project.py          project data model + project.json persistence
├── ops.py              generation loops shared by CLI and API
├── prompts.py          style-context + character/garment prompt composition
├── breakdown.py        LLM scene breakdown (Together AI)
├── stitch.py           two-pass ffmpeg: normalize → xfade chain
├── config.py           model registry + env config
├── server/
│   ├── api.py          FastAPI JSON API (profile-scoped routes)
│   ├── jobs.py         background job management
│   └── uploads.py      multipart upload validation
└── backends/
    ├── together_image.py   FLUX via Together AI
    ├── together_video.py   Seedance/Veo/Kling via Together AI
    ├── runpod_backend.py   self-hosted FLUX/Wan on RunPod
    └── fake.py             zero-cost test backends

frontend/               React SPA (Vite + react-query + react-router)
runpod-worker/          RunPod serverless GPU worker (Wan2.2-TI2V-5B + FLUX.1-schnell)
site/                   static landing page (Vercel)
```

Projects are plain directories — `project.json` plus `images/`, `clips/`, `output/`. No database, no accounts, no cloud dependency beyond the generation APIs.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env    # add your TOGETHER_API_KEY
brew install ffmpeg     # if you don't have it

sceneforge studio       # Studio SPA at http://127.0.0.1:8000
```

Or drive everything from the CLI:

```bash
sceneforge create "autumn morning"       # concept + style → project
sceneforge add-scenes --count 6          # LLM breakdown
sceneforge generate-images               # N options per scene
sceneforge select scene-01 2             # pick winners
sceneforge generate-clips                # I2V animation
sceneforge stitch                        # final cut
```

## Development

```bash
pip install -e ".[dev]"
pytest                   # 76 tests, $0 (fake backends)
cd frontend && npm i && npm run dev     # SPA dev server at :5173
```

CI runs the full suite on every PR (no API secrets needed).

## Deploy

```bash
cd frontend && vercel --prod     # sceneforge-studio project
cd site && vercel --prod         # sceneforge landing page
```

RunPod worker images are built via GitHub Actions — see `runpod-worker/README.md`.
