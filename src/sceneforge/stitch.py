"""Stitch scene clips into the final video.

Two passes:
1. Normalize each clip (speed, fps, geometry, pixel format) into work/.
   xfade requires identical size/fps/timebase across inputs, and doing
   the speed change first makes the offset math exact.
2. Chain xfade filters using ffprobe-MEASURED durations of the
   normalized clips — computed durations drift after setpts+fps.

Offsets for fade f over measured durations d_i:
    o_1 = d_1 - f
    o_k = o_{k-1} + d_k - f
Final duration = sum(d_i) - (N-1)*f.
"""

import shutil
from pathlib import Path

from .util import ffprobe_duration, run_ffmpeg


def normalize_clip(src: Path, dst: Path, *, width: int, height: int,
                   speed: float, fps: int = 30) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    filters = (
        f"setpts=PTS/{speed},fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
    )
    run_ffmpeg([
        "-i", str(src),
        "-filter:v", filters,
        "-an", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
        str(dst),
    ])
    return dst


def xfade_offsets(durations: list[float], fade: float) -> list[float]:
    offsets = []
    total = 0.0
    for d in durations[:-1]:
        total += d - fade
        offsets.append(round(total, 3))
    return offsets


def stitch(clips: list[Path], out_path: Path, *, work_dir: Path,
           width: int, height: int, speed: float, fade: float) -> float:
    """Normalize and stitch clips in order. Returns the final duration."""
    if not clips:
        raise ValueError("No clips to stitch")

    normalized = [
        normalize_clip(src, work_dir / f"{i:02d}-{src.stem}.mp4",
                       width=width, height=height, speed=speed)
        for i, src in enumerate(clips, 1)
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if len(normalized) == 1:
        # re-mux for faststart; content already normalized
        run_ffmpeg(["-i", str(normalized[0]), "-c", "copy",
                    "-movflags", "+faststart", str(out_path)])
        return ffprobe_duration(out_path)

    durations = [ffprobe_duration(p) for p in normalized]
    offsets = xfade_offsets(durations, fade)

    filter_parts = []
    prev = "[0:v]"
    for i, offset in enumerate(offsets, 1):
        label = f"[v{i}]"
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={fade}:offset={offset}{label}"
        )
        prev = label

    inputs = []
    for p in normalized:
        inputs += ["-i", str(p)]
    run_ffmpeg([
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", prev,
        "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ])

    actual = ffprobe_duration(out_path)
    expected = sum(durations) - (len(durations) - 1) * fade
    if abs(actual - expected) > 0.2:
        raise RuntimeError(
            f"Stitched duration {actual:.2f}s deviates from expected "
            f"{expected:.2f}s — check clip normalization"
        )
    return actual


def clean_work_dir(work_dir: Path) -> None:
    if work_dir.is_dir():
        shutil.rmtree(work_dir)
