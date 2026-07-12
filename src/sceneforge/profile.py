"""Profiles: global, cross-project context.

A profile is a brand/workspace — its characters (recurring subjects with
identity refs), style defaults, and seed assets are available in every
project created under it:

    $SCENEFORGE_HOME (~/SceneForge)/
    └── <profile-slug>/
        ├── profile.json
        ├── refs/characters/pchar-1/ , refs/style/
        ├── seeds/
        ├── brainstorms/
        └── projects/<project-slug>/   (standard project dirs)

Profile characters use pchar-* ids; project scenes may reference them
directly. Style and defaults are COPIED into new projects (styles
diverge per post); only characters resolve live, because identity refs
keep improving and must propagate everywhere.
"""

import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .project import Character, Project, now_iso

PROFILE_SCHEMA_VERSION = 2

PROFILE_FILE = "profile.json"


def home_dir() -> Path:
    return Path(os.environ.get("SCENEFORGE_HOME", Path.home() / "SceneForge"))


@dataclass
class Seed:
    id: str
    kind: str  # image | clip | note
    file: str | None = None
    text: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)


@dataclass
class ProfileStyle:
    anchor: str = ""
    mood: str = ""
    palette: str = ""
    lighting: str = ""
    suffix: str = ""
    reference_image: str | None = None


@dataclass
class ProfileDefaults:
    image_model: str = "flux-2-pro"
    final_image_model: str = "nano-banana-pro"
    video_model: str = "kling-2.1"
    aspect: str = "9:16"
    image_options: int = 2


@dataclass
class ProfileKeys:
    together: str = ""
    openrouter: str = ""
    runpod_api: str = ""
    runpod_endpoint: str = ""


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


@dataclass
class Profile:
    name: str
    style: ProfileStyle = field(default_factory=ProfileStyle)
    defaults: ProfileDefaults = field(default_factory=ProfileDefaults)
    characters: list[Character] = field(default_factory=list)
    seeds: list[Seed] = field(default_factory=list)
    keys: ProfileKeys = field(default_factory=ProfileKeys)
    password_hash: str = ""
    password_salt: str = ""
    schema_version: int = PROFILE_SCHEMA_VERSION
    root: Path = field(default=Path("."), compare=False)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    def set_password(self, password: str) -> None:
        self.password_salt = secrets.token_hex(16)
        self.password_hash = _hash_password(password, self.password_salt)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return True
        return _hash_password(password, self.password_salt) == self.password_hash

    @property
    def path(self) -> Path:
        return self.root / PROFILE_FILE

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def seeds_dir(self) -> Path:
        return self.root / "seeds"

    def character_refs_dir(self, character: Character) -> Path:
        return self.root / "refs" / "characters" / character.id

    def add_character(self, name: str, description: str = "",
                      main: bool = False) -> Character:
        character = Character(id=f"pchar-{len(self.characters) + 1}",
                              name=name, description=description, main=main)
        if main:
            for other in self.characters:
                other.main = False
        if not self.characters:
            character.main = True
        self.characters.append(character)
        return character

    def find_character(self, character_id: str) -> Character:
        for character in self.characters:
            if character.id == character_id:
                return character
        valid = ", ".join(c.id for c in self.characters) or "(none)"
        raise KeyError(f"No profile character '{character_id}'. Characters: {valid}")

    @property
    def main_character(self) -> Character | None:
        for character in self.characters:
            if character.main:
                return character
        return self.characters[0] if self.characters else None

    def add_seed(self, kind: str, *, file: str | None = None,
                 text: str | None = None, tags: list[str] | None = None) -> Seed:
        seed = Seed(id=f"seed-{len(self.seeds) + 1}", kind=kind,
                    file=file, text=text, tags=tags or [])
        self.seeds.append(seed)
        return seed

    def save(self) -> None:
        data = asdict(self)
        data.pop("root")
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, root: Path) -> "Profile":
        data = json.loads((root / PROFILE_FILE).read_text())
        version = data.get("schema_version", 0)
        if version > PROFILE_SCHEMA_VERSION:
            raise ValueError(
                f"profile.json schema v{version} is newer than this tool"
            )
        return cls(
            name=data["name"],
            style=ProfileStyle(**data.get("style", {})),
            defaults=ProfileDefaults(**data.get("defaults", {})),
            characters=[Character(**c) for c in data.get("characters", [])],
            seeds=[Seed(**s) for s in data.get("seeds", [])],
            keys=ProfileKeys(**data.get("keys", {})),
            password_hash=data.get("password_hash", ""),
            password_salt=data.get("password_salt", ""),
            schema_version=PROFILE_SCHEMA_VERSION,
            root=root,
        )


def create_profile(name: str, home: Path | None = None) -> Profile:
    from .util import slugify

    base = home or home_dir()
    root = base / slugify(name)
    if (root / PROFILE_FILE).exists():
        raise FileExistsError(f"Profile already exists at {root}")
    profile = Profile(name=name, root=root)
    (root / "projects").mkdir(parents=True)
    (root / "seeds").mkdir()
    (root / "brainstorms").mkdir()
    profile.save()
    return profile


def find_profile_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / PROFILE_FILE).is_file():
            return candidate
    return None


def profile_for_project(project: Project) -> "Profile | None":
    root = find_profile_root(project.root)
    return Profile.load(root) if root else None


def resolve_character(project: Project, profile: "Profile | None",
                      character_id: str) -> tuple[Character, Path]:
    """pchar-* resolves against the profile (refs are profile-relative),
    char-* against the project. Returns (character, base dir)."""
    if character_id.startswith("pchar-"):
        if profile is None:
            raise KeyError(
                f"Scene references profile character '{character_id}' but the "
                "project is not inside a profile"
            )
        return profile.find_character(character_id), profile.root
    return project.find_character(character_id), project.root
