"""Tests for Style Consistency Scoring — cosine similarity + outlier detection."""

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sceneforge.backends.clip_scorer import (
    _cosine_similarity,
    find_outliers,
    score_consistency,
    score_project_consistency,
)
from sceneforge.project import ImageArtifact, Project, Scene
from sceneforge.server import create_app


# --------------------------------------------------------- unit tests


def test_cosine_similarity_identical():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_similar():
    a = [1.0, 1.0]
    b = [1.0, 0.9]
    sim = _cosine_similarity(a, b)
    assert sim > 0.99


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    assert _cosine_similarity(a, b) == 0.0


def test_score_consistency_single_image(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 100)
    assert score_consistency([img], embeddings=[[1.0, 0.0]]) == 1.0


def test_score_consistency_identical_embeddings(tmp_path):
    images = [tmp_path / f"{i}.png" for i in range(3)]
    for img in images:
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)

    embeddings = [[1.0, 0.5, 0.3]] * 3
    score = score_consistency(images, embeddings=embeddings)
    assert score == pytest.approx(1.0, abs=0.001)


def test_score_consistency_diverse_embeddings(tmp_path):
    images = [tmp_path / f"{i}.png" for i in range(3)]
    for img in images:
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)

    embeddings = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    score = score_consistency(images, embeddings=embeddings)
    assert score == pytest.approx(0.0, abs=0.001)


def test_find_outliers_no_outliers(tmp_path):
    images = [tmp_path / f"{i}.png" for i in range(3)]
    for img in images:
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)

    embeddings = [
        [1.0, 0.5],
        [1.0, 0.6],
        [1.0, 0.55],
    ]
    outliers = find_outliers(images, threshold=0.7, embeddings=embeddings)
    assert outliers == []


def test_find_outliers_with_outlier(tmp_path):
    images = [tmp_path / f"{i}.png" for i in range(4)]
    for img in images:
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)

    embeddings = [
        [1.0, 0.5, 0.0],
        [1.0, 0.6, 0.0],
        [1.0, 0.55, 0.0],
        [0.0, 0.0, 1.0],  # outlier
    ]
    outliers = find_outliers(images, threshold=0.7, embeddings=embeddings)
    assert 3 in outliers


def test_find_outliers_single_image():
    outliers = find_outliers([Path("a.png")], threshold=0.7, embeddings=[[1.0]])
    assert outliers == []


def test_score_project_consistency_no_selected(tmp_path):
    proj = Project(name="test", root=tmp_path)
    proj.scenes = [
        Scene(id="s1", description="look", images=[
            ImageArtifact(file="img/a.png", prompt="test", model="flux"),
        ], selected_image=None),
    ]
    result = score_project_consistency(proj, embeddings=[])
    assert result["score"] == 1.0
    assert result["images_scored"] == 0


def test_score_project_consistency_with_selected(tmp_path):
    (tmp_path / "img").mkdir()
    for name in ["a.png", "b.png", "c.png"]:
        (tmp_path / "img" / name).write_bytes(b"\x89PNG" + b"\x00" * 100)

    proj = Project(name="test", root=tmp_path)
    proj.scenes = [
        Scene(id="s1", description="look 1", images=[
            ImageArtifact(file="img/a.png", prompt="test", model="flux"),
        ], selected_image=0),
        Scene(id="s2", description="look 2", images=[
            ImageArtifact(file="img/b.png", prompt="test", model="flux"),
        ], selected_image=0),
        Scene(id="s3", description="look 3", images=[
            ImageArtifact(file="img/c.png", prompt="test", model="flux"),
        ], selected_image=0),
    ]

    embeddings = [
        [1.0, 0.5, 0.0],
        [1.0, 0.6, 0.0],
        [0.0, 0.0, 1.0],  # outlier
    ]
    result = score_project_consistency(proj, embeddings=embeddings)
    assert result["images_scored"] == 3
    assert 0 < result["score"] < 1.0
    assert len(result["outliers"]) >= 1
    outlier_ids = [o["scene_id"] for o in result["outliers"]]
    assert "s3" in outlier_ids


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


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof, name="Looks"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts",
        "anchor": "soft light", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def test_score_consistency_endpoint_no_key(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    with patch("sceneforge.config.together_api_key",
               side_effect=RuntimeError("No Together API key. Add it in profile settings or .env.")):
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/score-consistency")
        assert r.status_code == 400
        assert "key" in r.json()["error"]["message"].lower()


def test_score_consistency_endpoint_mocked(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    mock_result = {"score": 0.85, "outliers": [], "images_scored": 3}

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("sceneforge.backends.clip_scorer.score_project_consistency",
               return_value=mock_result):
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/score-consistency")
        assert r.status_code == 200
        data = r.json()
        assert data["score"] == 0.85
        assert data["images_scored"] == 3
