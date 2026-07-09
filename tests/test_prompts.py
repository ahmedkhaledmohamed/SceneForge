import pytest

from sceneforge.project import Project, Scene, Style
from sceneforge.prompts import build_anchor, compose_prompt


def make_project(anchor="warm golden hour, 35mm film", suffix="no text"):
    return Project(name="t", style=Style(anchor=anchor, suffix=suffix))


def test_compose_prepends_anchor_and_appends_suffix():
    scene = Scene(id="scene-01", description="a hand pours coffee")
    result = compose_prompt(make_project(), scene)
    assert result == "warm golden hour, 35mm film. a hand pours coffee. no text."


def test_override_replaces_anchor_keeps_suffix():
    scene = Scene(id="scene-01", description="a hand pours coffee",
                  style_override="cool blue night")
    result = compose_prompt(make_project(), scene)
    assert result == "cool blue night. a hand pours coffee. no text."


def test_missing_parts_are_skipped():
    scene = Scene(id="scene-01", description="a hand pours coffee")
    assert compose_prompt(make_project(anchor="", suffix=""), scene) == "a hand pours coffee."


def test_trailing_periods_not_doubled():
    scene = Scene(id="scene-01", description="a hand pours coffee.")
    result = compose_prompt(make_project(anchor="soft light.", suffix=""), scene)
    assert result == "soft light. a hand pours coffee."


def test_all_empty_raises():
    scene = Scene(id="scene-01", description="  ")
    with pytest.raises(ValueError):
        compose_prompt(make_project(anchor="", suffix=""), scene)


def test_build_anchor_joins_nonempty_facets():
    assert build_anchor("cozy", "", "golden hour") == "golden hour, cozy"
    assert build_anchor("", "", "") == ""
