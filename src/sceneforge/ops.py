"""Core generation operations shared by the CLI and the web UI.

These functions mutate the project (saving after every artifact) and
report progress through a log callback, so typer commands and background
web jobs drive identical code paths.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .backends import get_image_backend, get_video_backend
from .project import ClipArtifact, ImageArtifact, Project, Scene
from .prompts import compose_prompt
from .stitch import stitch as stitch_clips

Log = Callable[[str], None]


def plan_images(scenes: list[Scene], options: int, force: bool) -> list[tuple[Scene, int]]:
    """Scenes that still need image options, with how many each needs."""
    todo = []
    for sc in scenes:
        needed = options if force else max(0, options - len(sc.images))
        if needed:
            todo.append((sc, needed))
    return todo


def unselected_scenes(scenes: list[Scene]) -> list[str]:
    return [sc.id for sc in scenes if sc.selected_image is None]


def plan_clips(scenes: list[Scene], force: bool) -> list[Scene]:
    return [sc for sc in scenes if force or sc.completed_clip is None]


def run_images(project: Project, todo: list[tuple[Scene, int]], model_key: str,
               log: Log = print) -> int:
    backend = get_image_backend(model_key)
    if project.style.reference_image and not backend.supports_reference_image:
        log(f"note: {model_key} ignores the project reference image")
    count = 0
    for sc, needed in todo:
        prompt = compose_prompt(project, sc)
        for _ in range(needed):
            opt_num = len(sc.images) + 1
            out = project.images_dir(sc) / f"opt-{opt_num}.png"
            ref = (
                project.root / project.style.reference_image
                if project.style.reference_image and backend.supports_reference_image
                else None
            )
            backend.generate_image(
                prompt, out,
                width=project.settings.width, height=project.settings.height,
                reference_image=ref,
            )
            sc.images.append(ImageArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                model=model_key,
            ))
            project.save()
            count += 1
            log(f"{sc.id} opt-{opt_num}: {out.relative_to(project.root)}")
    return count


def run_clips(project: Project, todo: list[Scene], model_key: str,
              log: Log = print) -> list[str]:
    """Generate clips for scenes with a selected image. Failures are
    recorded on the scene and returned; the batch continues."""
    resolved = config.resolve_model(model_key, "video")
    supports_i2v = resolved.get("supports_i2v")
    if supports_i2v is False:
        log(f"WARNING: {model_key} is text-to-video only — selected images will "
            "be IGNORED and visual consistency with your stills is not guaranteed.")
    elif supports_i2v is None:
        log(f"note: I2V support for {model_key} is unverified — attempting")

    backend = get_video_backend(model_key)
    failures = []
    for sc in todo:
        prompt = compose_prompt(project, sc)
        out = project.clips_dir / f"{sc.id}.mp4"
        if out.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            out.rename(out.with_name(f"{sc.id}.{stamp}.mp4"))
        image = (
            project.root / sc.selected_image_file
            if supports_i2v is not False
            else None
        )
        log(f"{sc.id}: generating...")
        try:
            result = backend.generate_clip(
                prompt, out,
                image=image,
                width=project.settings.width, height=project.settings.height,
                timeout_s=config.VIDEO_TIMEOUT_S,
            )
            sc.clips.append(ClipArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                source_image=sc.selected_image_file,
                model=model_key,
                job_id=result.job_id,
                duration_s=result.duration_s,
                status="completed",
            ))
            log(f"{sc.id}: done ({result.duration_s:.1f}s)")
        except Exception as exc:
            sc.clips.append(ClipArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                source_image=sc.selected_image_file,
                model=model_key,
                status="failed",
                error=str(exc),
            ))
            failures.append(sc.id)
            log(f"{sc.id}: FAILED — {exc}")
        project.save()
    return failures


def run_stitch(project: Project, *, speed: float | None = None,
               fade: float | None = None, out: Path | None = None) -> tuple[Path, float]:
    if not project.scenes:
        raise ValueError("No scenes to stitch")
    missing = [sc.id for sc in project.scenes if sc.completed_clip is None]
    if missing:
        raise ValueError("These scenes have no completed clip: " + ", ".join(missing))
    clips = [project.root / sc.completed_clip.file for sc in project.scenes]
    out_path = out or project.output_dir / "final.mp4"
    duration = stitch_clips(
        clips, out_path,
        work_dir=project.work_dir,
        width=project.settings.width, height=project.settings.height,
        speed=speed if speed is not None else project.settings.clip_speed,
        fade=fade if fade is not None else project.settings.crossfade,
    )
    return out_path, duration
