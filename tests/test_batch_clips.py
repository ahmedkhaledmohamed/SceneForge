"""Tests for batch clip generation from scenes (generate-all-clips-batch)."""

import time

from fastapi.testclient import TestClient

from sceneforge.server import create_app


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201
    return r.json()["slug"]


def create_project(client, prof, name="Looks", **kwargs):
    body = {
        "name": name, "concept": "outfit posts", "anchor": "soft light",
        "image_model": "fake-image", "video_model": "fake-video",
        **kwargs,
    }
    r = client.post(f"/api/profiles/{prof}/projects", json=body)
    assert r.status_code == 201
    return r.json()["slug"]


def wait_job(client, prof, slug, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/profiles/{prof}/projects/{slug}/job").json()
        if job["status"] in ("done", "failed", "idle"):
            return job
        time.sleep(0.05)
    raise TimeoutError("job did not finish")


def setup_scenes_with_images(client, prof, slug, count=2):
    """Add scenes, generate images, and select the first image for each."""
    for i in range(count):
        client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                    json={"description": f"scene {i + 1} look"})

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-images",
                    json={"options": 1})
    assert r.status_code == 202
    wait_job(client, prof, slug)

    # Select first image for each scene
    for i in range(count):
        client.post(f"/api/profiles/{prof}/projects/{slug}/scenes/scene-{i + 1:02d}/select",
                    json={"image_index": 0})


# ------------------------------------------------------------------ tests


def test_batch_creates_clips_from_scenes(tmp_path):
    """Clips are created and generated for scenes with selected images."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=2)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["clips"]) == 2
    for clip in doc["clips"]:
        assert clip["status"] == "completed"
        assert clip["model"] == "fake-video"
        assert clip["seconds"] == 5
        assert len(clip["source_images"]) == 1


def test_batch_skips_scenes_without_selection(tmp_path):
    """Scenes without a selected image are not included."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Add 2 scenes, generate images, but only select one
    for desc in ["selected scene", "unselected scene"]:
        client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                    json={"description": desc})

    client.post(f"/api/profiles/{prof}/projects/{slug}/generate-images",
                json={"options": 1})
    wait_job(client, prof, slug)

    # Select only the first scene
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/select",
                json={"image_index": 0})

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["clips"]) == 1


def test_batch_skips_scenes_with_completed_clips(tmp_path):
    """Scenes that already have a completed clip are not duplicated."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=2)

    # Generate a batch first
    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    wait_job(client, prof, slug)

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["clips"]) == 2

    # Run batch again -- should find nothing new to generate
    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    body = r.json()
    assert body["started"] is None
    assert "no eligible" in body.get("note", "")


def test_batch_model_override(tmp_path):
    """Passing a specific model overrides auto routing."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=1)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert doc["clips"][0]["model"] == "fake-video"


def test_batch_auto_routing(tmp_path):
    """Model 'auto' uses config.recommend_model for each clip."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=1)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "auto", "seconds": 5})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    # auto should resolve to a real model, not remain "auto"
    assert doc["clips"][0]["model"] != "auto"
    assert doc["clips"][0]["status"] == "completed"


def test_batch_structured_progress(tmp_path):
    """Job exposes total, completed, and results fields."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=2)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)

    assert job["status"] == "done"
    assert job["total"] == 2
    assert job["completed"] == 2
    assert len(job["results"]) == 2
    assert all(r["status"] == "ok" for r in job["results"])


def test_batch_no_eligible_scenes(tmp_path):
    """Empty project returns no-op."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 5})
    assert r.status_code == 202
    body = r.json()
    assert body["started"] is None


def test_batch_seconds_parameter(tmp_path):
    """The seconds parameter is passed through to created clips."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    setup_scenes_with_images(client, prof, slug, count=1)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                    json={"model": "fake-video", "seconds": 7})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert doc["clips"][0]["seconds"] == 7
