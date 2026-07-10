"""Lazy pipeline loading for the worker.

A 24 GB RTX 4090 cannot hold FLUX (~34 GB of weights) and a video model
at once, so exactly one pipeline is resident at a time; switching tasks
evicts the other and reloads from the network volume (~1-4 min). This
is why SceneForge's workflow batches all images before all clips —
model swaps are rare in practice.
"""

import gc

_current: tuple[str, object] | None = None


def get_pipeline(task: str):
    global _current
    if _current is not None and _current[0] == task:
        return _current[1]
    if _current is not None:
        import torch

        _current = None
        gc.collect()
        torch.cuda.empty_cache()
    pipe = _load_video() if task == "video" else _load_image()
    _current = (task, pipe)
    return pipe


def _vram_gb() -> float:
    import torch

    return torch.cuda.get_device_properties(0).total_memory / 1e9


def _load_image():
    import torch
    from diffusers import FluxPipeline

    pipe = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-schnell", torch_dtype=torch.bfloat16
    )
    if _vram_gb() < 40:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")
    return pipe


def _load_video():
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline

    mid = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
    vae = AutoencoderKLWan.from_pretrained(
        mid, subfolder="vae", torch_dtype=torch.float32
    )
    pipe = WanPipeline.from_pretrained(
        mid, vae=vae, torch_dtype=torch.bfloat16
    )
    if _vram_gb() < 40:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")
    return pipe
