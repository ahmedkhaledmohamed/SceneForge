"""Backend factories. Local backends (torch/diffusers) are imported
lazily so the Together-only install stays dependency-light."""

from ..config import resolve_model
from .base import ImageBackend, VideoBackend


def get_image_backend(model_key: str) -> ImageBackend:
    model = resolve_model(model_key, "image")
    if model["backend"] == "together":
        from .together_image import TogetherImageBackend
        return TogetherImageBackend(model)
    if model["backend"] == "fake":
        from .fake import FakeImageBackend
        return FakeImageBackend(model)
    raise ValueError(f"No image backend '{model['backend']}'")


def get_video_backend(model_key: str) -> VideoBackend:
    model = resolve_model(model_key, "video")
    if model["backend"] == "together":
        from .together_video import TogetherVideoBackend
        return TogetherVideoBackend(model)
    if model["backend"] == "fake":
        from .fake import FakeVideoBackend
        return FakeVideoBackend(model)
    raise ValueError(f"No video backend '{model['backend']}'")
