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


def create_project(name: str, parent: Path, *, concept: str = "",
                   anchor: str = "", suffix: str | None = None,
                   aspect: str = "9:16",
                   image_model: str | None = None,
                   video_model: str | None = None) -> Project:
    """Create a project directory + project.json (shared by CLI and API)."""
    from . import config as cfg
    from .project import Settings, Style
    from .prompts import DEFAULT_SUFFIX
    from .util import slugify

    if aspect not in cfg.ASPECTS:
        raise ValueError(f"Unknown aspect '{aspect}'. Options: {', '.join(cfg.ASPECTS)}")
    root = parent / slugify(name)
    if (root / "project.json").exists():
        raise FileExistsError(f"Project already exists at {root}")
    width, height = cfg.ASPECTS[aspect]
    project = Project(
        name=name,
        concept=concept,
        style=Style(anchor=anchor, suffix=DEFAULT_SUFFIX if suffix is None else suffix),
        settings=Settings(
            aspect=aspect, width=width, height=height,
            image_model=image_model or cfg.DEFAULT_IMAGE_MODEL,
            video_model=video_model or cfg.DEFAULT_VIDEO_MODEL,
        ),
        root=root,
    )
    root.mkdir(parents=True)
    project.save()
    return project


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


def scene_reference_images(project: Project, scene: Scene,
                           profile=None) -> list[Path]:
    """Ordered reference set for a scene: character identity refs first
    (the prompt calls them 'the first N reference images'), then outfit
    item photos in listing order, then the project style ref last.
    Profile characters (pchar-*) resolve against the profile root."""
    refs: list[Path] = []
    if scene.character_id:
        from .profile import resolve_character
        character, base = resolve_character(project, profile, scene.character_id)
        refs += [base / r for r in character.reference_images]
    if scene.outfit_id:
        outfit = project.find_outfit(scene.outfit_id)
        refs += [project.root / item.image for item in outfit.items if item.image]
    if project.style.reference_image:
        refs.append(project.root / project.style.reference_image)
    return refs


def run_images(project: Project, todo: list[tuple[Scene, int]], model_key: str,
               log: Log = print, profile=None) -> int:
    gen_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backend = get_image_backend(model_key, log)
    count = 0
    for sc, needed in todo:
        prompt = compose_prompt(project, sc, profile=profile)
        refs = scene_reference_images(project, sc, profile=profile)
        cap = backend.max_reference_images
        if refs and cap == 0:
            log(f"note: {model_key} does not accept reference images — "
                f"{len(refs)} ignored for {sc.id}")
            refs = []
        elif len(refs) > cap:
            dropped = ", ".join(p.name for p in refs[cap:])
            log(f"WARNING: {model_key} accepts {cap} reference images — "
                f"dropping from the tail: {dropped}")
            refs = refs[:cap]
        for _ in range(needed):
            opt_num = len(sc.images) + 1
            out = project.images_dir(sc) / f"opt-{opt_num}.png"
            result = backend.generate_image(
                prompt, out,
                width=project.settings.width, height=project.settings.height,
                reference_images=refs or None,
            )
            meta = result.meta
            if "cost_usd" not in meta:
                meta["cost_usd"] = config.MODELS.get(model_key, {}).get("price", 0)
            sc.images.append(ImageArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                model=model_key,
                meta=meta,
                generation_id=gen_id,
            ))
            project.save()
            count += 1
            log(f"{sc.id} opt-{opt_num}: {out.relative_to(project.root)}"
                + _cost_suffix(result.meta))
    return count


def _cost_suffix(meta: dict) -> str:
    cost = meta.get("cost_usd")
    return f" (${cost:.3f})" if cost else ""


def run_clips(project: Project, todo: list[Scene], model_key: str,
              log: Log = print, profile=None) -> list[str]:
    """Generate clips for scenes with a selected image. Failures are
    recorded on the scene and returned; the batch continues."""
    resolved = config.resolve_model(model_key, "video")
    supports_i2v = resolved.get("supports_i2v")
    if supports_i2v is False:
        log(f"WARNING: {model_key} is text-to-video only — selected images will "
            "be IGNORED and visual consistency with your stills is not guaranteed.")
    elif supports_i2v is None:
        log(f"note: I2V support for {model_key} is unverified — attempting")

    backend = get_video_backend(model_key, log)
    failures = []
    for sc in todo:
        prompt = compose_prompt(project, sc, profile=profile)
        out = project.clips_dir / f"{sc.id}.mp4"
        # Generate to a working name; the existing clip is archived only
        # after the new one succeeds. A failed regen must never orphan
        # the completed clip a stitch depends on.
        pending = out.with_name(f"{sc.id}.pending.mp4")
        image = (
            project.root / sc.selected_image_file
            if supports_i2v is not False
            else None
        )
        log(f"{sc.id}: generating...")
        try:
            result = backend.generate_clip(
                prompt, pending,
                image=image,
                width=project.settings.width, height=project.settings.height,
                timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
            )
            if out.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                archived = out.with_name(f"{sc.id}.{stamp}.mp4")
                out.rename(archived)
                rel_old = str(out.relative_to(project.root))
                rel_new = str(archived.relative_to(project.root))
                for clip in sc.clips:
                    if clip.file == rel_old:
                        clip.file = rel_new
            pending.rename(out)
            clip_meta = result.meta
            if "cost_usd" not in clip_meta:
                clip_meta["cost_usd"] = config.MODELS.get(model_key, {}).get("price", 0)
            sc.clips.append(ClipArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                source_image=sc.selected_image_file,
                model=model_key,
                job_id=result.job_id,
                duration_s=result.duration_s,
                status="completed",
                meta=clip_meta,
            ))
            log(f"{sc.id}: done ({result.duration_s:.1f}s){_cost_suffix(result.meta)}")
        except Exception as exc:
            pending.unlink(missing_ok=True)
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


