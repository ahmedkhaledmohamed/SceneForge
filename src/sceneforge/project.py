"""Project data model and project.json persistence.

A project is a directory containing project.json plus generated media:

    my-video/
    ├── project.json
    ├── images/scene-01/opt-1.png ...
    ├── refs/scenes/scene-01/      (reference images per scene)
    ├── clips/scene-01/take-01.mp4
    ├── work/        (normalized intermediates, regenerable)
    └── output/final.mp4

Scene order is array order. Each scene owns its reference images
(garment photos, style refs, etc.) and optional shop links.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 5  # v5: clips as project-level entities

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
class Character:
    id: str
    name: str
    description: str = ""
    reference_images: list[str] = field(default_factory=list)
    main: bool = False


@dataclass
class SceneRef:
    """A reference image attached to a scene — garment photo, style ref,
    background, or prop. Optional url is a shop link for export."""
    file: str
    role: str = "garment"  # garment | style | background | prop | other
    label: str = ""
    url: str | None = None


@dataclass
class ReferenceImage:
    """Project-level reference image (style/background shared across scenes)."""
    file: str
    role: str = "style"
    label: str = ""


@dataclass
class ImageArtifact:
    file: str
    prompt: str
    model: str
    created_at: str = field(default_factory=now_iso)
    meta: dict = field(default_factory=dict)
    generation_id: str = ""


@dataclass
class ClipArtifact:
    file: str
    prompt: str
    source_image: str | None
    model: str
    job_id: str | None = None
    duration_s: float | None = None
    status: str = "pending"
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    meta: dict = field(default_factory=dict)
    take: int | None = None
    source_image_index: int | None = None
    kept: bool = False


@dataclass
class Clip:
    """A video clip — project-level, can reference images from any scene."""
    id: str
    source_images: list[str] = field(default_factory=list)
    prompt: str = ""
    model: str = ""
    seconds: int = 5
    file: str = ""
    status: str = "pending"
    error: str | None = None
    duration_s: float | None = None
    job_id: str | None = None
    created_at: str = field(default_factory=now_iso)
    meta: dict = field(default_factory=dict)
    kept: bool = False
    shot_type: str = ""


@dataclass
class Scene:
    id: str
    description: str
    style_override: str | None = None
    character_id: str | None = None
    pose: str | None = None
    refs: list[SceneRef] = field(default_factory=list)
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
    characters: list[Character] = field(default_factory=list)
    refs: list[ReferenceImage] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)
    notes: str = ""
    budget_usd: float = 0.0
    schema_version: int = SCHEMA_VERSION
    root: Path = field(default=Path("."), compare=False)

    # --- paths ---

    @property
    def path(self) -> Path:
        return self.root / PROJECT_FILE

    def images_dir(self, scene: Scene) -> Path:
        return self.root / "images" / scene.id

    def scene_refs_dir(self, scene: Scene) -> Path:
        return self.root / "refs" / "scenes" / scene.id

    def character_refs_dir(self, character: Character) -> Path:
        return self.root / "refs" / "characters" / character.id

    @property
    def clips_dir(self) -> Path:
        return self.root / "clips"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    # --- scenes / characters ---

    def add_scene(self, description: str, **fields) -> Scene:
        scene = Scene(id=f"scene-{len(self.scenes) + 1:02d}",
                      description=description, **fields)
        self.scenes.append(scene)
        return scene

    def find_scene(self, scene_id: str) -> Scene:
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        valid = ", ".join(s.id for s in self.scenes) or "(none)"
        raise KeyError(f"No scene '{scene_id}' in project. Scenes: {valid}")

    def add_character(self, name: str, description: str = "") -> Character:
        character = Character(id=f"char-{len(self.characters) + 1}",
                              name=name, description=description)
        self.characters.append(character)
        return character

    def find_character(self, character_id: str) -> Character:
        for character in self.characters:
            if character.id == character_id:
                return character
        valid = ", ".join(c.id for c in self.characters) or "(none)"
        raise KeyError(f"No character '{character_id}'. Characters: {valid}")

    def add_clip(self, source_images: list[str], prompt: str = "",
                 model: str = "") -> Clip:
        clip = Clip(id=f"clip-{len(self.clips) + 1:02d}",
                    source_images=source_images, prompt=prompt, model=model)
        self.clips.append(clip)
        return clip

    def find_clip(self, clip_id: str) -> Clip:
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        valid = ", ".join(c.id for c in self.clips) or "(none)"
        raise KeyError(f"No clip '{clip_id}'. Clips: {valid}")

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

        # --- v3 migration: outfits → scene refs ---
        outfits_by_id = {}
        if version < 4:
            for o in data.get("outfits", []):
                outfits_by_id[o["id"]] = o

        scenes = []
        for s in data.get("scenes", []):
            scene_refs = [SceneRef(**r) for r in s.get("refs", [])]

            # migrate outfit items into scene refs
            outfit_id = s.get("outfit_id")
            if version < 4 and outfit_id and outfit_id in outfits_by_id:
                outfit = outfits_by_id[outfit_id]
                for item in outfit.get("items", []):
                    scene_refs.append(SceneRef(
                        file=item.get("image") or "",
                        role="garment",
                        label=item.get("name", ""),
                        url=item.get("url"),
                    ))

            scenes.append(Scene(
                id=s["id"],
                description=s["description"],
                style_override=s.get("style_override"),
                character_id=s.get("character_id"),
                pose=s.get("pose"),
                refs=scene_refs,
                images=[ImageArtifact(**img) for img in s.get("images", [])],
                selected_image=s.get("selected_image"),
                clips=[ClipArtifact(**c) for c in s.get("clips", [])],
            ))

        characters = [Character(**c) for c in data.get("characters", [])]

        # v5: clips as project-level entities
        project_clips = [Clip(**c) for c in data.get("clips", [])]
        if version < 5:
            # migrate scene-level clips to project clips
            for sc in scenes:
                for ca in sc.clips:
                    if ca.status == "completed":
                        project_clips.append(Clip(
                            id=f"clip-{len(project_clips) + 1:02d}",
                            source_images=[ca.source_image] if ca.source_image else [],
                            prompt=ca.prompt,
                            model=ca.model,
                            file=ca.file,
                            status=ca.status,
                            duration_s=ca.duration_s,
                            job_id=ca.job_id,
                            created_at=ca.created_at,
                            meta=ca.meta,
                            kept=ca.kept,
                        ))

        return cls(
            name=data["name"],
            concept=data.get("concept", ""),
            style=Style(**data.get("style", {})),
            settings=Settings(**data.get("settings", {})),
            characters=characters,
            refs=[ReferenceImage(**r) for r in data.get("refs", [])],
            scenes=scenes,
            clips=project_clips,
            notes=data.get("notes", ""),
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
