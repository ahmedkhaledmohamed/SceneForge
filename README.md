# SceneForge

[![CI](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml)

**AI video production studio.** Concept to finished short-form video in one tool:

```
profile → project → scenes + reference images → generate → select → clips → export
```

Multi-reference AI image composition, per-scene generation with reference images, configurable video clips, and direct download. Built for content creators who need consistent visuals across scenes.

## Studio

A React SPA backed by a FastAPI API. Deploy on Railway or run locally:

```bash
# Railway (recommended): connect repo, add volume at /data, set TOGETHER_API_KEY
# Or locally:
pip install -e .
sceneforge studio
```

Everything is **profile-scoped**: a profile is a brand/workspace with global characters, style defaults, and API keys shared across all projects within it.

### The workflow

1. **Create a profile** — name your brand, set a style anchor, add recurring characters with reference images
2. **New project** — one project per post/video, inherits profile defaults
3. **Add scenes** — describe each visual moment, drop reference images directly onto the scene
4. **Generate images** — per-scene: multi-reference composition (character + scene refs → composed image), multiple options
5. **Refine + select** — compare side by side, swap models, edit prompts, generation lanes show full history
6. **Create clips** — pick start image (and optional end image) from any scene, set model + duration + prompt, generate
7. **Download** — download clips directly, import into your video editor

### Key features

- **Self-contained scenes** — each scene owns its reference images
- **Clips as separate entities** — pick source images from any scene, set duration (3-10s), model, and motion prompt
- **Multi-reference image composition** — character refs + scene refs → composed image (FLUX.2-pro $0.03 drafts, Nano Banana Pro $0.134 premium)
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
| `nano-banana-pro` | image | $0.134 | 14 | best multi-ref fidelity + character consistency |
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

## Deploy (remote)

The full stack (API + SPA + ffmpeg) runs from a single Docker image. Deploy to Railway, Render, or any Docker host with a persistent volume:

```bash
# Railway (recommended — auto-deploy from GitHub, ~$5/month)
# 1. Connect your repo at railway.app
# 2. Add a volume mounted at /data
# 3. Set env: TOGETHER_API_KEY=your-key
# 4. Deploy — the Dockerfile handles everything

# Or run the Docker image directly:
docker build -t sceneforge .
docker run -p 8000:8000 -v sceneforge-data:/data \
  -e TOGETHER_API_KEY=your-key sceneforge
```

API keys can also be set per-profile in Settings instead of env vars.

## Deploy (local)

```bash
pip install -e .
sceneforge studio    # auto-opens browser at http://127.0.0.1:8000
```

## Development

```bash
pip install -e ".[dev]"
pytest                   # 77 tests, $0 (fake backends)
cd frontend && npm i && npm run dev     # SPA dev server at :5173
```

CI runs the full suite on every PR (no API secrets needed).
