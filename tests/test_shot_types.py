"""Tests for shot type tagging on clips."""

from dataclasses import asdict

from sceneforge.config import SHOT_TYPES
from sceneforge.project import Clip, Project, Settings, Style


def test_shot_types_config_has_required_fields():
    for key, st in SHOT_TYPES.items():
        assert "label" in st, f"{key} missing label"
        assert "description" in st, f"{key} missing description"
        assert "color" in st, f"{key} missing color"
        assert "recommended_video" in st, f"{key} missing recommended_video"


def test_clip_shot_type_default_empty():
    clip = Clip(id="clip-01")
    assert clip.shot_type == ""


def test_clip_shot_type_persists():
    clip = Clip(id="clip-01", shot_type="hero")
    assert clip.shot_type == "hero"
    d = asdict(clip)
    assert d["shot_type"] == "hero"


def test_clip_shot_type_roundtrip():
    project = Project(name="test", style=Style(), settings=Settings())
    clip = project.add_clip(source_images=["img.png"], prompt="test")
    clip.shot_type = "broll"
    d = asdict(clip)
    restored = Clip(**d)
    assert restored.shot_type == "broll"


def test_all_shot_types_valid():
    valid = set(SHOT_TYPES.keys())
    assert "hero" in valid
    assert "detail" in valid
    assert "transition" in valid
    assert "broll" in valid
    assert "wide" in valid
    assert "overhead" in valid
