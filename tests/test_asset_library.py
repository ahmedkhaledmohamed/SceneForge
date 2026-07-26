"""Tests for Asset Library — CRUD, filtering, and asset-to-ref flow."""

import pytest
from fastapi.testclient import TestClient

from sceneforge.profile import Asset, Profile
from sceneforge.server import create_app

PROF = "test-brand"

TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --------------------------------------------------------- unit tests


def test_asset_defaults():
    a = Asset(id="asset-1", file="assets/dress.png")
    assert a.tags == []
    assert a.role == "garment"
    assert a.url == ""
    assert a.projects_used == []
    assert a.created_at


def test_profile_add_asset():
    prof = Profile(name="test")
    a = prof.add_asset("assets/dress.png", label="White Dress",
                       tags=["fashion", "summer"])
    assert a.id == "asset-1"
    assert a.label == "White Dress"
    assert len(prof.assets) == 1


def test_profile_find_asset():
    prof = Profile(name="test")
    prof.add_asset("assets/a.png", label="A")
    prof.add_asset("assets/b.png", label="B")
    found = prof.find_asset("asset-2")
    assert found.label == "B"


def test_profile_find_asset_not_found():
    prof = Profile(name="test")
    with pytest.raises(KeyError, match="No asset"):
        prof.find_asset("asset-99")


def test_assets_persist(tmp_path):
    prof = Profile(name="test", root=tmp_path)
    (tmp_path / "projects").mkdir()
    prof.add_asset("assets/dress.png", label="Dress", tags=["fashion"])
    prof.save()

    loaded = Profile.load(tmp_path)
    assert len(loaded.assets) == 1
    assert loaded.assets[0].label == "Dress"
    assert loaded.assets[0].tags == ["fashion"]


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


def upload_asset(client, prof, label="White Dress", role="garment",
                 tags="fashion,summer"):
    r = client.post(
        f"/api/profiles/{prof}/assets",
        data={"role": role, "label": label, "tags": tags},
        files=[("file", ("dress.png", TINY_PNG, "image/png"))],
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_list_assets_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    r = client.get(f"/api/profiles/{prof}/assets")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_and_list_asset(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    data = upload_asset(client, prof)
    assert data["label"] == "White Dress"
    assert data["role"] == "garment"
    assert data["tags"] == ["fashion", "summer"]
    assert data["file"].startswith("assets/")

    r = client.get(f"/api/profiles/{prof}/assets")
    assert len(r.json()) == 1


def test_filter_assets_by_role(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    upload_asset(client, prof, label="Dress", role="garment")
    upload_asset(client, prof, label="Backdrop", role="background")

    r = client.get(f"/api/profiles/{prof}/assets?role=garment")
    assert len(r.json()) == 1
    assert r.json()[0]["label"] == "Dress"

    r = client.get(f"/api/profiles/{prof}/assets?role=background")
    assert len(r.json()) == 1
    assert r.json()[0]["label"] == "Backdrop"


def test_filter_assets_by_tag(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    upload_asset(client, prof, label="Dress", tags="fashion,summer")
    upload_asset(client, prof, label="Shoes", tags="fashion,winter")

    r = client.get(f"/api/profiles/{prof}/assets?tag=summer")
    assert len(r.json()) == 1
    assert r.json()[0]["label"] == "Dress"


def test_delete_asset(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    data = upload_asset(client, prof)
    aid = data["id"]

    r = client.delete(f"/api/profiles/{prof}/assets/{aid}")
    assert r.status_code == 200
    assert r.json() == {"deleted": aid}

    r = client.get(f"/api/profiles/{prof}/assets")
    assert r.json() == []


def test_delete_asset_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    r = client.delete(f"/api/profiles/{prof}/assets/asset-99")
    assert r.status_code == 404


def test_ref_from_asset(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Create scene
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "outfit shot"})
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    sid = proj["scenes"][0]["id"]

    # Upload asset
    asset = upload_asset(client, prof, label="White Dress",
                         role="garment", tags="fashion")

    # Add asset as scene ref
    r = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/refs/from-asset/{asset['id']}"
    )
    assert r.status_code == 201
    ref = r.json()
    assert ref["label"] == "White Dress"
    assert ref["role"] == "garment"

    # Verify ref was added to scene
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(proj["scenes"][0]["refs"]) == 1

    # Verify projects_used was updated
    r = client.get(f"/api/profiles/{prof}/assets")
    assert slug in r.json()[0]["projects_used"]


def test_ref_from_asset_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "shot"})
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    sid = proj["scenes"][0]["id"]

    r = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/refs/from-asset/asset-99"
    )
    assert r.status_code == 404


def test_ref_from_asset_tracks_multiple_projects(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug1 = create_project(client, prof, name="Project 1")
    slug2 = create_project(client, prof, name="Project 2")

    asset = upload_asset(client, prof)

    # Add scene to each project and use the asset
    for slug in [slug1, slug2]:
        client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                    json={"description": "shot"})
        proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
        sid = proj["scenes"][0]["id"]
        client.post(
            f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/refs/from-asset/{asset['id']}"
        )

    r = client.get(f"/api/profiles/{prof}/assets")
    assert len(r.json()[0]["projects_used"]) == 2
