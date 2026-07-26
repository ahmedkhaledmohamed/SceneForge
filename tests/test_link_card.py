"""Tests for Shop Link Cards — link card generation + API endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from sceneforge.link_card import (
    collect_product_refs,
    generate_link_card,
    generate_links_overlay,
    generate_links_text,
)
from sceneforge.project import Project, Scene, SceneRef
from sceneforge.server import create_app

PROF = "test-brand"

TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --------------------------------------------------------- unit tests


def test_collect_product_refs_deduplicates():
    proj = Project(name="test")
    ref1 = SceneRef(file="a.png", label="Dress", url="https://shop.com/dress")
    ref2 = SceneRef(file="b.png", label="Shoes", url="https://shop.com/shoes")
    ref3 = SceneRef(file="c.png", label="Dress dupe", url="https://shop.com/dress")
    proj.scenes = [
        Scene(id="scene-01", description="look 1", refs=[ref1, ref2]),
        Scene(id="scene-02", description="look 2", refs=[ref3]),
    ]
    refs = collect_product_refs(proj)
    assert len(refs) == 2
    urls = [r["url"] for r in refs]
    assert "https://shop.com/dress" in urls
    assert "https://shop.com/shoes" in urls


def test_collect_refs_skips_no_url():
    proj = Project(name="test")
    proj.scenes = [
        Scene(id="scene-01", description="look", refs=[
            SceneRef(file="a.png", label="Garment"),
        ]),
    ]
    refs = collect_product_refs(proj)
    assert len(refs) == 0


def test_generate_link_card_creates_png(tmp_path):
    proj = Project(name="test", root=tmp_path)
    scene = proj.add_scene("look 1")
    scene.refs = [
        SceneRef(file="dress.png", label="White Dress",
                 url="https://shop.com/dress"),
    ]

    out = generate_link_card(proj)
    assert out.exists()
    assert out.suffix == ".png"
    assert out.stat().st_size > 100


def test_generate_link_card_no_refs_raises(tmp_path):
    proj = Project(name="test", root=tmp_path)
    proj.add_scene("no refs")
    with pytest.raises(ValueError, match="No product refs"):
        generate_link_card(proj)


def test_generate_links_text():
    proj = Project(name="test")
    proj.scenes = [
        Scene(id="s1", description="look", refs=[
            SceneRef(file="a.png", label="Dress",
                     url="https://shop.com/dress"),
            SceneRef(file="b.png", label="Shoes",
                     url="https://shop.com/shoes"),
        ]),
    ]
    text = generate_links_text(proj)
    assert "1. Dress: https://shop.com/dress" in text
    assert "2. Shoes: https://shop.com/shoes" in text


def test_generate_links_text_no_refs_raises():
    proj = Project(name="test")
    proj.scenes = [Scene(id="s1", description="look", refs=[])]
    with pytest.raises(ValueError, match="No product refs"):
        generate_links_text(proj)


def test_generate_links_overlay_creates_srt(tmp_path):
    proj = Project(name="test", root=tmp_path)
    scene = proj.add_scene("look 1")
    scene.refs = [
        SceneRef(file="a.png", label="Dress",
                 url="https://shop.com/dress"),
    ]
    out = generate_links_overlay(proj)
    assert out.exists()
    assert out.suffix == ".srt"
    content = out.read_text()
    assert "Dress" in content
    assert "-->" in content


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof=PROF, name="Looks"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts",
        "anchor": "soft light", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def add_scene_with_ref(client, prof, slug):
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "outfit shot"})
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    sid = proj["scenes"][0]["id"]
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/refs",
                data={"role": "garment", "label": "White Dress",
                      "url": "https://shop.com/dress"},
                files=[("file", ("dress.png", TINY_PNG, "image/png"))])
    return sid


def test_link_card_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    add_scene_with_ref(client, prof, slug)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/link-card")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 100


def test_link_card_no_refs(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "no refs"})

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/link-card")
    assert r.status_code == 400


def test_link_card_preview_after_generate(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    add_scene_with_ref(client, prof, slug)

    # Preview before generation should 404
    r = client.get(f"/api/profiles/{prof}/projects/{slug}/link-card/preview")
    assert r.status_code == 404

    # Generate the card
    client.post(f"/api/profiles/{prof}/projects/{slug}/link-card")

    # Preview should now work
    r = client.get(f"/api/profiles/{prof}/projects/{slug}/link-card/preview")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_links_text_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    add_scene_with_ref(client, prof, slug)

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/links-text")
    assert r.status_code == 200
    assert "White Dress" in r.text
    assert "https://shop.com/dress" in r.text


def test_links_text_no_refs(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "no refs"})

    r = client.get(f"/api/profiles/{prof}/projects/{slug}/links-text")
    assert r.status_code == 400


def test_links_overlay_endpoint(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    add_scene_with_ref(client, prof, slug)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/links-overlay")
    assert r.status_code == 200
    assert "White Dress" in r.text
    assert "-->" in r.text


def test_links_overlay_no_refs(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/links-overlay")
    assert r.status_code == 400
