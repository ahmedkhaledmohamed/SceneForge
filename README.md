# SceneForge

[![CI](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmedkhaledmohamed/SceneForge/actions/workflows/ci.yml)

**Local-first AI video production.** One pipeline from concept to finished short-form video:

```
concept → LLM scene breakdown → image options per scene → pick → image-to-video → stitched 9:16 final cut
```

Built to replace a real content creator's manual workflow (Midjourney → Higgsfield → CapCut) where every generation is an isolated prompt and scenes drift apart visually.

## Why it exists: the style context

The core problem with prompt-by-prompt generation is **visual inconsistency across scenes**. SceneForge fixes this with a project-level *style anchor* — mood, palette, lighting captured once at project creation and prepended to every image and video prompt automatically:

```
"warm golden hour light through windows, muted earth tones, amber, cream. {scene description}. photorealistic, cinematic composition, no text."
 └────────────────── style anchor (per project) ─────────────────┘                └───────── suffix (per project) ─────────┘
```

Per-scene overrides are supported, and every generated artifact records the exact composed prompt and model used — the project file is a full generation history.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env    # add your TOGETHER_API_KEY
brew install ffmpeg     # if you don't have it

sceneforge create "autumn morning"       # prompts for concept + style
cd autumn-morning
sceneforge add-scenes --count 6          # LLM breakdown, confirm before saving
sceneforge generate-images               # N options per scene, style anchor applied
sceneforge select scene-01 2             # pick winners
sceneforge generate-clips                # animate stills (image-to-video)
sceneforge stitch                        # 2x speed + crossfades → output/final.mp4
```

Or drive everything from a browser:

```bash
sceneforge ui --dir ~/videos             # http://127.0.0.1:8000
```

The web UI and CLI share the same `project.json` state — compare image options side by side, click to select, watch clips inline.

## Models

Model choice is part of the workflow, not a config constant — pick per run with `--model`, see prices with `sceneforge models`:

| Key | Kind | Price | Notes |
|---|---|---|---|
| `flux-schnell` | image | $0.003 | fast drafts (default) |
| `flux-dev` | image | $0.025 | higher quality |
| `seedance-2.0` | video | $0.80/clip | most realistic I2V (default) |
| `veo-3.0-fast` | video | $0.40/clip | mid-price |
| `kling-2.1` | video | $0.18/clip | cheapest hosted I2V |
| `fake-image` / `fake-video` | test | $0 | ffmpeg-generated, powers the test suite |

Generation is **idempotent**: re-running a batch skips what's done, failed jobs are recorded and retried on the next run, `--force`/`regenerate` redoes on demand. `sceneforge status` shows progress and estimated remaining cost.

## Architecture

```
src/sceneforge/
├── cli.py          typer commands (create/add-scenes/generate-*/select/stitch/status/ui)
├── web.py          FastAPI + htmx local UI, background jobs over the same ops
├── ops.py          generation loops shared by CLI and web
├── project.py      data model + project.json persistence (atomic writes)
├── prompts.py      style-context composition
├── breakdown.py    LLM scene breakdown (JSON-validated, retry on parse failure)
├── stitch.py       two-pass ffmpeg: normalize (speed/fps/geometry) → xfade chain
└── backends/       pluggable generation backends
    ├── base.py             ImageBackend / VideoBackend interfaces
    ├── together_image.py   FLUX via Together AI REST
    ├── together_video.py   Seedance/Veo/Kling via Together AI (submit → poll → download)
    └── fake.py             zero-cost lavfi backends for tests
```

Projects are plain directories — `project.json` plus `images/`, `clips/`, `output/`. No database, no accounts, no cloud dependency beyond the generation APIs.

## Development

```bash
pip install -e ".[dev]"
pytest        # entire suite runs at $0 — fake backends + synthetic ffmpeg fixtures
```

CI runs the full suite on every PR (no API secrets needed).

## Roadmap

- **Cloud GPU backend** — self-hosted Wan2.1 I2V + FLUX on RunPod serverless (~$0.10/clip vs $0.80), with automatic fallback to hosted APIs
- Audio/music track support
- Text overlays
- Local Apple Silicon backends (`pip install -e ".[local]"`) once the PyTorch/Python 3.14 story settles
