"""Environment config and the model registry.

.env holds credentials and optional global default overrides. Creative
parameters (dimensions, speed, crossfade) live in each project's
project.json so they travel with the project.
"""

import os
import threading

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

TOGETHER_BASE_URL = "https://api.together.xyz/v1"

MODELS = {
    # --- images (Together AI) ---
    "flux-schnell": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.1-schnell",
        "price": 0.003,
        "steps": 4,
        "max_refs": 0,
        "resolutions": ["720x1280", "1280x720", "512x512", "1024x1024"],
        "params": ["seed", "steps", "width", "height", "negative_prompt"],
        "notes": "fast, cheap drafts — no multi-ref",
    },
    "flux-dev": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.1-dev",
        "price": 0.025,
        "steps": 28,
        "max_refs": 0,
        "resolutions": ["720x1280", "1280x720", "1024x1024"],
        "params": ["seed", "steps", "width", "height", "negative_prompt", "guidance_scale"],
        "notes": "higher quality, slower — no multi-ref",
    },
    "flux-2-pro": {
        "kind": "image",
        "backend": "together",
        "id": "black-forest-labs/FLUX.2-pro",
        "price": 0.03,
        "max_refs": 8,
        "resolutions": ["720x1280", "1280x720", "1024x1024"],
        "params": ["seed", "width", "height"],
        "notes": "multi-ref drafts (up to 8 reference images)",
    },
    "nano-banana-pro": {
        "kind": "image",
        "backend": "together",
        "id": "google/gemini-3-pro-image",
        "price": 0.134,
        "max_refs": 14,
        "fallback": "flux-2-pro",
        "resolutions": ["720x1280", "1280x720", "1024x1024"],
        "params": ["seed", "width", "height"],
        "notes": "highest quality multi-ref (up to 14 references)",
    },
    # --- video (Together AI) ---
    "seedance-2.0": {
        "kind": "video",
        "backend": "together",
        "id": "ByteDance/Seedance-2.0",
        "price": 0.80,
        "price_per_s": 0.16,
        "supports_i2v": True,
        "resolutions": ["720p"],
        "durations": [5],
        "params": ["seed", "seconds", "fps"],
        "notes": "most realistic I2V — expensive via Together",
    },
    "veo-3.0-fast": {
        "kind": "video",
        "backend": "together",
        "id": "google/veo-3.0-fast",
        "price": 0.40,
        "supports_i2v": None,
        "resolutions": ["720p"],
        "durations": [5, 8],
        "params": ["seed", "seconds"],
        "notes": "mid-price, I2V unverified",
    },
    "kling-2.1": {
        "kind": "video",
        "backend": "together",
        "id": "kwaivgI/kling-2.1-standard",
        "price": 0.18,
        "supports_i2v": True,
        "resolutions": ["720p"],
        "durations": [5, 10],
        "params": ["seed", "seconds"],
        "notes": "cheapest hosted I2V on Together",
    },
    # --- video (OpenRouter — cheaper Seedance) ---
    "seedance-1.5-pro": {
        "kind": "video",
        "backend": "openrouter",
        "id": "bytedance/seedance-1-5-pro",
        "price": 0.12,
        "price_per_s": 0.023,
        "supports_i2v": True,
        "supports_last_frame": True,
        "supports_audio": True,
        "resolutions": ["480p", "720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "durations": [4, 5, 6, 7, 8, 9, 10, 11, 12],
        "params": ["seed", "duration", "resolution", "aspect_ratio", "generate_audio"],
        "timeout_s": 600,
        "notes": "best value Seedance — $0.023/s via OpenRouter",
    },
    "seedance-2.0-or": {
        "kind": "video",
        "backend": "openrouter",
        "id": "bytedance/seedance-2.0",
        "price": 0.34,
        "price_per_s": 0.067,
        "supports_i2v": True,
        "supports_last_frame": True,
        "resolutions": ["480p", "720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "durations": [4, 5, 6, 7, 8, 9, 10],
        "params": ["seed", "duration", "resolution", "aspect_ratio"],
        "timeout_s": 600,
        "notes": "Seedance 2.0 via OpenRouter — 57% cheaper than Together",
    },
    # --- self-hosted (RunPod) ---
    "runpod-flux": {
        "kind": "image",
        "backend": "runpod",
        "id": "black-forest-labs/FLUX.1-schnell",
        "price": 0.005,
        "gpu_price_per_s": 0.000306,
        "max_refs": 0,
        "resolutions": ["720x1280", "1280x720"],
        "params": ["seed", "width", "height"],
        "timeout_s": 600,
        "fallback": "flux-schnell",
        "notes": "self-hosted FLUX on RunPod 4090",
    },
    "runpod-wan-i2v": {
        "kind": "video",
        "backend": "runpod",
        "id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",
        "price": 0.10,
        "gpu_price_per_s": 0.000306,
        "supports_i2v": True,
        "resolutions": ["720p (1280x704)"],
        "durations": [5],
        "params": ["num_frames"],
        "timeout_s": 1800,
        "fallback": "seedance-1.5-pro",
        "notes": "self-hosted Wan2.2 on RunPod 4090, 720p 24fps",
    },
    # --- test ---
    "fake-image": {
        "kind": "image",
        "backend": "fake",
        "id": "lavfi/color",
        "price": 0.0,
        "max_refs": 14,
        "resolutions": ["720x1280"],
        "params": [],
        "notes": "test backend (ffmpeg)",
    },
    "fake-video": {
        "kind": "video",
        "backend": "fake",
        "id": "lavfi/testsrc",
        "price": 0.0,
        "supports_i2v": False,
        "resolutions": ["720x1280"],
        "durations": [5],
        "params": [],
        "notes": "test backend (ffmpeg)",
    },
}

DEFAULT_IMAGE_MODEL = os.environ.get("SCENEFORGE_IMAGE_MODEL", "flux-schnell")
DEFAULT_VIDEO_MODEL = os.environ.get("SCENEFORGE_VIDEO_MODEL", "seedance-1.5-pro")
DEFAULT_LLM_MODEL = os.environ.get(
    "SCENEFORGE_LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"
)

VIDEO_POLL_INTERVAL_S = 5
VIDEO_TIMEOUT_S = 600

ASPECTS = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
}


