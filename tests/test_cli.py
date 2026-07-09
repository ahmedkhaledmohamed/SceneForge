"""End-to-end workflow test with fake (lavfi) backends — no API calls."""

import json

from typer.testing import CliRunner

from sceneforge.cli import app
from sceneforge.util import ffprobe_duration

runner = CliRunner()


def run(args, **kwargs):
    result = runner.invoke(app, args, **kwargs)
    assert result.exit_code == 0, result.output
    return result


def test_full_workflow(tmp_path):
    run([
        "create", "Autumn Morning",
        "--concept", "a cozy autumn morning routine",
        "--anchor", "warm golden hour lighting, muted earth tones",
        "--dir", str(tmp_path),
        "--image-model", "fake-image",
        "--video-model", "fake-video",
    ])
    root = tmp_path / "autumn-morning"
    assert (root / "project.json").is_file()
    p = ["--project", str(root)]

    run([*p, "add-scenes",
         "--scene", "steam rises from a ceramic mug",
         "--scene", "rain drips down a window pane",
         "--scene", "socked feet on a wooden floor"])

    run([*p, "generate-images", "--options", "2"])
    data = json.loads((root / "project.json").read_text())
    assert all(len(s["images"]) == 2 for s in data["scenes"])
    assert (root / "images" / "scene-01" / "opt-1.png").is_file()
    # style anchor is baked into every stored prompt
    assert all("warm golden hour lighting" in img["prompt"]
               for s in data["scenes"] for img in s["images"])

    # idempotent: second run generates nothing new
    run([*p, "generate-images", "--options", "2"])
    data = json.loads((root / "project.json").read_text())
    assert all(len(s["images"]) == 2 for s in data["scenes"])

    # clips blocked until images are selected
    result = runner.invoke(app, [*p, "generate-clips"])
    assert result.exit_code == 1
    assert "no selected image" in result.output

    for scene_id in ("scene-01", "scene-02", "scene-03"):
        run([*p, "select", scene_id, "1"])

    run([*p, "generate-clips"])
    data = json.loads((root / "project.json").read_text())
    assert all(s["clips"][-1]["status"] == "completed" for s in data["scenes"])

    # idempotent: clips exist, nothing regenerated
    result = run([*p, "generate-clips"])
    assert "skipping" in result.output

    run([*p, "stitch"])
    final = root / "output" / "final.mp4"
    assert final.is_file()
    # 3 clips x 4s at 2x speed = 2s each, minus 2 crossfades x 0.3s = 5.4s
    assert abs(ffprobe_duration(final) - 5.4) < 0.2

    result = run([*p, "status"])
    assert "scene-03" in result.output


def test_select_out_of_range(tmp_path):
    run(["create", "T", "--concept", "c", "--anchor", "a",
         "--dir", str(tmp_path),
         "--image-model", "fake-image", "--video-model", "fake-video"])
    p = ["--project", str(tmp_path / "t")]
    run([*p, "add-scenes", "--scene", "something"])
    result = runner.invoke(app, [*p, "select", "scene-01", "1"])
    assert result.exit_code == 1


def test_dry_run_generates_nothing(tmp_path):
    run(["create", "T", "--concept", "c", "--anchor", "night mood",
         "--dir", str(tmp_path),
         "--image-model", "fake-image", "--video-model", "fake-video"])
    p = ["--project", str(tmp_path / "t")]
    run([*p, "add-scenes", "--scene", "a lantern glows"])
    result = run([*p, "generate-images", "--dry-run"])
    assert "night mood. a lantern glows" in result.output
    assert not (tmp_path / "t" / "images").exists()


def test_no_project_errors_cleanly(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "No project found" in result.output
