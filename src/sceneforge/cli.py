"""SceneForge CLI.

Workflow: create -> add-scenes -> generate-images -> select ->
generate-clips -> stitch. Generation commands are idempotent: they skip
scenes that already have what they need unless --force / regenerate.
"""

from pathlib import Path

import typer

from . import config, ops
from .project import Project, Settings, Style, find_project_root
from .prompts import DEFAULT_SUFFIX, build_anchor, compose_prompt
from .util import slugify

app = typer.Typer(help="Local-first AI video production: images -> clips -> final cut.")


@app.callback()
def main(
    ctx: typer.Context,
    project: Path = typer.Option(
        None, "--project", "-p", help="Project directory (default: walk up from cwd)"
    ),
):
    ctx.obj = {"project_path": project}


def _load(ctx: typer.Context) -> Project:
    explicit = ctx.obj.get("project_path")
    root = explicit if explicit else find_project_root()
    if root is None or not (root / "project.json").is_file():
        typer.secho(
            "No project found. Run from inside a project directory, pass "
            "--project, or create one with: sceneforge create \"name\"",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    return Project.load(Path(root))


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED)
    raise typer.Exit(1)


# ---------------------------------------------------------------- create


@app.command()
def create(
    name: str,
    aspect: str = typer.Option("9:16", help="9:16 (Reels/TikTok) or 16:9"),
    concept: str = typer.Option(None, help="Video concept (prompted if omitted)"),
    mood: str = typer.Option(None, help="Mood, e.g. 'cozy, slow, intimate'"),
    palette: str = typer.Option(None, help="Palette, e.g. 'muted earth tones'"),
    lighting: str = typer.Option(None, help="Lighting, e.g. 'warm golden hour'"),
    anchor: str = typer.Option(
        None, help="Full style anchor (overrides mood/palette/lighting composition)"
    ),
    image_model: str = typer.Option(config.DEFAULT_IMAGE_MODEL),
    video_model: str = typer.Option(config.DEFAULT_VIDEO_MODEL),
    directory: Path = typer.Option(
        None, "--dir", help="Parent directory for the project (default: cwd)"
    ),
):
    """Create a new project directory with its style context."""
    if aspect not in config.ASPECTS:
        _fail(f"Unknown aspect '{aspect}'. Options: {', '.join(config.ASPECTS)}")
    config.resolve_model(image_model, "image")
    config.resolve_model(video_model, "video")

    root = (directory or Path.cwd()) / slugify(name)
    if (root / "project.json").exists():
        _fail(f"Project already exists at {root}")

    if concept is None:
        concept = typer.prompt("Concept (what is this video about?)")
    if anchor is None:
        if mood is None:
            mood = typer.prompt("Mood", default="")
        if palette is None:
            palette = typer.prompt("Color palette", default="")
        if lighting is None:
            lighting = typer.prompt("Lighting", default="")
        anchor = build_anchor(mood or "", palette or "", lighting or "")
        if not anchor:
            typer.echo("No style facets given — scenes will rely on descriptions only.")

    width, height = config.ASPECTS[aspect]
    project = Project(
        name=name,
        concept=concept,
        style=Style(
            anchor=anchor,
            mood=mood or "",
            palette=palette or "",
            lighting=lighting or "",
            suffix=DEFAULT_SUFFIX,
        ),
        settings=Settings(
            aspect=aspect,
            width=width,
            height=height,
            image_model=image_model,
            video_model=video_model,
        ),
        root=root,
    )
    root.mkdir(parents=True)
    project.save()
    typer.secho(f"Created project at {root}", fg=typer.colors.GREEN)
    typer.echo(f"  style anchor: {anchor or '(none)'}")
    typer.echo(f"  models: {image_model} (images), {video_model} (video)")
    typer.echo("Next: cd in and run 'sceneforge add-scenes'")


# ---------------------------------------------------------------- models


@app.command()
def models(kind: str = typer.Argument(None, help="Filter: image or video")):
    """List available generation models with prices and capabilities."""
    if kind is not None and kind not in ("image", "video"):
        _fail("Kind must be 'image' or 'video'")
    typer.echo(f"{'MODEL':<14} {'KIND':<6} {'PRICE':<8} {'I2V':<10} NOTES")
    for key, model in config.MODELS.items():
        if kind and model["kind"] != kind:
            continue
        i2v = {True: "yes", False: "no", None: "unverified"}.get(
            model.get("supports_i2v"), "-"
        )
        if model["kind"] == "image":
            i2v = "-"
        typer.echo(
            f"{key:<14} {model['kind']:<6} ${model['price']:<7.2f} {i2v:<10} "
            f"{model.get('notes', '')}"
        )


# ---------------------------------------------------------------- add-scenes


