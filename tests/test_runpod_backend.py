"""RunPod backend tests — scripted HTTP responses, no network, no cost."""

import base64
import subprocess

import pytest

from sceneforge.backends import get_video_backend
from sceneforge.backends.fake import FakeVideoBackend
from sceneforge.backends.fallback import FallbackVideoBackend
from sceneforge.backends.runpod_backend import (
    RunPodImageBackend,
    RunPodVideoBackend,
    _cost_meta,
)
from sceneforge.backends.runpod_client import RunPodClient, RunPodUnavailableError

IMAGE_MODEL = {
    "key": "runpod-flux", "kind": "image", "backend": "runpod",
    "id": "black-forest-labs/FLUX.1-schnell", "price": 0.005,
    "gpu_price_per_s": 0.000306, "timeout_s": 5, "poll_interval_s": 0,
}
VIDEO_MODEL = {
    "key": "runpod-wan-i2v", "kind": "video", "backend": "runpod",
    "id": "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers", "price": 0.12,
    "gpu_price_per_s": 0.000306, "supports_i2v": True,
    "timeout_s": 5, "poll_interval_s": 0,
}
FAKE_VIDEO_MODEL = {"key": "fake-video", "kind": "video", "backend": "fake",
                    "id": "lavfi/testsrc", "price": 0.0, "supports_i2v": False}


class ScriptedHTTP:
    """Fake http callable: returns queued responses in order, records calls.
    An Exception instance in the queue is raised instead of returned."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, api_key, payload=None, timeout=60):
        self.calls.append((url, payload))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(responses):
    http = ScriptedHTTP(responses)
    return RunPodClient("test-endpoint", "test-key", http=http), http


def tiny_mp4_b64(tmp_path):
    path = tmp_path / "tiny.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=duration=1:size=64x64:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return base64.b64encode(path.read_bytes()).decode()


def test_video_success_end_to_end(tmp_path):
    video_b64 = tiny_mp4_b64(tmp_path)
    client, http = make_client([
        {"id": "job-1", "status": "IN_QUEUE"},
        {"status": "IN_QUEUE"},
        {"status": "IN_PROGRESS"},
        {"status": "COMPLETED", "executionTime": 300000, "delayTime": 1200,
         "output": {"video_b64": video_b64, "width": 480, "height": 832,
                    "gen_time_s": 290.0}},
    ])
    backend = RunPodVideoBackend(VIDEO_MODEL, client=client)

    src_image = tmp_path / "still.png"
    src_image.write_bytes(b"png-bytes")
    out = tmp_path / "clip.mp4"
    result = backend.generate_clip("a mug steams", out, image=src_image,
                                   width=720, height=1280)

    assert out.is_file()
    assert result.duration_s == pytest.approx(1.0, abs=0.2)
    assert result.job_id == "job-1"
    # 300s of 4090 flex time at $0.000306/s
    assert result.meta["cost_usd"] == pytest.approx(0.0918)
    # the input image travelled as raw base64 in the run payload
    run_payload = http.calls[0][1]
    assert run_payload["input"]["image_b64"] == base64.b64encode(b"png-bytes").decode()
    assert run_payload["input"]["task"] == "video"


def test_image_success(tmp_path):
    png_b64 = base64.b64encode(b"png-data").decode()
    client, _ = make_client([
        {"id": "job-2", "status": "IN_QUEUE"},
        {"status": "COMPLETED", "executionTime": 12000,
         "output": {"image_b64": png_b64, "gen_time_s": 10.5}},
    ])
    backend = RunPodImageBackend(IMAGE_MODEL, client=client)
    out = tmp_path / "img" / "opt-1.png"
    result = backend.generate_image("a mug", out, width=720, height=1280)
    assert out.read_bytes() == b"png-data"
    assert result.meta["cost_usd"] == pytest.approx(0.0037, abs=0.0001)


def test_failed_job_raises(tmp_path):
    client, _ = make_client([
        {"id": "job-3", "status": "IN_QUEUE"},
        {"status": "FAILED", "error": "CUDA out of memory"},
    ])
    backend = RunPodVideoBackend(VIDEO_MODEL, client=client)
    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        backend.generate_clip("p", tmp_path / "c.mp4", image=None,
                              width=720, height=1280)


def test_poll_timeout_raises(tmp_path):
    model = {**VIDEO_MODEL, "timeout_s": 0}
    client, _ = make_client([
        {"id": "job-4", "status": "IN_QUEUE"},
        {"status": "IN_QUEUE"},
        {"status": "IN_QUEUE"},
    ])
    backend = RunPodVideoBackend(model, client=client)
    with pytest.raises(TimeoutError):
        backend.generate_clip("p", tmp_path / "c.mp4", image=None,
                              width=720, height=1280)


def test_unavailable_endpoint_raises_runpod_error(tmp_path):
    client, _ = make_client([RunPodUnavailableError("RunPod API 404")])
    backend = RunPodVideoBackend(VIDEO_MODEL, client=client)
    with pytest.raises(RunPodUnavailableError):
        backend.generate_clip("p", tmp_path / "c.mp4", image=None,
                              width=720, height=1280)


def test_fallback_delegates_and_tags(tmp_path):
    client, _ = make_client([RunPodUnavailableError("RunPod API 404")])
    primary = RunPodVideoBackend(VIDEO_MODEL, client=client)
    fallback = FakeVideoBackend(FAKE_VIDEO_MODEL)
    logs = []
    wrapped = FallbackVideoBackend(primary, fallback, log=logs.append)

    out = tmp_path / "clip.mp4"
    result = wrapped.generate_clip("p", out, image=None, width=64, height=64)

    assert out.is_file()
    assert result.model == "fake-video"
    assert result.meta["fallback_from"] == "runpod-wan-i2v"
    assert any("falling back to fake-video" in line for line in logs)


def test_cost_meta_without_price():
    meta = _cost_meta({"executionTime": 5000}, {"key": "x"})
    assert "cost_usd" not in meta
    assert meta["execution_ms"] == 5000


def test_factory_wires_fallback():
    backend = get_video_backend("runpod-wan-i2v")
    assert isinstance(backend, FallbackVideoBackend)
    assert isinstance(backend.primary, RunPodVideoBackend)
    assert backend.supports_i2v is True
    # constructing the backend must not require RunPod env vars
    assert backend.fallback.model["key"] == "seedance-1.5-pro"