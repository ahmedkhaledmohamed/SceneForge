"""Tests for smart model routing based on shot type and budget."""

from sceneforge.config import MODELS, SHOT_TYPES, recommend_model


def test_recommend_hero_gets_premium():
    model = recommend_model(shot_type="hero")
    assert model == "seedance-2.0-or"


def test_recommend_broll_gets_cheap():
    model = recommend_model(shot_type="broll")
    assert model == "kling-2.1"


def test_recommend_transition_gets_cheap():
    model = recommend_model(shot_type="transition")
    assert model == "kling-2.1"


def test_recommend_detail_gets_mid():
    model = recommend_model(shot_type="detail")
    assert model == "seedance-1.5-pro"


def test_recommend_empty_shot_type_uses_fallback():
    model = recommend_model(shot_type="", fallback="seedance-1.5-pro")
    assert model == "seedance-1.5-pro"


def test_recommend_unknown_shot_type_uses_fallback():
    model = recommend_model(shot_type="nonexistent", fallback="kling-2.1")
    assert model == "kling-2.1"


def test_budget_constraint_downgrades():
    model = recommend_model(shot_type="hero", budget_remaining=0.50)
    hero_price = MODELS.get("seedance-2.0-or", {}).get("price", 999)
    actual_price = MODELS.get(model, {}).get("price", 0)
    assert actual_price <= hero_price


def test_no_budget_constraint_keeps_recommendation():
    model = recommend_model(shot_type="hero", budget_remaining=None)
    assert model == "seedance-2.0-or"


def test_high_budget_keeps_recommendation():
    model = recommend_model(shot_type="hero", budget_remaining=100.0)
    assert model == "seedance-2.0-or"


def test_all_shot_types_have_valid_recommended_model():
    for key, st in SHOT_TYPES.items():
        rec = st["recommended_video"]
        assert rec in MODELS, f"Shot type '{key}' recommends unknown model '{rec}'"
        assert MODELS[rec]["kind"] == "video", f"Recommended model '{rec}' is not a video model"
