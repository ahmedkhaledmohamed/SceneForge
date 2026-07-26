"""Tests for Prompt Library — CRUD + usage counter."""

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from sceneforge.profile import Profile, SavedPrompt
from sceneforge.server import create_app

PROF = "test-brand"


# --------------------------------------------------------- unit tests


def test_saved_prompt_defaults():
    p = SavedPrompt(id="prompt-1", text="a golden hour portrait")
    assert p.tags == []
    assert p.model == ""
    assert p.times_used == 0
    assert p.created_at  # auto-set


def test_profile_add_prompt():
    prof = Profile(name="test")
    p = prof.add_prompt("sunset portrait", tags=["fashion", "golden-hour"])
    assert p.id == "prompt-1"
    assert p.text == "sunset portrait"
    assert p.tags == ["fashion", "golden-hour"]
    assert len(prof.saved_prompts) == 1


def test_profile_find_prompt():
    prof = Profile(name="test")
    prof.add_prompt("first")
    prof.add_prompt("second")
    found = prof.find_prompt("prompt-2")
    assert found.text == "second"


def test_profile_find_prompt_not_found():
    prof = Profile(name="test")
    with pytest.raises(KeyError, match="No prompt"):
        prof.find_prompt("prompt-99")


def test_saved_prompts_persist(tmp_path):
    prof = Profile(name="test", root=tmp_path)
    (tmp_path / "projects").mkdir()
    prof.add_prompt("test prompt", tags=["tag1"])
    prof.save()

    loaded = Profile.load(tmp_path)
    assert len(loaded.saved_prompts) == 1
    assert loaded.saved_prompts[0].text == "test prompt"
    assert loaded.saved_prompts[0].tags == ["tag1"]


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def test_list_prompts_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    r = client.get(f"/api/profiles/{prof}/prompts")
    assert r.status_code == 200
    assert r.json() == []


def test_save_and_list_prompt(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(f"/api/profiles/{prof}/prompts", json={
        "text": "a golden hour portrait in café",
        "tags": ["fashion", "golden-hour"],
        "model": "flux-schnell",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["text"] == "a golden hour portrait in café"
    assert data["tags"] == ["fashion", "golden-hour"]
    assert data["model"] == "flux-schnell"
    assert data["times_used"] == 0

    r = client.get(f"/api/profiles/{prof}/prompts")
    assert len(r.json()) == 1


def test_save_prompt_requires_text(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(f"/api/profiles/{prof}/prompts", json={"text": ""})
    assert r.status_code == 400


def test_save_prompt_tags_as_string(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(f"/api/profiles/{prof}/prompts", json={
        "text": "test prompt",
        "tags": "fashion, golden-hour, ootd",
    })
    assert r.status_code == 201
    assert r.json()["tags"] == ["fashion", "golden-hour", "ootd"]


def test_filter_prompts_by_tag(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    client.post(f"/api/profiles/{prof}/prompts", json={
        "text": "sunset look", "tags": ["fashion", "sunset"],
    })
    client.post(f"/api/profiles/{prof}/prompts", json={
        "text": "product detail", "tags": ["product"],
    })

    r = client.get(f"/api/profiles/{prof}/prompts?tag=fashion")
    assert len(r.json()) == 1
    assert r.json()[0]["text"] == "sunset look"

    r = client.get(f"/api/profiles/{prof}/prompts?tag=product")
    assert len(r.json()) == 1
    assert r.json()[0]["text"] == "product detail"

    r = client.get(f"/api/profiles/{prof}/prompts")
    assert len(r.json()) == 2


def test_delete_prompt(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    client.post(f"/api/profiles/{prof}/prompts", json={"text": "delete me"})
    r = client.delete(f"/api/profiles/{prof}/prompts/prompt-1")
    assert r.status_code == 200
    assert r.json() == {"deleted": "prompt-1"}

    r = client.get(f"/api/profiles/{prof}/prompts")
    assert r.json() == []


def test_delete_prompt_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.delete(f"/api/profiles/{prof}/prompts/prompt-99")
    assert r.status_code == 404


def test_use_prompt_increments_counter(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    client.post(f"/api/profiles/{prof}/prompts", json={"text": "reuse me"})

    r = client.post(f"/api/profiles/{prof}/prompts/prompt-1/use")
    assert r.status_code == 200
    assert r.json()["text"] == "reuse me"
    assert r.json()["times_used"] == 1

    r = client.post(f"/api/profiles/{prof}/prompts/prompt-1/use")
    assert r.json()["times_used"] == 2

    # Verify persisted
    r = client.get(f"/api/profiles/{prof}/prompts")
    assert r.json()[0]["times_used"] == 2


def test_use_prompt_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)

    r = client.post(f"/api/profiles/{prof}/prompts/prompt-99/use")
    assert r.status_code == 404
