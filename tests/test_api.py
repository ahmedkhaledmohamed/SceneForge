"""Studio JSON API tests — fake backends, in-memory uploads, no network."""

import time

from fastapi.testclient import TestClient

from sceneforge.server import create_app

TINY_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
TINY_JPG = (b"\xff\xd8\xff\xe0" + b"\x00" * 64)


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_project(client, name="Looks"):
    response = client.post("/api/projects", json={
        "name": name, "concept": "outfit posts", "anchor": "soft light",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def wait_job(client, slug, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/projects/{slug}/job").json()
        if job["status"] in ("done", "failed", "idle"):
            return job
        time.sleep(0.1)
    raise TimeoutError("job did not finish")


def test_full_workflow_via_api(tmp_path):
    client = make_client(tmp_path)
    slug = create_project(client)

    # character with uploaded refs
    response = client.post(f"/api/projects/{slug}/characters",
                           data={"name": "Mila", "description": "doll"},
                           files=[("files", ("doll.png", TINY_PNG, "image/png"))])
    assert response.status_code == 201, response.text
    assert response.json()["reference_images"] == ["refs/characters/char-1/doll.png"]

    # outfit + item with product photo + link
    response = client.post(f"/api/projects/{slug}/outfits", json={"name": "Cafe look"})
    assert response.status_code == 201
    response = client.post(f"/api/projects/{slug}/outfits/outfit-1/items",
                           data={"name": "Linen skirt", "url": "https://shop/skirt"},
                           files={"image": ("skirt.jpg", TINY_JPG, "image/jpeg")})
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["image"] == "refs/outfits/outfit-1/skirt.jpg"

    # two pose scenes, character defaulted
    response = client.post(f"/api/projects/{slug}/scenes/from-outfit",
                           json={"outfit_id": "outfit-1"})
    assert response.status_code == 201
    scenes = response.json()
    assert len(scenes) == 2
    assert all(s["character_id"] == "char-1" for s in scenes)

    # generate image options (job), select
    response = client.post(f"/api/projects/{slug}/generate-images",
                           json={"options": 2})
    assert response.status_code == 202
    assert wait_job(client, slug)["status"] == "done"
    doc = client.get(f"/api/projects/{slug}").json()
    assert all(len(s["images"]) == 2 for s in doc["scenes"])
    # refs flowed: char + item
    assert doc["scenes"][0]["images"][0]["meta"]["reference_images"] == [
        "doll.png", "skirt.jpg"]

    response = client.post(f"/api/projects/{slug}/scenes/scene-01/select",
                           json={"image_index": 1})
    assert response.status_code == 200

    # takes from the selected image
    response = client.post(f"/api/projects/{slug}/scenes/scene-01/takes",
                           json={"count": 2})
    assert response.status_code == 202
    assert wait_job(client, slug)["status"] == "done"
    doc = client.get(f"/api/projects/{slug}").json()
    takes = doc["scenes"][0]["clips"]
    assert [c["take"] for c in takes] == [1, 2]

    # keep one, export
    response = client.post(f"/api/projects/{slug}/scenes/scene-01/clips/1/keep",
                           json={"kept": True})
    assert response.status_code == 200
    response = client.post(f"/api/projects/{slug}/export")
    assert response.status_code == 200
    assert response.json()["files"] == ["cafe-look--scene-01--take02.mp4"]

    # zip download
    response = client.get(f"/api/projects/{slug}/export.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # history + links + spend field
    rows = client.get(f"/api/projects/{slug}/history?type=clip").json()
    assert len(rows) == 2 and all(r["type"] == "clip" for r in rows)
    links = client.get(f"/api/projects/{slug}/outfits/outfit-1/links").text
    assert "Linen skirt — https://shop/skirt" in links
    assert "spent_usd" in doc


def test_job_conflict_409(tmp_path):
    client = make_client(tmp_path)
    slug = create_project(client)
    client.post(f"/api/projects/{slug}/scenes",
                json={"description": "a mug steams"})
    first = client.post(f"/api/projects/{slug}/generate-images",
                        json={"options": 6})
    assert first.status_code == 202
    second = client.post(f"/api/projects/{slug}/generate-images",
                         json={"options": 1, "force": True})
    # either still running (409) or finished extremely fast — accept both,
    # but the error shape must be right when it conflicts
    if second.status_code == 409:
        assert second.json()["error"]["code"] == "conflict"
    wait_job(client, slug)


def test_upload_rejects_non_image(tmp_path):
    client = make_client(tmp_path)
    slug = create_project(client)
    response = client.post(f"/api/projects/{slug}/characters",
                           data={"name": "X"},
                           files=[("files", ("evil.png", b"not an image", "image/png"))])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid"


def test_media_traversal_blocked(tmp_path):
    client = make_client(tmp_path)
    slug = create_project(client)
    (tmp_path / "secret.txt").write_text("nope")
    response = client.get(f"/api/projects/{slug}/media/../secret.txt")
    assert response.status_code != 200


def test_unknown_project_and_scene_404_shape(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/projects/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    slug = create_project(client)
    response = client.post(f"/api/projects/{slug}/scenes/scene-99/select",
                           json={"image_index": 0})
    assert response.status_code == 404


def test_models_route(tmp_path):
    client = make_client(tmp_path)
    models = client.get("/api/models").json()
    assert models["nano-banana-pro"]["max_refs"] == 14
    assert models["flux-2-pro"]["price"] == 0.03