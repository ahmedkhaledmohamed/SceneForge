"""Environment config and the model registry.

.env holds credentials and optional global default overrides. Creative
parameters (dimensions, speed, crossfade) live in each project's
project.json so they travel with the project.
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

TOGETHER_BASE_URL = "https://api.together.xyz/v1"

# supports_i2v: True = confirmed image-to-video, False = text-to-video only
# (selected image is ignored, with a warning), None = unverified — the tool
# attempts I2V and surfaces the API error if unsupported.
MODELS = {
    # --- images ---
    "flux-schnell": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.1-schnell",
        "price": 0.003,
        "steps": 4,
        "notes": "fast, cheap drafts",
    },
    "flux-dev": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.1-dev",
        "price": 0.025,
        "steps": 28,
        "notes": "higher quality, slower",
    },
    # --- multi-reference models (character + garment conditioning) ---
    "flux-2-pro": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.2-pro",
        "price": 0.03,
        "max_refs": 8,
        "notes": "multi-ref drafts, $0.03/MP",
    },
    "nano-banana-pro": {
        "kind": "image",
        "backend": "together",
        "id": "google/gemini-3-pro-image",
        "price": 0.134,
        "max_refs": 14,
        "fallback": "flux-2-pro",
        "notes": "best garment fidelity + character consistency",
    },
    # --- video ---
    "seedance-2.0": {
        "kind": "video",
        "backend": "together",
        "id": "ByteDance/Seedance-2.0",
        "price": 0.80,  # $0.16/sec at 720p, 5s clip
        "supports_i2v": True,
        "notes": "most realistic",
    },
    "veo-3.0-fast": {
        "kind": "video",
        "backend": "together",
        "id": "google/veo-3.0-fast",
        "price": 0.40,
        "supports_i2v": None,
        "notes": "mid-price",
    },
    "kling-2.1": {
        "kind": "video",
        "backend": "together",
        "id": "kwaivgI/kling-2.1-standard",
        "price": 0.18,
        "supports_i2v": True,
        "notes": "cheapest I2V",
    },
    # --- self-hosted on RunPod serverless (see runpod-worker/) ---
    "runpod-flux": {
        "kind": "image",
        "backend": "runpod",
        "id": "black-forest-labs/FLUX.1-schnell",
        "price": 0.005,  # estimate; actual cost computed per artifact
        "gpu_price_per_s": 0.000306,  # RTX 4090 flex, verified 2026-07
        "timeout_s": 600,
        "fallback": "flux-schnell",
        "notes": "self-hosted FLUX on RunPod 4090",
    },
    "runpod-wan-i2v": {
        "kind": "video",
        "backend": "runpod",
        "id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
        "price": 0.10,  # estimate; actual cost computed per artifact
        "gpu_price_per_s": 0.000306,
        "supports_i2v": True,
        "timeout_s": 1800,  # cold model load + ~9 min generation
        "fallback": "seedance-2.0",
        "notes": "self-hosted Wan2.2-TI2V-5B on RunPod 4090, 720p",
    },
    # --- zero-cost test backends (ffmpeg lavfi) ---
    "fake-image": {
        "kind": "image",
        "backend": "fake",
        "id": "lavfi/color",
        "price": 0.0,
        "max_refs": 14,  # mirrors nano-banana-pro so ref flow is testable
        "notes": "test backend",
    },
    "fake-video": {
        "kind": "video",
        "backend": "fake",
        "id": "lavfi/testsrc",
        "price": 0.0,
        "supports_i2v": False,
        "notes": "test backend",
    },
}

DEFAULT_IMAGE_MODEL = os.environ.get("SCENEFORGE_IMAGE_MODEL", "flux-schnell")
DEFAULT_VIDEO_MODEL = os.environ.get("SCENEFORGE_VIDEO_MODEL", "seedance-2.0")
DEFAULT_LLM_MODEL = os.environ.get(
    "SCENEFORGE_LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"
)

VIDEO_POLL_INTERVAL_S = 5
VIDEO_TIMEOUT_S = 600

ASPECTS = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
}


def together_api_key() -> str:
    key = os.environ.get("TOGETHER_API_KEY")
    if not key:
        raise RuntimeError(
            "TOGETHER_API_KEY not set. Add it to a .env file (see .env.example)."
        )
    return key


def runpod_api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise RuntimeError(
            "RUNPOD_API_KEY not set. Add it to .env (see .env.example and "
            "runpod-worker/README.md for endpoint setup)."
        )
    return key


def runpod_endpoint_id() -> str:
    endpoint = os.environ.get("RUNPOD_ENDPOINT_ID")
    if not endpoint:
        raise RuntimeError(
            "RUNPOD_ENDPOINT_ID not set. Create a serverless endpoint "
            "(runpod-worker/README.md) and add its id to .env."
        )
    return endpoint


def resolve_model(key: str, kind: str) -> dict:
    """Look up a model by registry key, enforcing kind ('image' or 'video')."""
    model = MODELS.get(key)
    if model is None:
        valid = ", ".join(k for k, m in MODELS.items() if m["kind"] == kind)
        raise ValueError(f"Unknown {kind} model '{key}'. Valid options: {valid}")
    if model["kind"] != kind:
        raise ValueError(f"Model '{key}' is a {model['kind']} model, not {kind}")
    return {"key": key, **model}
