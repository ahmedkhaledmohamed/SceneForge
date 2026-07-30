"""Tests for Quick Generate — standalone image/video generation."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sceneforge.server import create_app


PROF = "test-brand"
TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def make_client(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/api/auth/signup", json={
        "email": "test@sceneforge.dev",
        "password": "test-password-123",
        "name": "Test User",
    })
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof, name="Target"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "test",
        "anchor": "soft", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def test_quick_generate_image(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(
        f"/api/profiles/{prof}/quick-generate",
        data={"prompt": "a cup of tea", "model": "fake-image", "mode": "image"},
    )
    assert r.status_code == 202, r.text


def test_quick_generate_results_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.get(f"/api/profiles/{prof}/quick-generate/results")
    assert r.status_code == 200
    data = r.json()
    assert data["images"] == []
    assert data["clips"] == []


def test_quick_generate_results_after_image(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    # Generate
    client.post(
        f"/api/profiles/{prof}/quick-generate",
        data={"prompt": "test image", "model": "fake-image", "mode": "image"},
    )

    # Wait for job
    import time
    for _ in range(30):
        job = client.get(f"/api/profiles/{prof}/projects/_quick/job").json()
        if job["status"] != "running":
            break
        time.sleep(0.2)

    r = client.get(f"/api/profiles/{prof}/quick-generate/results")
    assert r.status_code == 200
    data = r.json()
    assert len(data["images"]) >= 1
    assert data["images"][0]["model"] == "fake-image"


def test_quick_generate_video_requires_file(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(
        f"/api/profiles/{prof}/quick-generate",
        data={"prompt": "test", "model": "fake-video", "mode": "video"},
    )
    assert r.status_code == 400


def test_quick_generate_invalid_mode(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(
        f"/api/profiles/{prof}/quick-generate",
        data={"prompt": "test", "model": "fake-image", "mode": "xyz"},
    )
    assert r.status_code == 400


def test_save_to_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Generate an image first
    client.post(
        f"/api/profiles/{prof}/quick-generate",
        data={"prompt": "save me", "model": "fake-image", "mode": "image"},
    )

    import time
    for _ in range(30):
        job = client.get(f"/api/profiles/{prof}/projects/_quick/job").json()
        if job["status"] != "running":
            break
        time.sleep(0.2)

    results = client.get(f"/api/profiles/{prof}/quick-generate/results").json()
    if results["images"]:
        file_path = results["images"][0]["file"]
        r = client.post(
            f"/api/profiles/{prof}/quick-generate/save-to-project",
            json={"target_slug": slug, "file": file_path},
        )
        assert r.status_code == 200
        assert r.json()["project"] == slug


def test_save_to_project_missing_params(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(
        f"/api/profiles/{prof}/quick-generate/save-to-project",
        json={},
    )
    assert r.status_code == 400
