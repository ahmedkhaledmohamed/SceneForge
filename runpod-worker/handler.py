"""RunPod serverless worker for SceneForge.

One container image serves three tasks, discriminated by input.task:

  image  — FLUX.1-schnell text-to-image
  video  — Wan2.1-I2V-14B-480P image-to-video
  warmup — download model weights into the network-volume HF cache

How this runs on RunPod:
  runpod.serverless.start() long-polls the endpoint's job queue. Each
  submitted job's JSON arrives here as job["input"]; whatever the
  handler returns becomes the job's "output" in the /status response.
  Returning {"error": ...} (or raising) marks the job FAILED.

Media travels as base64 inside the job payload: inputs are capped at
10 MB on /run (a 720x1280 PNG is ~1-2 MB, fine) and a 5s 480p mp4
output is 1-4 MB. If outputs ever outgrow this (e.g. a 720p model),
the escape hatch is writing to the network volume and fetching via
RunPod's S3-compatible API.

Model weights live on the attached network volume — the Dockerfile sets
HF_HOME=/runpod-volume/huggingface-cache — so cold-starting workers
load from disk instead of re-downloading ~100 GB from HuggingFace.

Local smoke test (no GPU needed for the dispatch logic):
  python handler.py --test_input '{"input": {"task": "nope"}}'
"""

import base64
import io
import tempfile
import time

import runpod

from pipelines import get_pipeline


def _image(inp: dict) -> dict:
    import torch

    pipe = get_pipeline("image")
    t0 = time.time()
    generator = (
        torch.Generator("cpu").manual_seed(inp["seed"])
        if inp.get("seed") is not None else None
    )
    result = pipe(
        prompt=inp["prompt"],
        # FLUX wants dimensions in multiples of 16
        width=inp.get("width", 720) // 16 * 16,
        height=inp.get("height", 1280) // 16 * 16,
        num_inference_steps=4,   # schnell is distilled for 4 steps
        guidance_scale=0.0,      # schnell ignores CFG
        generator=generator,
    )
    buf = io.BytesIO()
    result.images[0].save(buf, format="PNG")
    return {
        "image_b64": base64.b64encode(buf.getvalue()).decode(),
        "gen_time_s": round(time.time() - t0, 1),
    }


def _video(inp: dict) -> dict:
    from diffusers.utils import export_to_video
    from PIL import Image

    pipe = get_pipeline("video")
    image = Image.open(io.BytesIO(base64.b64decode(inp["image_b64"]))).convert("RGB")

    # Snap dimensions to the model's 480P training grid: fit the source
    # aspect ratio into max_area, rounded down to VAE-stride multiples
    # (this is the Wan model card's own sizing math).
    max_area = 480 * 832
    aspect = image.height / image.width
    mod = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
    height = round((max_area * aspect) ** 0.5) // mod * mod
    width = round((max_area / aspect) ** 0.5) // mod * mod
    image = image.resize((width, height))

    t0 = time.time()
    frames = pipe(
        image=image,
        prompt=inp["prompt"],
        height=height,
        width=width,
        num_frames=inp.get("num_frames", 81),  # 81 frames @ 16 fps ≈ 5s
        guidance_scale=5.0,
    ).frames[0]
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        export_to_video(frames, f.name, fps=inp.get("fps", 16))
        video_b64 = base64.b64encode(open(f.name, "rb").read()).decode()
    return {
        "video_b64": video_b64,
        "width": width,
        "height": height,
        "gen_time_s": round(time.time() - t0, 1),
    }


def _warmup(inp: dict) -> dict:
    """One-time weight download into the network volume's HF cache.

    Run this once after creating the endpoint (~10-15 min of GPU time).
    Every later cold start loads from the volume instead of the network.
    """
    from huggingface_hub import snapshot_download

    t0 = time.time()
    paths = {}
    for repo in (
        "black-forest-labs/FLUX.1-schnell",
        "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers",
    ):
        paths[repo] = snapshot_download(repo)
    return {"downloaded": paths, "time_s": round(time.time() - t0, 1)}


def handler(job: dict) -> dict:
    inp = job["input"]
    dispatch = {"image": _image, "video": _video, "warmup": _warmup}
    task = inp.get("task")
    if task not in dispatch:
        return {"error": f"unknown task {task!r}; expected one of {sorted(dispatch)}"}
    return dispatch[task](inp)


runpod.serverless.start({"handler": handler})
