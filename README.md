# GenerationStyled — SceneForge

Local-first AI video production CLI for the GenerationStyled content workflow.
Replaces the manual Midjourney/Higgsfield generation loop with one pipeline:

**concept → scene breakdown → image options → pick → image-to-video → stitched vertical video**

The core value: a project-level **style context** (shared prompt anchor) is
prepended to every generation, so all scenes share one visual language instead
of drifting like independent one-off prompts do.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # add your TOGETHER_API_KEY
```

Requires `ffmpeg` on PATH (`brew install ffmpeg`).

## Workflow

```bash
# 1. Create a project (prompts for concept + style: mood, palette, lighting)
sceneforge create "autumn morning"
cd autumn-morning

# 2. Break the concept into scenes (LLM-assisted, confirm before saving)
sceneforge add-scenes --count 6
#    ...or write them yourself:
sceneforge add-scenes --scene "steam rises from a mug" --scene "rain on the window"

# 3. Generate image options per scene (style anchor applied automatically)
sceneforge generate-images                # 3 options per scene by default
sceneforge generate-images scene-02 --model flux-dev   # higher quality for one scene

# 4. Look at images/scene-XX/opt-N.png, pick winners
sceneforge select scene-01 2

# 5. Animate the selected stills (image-to-video)
sceneforge generate-clips                 # uses the project's default video model
sceneforge generate-clips --model kling-2.1   # or pick a model per run

# 6. Final cut: 2x speed, 0.3s crossfades, no audio, 720x1280
sceneforge stitch

# Anytime
sceneforge status            # scene table + estimated remaining cost
sceneforge models            # available models, prices, I2V support
sceneforge regenerate scene-03 clip --model veo-3.0-fast
```

Generation commands are idempotent — re-running skips scenes that already
have what they need (so a failed batch resumes where it left off). Use
`--force` or `regenerate` to redo. Every artifact records the exact prompt
and model used in `project.json`.

## Models

| Key | Kind | Price | Notes |
|---|---|---|---|
| flux-schnell | image | $0.003 | fast drafts (default) |
| flux-dev | image | $0.025 | higher quality |
| seedance-2.0 | video | $0.80 | most realistic (default) |
| veo-3.0-fast | video | $0.40 | mid-price |
| kling-2.1 | video | $0.18 | cheapest confirmed I2V |
| fake-image / fake-video | test | $0 | ffmpeg-generated, for testing |

Model selection precedence: `--model` flag → project settings → global
default (`SCENEFORGE_*` in `.env`).

## Style context

- `style.anchor` — shared prefix from mood/palette/lighting, prepended to every prompt
- `scene.style_override` — replaces the anchor for one scene
- `style.suffix` — always appended (realism/framing/no-text directives)
- Composed prompt per generation: `anchor. scene description. suffix.`

## Development

```bash
pip install -e ".[dev]"
pytest                       # zero-cost: fake backends + lavfi fixtures, no API calls
```

Layout: `src/sceneforge/` — `cli.py` (typer commands), `project.py` (data
model + project.json), `prompts.py` (style composition), `stitch.py`
(ffmpeg normalize + xfade), `breakdown.py` (LLM scenes),
`backends/` (Together AI + fake lavfi backends).

Not in scope yet: audio/music, text overlays, web UI, local
Stable Diffusion / Wan2.1 backends (planned as `pip install -e ".[local]"`).
