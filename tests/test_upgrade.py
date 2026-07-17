"""Tests for draft → premium upgrade fields."""

from dataclasses import asdict

from sceneforge.project import Clip, ImageArtifact, Project, Settings, Style


def test_image_artifact_upgraded_from_default_empty():
    art = ImageArtifact(file="t.png", prompt="p", model="flux-schnell")
    assert art.upgraded_from == ""


def test_image_artifact_upgraded_from_persists():
    art = ImageArtifact(
        file="t.png", prompt="p", model="nano-banana-pro",
        upgraded_from="flux-schnell",
    )
    d = asdict(art)
    assert d["upgraded_from"] == "flux-schnell"
    restored = ImageArtifact(**d)
    assert restored.upgraded_from == "flux-schnell"


def test_clip_upgraded_from_default_empty():
    clip = Clip(id="clip-01")
    assert clip.upgraded_from == ""


def test_clip_upgraded_from_persists():
    clip = Clip(id="clip-02", upgraded_from="clip-01")
    d = asdict(clip)
    assert d["upgraded_from"] == "clip-01"
    restored = Clip(**d)
    assert restored.upgraded_from == "clip-01"


def test_upgrade_clip_creates_new_clip():
    project = Project(name="test", style=Style(), settings=Settings())
    original = project.add_clip(source_images=["img.png"], prompt="sway", model="kling-2.1")
    original.status = "completed"
    upgraded = project.add_clip(
        source_images=original.source_images,
        prompt=original.prompt,
        model="seedance-2.0-or",
    )
    upgraded.upgraded_from = original.id
    assert len(project.clips) == 2
    assert upgraded.upgraded_from == "clip-01"
    assert upgraded.model == "seedance-2.0-or"
    assert upgraded.source_images == ["img.png"]
