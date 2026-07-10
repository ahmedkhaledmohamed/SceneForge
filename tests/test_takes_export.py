"""Multi-take generation, keep marking, and CapCut export. Offline."""

import json

import pytest
from typer.testing import CliRunner

from sceneforge import ops
from sceneforge.cli import app
from sceneforge.project import ClipArtifact, Project

runner = CliRunner()


def make_project(tmp_path, scenes=1):
    result = runner.invoke(app, [
        "create", "Takes Test", "--concept", "c", "--anchor", "soft light",
        "--dir", str(tmp_path),
        "--image-model", "fake-image", "--video-model", "fake-video",
    ])
    assert result.exit_code == 0, result.output
    root = tmp_path / "takes-test"
    p = ["--project", str(root)]
    (tmp_path / "skirt.jpg").write_bytes(b"img")
    runner.invoke(app, [*p, "add-outfit", "Cafe look",
                        "--item", f"Skirt|https://shop/skirt|{tmp_path / 'skirt.jpg'}"])
    runner.invoke(app, [*p, "add-outfit-scenes", "outfit-1", "--pose", "front"])
    result = runner.invoke(app, [*p, "generate-images", "--options", "2"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, [*p, "select", "scene-01", "1"])
    assert result.exit_code == 0, result.output
    return root, p


def test_takes_generate_numbered_files(tmp_path):
    root, p = make_project(tmp_path)
    result = runner.invoke(app, [*p, "takes", "scene-01", "--count", "2"])
    assert result.exit_code == 0, result.output
    assert (root / "clips" / "scene-01" / "take-01.mp4").is_file()
    assert (root / "clips" / "scene-01" / "take-02.mp4").is_file()

    # takes from the OTHER image option, appended after existing takes
    result = runner.invoke(app, [*p, "takes", "scene-01", "--image", "2",
                                 "--count", "1"])
    assert result.exit_code == 0, result.output
    data = json.loads((root / "project.json").read_text())
    clips = data["scenes"][0]["clips"]
    assert [c["take"] for c in clips] == [1, 2, 3]
    assert [c["source_image_index"] for c in clips] == [0, 0, 1]
    assert all(c["kept"] is False for c in clips)


def test_keep_and_export(tmp_path):
    root, p = make_project(tmp_path)
    runner.invoke(app, [*p, "takes", "scene-01", "--count", "2"])
    result = runner.invoke(app, [*p, "keep", "scene-01", "2"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, [*p, "export"])
    assert result.exit_code == 0, result.output
    exported = list((root / "export").glob("*.mp4"))
    assert [f.name for f in exported] == ["cafe-look--scene-01--take02.mp4"]
    links = (root / "export" / "links.txt").read_text()
    assert "Skirt — https://shop/skirt" in links

    # unkeep -> export refuses
    runner.invoke(app, [*p, "keep", "scene-01", "2", "--unkeep"])
    result = runner.invoke(app, [*p, "export"])
    assert result.exit_code == 1
    assert "No takes marked" in result.output


def test_failed_take_recorded_batch_continues(tmp_path, monkeypatch):
    root, p = make_project(tmp_path)
    project = Project.load(root)
    scene = project.scenes[0]

    calls = {"n": 0}

    class FlakyBackend:
        supports_i2v = True
        model = {"key": "fake-video"}

        def generate_clip(self, prompt, out_path, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"clip")
            from sceneforge.backends.base import ClipResult
            return ClipResult(path=out_path, prompt=prompt, model="fake-video",
                              job_id=None, duration_s=4.0)

    monkeypatch.setattr(ops, "get_video_backend",
                        lambda k, log=print: FlakyBackend())
    failures = ops.run_takes(project, scene, 0, 2, "fake-video",
                             log=lambda m: None)
    assert failures == ["scene-01 take 1"]
    statuses = [(c.take, c.status) for c in scene.clips]
    assert statuses == [(1, "failed"), (2, "completed")]
    assert not list((root / "clips" / "scene-01").glob("*.pending.mp4"))


def test_v2_clips_load_as_legacy(tmp_path):
    project = Project(name="t", root=tmp_path)
    scene = project.add_scene("s")
    # simulate a v2 file: clip dict without take/kept fields
    project.save()
    data = json.loads((tmp_path / "project.json").read_text())
    data["schema_version"] = 2
    data["scenes"][0]["clips"] = [{
        "file": "clips/scene-01.mp4", "prompt": "p", "source_image": None,
        "model": "kling-2.1", "status": "completed", "duration_s": 5.0,
        "job_id": None, "error": None, "created_at": "2026-07-10T00:00:00+00:00",
        "meta": {},
    }]
    (tmp_path / "project.json").write_text(json.dumps(data))

    loaded = Project.load(tmp_path)
    clip = loaded.scenes[0].clips[0]
    assert clip.take is None and clip.kept is False
    assert loaded.scenes[0].completed_clip is clip  # legacy flow intact