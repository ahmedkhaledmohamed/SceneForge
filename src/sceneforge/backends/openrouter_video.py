"""OpenRouter video backend — Seedance 1.5 Pro, Seedance 2.0, and other models
at significantly lower prices than Together AI."""

import json
import time
import urllib.request

from ..config import VIDEO_POLL_INTERVAL_S
import subprocess
from pathlib import Path

from ..util import image_data_uri
from .base import ClipResult, VideoBackend


def _download_with_auth(url: str, out_path: Path, api_key: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["curl", "-L", "--fail", "--silent", "--show-error",
         "-H", f"Authorization: Bearer {api_key}",
         "-H", "User-Agent: SceneForge/1.0",
         "-o", str(out_path), url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Download failed for {url}: {result.stderr.strip()}")


class OpenRouterVideoBackend(VideoBackend):
    def generate_clip(self, prompt, out_path, *, image=None, width=720, height=1280,
                      seconds=None, timeout_s=600):
        from ..config import openrouter_api_key

        api_key = openrouter_api_key()
        body: dict = {
            "model": self.model["id"],
            "prompt": prompt,
            "resolution": "720p",
            "aspect_ratio": "9:16" if height > width else "16:9",
        }
        if seconds:
            body["duration"] = seconds
        if image is not None:
            body["frame_images"] = [{
                "type": "image_url",
                "image_url": {"url": image_data_uri(image)},
                "frame_type": "first_frame",
            }]

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/videos",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SceneForge/1.0",
            },
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        job_id = resp.get("id") or resp.get("job_id")
        if not job_id:
            raise RuntimeError(f"No job ID in response: {resp}")

        deadline = time.monotonic() + timeout_s
        while True:
            poll_req = urllib.request.Request(
                f"https://openrouter.ai/api/v1/videos/{job_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "SceneForge/1.0",
                },
            )
            status_resp = json.loads(urllib.request.urlopen(poll_req, timeout=30).read())
            status = status_resp.get("status", "")
            if status in ("completed", "succeeded", "success"):
                break
            if status in ("failed", "error", "cancelled"):
                detail = status_resp.get("error") or status
                raise RuntimeError(f"Video job {job_id} failed: {detail}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"Video job {job_id} still '{status}' after {timeout_s}s")
            time.sleep(max(VIDEO_POLL_INTERVAL_S, 15))

        urls = status_resp.get("unsigned_urls", [])
        if urls:
            video_url = urls[0]
        else:
            video_url = f"https://openrouter.ai/api/v1/videos/{job_id}/content?index=0"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _download_with_auth(video_url, out_path, api_key)

        from ..util import ffprobe_duration
        return ClipResult(
            path=out_path,
            prompt=prompt,
            model=self.model.get("key", self.model["id"]),
            job_id=job_id,
            duration_s=ffprobe_duration(out_path),
        )
