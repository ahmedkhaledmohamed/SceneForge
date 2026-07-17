"""Tests for the AI Director (direct) endpoint — full concept-to-clips pipeline."""

import json
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sceneforge.server import create_app

GOOD_SHOTS = json.dumps({
    "shots": [
        {
            "description": "Hero shot in golden morning light",
            "composition": "medium shot, eye level",
            "shot_type": "hero",
            "prompt": "a character in soft golden light, medium shot",
        },
        {
            "description": "Close-up of accessory details",
            "composition": "tight close-up, shallow DOF",
            "shot_type": "detail",
            "prompt": "macro shot of jewelry and bag details",
        },
    ]
})


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201
    return r.json()["slug"]


def create_project(client, prof, name="Looks", **kwargs):
    body = {
        "name": name, "concept": "outfit posts for IG reels",
        "anchor": "soft light",
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


def mock_shot_list():
    """Return a context manager that mocks the LLM call for generate_shot_list."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_SHOTS

    return patch("sceneforge.config.together_api_key", return_value="fake-key"), \
        patch("openai.OpenAI", return_value=MagicMock(
            chat=MagicMock(completions=MagicMock(
                create=MagicMock(return_value=mock_response)
            ))
        ))


# ------------------------------------------------------------------ tests


def test_direct_full_pipeline(tmp_path):
    """Director generates shots, images, auto-selects, and creates clips."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    p1, p2 = mock_shot_list()
    with p1, p2:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                        json={"num_scenes": 2,
                              "image_model": "fake-image",
                              "video_model": "fake-video",
                              "seconds": 5})
    assert r.status_code == 202
    body = r.json()
    assert body["started"] == "direct (AI director)"
    assert body["estimate"]["num_scenes"] == 2

    job = wait_job(client, prof, slug)
    assert job["status"] == "done"
    assert "Stage 1/5" in " ".join(job["log"])
    assert "Stage 2/5" in " ".join(job["log"])
    assert "Stage 3/5" in " ".join(job["log"])
    assert "Stage 4/5" in " ".join(job["log"])
    assert "Stage 5/5" in " ".join(job["log"])
    assert "Director complete." in " ".join(job["log"])

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    # Shot list had 2 shots -> 2 scenes
    assert len(doc["scenes"]) == 2
    for sc in doc["scenes"]:
        assert len(sc["images"]) >= 1
        assert sc["selected_image"] is not None
    assert len(doc["clips"]) == 2
    for clip in doc["clips"]:
        assert clip["status"] == "completed"


def test_direct_no_concept(tmp_path):
    """Director fails when the project has no concept."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": "Empty", "concept": "", "anchor": "soft",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    slug = r.json()["slug"]

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct", json={})
    assert r.status_code == 400
    body = r.json()
    msg = (body.get("error", {}).get("message") or
           body.get("detail", {}).get("message", "")).lower()
    assert "no concept" in msg


def test_direct_invalid_model(tmp_path):
    """Director rejects invalid model names."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                    json={"image_model": "nonexistent-model"})
    assert r.status_code == 400


def test_direct_estimate_returned(tmp_path):
    """Response includes cost estimate with scene, image, and clip counts."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    p1, p2 = mock_shot_list()
    with p1, p2:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                        json={"num_scenes": 4,
                              "image_model": "fake-image",
                              "video_model": "fake-video"})
    assert r.status_code == 202
    body = r.json()
    assert "estimate" in body
    assert body["estimate"]["num_scenes"] == 4
    assert body["estimate"]["clips"] == 4
    assert isinstance(body["estimate"]["cost_usd"], (int, float))


def test_direct_with_auto_video_model(tmp_path):
    """Director accepts 'auto' as the video model."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    p1, p2 = mock_shot_list()
    with p1, p2:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                        json={"num_scenes": 2,
                              "image_model": "fake-image",
                              "video_model": "auto"})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["clips"]) == 2
    for clip in doc["clips"]:
        assert clip["model"] != "auto"


def test_direct_progress_tracking(tmp_path):
    """Job tracks progress through the 5 stages."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    p1, p2 = mock_shot_list()
    with p1, p2:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                        json={"num_scenes": 2,
                              "image_model": "fake-image",
                              "video_model": "fake-video"})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)

    assert job["status"] == "done"
    assert job["total"] == 5
    assert job["completed"] == 5


def test_direct_with_character(tmp_path):
    """Director passes character_id through to scenes."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    char = client.post(f"/api/profiles/{prof}/characters",
                       data={"name": "Mila", "description": "doll"},
                       files=[("files", ("doll.png", TINY_PNG, "image/png"))]).json()

    p1, p2 = mock_shot_list()
    with p1, p2:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                        json={"num_scenes": 2,
                              "image_model": "fake-image",
                              "video_model": "fake-video",
                              "character_id": char["id"]})
    assert r.status_code == 202
    job = wait_job(client, prof, slug)
    assert job["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    for sc in doc["scenes"]:
        assert sc["character_id"] == char["id"]


def test_direct_conflict_when_job_running(tmp_path):
    """Director returns 409 if a job is already running."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    p1, p2 = mock_shot_list()
    with p1, p2:
        r1 = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                         json={"num_scenes": 2,
                               "image_model": "fake-image",
                               "video_model": "fake-video"})
        assert r1.status_code == 202

        # Second call while job is running should 409
        r2 = client.post(f"/api/profiles/{prof}/projects/{slug}/direct",
                         json={"num_scenes": 2,
                               "image_model": "fake-image",
                               "video_model": "fake-video"})
        assert r2.status_code == 409

    wait_job(client, prof, slug)
