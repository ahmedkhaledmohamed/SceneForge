"""Self-hosted generation on RunPod serverless GPUs.

Flow: submit job (input image as raw base64) → poll /status → decode
the base64 media from the output → compute the actual dollar cost from
executionTime × the GPU's per-second price (both in the model registry
entry). The worker that executes these jobs lives in runpod-worker/.

Cost note: executionTime covers the handler run, which includes lazy
model loading on a cold worker — so cold-start clips honestly cost
more. Worker boot before the handler starts is not billed to the job.
"""

import base64
import time
from pathlib import Path

from .. import config
from ..util import ffprobe_duration, image_b64
from .base import ClipResult, ImageBackend, ImageResult, VideoBackend
from .runpod_client import RunPodClient

TERMINAL_FAILED = {"FAILED", "CANCELLED", "TIMED_OUT"}


def _await_job(client: RunPodClient, job_id: str, *, poll_interval: float,
               timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        data = client.status(job_id)
        status = data.get("status")
        if status == "COMPLETED":
            return data
        if status in TERMINAL_FAILED:
            detail = data.get("error") or data.get("output") or status
            raise RuntimeError(f"RunPod job {job_id} {status}: {detail}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"RunPod job {job_id} still {status} after {timeout_s}s")
        time.sleep(poll_interval)


def _cost_meta(data: dict, model: dict) -> dict:
    execution_ms = data.get("executionTime") or 0
    meta = {
        "backend": "runpod",
        "execution_ms": execution_ms,
        "delay_ms": data.get("delayTime"),
    }
    price_per_s = model.get("gpu_price_per_s")
    if price_per_s and execution_ms:
        meta["cost_usd"] = round(execution_ms / 1000 * price_per_s, 4)
    return meta


class _RunPodMixin:
    def __init__(self, model: dict, client: RunPodClient | None = None):
        super().__init__(model)
        self._client = client

    @property
    def client(self) -> RunPodClient:
        # Built lazily so constructing the backend (e.g. in the factory)
        # doesn't require RunPod env vars — only actually generating does.
        if self._client is None:
            self._client = RunPodClient(
                config.runpod_endpoint_id(), config.runpod_api_key()
            )
        return self._client

    def _poll_interval(self) -> float:
        return self.model.get("poll_interval_s", config.VIDEO_POLL_INTERVAL_S)


class RunPodImageBackend(_RunPodMixin, ImageBackend):
    def generate_image(self, prompt, out_path: Path, *, width, height,
                       reference_image=None, seed=None):
        payload = {"task": "image", "prompt": prompt, "width": width, "height": height}
        if seed is not None:
            payload["seed"] = seed
        job_id = self.client.run(payload)
        data = _await_job(
            self.client, job_id,
            poll_interval=self._poll_interval(),
            timeout_s=self.model.get("timeout_s", 600),
        )
        output = data.get("output") or {}
        if "image_b64" not in output:
            raise RuntimeError(f"RunPod job {job_id} returned no image: {output}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(output["image_b64"]))
        return ImageResult(
            path=out_path, prompt=prompt, model=self.model["key"],
            meta={**_cost_meta(data, self.model), "gen_time_s": output.get("gen_time_s")},
        )


class RunPodVideoBackend(_RunPodMixin, VideoBackend):
    def generate_clip(self, prompt, out_path: Path, *, image, width, height,
                      timeout_s=600):
        payload = {"task": "video", "prompt": prompt, "num_frames": 81, "fps": 16}
        if image is not None:
            payload["image_b64"] = image_b64(image)
        job_id = self.client.run(payload)
        data = _await_job(
            self.client, job_id,
            poll_interval=self._poll_interval(),
            timeout_s=self.model.get("timeout_s", timeout_s),
        )
        output = data.get("output") or {}
        if "video_b64" not in output:
            raise RuntimeError(f"RunPod job {job_id} returned no video: {output}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(output["video_b64"]))
        return ClipResult(
            path=out_path, prompt=prompt, model=self.model["key"],
            job_id=job_id, duration_s=ffprobe_duration(out_path),
            meta={
                **_cost_meta(data, self.model),
                "gen_time_s": output.get("gen_time_s"),
                "worker_resolution": f"{output.get('width')}x{output.get('height')}",
            },
        )
