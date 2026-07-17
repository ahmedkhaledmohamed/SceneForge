"""Tests for the prompt enhancement layer."""

from unittest.mock import MagicMock, patch

import pytest

from sceneforge.project import Project, Scene, SceneRef, Settings, Style
from sceneforge.prompts import (
    ENHANCE_SYSTEM,
    compose_prompt,
    enhance_prompt,
)


def make_project(**kw):
    defaults = dict(
        name="test",
        style=Style(anchor="warm studio light, muted pastels"),
        settings=Settings(auto_enhance=False),
    )
    defaults.update(kw)
    return Project(**defaults)


ENHANCED_TEXT = (
    "A handcrafted cloth doll wearing a sage green linen dress sits at "
    "a round marble café table, warm studio light filtering through "
    "sheer curtains, soft focus background with potted plants, muted "
    "earth-tone palette, 3/4 angle shot from slightly above"
)


class FakeChoice:
    def __init__(self, text):
        self.message = MagicMock(content=text)


class FakeResponse:
    def __init__(self, text):
        self.choices = [FakeChoice(text)]


@patch("sceneforge.config.together_api_key", return_value="test-key")
def test_enhance_prompt_calls_llm(mock_key):
    project = make_project()
    scene = Scene(
        id="scene-01",
        description="doll sitting at café table",
        refs=[
            SceneRef(file="dress.jpg", role="garment", label="Sage linen dress"),
        ],
    )
    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = FakeResponse(ENHANCED_TEXT)

        result = enhance_prompt(project, scene)

    assert result == ENHANCED_TEXT
    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["content"] == ENHANCE_SYSTEM
    assert "doll sitting at café table" in messages[1]["content"]
    assert "Sage linen dress" in messages[1]["content"]
    assert "warm studio light" in messages[1]["content"]


@patch("sceneforge.config.together_api_key", return_value="test-key")
def test_enhance_strips_quotes(mock_key):
    project = make_project()
    scene = Scene(id="s1", description="test")
    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = FakeResponse(
            '"enhanced prompt with quotes"'
        )
        result = enhance_prompt(project, scene)
    assert result == "enhanced prompt with quotes"


def test_compose_with_enhanced_description():
    project = make_project()
    scene = Scene(id="s1", description="original short prompt")
    result = compose_prompt(
        project, scene,
        enhanced_description="detailed enhanced prompt with rich detail",
    )
    assert "detailed enhanced prompt" in result
    assert "original short prompt" not in result


def test_compose_without_enhanced_uses_original():
    project = make_project()
    scene = Scene(id="s1", description="original short prompt")
    result = compose_prompt(project, scene)
    assert "original short prompt" in result


def test_enhanced_prompt_field_on_artifact():
    from sceneforge.project import ImageArtifact
    art = ImageArtifact(
        file="test.png", prompt="full prompt", model="test",
        enhanced_prompt="the enhanced version",
    )
    assert art.enhanced_prompt == "the enhanced version"


def test_auto_enhance_setting():
    settings = Settings(auto_enhance=True)
    assert settings.auto_enhance is True
    settings2 = Settings()
    assert settings2.auto_enhance is False
