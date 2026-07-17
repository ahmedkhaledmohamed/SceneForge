"""Sequence builder tests — ordering, validation, render endpoint."""

import time

from fastapi.testclient import TestClient

from sceneforge.project import Clip, Project
from sceneforge.server import create_app

PROF = "test-brand"


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof=PROF, name="Seq Test"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "test", "anchor": "soft",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def seed_project_with_clips(tmp_path, prof, slug):
    """Add completed clips directly to project.json for testing."""
    root = tmp_path / prof / "projects" / slug
    project = Project.load(root)
    for i in range(3):
        clip = project.add_clip(source_images=[], prompt=f"clip {i}", model="fake")
        clip.status = "completed"
        clip.file = f"clips/{clip.id}.mp4"
        clip.duration_s = 3.0 + i
        # Create a dummy file so file checks pass
        (root / "clips").mkdir(parents=True, exist_ok=True)
        (root / "clips" / f"{clip.id}.mp4").write_bytes(b"\x00" * 16)
    project.save()
    return [c.id for c in project.clips]


# ---------------------------------------------------------------- model


def test_sequence_persists_on_save(tmp_path):
    project = Project(name="t", root=tmp_path)
    c1 = project.add_clip([], prompt="a", model="m")
    c1.status = "completed"
    c2 = project.add_clip([], prompt="b", model="m")
    c2.status = "completed"
    project.sequence = [c2.id, c1.id]
    project.save()

    loaded = Project.load(tmp_path)
    assert loaded.sequence == [c2.id, c1.id]


def test_sequence_defaults_empty(tmp_path):
    project = Project(name="t", root=tmp_path)
    project.save()
    loaded = Project.load(tmp_path)
    assert loaded.sequence == []


# ---------------------------------------------------------------- API


def test_get_empty_sequence(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/sequence")
    assert r.status_code == 200
    data = r.json()
    assert data["sequence"] == []
    assert data["total_duration"] == 0


def test_set_and_get_sequence(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    clip_ids = seed_project_with_clips(tmp_path, prof, slug)

    # Set sequence in reverse order
    r = client.put(
        f"/api/profiles/{prof}/projects/{slug}/sequence",
        json={"clip_ids": list(reversed(clip_ids))},
    )
    assert r.status_code == 200
    data = r.json()
    assert [item["id"] for item in data["sequence"]] == list(reversed(clip_ids))
    assert data["total_duration"] > 0

    # Verify persistence via GET
    r2 = client.get(f"/api/profiles/{prof}/projects/{slug}/sequence")
    assert [item["id"] for item in r2.json()["sequence"]] == list(reversed(clip_ids))


def test_set_sequence_rejects_invalid_ids(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    seed_project_with_clips(tmp_path, prof, slug)

    r = client.put(
        f"/api/profiles/{prof}/projects/{slug}/sequence",
        json={"clip_ids": ["nonexistent-clip"]},
    )
    assert r.status_code == 400
    body = r.json()
    # Error may be in {"error": {...}} or {"detail": {...}}
    err = body.get("error") or body.get("detail") or {}
    assert "invalid" in (err.get("code", "") or "").lower() or "invalid" in str(body).lower()


def test_set_sequence_rejects_pending_clips(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Add a pending clip (not completed)
    root = tmp_path / prof / "projects" / slug
    project = Project.load(root)
    clip = project.add_clip([], prompt="pending", model="fake")
    # status stays "pending" by default
    project.save()

    r = client.put(
        f"/api/profiles/{prof}/projects/{slug}/sequence",
        json={"clip_ids": [clip.id]},
    )
    assert r.status_code == 400


def test_render_empty_sequence_fails(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/sequence/render")
    assert r.status_code == 400
    body = r.json()
    err = body.get("error") or body.get("detail") or {}
    msg = err.get("message", "") if isinstance(err, dict) else str(err)
    assert "empty" in msg.lower()


def test_render_sequence_starts_job(tmp_path):
    """Render should start a background job (it will fail since clips
    are dummy files, but the job should start)."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    clip_ids = seed_project_with_clips(tmp_path, prof, slug)

    # Set sequence
    client.put(
        f"/api/profiles/{prof}/projects/{slug}/sequence",
        json={"clip_ids": clip_ids[:2]},
    )

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/sequence/render")
    assert r.status_code == 202
    assert r.json()["started"] == "render sequence"
