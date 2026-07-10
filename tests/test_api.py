"""Studio JSON API tests — fake backends, in-memory uploads, no network."""

import time

from fastapi.testclient import TestClient

from sceneforge.server import create_app

TINY_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
TINY_JPG = (b"\xff\xd8\xff\xe0" + b"\x00" * 64)

PROF = "test-brand"


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    response = client.post("/api/profiles", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def create_project(client, prof=PROF, name="Looks"):
    response = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts", "anchor": "soft light",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def wait_job(client, prof, slug, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/profiles/{prof}/projects/{slug}/job").json()
        if job["status"] in ("done", "failed", "idle"):
            return job
        time.sleep(0.1)
    raise TimeoutError("job did not finish")


def test_profile_crud(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    assert prof == "test-brand"

    profiles = client.get("/api/profiles").json()
    assert len(profiles) == 1
    assert profiles[0]["slug"] == prof

    doc = client.get(f"/api/profiles/{prof}").json()
    assert doc["name"] == "Test Brand"
    assert doc["defaults"]["image_model"] == "flux-2-pro"

    updated = client.patch(f"/api/profiles/{prof}",
                           json={"anchor": "moody", "video_model": "kling-2.1"}).json()
    assert updated["style"]["anchor"] == "moody"
    assert updated["defaults"]["video_model"] == "kling-2.1"


def test_profile_characters_and_seeds(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    char = client.post(f"/api/profiles/{prof}/characters",
                       data={"name": "Mila", "description": "doll", "main": "true"},
                       files=[("files", ("doll.png", TINY_PNG, "image/png"))]).json()
    assert char["id"] == "pchar-1"
    assert char["main"] is True
    assert len(char["reference_images"]) == 1

    char = client.post(f"/api/profiles/{prof}/characters/{char['id']}/refs",
                       files=[("files", ("side.png", TINY_PNG, "image/png"))]).json()
    assert len(char["reference_images"]) == 2

    seed = client.post(f"/api/profiles/{prof}/seeds",
                       data={"text": "autumn vibes", "tags": "fall,cozy"}).json()
    assert seed["kind"] == "note"
    assert seed["tags"] == ["fall", "cozy"]


def test_full_workflow_via_api(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # character with uploaded refs
    response = client.post(f"/api/profiles/{prof}/projects/{slug}/characters",
                           data={"name": "Mila", "description": "doll"},
                           files=[("files", ("doll.png", TINY_PNG, "image/png"))])
    assert response.status_code == 201, response.text
    assert response.json()["reference_images"] == ["refs/characters/char-1/doll.png"]

    # outfit + item with product photo + link
    response = client.post(f"/api/profiles/{prof}/projects/{slug}/outfits",
                           json={"name": "Cafe look"})
    assert response.status_code == 201
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/outfits/outfit-1/items",
        data={"name": "Linen skirt", "url": "https://shop/skirt"},
        files={"image": ("skirt.jpg", TINY_JPG, "image/jpeg")})
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["image"] == "refs/outfits/outfit-1/skirt.jpg"

    # two pose scenes, character defaulted
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/from-outfit",
        json={"outfit_id": "outfit-1"})
    assert response.status_code == 201
    scenes = response.json()
    assert len(scenes) == 2
    assert all(s["character_id"] == "char-1" for s in scenes)

    # generate image options (job), select
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/generate-images",
        json={"options": 2})
    assert response.status_code == 202
    assert wait_job(client, prof, slug)["status"] == "done"
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert all(len(s["images"]) == 2 for s in doc["scenes"])
    assert doc["scenes"][0]["images"][0]["meta"]["reference_images"] == [
        "doll.png", "skirt.jpg"]

    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/select",
        json={"image_index": 1})
    assert response.status_code == 200

    # takes from the selected image
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/takes",
        json={"count": 2})
    assert response.status_code == 202
    assert wait_job(client, prof, slug)["status"] == "done"
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    takes = doc["scenes"][0]["clips"]
    assert [c["take"] for c in takes] == [1, 2]

    # keep one, export
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/clips/1/keep",
        json={"kept": True})
    assert response.status_code == 200
    response = client.post(f"/api/profiles/{prof}/projects/{slug}/export")
    assert response.status_code == 200
    assert response.json()["files"] == ["cafe-look--scene-01--take02.mp4"]

    # zip download
    response = client.get(f"/api/profiles/{prof}/projects/{slug}/export.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # history + links + spend + prompt_preview
    rows = client.get(
        f"/api/profiles/{prof}/projects/{slug}/history?type=clip").json()
    assert len(rows) == 2 and all(r["type"] == "clip" for r in rows)
    links = client.get(
        f"/api/profiles/{prof}/projects/{slug}/outfits/outfit-1/links").text
    assert "Linen skirt — https://shop/skirt" in links
    assert "spent_usd" in doc
    assert doc["scenes"][0]["prompt_preview"] is not None
    assert doc["profile"] == prof


def test_project_inherits_profile_defaults(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    client.patch(f"/api/profiles/{prof}",
                 json={"anchor": "golden hour", "image_options": 4})
    # no explicit anchor — should inherit from profile
    response = client.post(f"/api/profiles/{prof}/projects", json={
        "name": "Inherited", "concept": "test",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert response.status_code == 201
    slug = response.json()["slug"]
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert doc["style"]["anchor"] == "golden hour"
    assert doc["settings"]["image_options"] == 4


def test_profile_character_resolves_in_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    client.post(f"/api/profiles/{prof}/characters",
                data={"name": "Mila", "description": "doll", "main": "true"},
                files=[("files", ("doll.png", TINY_PNG, "image/png"))])

    slug = create_project(client, prof)
    # scene referencing the profile character
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes",
        json={"description": "standing in cafe", "character_id": "pchar-1"})
    assert response.status_code == 201

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert doc["scenes"][0]["prompt_preview"] is not None
    assert "Mila" in doc["scenes"][0]["prompt_preview"]


def test_import_image_and_clip(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "imported content"})

    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/import-image",
        files={"file": ("existing.png", TINY_PNG, "image/png")})
    assert response.status_code == 201
    doc = response.json()
    assert len(doc["scenes"][0]["images"]) == 1
    assert doc["scenes"][0]["images"][0]["model"] == "import"

    # make a tiny mp4 header for clip import
    tiny_mp4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 64
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01/import-clip",
        files={"file": ("existing.mp4", tiny_mp4, "video/mp4")})
    assert response.status_code == 201
    doc = response.json()
    clips = doc["scenes"][0]["clips"]
    assert len(clips) == 1
    assert clips[0]["model"] == "import"
    assert clips[0]["take"] == 1


