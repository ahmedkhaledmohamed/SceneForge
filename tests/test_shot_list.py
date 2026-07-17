"""Tests for AI Shot List Generator — prompt parsing + API endpoints."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sceneforge.prompts import _parse_shot_list, generate_shot_list
from sceneforge.server import create_app

PROF = "test-brand"

GOOD_RESPONSE = json.dumps({
    "shots": [
        {
            "description": "Character standing in morning light",
            "composition": "medium shot, eye level",
            "shot_type": "hero",
            "prompt": "a character standing in soft golden morning light, medium shot",
        },
        {
            "description": "Close-up of accessory details",
            "composition": "tight close-up, shallow DOF",
            "shot_type": "detail",
            "prompt": "close-up macro shot of jewelry and bag details",
        },
        {
            "description": "Wide establishing shot of the street",
            "composition": "wide angle, low perspective",
            "shot_type": "wide",
            "prompt": "wide establishing shot of a sunlit city street",
        },
    ]
})

# ---------------------------------------------------------------- parsing


def test_parses_clean_json():
    result = _parse_shot_list(GOOD_RESPONSE)
    assert len(result) == 3
    assert result[0]["description"] == "Character standing in morning light"
    assert result[0]["shot_type"] == "hero"
    assert result[1]["shot_type"] == "detail"
    assert result[2]["shot_type"] == "wide"


def test_parses_fenced_json():
    result = _parse_shot_list(f"```json\n{GOOD_RESPONSE}\n```")
    assert len(result) == 3


def test_parses_json_wrapped_in_prose():
    result = _parse_shot_list(f"Here is your shot list:\n{GOOD_RESPONSE}\nHope that helps!")
    assert len(result) == 3


def test_invalid_shot_type_falls_back_to_broll():
    raw = json.dumps({
        "shots": [{
            "description": "Some scene",
            "composition": "wide",
            "shot_type": "unknown_type",
            "prompt": "some prompt",
        }]
    })
    result = _parse_shot_list(raw)
    assert result[0]["shot_type"] == "broll"


def test_empty_shots_raises():
    with pytest.raises(ValueError):
        _parse_shot_list('{"shots": []}')


def test_missing_description_raises():
    raw = json.dumps({"shots": [{"description": "", "shot_type": "hero"}]})
    with pytest.raises(ValueError):
        _parse_shot_list(raw)


def test_no_json_raises():
    with pytest.raises(ValueError):
        _parse_shot_list("I cannot help with that.")


def test_missing_fields_default_to_empty():
    raw = json.dumps({
        "shots": [{
            "description": "A simple scene",
        }]
    })
    result = _parse_shot_list(raw)
    assert result[0]["composition"] == ""
    assert result[0]["shot_type"] == "broll"
    assert result[0]["prompt"] == ""


# ------------------------------------------------------ generate_shot_list


def test_generate_shot_list_calls_llm():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_RESPONSE

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = generate_shot_list("outfit reel", style_anchor="warm tones")
        assert len(result) == 3
        assert result[0]["shot_type"] == "hero"

        # Verify LLM was called with correct params
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert any("outfit reel" in m["content"] for m in messages)
        assert any("warm tones" in m["content"] for m in messages)


def test_generate_shot_list_retries_on_bad_json():
    bad_response = MagicMock()
    bad_response.choices = [MagicMock()]
    bad_response.choices[0].message.content = "not json"

    good_response = MagicMock()
    good_response.choices = [MagicMock()]
    good_response.choices[0].message.content = GOOD_RESPONSE

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [bad_response, good_response]

        result = generate_shot_list("outfit reel")
        assert len(result) == 3
        assert mock_client.chat.completions.create.call_count == 2


# ----------------------------------------------------------- API endpoints


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof=PROF, name="Looks"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts for IG reels",
        "anchor": "soft light", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def test_generate_shot_list_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_RESPONSE

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-shot-list",
                        json={"num_scenes": 3})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "shots" in data
        assert len(data["shots"]) == 3
        assert data["shots"][0]["shot_type"] == "hero"


def test_generate_shot_list_no_concept(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    # Project with no concept
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": "Empty", "concept": "", "anchor": "soft",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    slug = r.json()["slug"]

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-shot-list",
                    json={})
    assert r.status_code == 400


def test_apply_shot_list_creates_scenes(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    shots = [
        {"description": "Hero shot in morning light", "composition": "medium",
         "shot_type": "hero", "prompt": "hero prompt"},
        {"description": "Detail of accessories", "composition": "close-up",
         "shot_type": "detail", "prompt": "detail prompt"},
    ]
    r = client.post(f"/api/profiles/{prof}/projects/{slug}/apply-shot-list",
                    json={"shots": shots})
    assert r.status_code == 201, r.text
    created = r.json()
    assert len(created) == 2
    assert created[0]["description"] == "Hero shot in morning light"
    assert created[1]["description"] == "Detail of accessories"

    # Verify scenes exist on the project
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    assert len(proj["scenes"]) == 2


def test_apply_shot_list_with_character(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Create a profile character
    TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    char = client.post(f"/api/profiles/{prof}/characters",
                       data={"name": "Mila", "description": "doll"},
                       files=[("files", ("doll.png", TINY_PNG, "image/png"))]).json()

    shots = [
        {"description": "Character poses", "composition": "medium",
         "shot_type": "hero", "prompt": "..."},
    ]
    r = client.post(f"/api/profiles/{prof}/projects/{slug}/apply-shot-list",
                    json={"shots": shots, "character_id": char["id"]})
    assert r.status_code == 201
    created = r.json()
    assert created[0]["character_id"] == char["id"]


def test_apply_shot_list_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/apply-shot-list",
                    json={"shots": []})
    assert r.status_code == 400
