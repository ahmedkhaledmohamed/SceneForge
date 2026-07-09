import subprocess

import pytest

from sceneforge.stitch import stitch, xfade_offsets
from sceneforge.util import ffprobe_duration


def make_clip(path, duration, size="640x360"):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
        check=True,
    )
    return path


def test_xfade_offsets():
    # 2s + 3s + 4s clips, 0.3s fade
    assert xfade_offsets([2.0, 3.0, 4.0], 0.3) == [1.7, 4.4]
    assert xfade_offsets([5.0], 0.3) == []


def test_stitch_three_clips(tmp_path):
    clips = [make_clip(tmp_path / f"c{i}.mp4", d) for i, d in enumerate([2, 3, 4])]
    out = tmp_path / "out" / "final.mp4"
    duration = stitch(clips, out, work_dir=tmp_path / "work",
                      width=720, height=1280, speed=2.0, fade=0.3)
    # (1 + 1.5 + 2) - 2*0.3 = 3.9
    assert out.exists()
    assert duration == pytest.approx(3.9, abs=0.2)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "720,1280"


def test_stitch_two_clips(tmp_path):
    clips = [make_clip(tmp_path / f"c{i}.mp4", 2) for i in range(2)]
    out = tmp_path / "final.mp4"
    duration = stitch(clips, out, work_dir=tmp_path / "work",
                      width=720, height=1280, speed=1.0, fade=0.3)
    assert duration == pytest.approx(3.7, abs=0.2)


def test_stitch_single_clip(tmp_path):
    clip = make_clip(tmp_path / "c.mp4", 3)
    out = tmp_path / "final.mp4"
    duration = stitch([clip], out, work_dir=tmp_path / "work",
                      width=720, height=1280, speed=2.0, fade=0.3)
    assert duration == pytest.approx(1.5, abs=0.2)


def test_stitch_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        stitch([], tmp_path / "final.mp4", work_dir=tmp_path / "work",
               width=720, height=1280, speed=2.0, fade=0.3)
