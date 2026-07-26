"""Tests for Data Backup & Export — zip export, import, and round-trip."""

import json
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from sceneforge.backup import export_project_zip, import_project_zip
from sceneforge.project import Clip, ImageArtifact, Project, Scene, SceneRef
from sceneforge.server import create_app

PROF = "test-brand"
TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --------------------------------------------------------- unit tests


def test_export_includes_manifest(tmp_path):
    proj = Project(name="Test Project", concept="test", root=tmp_path)
    proj.add_scene("scene 1")
    proj.save()

    data = export_project_zip(proj)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert "manifest.json" in zf.namelist()
        assert "project.json" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["project_name"] == "Test Project"
        assert manifest["scenes"] == 1
        assert manifest["version"] == 1


def test_export_includes_refs(tmp_path):
    proj = Project(name="Test", root=tmp_path)
    scene = proj.add_scene("look")
    refs_dir = proj.scene_refs_dir(scene)
    refs_dir.mkdir(parents=True)
    (refs_dir / "dress.png").write_bytes(TINY_PNG)
    scene.refs.append(SceneRef(file=f"refs/scenes/{scene.id}/dress.png",
                               label="Dress"))
    proj.save()

    data = export_project_zip(proj)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        assert any("dress.png" in n for n in names)


def test_export_includes_kept_clips(tmp_path):
    proj = Project(name="Test", root=tmp_path)
    clips_dir = proj.clips_dir
    clips_dir.mkdir(parents=True)
    (clips_dir / "clip-01.mp4").write_bytes(b"fake-video")
    (clips_dir / "clip-02.mp4").write_bytes(b"fake-video-2")
    proj.clips = [
        Clip(id="clip-01", file="clips/clip-01.mp4", status="completed", kept=True),
        Clip(id="clip-02", file="clips/clip-02.mp4", status="completed", kept=False),
    ]
    proj.save()

    data = export_project_zip(proj)
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        assert "clips/clip-01.mp4" in names
        assert "clips/clip-02.mp4" not in names


def test_import_creates_project(tmp_path):
    # Create a zip with project.json
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "name": "Imported Look",
            "concept": "test import",
            "style": {},
            "settings": {},
            "characters": [],
            "refs": [],
            "scenes": [],
            "clips": [],
            "sequence": [],
            "captions": {},
            "notes": "",
            "budget_usd": 0,
            "schema_version": 5,
        }))
        zf.writestr("manifest.json", json.dumps({"version": 1}))

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    project = import_project_zip(buf.getvalue(), projects_dir)
    assert project.name == "Imported Look"
    assert project.concept == "test import"


def test_import_invalid_zip_raises(tmp_path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a project")

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    with pytest.raises(ValueError, match="missing project.json"):
        import_project_zip(buf.getvalue(), projects_dir)


def test_round_trip_export_import(tmp_path):
    # Create original project
    proj = Project(name="Round Trip", concept="test round trip", root=tmp_path)
    scene = proj.add_scene("look 1")
    refs_dir = proj.scene_refs_dir(scene)
    refs_dir.mkdir(parents=True)
    (refs_dir / "ref.png").write_bytes(TINY_PNG)
    scene.refs.append(SceneRef(
        file=f"refs/scenes/{scene.id}/ref.png", label="My Ref"))
    proj.save()

    # Export
    data = export_project_zip(proj)

    # Import into new location
    import_dir = tmp_path / "imported" / "projects"
    import_dir.mkdir(parents=True)
    imported = import_project_zip(data, import_dir)

    assert imported.name == "Round Trip"
    assert imported.concept == "test round trip"
    assert len(imported.scenes) == 1
    assert imported.scenes[0].description == "look 1"
    assert len(imported.scenes[0].refs) == 1


def test_import_avoids_slug_collision(tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "imported-look").mkdir()
    (projects_dir / "imported-look" / "project.json").write_text("{}")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "name": "Imported Look",
            "concept": "",
            "style": {},
            "settings": {},
            "characters": [],
            "refs": [],
            "scenes": [],
            "clips": [],
            "sequence": [],
            "captions": {},
            "notes": "",
            "budget_usd": 0,
            "schema_version": 5,
        }))

    project = import_project_zip(buf.getvalue(), projects_dir)
    assert project.root.name != "imported-look"


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


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


def test_backup_project_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/backup.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        assert "project.json" in zf.namelist()
        assert "manifest.json" in zf.namelist()


def test_backup_all_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    create_project(client, prof, "Project 1")
    create_project(client, prof, "Project 2")

    r = client.get(f"/api/profiles/{prof}/backup-all.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        project_jsons = [n for n in names if n.endswith("project.json")]
        assert len(project_jsons) == 2


def test_import_zip_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    # Create a valid project zip
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("project.json", json.dumps({
            "name": "Imported via API",
            "concept": "test import",
            "style": {},
            "settings": {},
            "characters": [],
            "refs": [],
            "scenes": [],
            "clips": [],
            "sequence": [],
            "captions": {},
            "notes": "",
            "budget_usd": 0,
            "schema_version": 5,
        }))

    r = client.post(
        f"/api/profiles/{prof}/import-zip",
        files=[("file", ("backup.zip", buf.getvalue(), "application/zip"))],
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Imported via API"

    # Verify it appears in project list
    r = client.get(f"/api/profiles/{prof}/projects")
    assert len(r.json()) == 1


def test_import_invalid_zip_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(
        f"/api/profiles/{prof}/import-zip",
        files=[("file", ("bad.zip", b"not a zip", "application/zip"))],
    )
    assert r.status_code == 400


def test_round_trip_via_api(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof, "Round Trip Test")

    # Add a scene
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "outfit shot"})

    # Export
    r = client.get(f"/api/profiles/{prof}/projects/{slug}/backup.zip")
    assert r.status_code == 200
    zip_data = r.content

    # Import
    r = client.post(
        f"/api/profiles/{prof}/import-zip",
        files=[("file", ("backup.zip", zip_data, "application/zip"))],
    )
    assert r.status_code == 201
    imported = r.json()
    assert imported["name"] == "Round Trip Test"
    assert len(imported["scenes"]) == 1
    assert imported["scenes"][0]["description"] == "outfit shot"
