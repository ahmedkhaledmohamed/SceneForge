"""Together AI video generation via the together SDK.

Creates a job, polls until it completes, downloads the result with curl
(Together's CDN 403s urllib's default User-Agent).

I2V: the selected image is passed inline as a base64 data URI in
frame_images with frame='first'.
"""

import time

from ..config import VIDEO_POLL_INTERVAL_S, together_api_key
from ..util import download, ffprobe_duration, image_data_uri
from .base import ClipResult, VideoBackend


class TogetherVideoBackend(VideoBackend):
    def generate_clip(self, prompt, out_path, *, image, width, height,
                      timeout_s=600):
        from together import Together

        client = Together(api_key=together_api_key())

        kwargs = {
            "model": self.model["id"],
            "prompt": prompt,
            "width": width,
            "height": height,
        }
        if image is not None:
            kwargs["frame_images"] = [
                {"input_image": image_data_uri(image), "frame": "first"}
            ]

        job = client.videos.create(**kwargs)
        job_id = job.id

        deadline = time.monotonic() + timeout_s
        while True:
            job = client.videos.retrieve(job_id)
            status = getattr(job, "status", None)
            if status in ("completed", "succeeded", "success"):
                break
            if status in ("failed", "error", "cancelled"):
                detail = getattr(job, "error", None) or status
                raise RuntimeError(f"Video job {job_id} failed: {detail}")
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Video job {job_id} still '{status}' after {timeout_s}s"
                )
            time.sleep(VIDEO_POLL_INTERVAL_S)

        url = _extract_video_url(job)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        download(url, out_path)

        return ClipResult(
            path=out_path,
            prompt=prompt,
            model=self.model["key"],
            job_id=job_id,
            duration_s=ffprobe_duration(out_path),
        )


def _extract_video_url(job) -> str:
    """The completed-job payload has varied across SDK versions — check the
    known locations before giving up."""
    url = getattr(job, "output_video_url", None)
    if url:
        return url
    outputs = getattr(job, "outputs", None)
    if outputs is not None:
        for candidate in (outputs if isinstance(outputs, list) else [outputs]):
            url = getattr(candidate, "video_url", None) or (
                candidate.get("video_url") if isinstance(candidate, dict) else None
            )
            if url:
                return url
    output = getattr(job, "output", None)
    if output is not None:
        url = getattr(output, "video_url", None) or (
            output.get("video_url") if isinstance(output, dict) else None
        )
        if url:
            return url
    raise RuntimeError(f"Completed video job has no video URL: {job!r}")