_active_profile = threading.local()


def set_active_profile(profile) -> None:
    _active_profile.value = profile


def get_active_profile():
    return getattr(_active_profile, "value", None)


def together_api_key(profile=None) -> str:
    profile = profile or get_active_profile()
    if profile and profile.keys.together:
        return profile.keys.together
    key = os.environ.get("TOGETHER_API_KEY")
    if not key:
        raise RuntimeError(
            "No Together API key. Add it in profile settings or .env."
        )
    return key


def openrouter_api_key(profile=None) -> str:
    profile = profile or get_active_profile()
    if profile and getattr(profile, 'keys', None) and getattr(profile.keys, 'openrouter', ''):
        return profile.keys.openrouter
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "No OpenRouter API key. Add it in profile settings or .env."
        )
    return key


def runpod_api_key(profile=None) -> str:
    profile = profile or get_active_profile()
    if profile and profile.keys.runpod_api:
        return profile.keys.runpod_api
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise RuntimeError(
            "No RunPod API key. Add it in profile settings or .env."
        )
    return key


def runpod_endpoint_id(profile=None) -> str:
    profile = profile or get_active_profile()
    if profile and profile.keys.runpod_endpoint:
        return profile.keys.runpod_endpoint
    endpoint = os.environ.get("RUNPOD_ENDPOINT_ID")
    if not endpoint:
        raise RuntimeError(
            "No RunPod endpoint ID. Add it in profile settings or .env."
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