def run_takes(project: Project, scene: Scene, image_index: int, count: int,
              model_key: str, *, prompt_override: str | None = None,
              log: Log = print, profile=None) -> list[str]:
    """Generate `count` clip takes from one scene image. Every take is its
    own file under clips/<scene>/ — takes never overwrite each other, and
    failures are recorded while the batch continues."""
    resolved = config.resolve_model(model_key, "video")
    if not scene.images or not 0 <= image_index < len(scene.images):
        raise ValueError(
            f"{scene.id} has {len(scene.images)} image option(s); "
            f"image index {image_index + 1} is invalid"
        )
    supports_i2v = resolved.get("supports_i2v")
    if supports_i2v is False:
        log(f"WARNING: {model_key} is text-to-video only — the source image "
            "will be IGNORED.")

    backend = get_video_backend(model_key, log)
    prompt = prompt_override or compose_prompt(project, scene, profile=profile)
    source = scene.images[image_index]
    image = project.root / source.file if supports_i2v is not False else None
    takes_dir = project.clips_dir / scene.id
    next_take = max((c.take for c in scene.clips if c.take), default=0) + 1

    failures = []
    for i in range(count):
        take_num = next_take + i
        out = takes_dir / f"take-{take_num:02d}.mp4"
        pending = out.with_name(f"take-{take_num:02d}.pending.mp4")
        log(f"{scene.id} take {take_num}: generating...")
        try:
            result = backend.generate_clip(
                prompt, pending,
                image=image,
                width=project.settings.width, height=project.settings.height,
                timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
            )
            pending.rename(out)
            take_meta = result.meta
            if "cost_usd" not in take_meta:
                take_meta["cost_usd"] = config.MODELS.get(model_key, {}).get("price", 0)
            scene.clips.append(ClipArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                source_image=source.file,
                model=model_key,
                job_id=result.job_id,
                duration_s=result.duration_s,
                status="completed",
                meta=take_meta,
                take=take_num,
                source_image_index=image_index,
            ))
            log(f"{scene.id} take {take_num}: done "
                f"({result.duration_s:.1f}s){_cost_suffix(take_meta)}")
        except Exception as exc:
            pending.unlink(missing_ok=True)
            scene.clips.append(ClipArtifact(
                file=str(out.relative_to(project.root)),
                prompt=prompt,
                source_image=source.file,
                model=model_key,
                status="failed",
                error=str(exc),
                take=take_num,
                source_image_index=image_index,
            ))
            failures.append(f"{scene.id} take {take_num}")
            log(f"{scene.id} take {take_num}: FAILED — {exc}")
        project.save()
    return failures


def run_export(project: Project, out_dir: Path | None = None) -> list[Path]:
    """Copy kept takes into a stable export folder (for CapCut import),
    named {outfit}--{scene}--takeN.mp4, plus links.txt with the shop
    blocks of the outfits involved. Rewritten from scratch each run."""
    import shutil

    from .util import slugify

    kept = [
        (sc, clip)
        for sc in project.scenes
        for clip in sc.clips
        if clip.kept and clip.status == "completed"
    ]
    if not kept:
        raise ValueError("No takes marked as kept — mark keepers first")

    export_dir = out_dir or project.root / "export"
    if export_dir.is_dir():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True)

    manifest = []
    outfit_ids: list[str] = []
    for sc, clip in kept:
        stem = "clip"
        if sc.outfit_id:
            outfit = project.find_outfit(sc.outfit_id)
            stem = slugify(outfit.name)
            if outfit.id not in outfit_ids:
                outfit_ids.append(outfit.id)
        name = f"{stem}--{sc.id}--take{clip.take or 0:02d}.mp4"
        dest = export_dir / name
        shutil.copy2(project.root / clip.file, dest)
        manifest.append(dest)

    if outfit_ids:
        blocks = []
        for oid in outfit_ids:
            outfit = project.find_outfit(oid)
            lines = [outfit.name] + [
                f"{item.name} — {item.url}" if item.url else item.name
                for item in outfit.items
            ]
            blocks.append("\n".join(lines))
        (export_dir / "links.txt").write_text("\n\n".join(blocks) + "\n")

    return manifest


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
