"""Tests for Caption & Copy Generation — prompt parsing + API endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sceneforge.prompts import _parse_caption, generate_caption
from sceneforge.server import create_app

PROF = "test-brand"

GOOD_CAPTION = json.dumps({
    "caption": "Golden hour vibes with our favorite pieces today!",
    "hashtags": ["fashion", "ootd", "styling", "goldenhour"],
    "cta": "Shop the look: link in bio",
})


# ---------------------------------------------------------------- parsing


def test_parses_clean_json():
    result = _parse_caption(GOOD_CAPTION)
    assert result["caption"] == "Golden hour vibes with our favorite pieces today!"
    assert "fashion" in result["hashtags"]
    assert "ootd" in result["hashtags"]
    assert len(result["hashtags"]) == 4
    assert result["cta"] == "Shop the look: link in bio"


def test_parses_fenced_json():
    result = _parse_caption(f"```json\n{GOOD_CAPTION}\n```")
    assert result["caption"].startswith("Golden hour")


def test_parses_json_wrapped_in_prose():
    result = _parse_caption(f"Here's your caption:\n{GOOD_CAPTION}\nEnjoy!")
    assert len(result["hashtags"]) == 4


def test_strips_hash_prefix_from_hashtags():
    raw = json.dumps({
        "caption": "test",
        "hashtags": ["#fashion", "#ootd", "plain"],
        "cta": "",
    })
    result = _parse_caption(raw)
    assert result["hashtags"] == ["fashion", "ootd", "plain"]


def test_empty_caption_raises():
    raw = json.dumps({"caption": "", "hashtags": [], "cta": ""})
    with pytest.raises(ValueError, match="empty"):
        _parse_caption(raw)


def test_no_json_raises():
    with pytest.raises(ValueError):
        _parse_caption("I cannot help with that.")


def test_missing_hashtags_defaults_to_list():
    raw = json.dumps({"caption": "Hello world"})
    result = _parse_caption(raw)
    assert result["hashtags"] == []
    assert result["cta"] == ""


# -------------------------------------------------- generate_caption


def test_generate_caption_calls_llm():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = generate_caption(
            concept="outfit posts",
            scene_descriptions=["morning look", "evening look"],
            product_refs=[{"label": "White Dress", "url": "https://shop.com/dress"}],
            platform="instagram",
            tone="playful",
        )
        assert result["caption"].startswith("Golden hour")
        assert "fashion" in result["hashtags"]

        # Verify user prompt includes product refs
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "White Dress" in user_msg
        assert "https://shop.com/dress" in user_msg
        assert "outfit posts" in user_msg
        assert "morning look" in user_msg


def test_generate_caption_includes_platform_in_prompt():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        generate_caption(
            concept="test",
            scene_descriptions=[],
            product_refs=[],
            platform="tiktok",
            tone="minimal",
        )
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "tiktok" in user_msg
        assert "short" in user_msg.lower()


def test_generate_caption_retries_on_bad_json():
    bad_response = MagicMock()
    bad_response.choices = [MagicMock()]
    bad_response.choices[0].message.content = "not json"

    good_response = MagicMock()
    good_response.choices = [MagicMock()]
    good_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [bad_response, good_response]

        result = generate_caption("test", [], [])
        assert result["caption"].startswith("Golden hour")
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


def test_generate_caption_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-caption",
                        json={"platform": "instagram", "tone": "playful"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "caption" in data
        assert "hashtags" in data
        assert isinstance(data["hashtags"], list)


def test_generate_caption_stores_in_project(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        client.post(f"/api/profiles/{prof}/projects/{slug}/generate-caption",
                    json={"platform": "instagram", "tone": "playful"})

        # Check stored via GET captions
        r = client.get(f"/api/profiles/{prof}/projects/{slug}/captions")
        assert r.status_code == 200
        captions = r.json()
        assert "instagram" in captions
        assert captions["instagram"]["caption"].startswith("Golden hour")


def test_generate_caption_includes_product_refs(tmp_path):
    """Captions include product refs from scene refs with URLs."""
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    # Add a scene with a ref that has a URL
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "outfit shot"})
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    sid = proj["scenes"][0]["id"]

    TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/refs",
                data={"role": "garment", "label": "White Dress",
                      "url": "https://shop.com/dress"},
                files=[("file", ("dress.png", TINY_PNG, "image/png"))])

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        client.post(f"/api/profiles/{prof}/projects/{slug}/generate-caption",
                    json={"platform": "instagram"})

        # Verify LLM was called with product ref in prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "White Dress" in user_msg
        assert "https://shop.com/dress" in user_msg


def test_get_captions_empty(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/captions")
    assert r.status_code == 200
    assert r.json() == {}


def test_delete_caption(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = GOOD_CAPTION

    with patch("sceneforge.config.together_api_key", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        client.post(f"/api/profiles/{prof}/projects/{slug}/generate-caption",
                    json={"platform": "instagram"})

    r = client.delete(f"/api/profiles/{prof}/projects/{slug}/captions/instagram")
    assert r.status_code == 200
    assert r.json() == {"deleted": "instagram"}

    # Verify it's gone
    r = client.get(f"/api/profiles/{prof}/projects/{slug}/captions")
    assert r.json() == {}


def test_delete_caption_not_found(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.delete(f"/api/profiles/{prof}/projects/{slug}/captions/tiktok")
    assert r.status_code == 404


def test_generate_caption_no_concept(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": "Empty", "concept": "", "anchor": "soft",
        "image_model": "fake-image", "video_model": "fake-video",
    })
    slug = r.json()["slug"]

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/generate-caption",
                    json={"platform": "instagram"})
    assert r.status_code == 400
