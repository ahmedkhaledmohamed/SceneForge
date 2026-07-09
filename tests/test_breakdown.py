import pytest

from sceneforge.breakdown import _parse_scenes

GOOD = '{"scenes": [{"description": "a cup steams"}, {"description": "rain on glass"}]}'


def test_parses_clean_json():
    assert _parse_scenes(GOOD) == ["a cup steams", "rain on glass"]


def test_parses_fenced_json():
    assert _parse_scenes(f"```json\n{GOOD}\n```") == ["a cup steams", "rain on glass"]


def test_parses_json_wrapped_in_prose():
    assert _parse_scenes(f"Here you go:\n{GOOD}\nEnjoy!") == [
        "a cup steams", "rain on glass"
    ]


def test_empty_scenes_raises():
    with pytest.raises(ValueError):
        _parse_scenes('{"scenes": []}')


def test_missing_description_raises():
    with pytest.raises(ValueError):
        _parse_scenes('{"scenes": [{"description": ""}]}')


def test_no_json_raises():
    with pytest.raises(ValueError):
        _parse_scenes("I cannot help with that.")