@app.command("add-scenes")
def add_scenes(
    ctx: typer.Context,
    scene: list[str] = typer.Option(
        None, "--scene", help="Scene description (repeatable, skips LLM)"
    ),
    manual: bool = typer.Option(False, help="Type scene descriptions interactively"),
    count: int = typer.Option(6, help="Number of scenes for LLM breakdown"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept LLM scenes without confirming"),
):
    """Add scenes: LLM breakdown of the concept (default), or manually."""
    project = _load(ctx)

    if scene:
        descriptions = list(scene)
    elif manual:
        descriptions = []
        typer.echo("Enter scene descriptions (empty line to finish):")
        while True:
            desc = typer.prompt(f"Scene {len(project.scenes) + len(descriptions) + 1}",
                                default="", show_default=False)
            if not desc.strip():
                break
            descriptions.append(desc.strip())
        if not descriptions:
            _fail("No scenes entered")
    else:
        if not project.concept:
            _fail("Project has no concept — add scenes with --scene or --manual")
        from .breakdown import generate_scenes

        typer.echo(f"Breaking '{project.concept}' into {count} scenes...")
        descriptions = generate_scenes(project.concept, project.style.anchor, count)
        for i, desc in enumerate(descriptions, len(project.scenes) + 1):
            typer.echo(f"  {i}. {desc}")
        if not yes and not typer.confirm("Add these scenes?"):
            raise typer.Exit(0)

    for desc in descriptions:
        project.add_scene(desc)
    project.save()
    typer.secho(f"Added {len(descriptions)} scenes ({len(project.scenes)} total)",
                fg=typer.colors.GREEN)


# ---------------------------------------------------------------- images


@app.command("generate-images")
def generate_images(
    ctx: typer.Context,
    scene_id: str = typer.Argument(None, help="Only this scene (default: all)"),
    options: int = typer.Option(None, help="Image options per scene (default: project setting)"),
    model: str = typer.Option(None, help="Image model (see 'sceneforge models image')"),
    force: bool = typer.Option(False, help="Regenerate even if options already exist"),
    dry_run: bool = typer.Option(False, help="Print prompts without generating"),
):
    """Generate image options for each scene using the project style context."""
    project = _load(ctx)
    scenes = [project.find_scene(scene_id)] if scene_id else project.scenes
    if not scenes:
        _fail("No scenes yet — run 'sceneforge add-scenes' first")
    n_options = options or project.settings.image_options
    model_key = model or project.settings.image_model
    resolved = config.resolve_model(model_key, "image")

    todo = ops.plan_images(scenes, n_options, force)
    in_todo = {sc.id for sc, _ in todo}
    for sc in scenes:
        if sc.id not in in_todo:
            typer.echo(f"{sc.id}: has {len(sc.images)} images, skipping (--force to redo)")
    if not todo:
        typer.echo("Nothing to generate.")
        return

    total = sum(n for _, n in todo)
    typer.echo(
        f"Generating {total} images with {model_key} "
        f"(~${total * resolved['price']:.2f})"
    )
    if dry_run:
        for sc, needed in todo:
            typer.echo(f"[dry-run] {sc.id} x{needed}: {compose_prompt(project, sc)}")
        return

    ops.run_images(project, todo, model_key, log=typer.echo)
    typer.secho("Done. Pick with: sceneforge select SCENE_ID OPTION_NUM",
                fg=typer.colors.GREEN)


@app.command()
def select(ctx: typer.Context, scene_id: str, option: int):
    """Select an image option (1-based) for a scene."""
    project = _load(ctx)
    sc = project.find_scene(scene_id)
    if not 1 <= option <= len(sc.images):
        _fail(f"{scene_id} has {len(sc.images)} image options, got {option}")
    sc.selected_image = option - 1
    project.save()
    typer.secho(f"{scene_id}: selected opt-{option} ({sc.selected_image_file})",
                fg=typer.colors.GREEN)


# ---------------------------------------------------------------- clips


@app.command("generate-clips")
def generate_clips(
    ctx: typer.Context,
    scene_id: str = typer.Argument(None, help="Only this scene (default: all)"),
    model: str = typer.Option(None, help="Video model (see 'sceneforge models video')"),
    force: bool = typer.Option(False, help="Regenerate even if a clip exists"),
    dry_run: bool = typer.Option(False, help="Print prompts without generating"),
):
    """Animate each scene's selected image into a clip (image-to-video)."""
    project = _load(ctx)
    scenes = [project.find_scene(scene_id)] if scene_id else project.scenes
    if not scenes:
        _fail("No scenes yet — run 'sceneforge add-scenes' first")
    model_key = model or project.settings.video_model
    resolved = config.resolve_model(model_key, "video")

    unselected = ops.unselected_scenes(scenes)
    if unselected:
        _fail(
            "These scenes have no selected image: " + ", ".join(unselected)
            + "\nRun 'sceneforge generate-images' then 'sceneforge select'."
        )

    todo = ops.plan_clips(scenes, force)
    for sc in scenes:
        if sc not in todo:
            typer.echo(f"{sc.id}: clip exists, skipping (--force to redo)")
    if not todo:
        typer.echo("Nothing to generate.")
        return

    typer.echo(f"Generating {len(todo)} clips with {model_key} "
               f"(~${len(todo) * resolved['price']:.2f})")
    if dry_run:
        for sc in todo:
            typer.echo(f"[dry-run] {sc.id} from {sc.selected_image_file}: "
                       f"{compose_prompt(project, sc)}")
        return

    failures = ops.run_clips(project, todo, model_key, log=typer.echo)
    if failures:
        _fail(f"{len(failures)} clip(s) failed: {', '.join(failures)}. "
              "Re-run generate-clips to retry just those.")
    typer.secho("All clips done. Next: sceneforge stitch", fg=typer.colors.GREEN)


# ---------------------------------------------------------------- stitch


@app.command()
def stitch(
    ctx: typer.Context,
    speed: float = typer.Option(None, help="Playback speed (default: project setting)"),
    fade: float = typer.Option(None, help="Crossfade seconds (default: project setting)"),
    out: Path = typer.Option(None, help="Output path (default: output/final.mp4)"),
):
    """Stitch all scene clips into the final video (speed + crossfades, no audio)."""
    project = _load(ctx)
    try:
        out_path, duration = ops.run_stitch(project, speed=speed, fade=fade, out=out)
    except ValueError as exc:
        _fail(str(exc))
    typer.secho(f"Final video: {out_path} ({duration:.1f}s, "
                f"{project.settings.width}x{project.settings.height})",
                fg=typer.colors.GREEN)


# ---------------------------------------------------------------- regenerate / status


@app.command()
def regenerate(
    ctx: typer.Context,
    scene_id: str,
    what: str = typer.Argument(..., help="'image' or 'clip'"),
    model: str = typer.Option(None, help="Model override for the redo"),
):
    """Redo generation for one scene (images or clip)."""
    if what == "image":
        ctx.invoke(generate_images, ctx=ctx, scene_id=scene_id, options=None,
                   model=model, force=True, dry_run=False)
    elif what == "clip":
        ctx.invoke(generate_clips, ctx=ctx, scene_id=scene_id, model=model,
                   force=True, dry_run=False)
    else:
        _fail("Specify what to regenerate: 'image' or 'clip'")


@app.command()
def status(ctx: typer.Context):
    """Show project state and estimated remaining generation cost."""
    project = _load(ctx)
    typer.echo(f"Project: {project.name} ({project.settings.aspect}, "
               f"{project.settings.width}x{project.settings.height})")
    typer.echo(f"Concept: {project.concept}")
    typer.echo(f"Style:   {project.style.anchor or '(none)'}")
    typer.echo(f"Models:  {project.settings.image_model} (images), "
               f"{project.settings.video_model} (video)")
    if not project.scenes:
        typer.echo("No scenes yet — run 'sceneforge add-scenes'")
        return

    typer.echo(f"\n{'SCENE':<10} {'IMAGES':<8} {'SELECTED':<10} {'CLIP':<10} DESCRIPTION")
    for sc in project.scenes:
        selected = f"opt-{sc.selected_image + 1}" if sc.selected_image is not None else "-"
        clip = sc.completed_clip.status if sc.completed_clip else (
            "failed" if any(c.status == "failed" for c in sc.clips) else "-"
        )
        desc = sc.description if len(sc.description) <= 60 else sc.description[:57] + "..."
        typer.echo(f"{sc.id:<10} {len(sc.images):<8} {selected:<10} {clip:<10} {desc}")

    image_model = config.resolve_model(project.settings.image_model, "image")
    video_model = config.resolve_model(project.settings.video_model, "video")
    images_needed = sum(
        max(0, project.settings.image_options - len(sc.images)) for sc in project.scenes
    )
    clips_needed = sum(1 for sc in project.scenes if sc.completed_clip is None)
    cost = images_needed * image_model["price"] + clips_needed * video_model["price"]
    typer.echo(f"\nRemaining: {images_needed} images, {clips_needed} clips "
               f"(~${cost:.2f} at current models)")


# ---------------------------------------------------------------- web ui


@app.command()
def ui(
    directory: Path = typer.Option(
        None, "--dir", help="Directory containing project folders (default: cwd)"
    ),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
):
    """Launch the local web UI for browsing and driving projects."""
    import uvicorn

    from .web import create_app

    base = (directory or Path.cwd()).resolve()
    typer.secho(f"SceneForge UI on http://{host}:{port} (projects in {base})",
                fg=typer.colors.GREEN)
    uvicorn.run(create_app(base), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