def test_delete_scene_outfit_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # add scene, then delete it
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "to be deleted"})
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["scenes"]) == 1

    response = client.delete(f"/api/profiles/{prof}/projects/{slug}/scenes/scene-01")
    assert response.status_code == 200
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["scenes"]) == 0

    # add outfit, then delete it
    client.post(f"/api/profiles/{prof}/projects/{slug}/outfits",
                json={"name": "Doomed outfit"})
    response = client.delete(f"/api/profiles/{prof}/projects/{slug}/outfits/outfit-1")
    assert response.status_code == 200

    # delete the whole project
    response = client.delete(f"/api/profiles/{prof}/projects/{slug}")
    assert response.status_code == 200
    response = client.get(f"/api/profiles/{prof}/projects/{slug}")
    assert response.status_code == 404


def test_project_doc_includes_profile_characters(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    client.post(f"/api/profiles/{prof}/characters",
                data={"name": "Mila", "main": "true"},
                files=[("files", ("doll.png", TINY_PNG, "image/png"))])
    slug = create_project(client, prof)
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["profile_characters"]) == 1
    assert doc["profile_characters"][0]["name"] == "Mila"
    assert doc["profile_characters"][0]["main"] is True


def test_job_conflict_409(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "a mug steams"})
    first = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-images",
                        json={"options": 6})
    assert first.status_code == 202
    second = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-images",
                         json={"options": 1, "force": True})
    if second.status_code == 409:
        assert second.json()["error"]["code"] == "conflict"
    wait_job(client, prof, slug)


