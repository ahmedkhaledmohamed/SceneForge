"""RunPod serverless worker for SceneForge.

One container image serves three tasks, discriminated by input.task:

  image  — FLUX.1-schnell text-to-image
  video  — Wan2.2-TI2V-5B text+image-to-video (720p, fits 24GB)
  warmup — download model weights into the network-volume HF cache

Media travels as base64 inside the job payload: inputs are capped at
10 MB on /run (a 720x1280 PNG is ~1-2 MB, fine).

Model weights live on the attached network volume — the Dockerfile sets
HF_HOME=/runpod-volume/huggingface-cache — so cold-starting workers
load from disk instead of re-downloading from HuggingFace.
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
        width=inp.get("width", 720) // 16 * 16,
        height=inp.get("height", 1280) // 16 * 16,
        num_inference_steps=4,
        guidance_scale=0.0,
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

    # Wan2.2-TI2V-5B native 720p grid: 1280x704 or 704x1280
    # Snap to the nearest valid resolution preserving aspect ratio
    mod = 16
    if image.height > image.width:
        width, height = 704, 1280
    else:
        width, height = 1280, 704
    image = image.resize((width, height))

    t0 = time.time()
    frames = pipe(
        image=image,
        prompt=inp["prompt"],
        height=height,
        width=width,
        num_frames=inp.get("num_frames", 121),  # 121 frames @ 24 fps ≈ 5s
        guidance_scale=5.0,
        num_inference_steps=50,
    ).frames[0]
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        export_to_video(frames, f.name, fps=inp.get("fps", 24))
        video_b64 = base64.b64encode(open(f.name, "rb").read()).decode()
    return {
        "video_b64": video_b64,
        "width": width,
        "height": height,
        "gen_time_s": round(time.time() - t0, 1),
    }


DEFAULT_WARMUP_REPOS = [
    "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
    "black-forest-labs/FLUX.1-schnell",
]


def _warmup(inp: dict) -> dict:
    from huggingface_hub import snapshot_download

    t0 = time.time()
    paths = {}
    for repo in inp.get("repos") or DEFAULT_WARMUP_REPOS:
        paths[repo] = snapshot_download(repo)
    return {"downloaded": paths, "time_s": round(time.time() - t0, 1)}


def _cleanup(inp: dict) -> dict:
    import os
    import shutil

    cache_dir = os.environ.get("HF_HOME", "/runpod-volume/huggingface-cache")
    models_dir = os.path.join(cache_dir, "hub")
    patterns = inp.get("patterns", ["Wan2.1"])
    removed = []
    if os.path.isdir(models_dir):
        for name in os.listdir(models_dir):
            if any(p in name for p in patterns):
                path = os.path.join(models_dir, name)
                shutil.rmtree(path, ignore_errors=True)
                removed.append(name)
    return {"removed": removed}


def handler(job: dict) -> dict:
    inp = job["input"]
    dispatch = {"image": _image, "video": _video, "warmup": _warmup, "cleanup": _cleanup}
    task = inp.get("task")
    if task not in dispatch:
        return {"error": f"unknown task {task!r}; expected one of {sorted(dispatch)}"}
    return dispatch[task](inp)


runpod.serverless.start({"handler": handler})
