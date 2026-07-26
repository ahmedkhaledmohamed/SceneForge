"""Tests for Audio Layer — audio fields, API endpoints, and merge utility."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sceneforge.audio import merge_audio_video, strip_audio
from sceneforge.project import Clip, Project
from sceneforge.server import create_app

PROF = "test-brand"


# --------------------------------------------------------- unit tests


def test_clip_audio_fields_default():
    clip = Clip(id="clip-01")
    assert clip.audio_file == ""
    assert clip.audio_type == ""


def test_clip_audio_fields_persist(tmp_path):
    proj = Project(name="test", root=tmp_path)
    clip = proj.add_clip(source_images=[], prompt="test", model="fake")
    clip.audio_file = "clips/audio/bgm.mp3"
    clip.audio_type = "music"
    proj.save()

    loaded = Project.load(tmp_path)
    assert loaded.clips[0].audio_file == "clips/audio/bgm.mp3"
    assert loaded.clips[0].audio_type == "music"


def test_merge_audio_video_calls_ffmpeg(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.mp3"
    output = tmp_path / "merged.mp4"
    video.write_bytes(b"fake-video")
    audio.write_bytes(b"fake-audio")

    with patch("sceneforge.audio.run_ffmpeg") as mock_ffmpeg:
        result = merge_audio_video(video, audio, output)
        assert result == output
        mock_ffmpeg.assert_called_once()
        args = mock_ffmpeg.call_args[0][0]
        assert str(video) in args
        assert str(audio) in args
        assert str(output) in args
        assert "-shortest" in args


def test_strip_audio_calls_ffmpeg(tmp_path):
    video = tmp_path / "video.mp4"
    output = tmp_path / "silent.mp4"
    video.write_bytes(b"fake-video")

    with patch("sceneforge.audio.run_ffmpeg") as mock_ffmpeg:
        result = strip_audio(video, output)
        assert result == output
        mock_ffmpeg.assert_called_once()
        args = mock_ffmpeg.call_args[0][0]
        assert "-an" in args


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def create_profile(client, name="Test Brand"):
    r = client.post("/api/profiles", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["slug"]


def create_project(client, prof, name="Looks"):
    r = client.post(f"/api/profiles/{prof}/projects", json={
        "name": name, "concept": "outfit posts",
        "anchor": "soft light", "image_model": "fake-image",
        "video_model": "fake-video",
    })
    assert r.status_code == 201, r.text
    return r.json()["slug"]


TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def create_clip(client, prof, slug):
    # Need a scene with an image for clip source
    client.post(f"/api/profiles/{prof}/projects/{slug}/scenes",
                json={"description": "test scene"})
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    sid = proj["scenes"][0]["id"]
    client.post(
        f"/api/profiles/{prof}/projects/{slug}/scenes/{sid}/import-image",
        files=[("file", ("test.png", TINY_PNG, "image/png"))],
    )
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    img_file = proj["scenes"][0]["images"][0]["file"]
    r = client.post(f"/api/profiles/{prof}/projects/{slug}/clips",
                    json={"source_images": [img_file], "prompt": "test", "model": "fake-video"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_list_audio_types(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/audio-types")
    assert r.status_code == 200
    data = r.json()
    assert "ambient" in data
    assert "music" in data
    assert "voiceover" in data


def test_add_audio_to_clip(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    cid = create_clip(client, prof, slug)

    TINY_MP4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
    r = client.post(
        f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/add-audio",
        data={"audio_type": "ambient"},
        files=[("file", ("bgm.mp4", TINY_MP4, "video/mp4"))],
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["audio_type"] == "ambient"
    assert "audio" in data["audio_file"]


def test_add_audio_invalid_type(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    cid = create_clip(client, prof, slug)

    TINY_MP4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
    r = client.post(
        f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/add-audio",
        data={"audio_type": "invalid"},
        files=[("file", ("bgm.mp4", TINY_MP4, "video/mp4"))],
    )
    assert r.status_code == 400


def test_remove_audio_from_clip(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    cid = create_clip(client, prof, slug)

    TINY_MP4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
    client.post(
        f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/add-audio",
        data={"audio_type": "music"},
        files=[("file", ("bgm.mp4", TINY_MP4, "video/mp4"))],
    )

    r = client.delete(f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/audio")
    assert r.status_code == 200

    # Verify audio removed
    proj = client.get(f"/api/profiles/{prof}/projects/{slug}").json()
    clip = next(c for c in proj["clips"] if c["id"] == cid)
    assert clip["audio_file"] == ""
    assert clip["audio_type"] == ""


def test_merge_audio_no_audio(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    cid = create_clip(client, prof, slug)

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/merge-audio")
    assert r.status_code == 400
    assert "no audio" in r.json()["error"]["message"].lower()


def test_merge_audio_no_video(tmp_path):
    client = make_client(tmp_path)
    prof = create_profile(client)
    slug = create_project(client, prof)
    cid = create_clip(client, prof, slug)

    TINY_MP4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
    client.post(
        f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/add-audio",
        data={"audio_type": "ambient"},
        files=[("file", ("bgm.mp4", TINY_MP4, "video/mp4"))],
    )

    r = client.post(f"/api/profiles/{prof}/projects/{slug}/clips/{cid}/merge-audio")
    assert r.status_code == 400
