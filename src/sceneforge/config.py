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
    # --- zero-cost test backends (ffmpeg lavfi) ---
    "fake-image": {
        "kind": "image",
        "backend": "fake",
        "id": "lavfi/color",
        "price": 0.0,
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


def resolve_model(key: str, kind: str) -> dict:
    """Look up a model by registry key, enforcing kind ('image' or 'video')."""
    model = MODELS.get(key)
    if model is None:
        valid = ", ".join(k for k, m in MODELS.items() if m["kind"] == kind)
        raise ValueError(f"Unknown {kind} model '{key}'. Valid options: {valid}")
    if model["kind"] != kind:
        raise ValueError(f"Model '{key}' is a {model['kind']} model, not {kind}")
    return {"key": key, **model}
