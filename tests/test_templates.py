"""Project Templates — save/load round-trip, create from template, built-ins."""

import json

from fastapi.testclient import TestClient

from sceneforge.server import create_app
from sceneforge.server.api import BUILTIN_TEMPLATES

PROF = "test-brand"


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    resp = client.post("/api/profiles", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["slug"]


def create_project(client, prof=PROF, name="Looks", concept="outfit posts"):
    resp = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": concept, "anchor": "soft light",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["slug"]


def test_builtin_templates_listed(tmp_path):
    """GET /templates returns all 3 built-in templates with builtin=True."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    resp = client.get(f"/api/profiles/{prof}/templates")
    assert resp.status_code == 200
    templates = resp.json()
    builtins = [t for t in templates if t["builtin"]]
    assert len(builtins) == 3
    names = {t["slug"] for t in builtins}
    assert names == {"product-lookbook", "day-in-the-life", "character-series"}
    for t in builtins:
        assert t["scenes"] > 0


def test_save_and_load_template_round_trip(tmp_path):
    """Save a project as template, verify it appears in the list."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # add some scenes
    for desc in ["hero shot", "detail close-up", "flat lay"]:
        r = client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                        json={"description": desc})
        assert r.status_code == 201

    # save as template
    resp = client.post(
        f"/api/profiles/{prof}/projects/{slug}/save-as-template",
        json={"name": "My Lookbook"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Lookbook"
    assert data["scenes"] == 3
    tpl_slug = data["slug"]

    # verify it shows in list
    templates = client.get(f"/api/profiles/{prof}/templates").json()
    user_templates = [t for t in templates if not t["builtin"]]
    assert len(user_templates) == 1
    assert user_templates[0]["slug"] == tpl_slug
    assert user_templates[0]["scenes"] == 3

    # verify the JSON file on disk has the right structure
    tpl_path = tmp_path / prof / "templates" / f"{tpl_slug}.json"
    assert tpl_path.is_file()
    tpl = json.loads(tpl_path.read_text())
    assert tpl["name"] == "My Lookbook"
    assert tpl["concept"] == "outfit posts"
    assert len(tpl["scenes"]) == 3
    # no generated media in template
    for scene in tpl["scenes"]:
        assert "images" not in scene
        assert "refs" not in scene
        assert "clips" not in scene


def test_create_project_from_builtin_template(tmp_path):
    """Create a project from a built-in template."""
    client = make_client(tmp_path)
    prof = create_profile(client)

    resp = client.post(f"/api/profiles/{prof}/projects/from-template", json={
        "template": "character-series",
        "name": "My Character Post",
    })
    assert resp.status_code == 201
    project = resp.json()
    assert project["name"] == "My Character Post"
    expected_scenes = len(BUILTIN_TEMPLATES["character-series"]["scenes"])
    assert len(project["scenes"]) == expected_scenes
    # scenes should have descriptions from the template
    assert "Portrait" in project["scenes"][0]["description"]


def test_create_project_from_saved_template(tmp_path):
    """Save as template, then create a new project from it."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof, name="Original")

    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "scene one", "pose": "standing"})
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "scene two"})

    # save as template
    save_resp = client.post(
        f"/api/profiles/{prof}/projects/{slug}/save-as-template",
        json={"name": "Saved Template"},
    )
    assert save_resp.status_code == 201
    tpl_slug = save_resp.json()["slug"]

    # create from it
    resp = client.post(f"/api/profiles/{prof}/projects/from-template", json={
        "template": tpl_slug,
        "name": "From Saved",
    })
    assert resp.status_code == 201
    project = resp.json()
    assert project["name"] == "From Saved"
    assert len(project["scenes"]) == 2
    assert project["scenes"][0]["description"] == "scene one"
    assert project["scenes"][0]["pose"] == "standing"


def test_delete_template(tmp_path):
    """Delete a saved template."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "test scene"})
    save_resp = client.post(
        f"/api/profiles/{prof}/projects/{slug}/save-as-template",
        json={"name": "Temp Template"},
    )
    tpl_slug = save_resp.json()["slug"]

    # delete it
    resp = client.delete(f"/api/profiles/{prof}/templates/{tpl_slug}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == tpl_slug

    # verify gone from list
    templates = client.get(f"/api/profiles/{prof}/templates").json()
    user_templates = [t for t in templates if not t["builtin"]]
    assert len(user_templates) == 0


def test_cannot_delete_builtin_template(tmp_path):
    """Built-in templates cannot be deleted."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    resp = client.delete(f"/api/profiles/{prof}/templates/product-lookbook")
    assert resp.status_code == 400
    assert "built-in" in resp.json()["error"]["message"].lower()


def test_cannot_overwrite_builtin_template(tmp_path):
    """Saving a template with a built-in name is rejected."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "test"})
    resp = client.post(
        f"/api/profiles/{prof}/projects/{slug}/save-as-template",
        json={"name": "Product lookbook"},
    )
    assert resp.status_code == 400
    assert "built-in" in resp.json()["error"]["message"].lower()


def test_create_from_nonexistent_template(tmp_path):
    """Creating from a template that doesn't exist returns 404."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    resp = client.post(f"/api/profiles/{prof}/projects/from-template", json={
        "template": "does-not-exist",
        "name": "Test",
    })
    assert resp.status_code == 404


def test_save_template_requires_name(tmp_path):
    """Saving a template without a name is rejected."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    resp = client.post(
        f"/api/profiles/{prof}/projects/{slug}/save-as-template",
        json={"name": ""},
    )
    assert resp.status_code == 400