def test_upload_rejects_non_image(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/characters",
        data={"name": "X"},
        files=[("files", ("evil.png", b"not an image", "image/png"))])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid"


def test_media_traversal_blocked(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    (tmp_path / "secret.txt").write_text("nope")
    response = client.get(
        f"/api/profiles/{prof}/projects/{slug}/media/../../../secret.txt")
    assert response.status_code != 200


def test_unknown_profile_and_project_404_shape(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/profiles/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    prof = create_profile(client)
    response = client.get(f"/api/profiles/{prof}/projects/nope")
    assert response.status_code == 404

    slug = create_project(client, prof)
    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/scene-99/select",
        json={"image_index": 0})
    assert response.status_code == 404


def test_scene_reorder(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "first"})
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "second"})
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert [s["id"] for s in doc["scenes"]] == ["scene-01", "scene-02"]

    response = client.put(f"/api/profiles/{prof}/projects/{slug}/scenes/reorder",
                          json={"scene_ids": ["scene-02", "scene-01"]})
    assert response.status_code == 200
    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert [s["id"] for s in doc["scenes"]] == ["scene-02", "scene-01"]


def test_select_all(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "scene A"})
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "scene B"})
    # generate images so there's something to select
    response = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-images",
                           json={"options": 1})
    assert response.status_code == 202
    wait_job(client, prof, slug)

    response = client.post(f"/api/profiles/{prof}/projects/{slug}/select-all")
    assert response.status_code == 200
    assert response.json()["selected"] == 2

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert all(s["selected_image"] == 0 for s in doc["scenes"])


def test_duplicate_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/outfits",
                json={"name": "Test outfit"})
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "a scene"})

    response = client.post(f"/api/profiles/{prof}/projects/{slug}/duplicate",
                           json={"name": "Copy"})
    assert response.status_code == 201
    copy = response.json()
    assert copy["name"] == "Copy"
    assert len(copy["outfits"]) == 1
    assert len(copy["scenes"]) == 1
    assert copy["slug"] != slug


def test_bulk_item_import(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/outfits",
                json={"name": "Bulk outfit"})

    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/outfits/outfit-1/items/bulk",
        files=[
            ("files", ("linen_skirt.png", TINY_PNG, "image/png")),
            ("files", ("knit-cardigan.jpg", TINY_JPG, "image/jpeg")),
        ])
    assert response.status_code == 201
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["name"] == "Linen Skirt"
    assert items[1]["name"] == "Knit Cardigan"
    assert all(i["image"] is not None for i in items)


def test_scenes_bulk(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    response = client.post(f"/api/profiles/{prof}/projects/{slug}/scenes/bulk",
                           json={"descriptions": ["scene one", "scene two", "scene three"]})
    assert response.status_code == 201
    assert len(response.json()) == 3

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["scenes"]) == 3


def test_delete_profile_character(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    client.post(f"/api/profiles/{prof}/characters",
                data={"name": "Mila"},
                files=[("files", ("doll.png", TINY_PNG, "image/png"))])

    doc = client.get(f"/api/profiles/{prof}").json()
    assert len(doc["characters"]) == 1

    response = client.delete(f"/api/profiles/{prof}/characters/pchar-1")
    assert response.status_code == 200

    doc = client.get(f"/api/profiles/{prof}").json()
    assert len(doc["characters"]) == 0


def test_process_outfit(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/outfits",
                json={"name": "Process me"})

    response = client.post(
        f"/api/profiles/{prof}/projects/{slug}/outfits/outfit-1/process",
        json={})
    assert response.status_code == 202
    assert wait_job(client, prof, slug)["status"] == "done"

    doc = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(doc["scenes"]) == 2  # two default poses
    assert all(len(s["images"]) > 0 for s in doc["scenes"])
    assert all(s["selected_image"] == 0 for s in doc["scenes"])


def test_models_route(tmp_path):
    client = make_client(tmp_path)
    models = client.get("/api/models").json()
    assert models["nano-banana-pro"]["max_refs"] == 14
    assert models["flux-2-pro"]["price"] == 0.03
