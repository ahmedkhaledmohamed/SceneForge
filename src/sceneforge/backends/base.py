"""Backend interfaces. Blocking/sequential — a call returns when the
artifact file exists on disk (video backends poll internally)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageResult:
    path: Path
    prompt: str
    model: str
    meta: dict = field(default_factory=dict)


@dataclass
class ClipResult:
    path: Path
    prompt: str
    model: str
    job_id: str | None
    duration_s: float
    meta: dict = field(default_factory=dict)


class ImageBackend(ABC):
    supports_reference_image: bool = False

    def __init__(self, model: dict):
        self.model = model  # resolved registry entry, includes "key" and "id"

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        out_path: Path,
        *,
        width: int,
        height: int,
        reference_image: Path | None = None,
        seed: int | None = None,
    ) -> ImageResult: ...


class VideoBackend(ABC):
    supports_i2v: bool = True

    def __init__(self, model: dict):
        self.model = model

    @abstractmethod
    def generate_clip(
        self,
        prompt: str,
        out_path: Path,
        *,
        image: Path | None,
        width: int,
        height: int,
        timeout_s: float = 600,
    ) -> ClipResult: ...
