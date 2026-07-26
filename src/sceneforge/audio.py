"""Audio layer — merge audio with video clips using ffmpeg."""

from __future__ import annotations

from pathlib import Path

from .util import run_ffmpeg


def merge_audio_video(video_path: Path, audio_path: Path,
                      output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ])
    return output_path


def strip_audio(video_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-i", str(video_path),
        "-an",
        "-c:v", "copy",
        str(output_path),
    ])
    return output_path
