"""Zero-cost test backends. Generate real media files with ffmpeg lavfi
so the full pipeline (selection, stitching, ffprobe) runs unchanged."""

import hashlib
from pathlib import Path

from ..util import ffprobe_duration, run_ffmpeg
from .base import ClipResult, ImageBackend, ImageResult, VideoBackend

FAKE_CLIP_DURATION_S = 4


def _prompt_color(prompt: str) -> str:
    return "#" + hashlib.sha256(prompt.encode()).hexdigest()[:6]


class FakeImageBackend(ImageBackend):
    def generate_image(self, prompt, out_path, *, width, height,
                       reference_images=None, seed=None):
        refs = [p.name for p in (reference_images or [])]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg([
            "-f", "lavfi",
            # refs participate in the color so tests can assert they arrived
            "-i", f"color=c={_prompt_color(prompt + ''.join(refs))}:s={width}x{height}",
            "-frames:v", "1",
            str(out_path),
        ])
        return ImageResult(
            path=out_path, prompt=prompt, model=self.model["key"],
            meta={"reference_images": refs} if refs else {},
        )


class FakeVideoBackend(VideoBackend):
    supports_i2v = False

    def generate_clip(self, prompt, out_path, *, image, width, height,
                      timeout_s=600, **_kwargs):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg([
            "-f", "lavfi",
            "-i", f"testsrc=duration={FAKE_CLIP_DURATION_S}:size={width}x{height}:rate=30",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            str(out_path),
        ])
        return ClipResult(
            path=out_path,
            prompt=prompt,
            model=self.model["key"],
            job_id=None,
            duration_s=ffprobe_duration(out_path),
        )
