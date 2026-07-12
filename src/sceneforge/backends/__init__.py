"""Backend factories. Heavy/optional imports stay lazy inside each
branch. When a registry entry has a "fallback" key, the backend is
wrapped so failures automatically delegate to the fallback model."""

from ..config import resolve_model
from .base import ImageBackend, VideoBackend


def _image_backend(model: dict) -> ImageBackend:
    if model["backend"] == "together":
        from .together_image import TogetherImageBackend
        return TogetherImageBackend(model)
    if model["backend"] == "runpod":
        from .runpod_backend import RunPodImageBackend
        return RunPodImageBackend(model)
    if model["backend"] == "fake":
        from .fake import FakeImageBackend
        return FakeImageBackend(model)
    raise ValueError(f"No image backend '{model['backend']}'")


def _video_backend(model: dict) -> VideoBackend:
    if model["backend"] == "together":
        from .together_video import TogetherVideoBackend
        return TogetherVideoBackend(model)
    if model["backend"] == "runpod":
        from .runpod_backend import RunPodVideoBackend
        return RunPodVideoBackend(model)
    if model["backend"] == "openrouter":
        from .openrouter_video import OpenRouterVideoBackend
        return OpenRouterVideoBackend(model)
    if model["backend"] == "fake":
        from .fake import FakeVideoBackend
        return FakeVideoBackend(model)
    raise ValueError(f"No video backend '{model['backend']}'")


def get_image_backend(model_key: str, log=print) -> ImageBackend:
    model = resolve_model(model_key, "image")
    backend = _image_backend(model)
    if model.get("fallback"):
        from .fallback import FallbackImageBackend
        backend = FallbackImageBackend(
            backend, get_image_backend(model["fallback"], log), log
        )
    return backend


def get_video_backend(model_key: str, log=print) -> VideoBackend:
    model = resolve_model(model_key, "video")
    backend = _video_backend(model)
    if model.get("fallback"):
        from .fallback import FallbackVideoBackend
        backend = FallbackVideoBackend(
            backend, get_video_backend(model["fallback"], log), log
        )
    return backend
