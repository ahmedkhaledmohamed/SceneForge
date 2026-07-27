"""Tests for Generation Analytics — computation + API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sceneforge.analytics import profile_analytics, project_analytics
from sceneforge.project import Clip, ImageArtifact, Project, Scene
from sceneforge.server import create_app

PROF = "test-brand"


# --------------------------------------------------------- unit tests


def test_project_analytics_empty():
    proj = Project(name="test")
    result = project_analytics(proj)
    assert result["total_images"] == 0
    assert result["total_clips"] == 0
    assert result["total_spend_usd"] == 0
    assert result["avg_cost_per_kept"] is None
    assert result["models"] == {}


def test_project_analytics_with_data():
    proj = Project(name="test")
    proj.scenes = [
        Scene(id="s1", description="look 1", images=[
            ImageArtifact(file="a.png", prompt="test", model="flux-schnell",
                          meta={"cost_usd": 0.003}),
            ImageArtifact(file="b.png", prompt="test", model="flux-schnell",
                          meta={"cost_usd": 0.003}),
        ]),
        Scene(id="s2", description="look 2", images=[
            ImageArtifact(file="c.png", prompt="test", model="nano-banana-pro",
                          meta={"cost_usd": 0.134}),
        ]),
    ]
    proj.clips = [
        Clip(id="clip-01", model="seedance-2.0", status="completed",
             kept=True, meta={"cost_usd": 0.80}),
        Clip(id="clip-02", model="seedance-2.0", status="completed",
             kept=False, meta={"cost_usd": 0.80}),
        Clip(id="clip-03", model="kling-2.1", status="failed",
             meta={"cost_usd": 0.18}),
    ]

    result = project_analytics(proj)
    assert result["total_images"] == 3
    assert result["total_clips"] == 3
    assert result["total_kept"] == 1
    assert result["total_spend_usd"] == pytest.approx(1.92, abs=0.01)
    assert result["avg_cost_per_kept"] == pytest.approx(1.92, abs=0.01)

    # Model stats
    assert "flux-schnell" in result["models"]
    assert result["models"]["flux-schnell"]["images"] == 2
    assert result["models"]["flux-schnell"]["spend_usd"] == pytest.approx(0.006, abs=0.001)

    assert "seedance-2.0" in result["models"]
    assert result["models"]["seedance-2.0"]["clips"] == 2
    assert result["models"]["seedance-2.0"]["clips_kept"] == 1
    assert result["models"]["seedance-2.0"]["keep_rate"] == 0.5
    assert result["models"]["seedance-2.0"]["success_rate"] == 1.0

    assert "kling-2.1" in result["models"]
    assert result["models"]["kling-2.1"]["clips_failed"] == 1
    assert result["models"]["kling-2.1"]["success_rate"] == 0.0


def test_project_analytics_cost_per_kept():
    proj = Project(name="test")
    proj.clips = [
        Clip(id="c1", model="seedance-2.0", status="completed",
             kept=True, meta={"cost_usd": 0.80}),
        Clip(id="c2", model="seedance-2.0", status="completed",
             kept=True, meta={"cost_usd": 0.80}),
    ]
    result = project_analytics(proj)
    assert result["models"]["seedance-2.0"]["cost_per_kept"] == pytest.approx(0.80, abs=0.01)


def test_profile_analytics(tmp_path):
    from sceneforge.profile import Profile, create_profile

    prof = create_profile("test-brand", tmp_path)

    # Create a project with data
    pj_dir = prof.projects_dir / "project-1"
    pj_dir.mkdir(parents=True)
    proj = Project(name="Project 1", root=pj_dir)
    proj.scenes = [
        Scene(id="s1", description="look", images=[
            ImageArtifact(file="a.png", prompt="test", model="flux-schnell",
                          meta={"cost_usd": 0.003},
                          created_at="2026-07-14T10:00:00+00:00"),
        ]),
    ]
    proj.clips = [
        Clip(id="c1", model="seedance-2.0", status="completed",
             kept=True, meta={"cost_usd": 0.80},
             created_at="2026-07-14T10:00:00+00:00"),
    ]
    proj.save()

    result = profile_analytics(prof.root)
    assert result["projects"] == 1
    assert result["total_images"] == 1
    assert result["total_clips"] == 1
    assert result["total_kept"] == 1
    assert result["total_spend_usd"] == pytest.approx(0.803, abs=0.001)
    assert result["best_value_model"] == "seedance-2.0"
    assert len(result["spend_trend"]) >= 1


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/api/auth/signup", json={
        "email": "test@sceneforge.dev",
        "password": "test-password-123",
        "name": "Test User",
    })
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return client


def create_test_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_test_project(client, prof, name="Looks"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts",
        "anchor": "soft light", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def test_profile_analytics_endpoint_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_test_profile(client)
    r = client.get(f"/api/profiles/{prof}/analytics")
    assert r.status_code == 200
    data = r.json()
    assert data["projects"] == 0
    assert data["total_spend_usd"] == 0


def test_profile_analytics_endpoint_with_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_test_profile(client)
    slug = create_test_project(client, prof)

    # Add a scene
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "look 1"})

    r = client.get(f"/api/profiles/{prof}/analytics")
    assert r.status_code == 200
    data = r.json()
    assert data["projects"] == 1


def test_project_analytics_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_test_profile(client)
    slug = create_test_project(client, prof)

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/analytics")
    assert r.status_code == 200
    data = r.json()
    assert data["total_images"] == 0
    assert data["total_clips"] == 0
    assert data["total_spend_usd"] == 0


def test_project_analytics_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_test_profile(client)
    r = client.get(f"/api/profiles/{prof}/projects/nonexistent/analytics")
    assert r.status_code == 404
