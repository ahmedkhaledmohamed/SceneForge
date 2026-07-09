"""Shared helpers: slugify, downloads, base64 data URIs, ffprobe."""

import base64
import json
import re
import subprocess
from pathlib import Path


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"Cannot derive a directory name from {name!r}")
    return slug


def download(url: str, out_path: Path) -> None:
    """Download a URL to a file. Uses curl with a User-Agent header —
    Together's media CDN returns 403 to urllib's default agent."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "curl", "-L", "--fail", "--silent", "--show-error",
            "-H", "User-Agent: SceneForge/1.0",
            "-o", str(out_path),
            url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Download failed for {url}: {result.stderr.strip()}")


def image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix, "image/png"
    )
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def run_ffmpeg(args: list[str]) -> None:
    """Run ffmpeg with -y and quiet logging; surface the stderr tail on failure."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-10:])
        raise RuntimeError(f"ffmpeg failed ({' '.join(cmd[:6])} ...):\n{tail}")
