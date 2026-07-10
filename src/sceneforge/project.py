"""Project data model and project.json persistence.

A project is a directory containing project.json plus generated media:

    my-video/
    ├── project.json
    ├── images/scene-01/opt-1.png ...
    ├── clips/scene-01.mp4
    ├── work/        (normalized intermediates, regenerable)
    └── output/final.mp4

Scene order is array order. Generation history is the append-only
images/clips arrays on each scene — every artifact records the full
composed prompt and model used.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

PROJECT_FILE = "project.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Style:
    anchor: str = ""
    mood: str = ""
    palette: str = ""
    lighting: str = ""
    suffix: str = ""
    reference_image: str | None = None


@dataclass
class Settings:
    aspect: str = "9:16"
    width: int = 720
    height: int = 1280
    image_options: int = 3
    clip_speed: float = 2.0
    crossfade: float = 0.3
    image_model: str = "flux-schnell"
    video_model: str = "seedance-2.0"


@dataclass
class ImageArtifact:
    file: str
    prompt: str
    model: str
    created_at: str = field(default_factory=now_iso)
    meta: dict = field(default_factory=dict)  # backend extras, e.g. cost_usd


@dataclass
class ClipArtifact:
    file: str
    prompt: str
    source_image: str | None
    model: str
    job_id: str | None = None
    duration_s: float | None = None
    status: str = "pending"  # pending | completed | failed
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    meta: dict = field(default_factory=dict)  # backend extras, e.g. cost_usd


@dataclass
class Scene:
    id: str
    description: str
    style_override: str | None = None
    images: list[ImageArtifact] = field(default_factory=list)
    selected_image: int | None = None
    clips: list[ClipArtifact] = field(default_factory=list)

    @property
    def selected_image_file(self) -> str | None:
        if self.selected_image is None:
            return None
        return self.images[self.selected_image].file

    @property
    def completed_clip(self) -> ClipArtifact | None:
        for clip in reversed(self.clips):
            if clip.status == "completed":
                return clip
        return None


@dataclass
class Project:
    name: str
    concept: str = ""
    style: Style = field(default_factory=Style)
    settings: Settings = field(default_factory=Settings)
    scenes: list[Scene] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    root: Path = field(default=Path("."), compare=False)

    # --- paths ---

    @property
    def path(self) -> Path:
        return self.root / PROJECT_FILE

    def images_dir(self, scene: Scene) -> Path:
        return self.root / "images" / scene.id

    @property
    def clips_dir(self) -> Path:
        return self.root / "clips"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    # --- scenes ---

    def add_scene(self, description: str) -> Scene:
        scene = Scene(id=f"scene-{len(self.scenes) + 1:02d}", description=description)
        self.scenes.append(scene)
        return scene

    def find_scene(self, scene_id: str) -> Scene:
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        valid = ", ".join(s.id for s in self.scenes) or "(none)"
        raise KeyError(f"No scene '{scene_id}' in project. Scenes: {valid}")

    # --- persistence ---

    def save(self) -> None:
        data = asdict(self)
        data.pop("root")
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, root: Path) -> "Project":
        data = json.loads((root / PROJECT_FILE).read_text())
        version = data.get("schema_version", 0)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"project.json schema v{version} is newer than this tool (v{SCHEMA_VERSION})"
            )
        scenes = [
            Scene(
                id=s["id"],
                description=s["description"],
                style_override=s.get("style_override"),
                images=[ImageArtifact(**img) for img in s.get("images", [])],
                selected_image=s.get("selected_image"),
                clips=[ClipArtifact(**c) for c in s.get("clips", [])],
            )
            for s in data.get("scenes", [])
        ]
        return cls(
            name=data["name"],
            concept=data.get("concept", ""),
            style=Style(**data.get("style", {})),
            settings=Settings(**data.get("settings", {})),
            scenes=scenes,
            schema_version=SCHEMA_VERSION,
            root=root,
        )


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default cwd) looking for project.json."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / PROJECT_FILE).is_file():
            return candidate
    return None
