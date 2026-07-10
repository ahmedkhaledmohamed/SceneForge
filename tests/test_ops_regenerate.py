"""Regenerating a clip must never orphan the existing completed clip."""

import pytest

from sceneforge import ops
from sceneforge.backends.base import ClipResult
from sceneforge.project import ClipArtifact, ImageArtifact, Project


class StubBackend:
    supports_i2v = True

    def __init__(self, model, fail=False):
        self.model = model
        self.fail = fail

    def generate_clip(self, prompt, out_path, **kwargs):
        if self.fail:
            raise RuntimeError("backend exploded")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"new-clip")
        return ClipResult(path=out_path, prompt=prompt, model=self.model["key"],
                          job_id=None, duration_s=5.0)


def make_project_with_clip(tmp_path):
    project = Project(name="t", root=tmp_path)
    scene = project.add_scene("a mug steams")
    img = tmp_path / "images" / "scene-01" / "opt-1.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"png")
    scene.images.append(ImageArtifact(file="images/scene-01/opt-1.png",
                                      prompt="p", model="fake-image"))
    scene.selected_image = 0
    clip = tmp_path / "clips" / "scene-01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"old-clip")
    scene.clips.append(ClipArtifact(file="clips/scene-01.mp4", prompt="p",
                                    source_image="images/scene-01/opt-1.png",
                                    model="fake-video", duration_s=5.0,
                                    status="completed"))
    project.save()
    return project, scene


def test_failed_regen_preserves_existing_clip(tmp_path, monkeypatch):
    project, scene = make_project_with_clip(tmp_path)
    monkeypatch.setattr(
        ops, "get_video_backend",
        lambda key, log=print: StubBackend({"key": "fake-video"}, fail=True),
    )
    failures = ops.run_clips(project, [scene], "fake-video", log=lambda m: None)

    assert failures == ["scene-01"]
    # the old completed clip is untouched and its record still resolves
    assert (tmp_path / "clips" / "scene-01.mp4").read_bytes() == b"old-clip"
    assert (tmp_path / scene.completed_clip.file).is_file()
    assert not list((tmp_path / "clips").glob("*.pending.mp4"))


def test_successful_regen_archives_and_repoints(tmp_path, monkeypatch):
    project, scene = make_project_with_clip(tmp_path)
    monkeypatch.setattr(
        ops, "get_video_backend",
        lambda key, log=print: StubBackend({"key": "fake-video"}),
    )
    failures = ops.run_clips(project, [scene], "fake-video", log=lambda m: None)

    assert failures == []
    # new clip is in place; old one is archived and its record repointed
    assert (tmp_path / "clips" / "scene-01.mp4").read_bytes() == b"new-clip"
    old_record = scene.clips[0]
    assert old_record.file != "clips/scene-01.mp4"
    assert (tmp_path / old_record.file).read_bytes() == b"old-clip"
    assert scene.completed_clip.file == "clips/scene-01.mp4"