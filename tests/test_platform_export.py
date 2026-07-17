"""Platform-aware export tests — config validation, endpoint errors."""

from fastapi.testclient import TestClient

from sceneforge import config
from sceneforge.project import Project
from sceneforge.server import create_app

PROF = "test-brand"


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof=PROF, name="Export Test"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "test", "anchor": "soft",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


# ------------------------------------------------------------ config


def test_platforms_dict_has_required_fields():
    required = {"label", "aspect", "max_duration", "width", "height", "codec"}
    for name, spec in config.PLATFORMS.items():
        missing = required - set(spec.keys())
        assert not missing, f"Platform '{name}' missing fields: {missing}"


def test_platforms_dict_values_are_valid():
    for name, spec in config.PLATFORMS.items():
        assert isinstance(spec["label"], str) and spec["label"]
        assert isinstance(spec["width"], int) and spec["width"] > 0
        assert isinstance(spec["height"], int) and spec["height"] > 0
        assert isinstance(spec["max_duration"], int) and spec["max_duration"] > 0
        assert isinstance(spec["codec"], str) and spec["codec"]


def test_all_platforms_present():
    assert set(config.PLATFORMS.keys()) == {"tiktok", "reels", "shorts", "pinterest"}


# ------------------------------------------------------------ API


def test_get_platforms(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/platforms")
    assert r.status_code == 200
    data = r.json()
    assert "tiktok" in data
    assert "reels" in data
    assert data["tiktok"]["width"] == 1080


def test_export_unknown_platform(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/export/fakebook")
    assert r.status_code == 400
    body = r.json()
    err = body.get("error") or body.get("detail") or {}
    msg = err.get("message", "") if isinstance(err, dict) else str(err)
    assert "unknown" in msg.lower() or "fakebook" in msg.lower()


def test_export_no_sequence_no_kept(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/export/tiktok")
    assert r.status_code == 400
    body = r.json()
    err = body.get("error") or body.get("detail") or {}
    msg = err.get("message", "") if isinstance(err, dict) else str(err)
    assert "no rendered sequence" in msg.lower() or "keep" in msg.lower()
