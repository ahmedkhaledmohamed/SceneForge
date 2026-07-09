"""Lazy pipeline loading for the worker.

A 24 GB RTX 4090 cannot hold FLUX (~34 GB of weights) and Wan-14B at
once, so exactly one pipeline is resident at a time; switching tasks
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


def _load_image():
    import torch
    from diffusers import FluxPipeline

    pipe = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-schnell", torch_dtype=torch.bfloat16
    )
    # Offloading keeps only the active submodule on the GPU — required
    # to fit schnell's full weight set next to activations in 24 GB.
    pipe.enable_model_cpu_offload()
    return pipe


def _load_video():
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from transformers import CLIPVisionModel

    mid = "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"
    # Per the model card: vision encoder + VAE in fp32, transformer bf16
    image_encoder = CLIPVisionModel.from_pretrained(
        mid, subfolder="image_encoder", torch_dtype=torch.float32
    )
    vae = AutoencoderKLWan.from_pretrained(
        mid, subfolder="vae", torch_dtype=torch.float32
    )
    pipe = WanImageToVideoPipeline.from_pretrained(
        mid, vae=vae, image_encoder=image_encoder, torch_dtype=torch.bfloat16
    )
    # Mandatory on 24 GB: the 14B transformer alone is ~28 GB in bf16.
    # A 48 GB card (A6000) runs without this and is noticeably faster.
    pipe.enable_model_cpu_offload()
    return pipe
