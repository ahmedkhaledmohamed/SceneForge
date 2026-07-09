"""Web UI tests — fake backends, no API calls."""

import time

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from sceneforge.cli import app as cli_app
from sceneforge.web import create_app

runner = CliRunner()


def make_project(tmp_path, scenes=("a cup of tea steams",)):
    result = runner.invoke(cli_app, [
        "create", "Web Test", "--concept", "a quiet evening",
        "--anchor", "soft lamplight", "--dir", str(tmp_path),
        "--image-model", "fake-image", "--video-model", "fake-video",
    ])
    assert result.exit_code == 0, result.output
    args = ["--project", str(tmp_path / "web-test"), "add-scenes"]
    for s in scenes:
        args += ["--scene", s]
    result = runner.invoke(cli_app, args)
    assert result.exit_code == 0, result.output
    return tmp_path / "web-test"


def wait_for_job(client, slug, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = client.get(f"/p/{slug}/job").text
        if "Running" not in text:
            return text
        time.sleep(0.1)
    raise TimeoutError("job did not finish")


def test_index_lists_projects(tmp_path):
    make_project(tmp_path)
    client = TestClient(create_app(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "Web Test" in response.text


def test_full_workflow_via_ui(tmp_path):
    root = make_project(tmp_path)
    client = TestClient(create_app(tmp_path))

    # generate images as a background job
    response = client.post("/p/web-test/generate-images",
                           data={"options": "2", "model": "fake-image"},
                           follow_redirects=False)
    assert response.status_code == 303
    text = wait_for_job(client, "web-test")
    assert "done" in text
    assert (root / "images" / "scene-01" / "opt-2.png").is_file()

    # clips are blocked until an image is selected
    response = client.post("/p/web-test/generate-clips",
                           data={"model": "fake-video"}, follow_redirects=False)
    assert response.status_code == 400

    response = client.post("/p/web-test/select",
                           data={"scene_id": "scene-01", "option": "1"},
                           follow_redirects=False)
    assert response.status_code == 303

    response = client.post("/p/web-test/generate-clips",
                           data={"model": "fake-video"}, follow_redirects=False)
    assert response.status_code == 303
    assert "done" in wait_for_job(client, "web-test")
    assert (root / "clips" / "scene-01.mp4").is_file()

    response = client.post("/p/web-test/stitch", follow_redirects=False)
    assert response.status_code == 303
    assert "done" in wait_for_job(client, "web-test")
    assert (root / "output" / "final.mp4").is_file()

    # project page shows the selected image and the final video
    page = client.get("/p/web-test").text
    assert "✓ selected" in page
    assert "output/final.mp4" in page


def test_select_out_of_range(tmp_path):
    make_project(tmp_path)
    client = TestClient(create_app(tmp_path))
    response = client.post("/p/web-test/select",
                           data={"scene_id": "scene-01", "option": "5"},
                           follow_redirects=False)
    assert response.status_code == 400


def test_media_blocks_path_traversal(tmp_path):
    make_project(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    client = TestClient(create_app(tmp_path))
    response = client.get("/p/web-test/media/../secret.txt")
    assert response.status_code != 200


def test_unknown_project_404(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/p/nope").status_code == 404
