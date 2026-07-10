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


def _load_with_profile(ctx: typer.Context):
    from .profile import profile_for_project

    project = _load(ctx)
    return project, profile_for_project(project)


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
    typer.echo(f"{'MODEL':<18} {'KIND':<6} {'PRICE':<8} {'I2V':<10} {'REFS':<5} NOTES")
    for key, model in config.MODELS.items():
        if kind and model["kind"] != kind:
            continue
        i2v = {True: "yes", False: "no", None: "unverified"}.get(
            model.get("supports_i2v"), "-"
        )
        if model["kind"] == "image":
            i2v = "-"
        refs = str(model.get("max_refs", 0)) if model["kind"] == "image" else "-"
        typer.echo(
            f"{key:<18} {model['kind']:<6} ${model['price']:<7.2f} {i2v:<10} {refs:<5} "
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


# ------------------------------------------------ characters / outfits


def _import_ref(src: Path, dest_dir: Path) -> str:
    """Copy a reference image into the project; returns project-relative path."""
    import shutil

    src = src.expanduser()
    if not src.is_file():
        _fail(f"Reference image not found: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


@app.command("add-character")
def add_character(
    ctx: typer.Context,
    name: str,
    ref: list[Path] = typer.Option(..., "--ref", help="Reference image (repeatable)"),
    description: str = typer.Option("", help="Short visual description"),
):
    """Add a recurring character (e.g. your doll) with its reference images."""
    project = _load(ctx)
    character = project.add_character(name, description)
    for src in ref:
        dest = _import_ref(src, project.character_refs_dir(character))
        character.reference_images.append(str(dest.relative_to(project.root)))
    project.save()
    typer.secho(f"{character.id}: '{name}' with {len(character.reference_images)} "
                "reference image(s)", fg=typer.colors.GREEN)


@app.command("add-outfit")
def add_outfit(
    ctx: typer.Context,
    name: str,
    item: list[str] = typer.Option(
        None, "--item",
        help="Clothing item as 'NAME|SHOP_URL|IMAGE_PATH' (URL/IMAGE optional, repeatable)",
    ),
):
    """Add an outfit: shoppable clothing items with links and product photos."""
    from .project import ClothingItem

    project = _load(ctx)
    outfit = project.add_outfit(name)

    specs = list(item or [])
    if not specs:
        typer.echo("Enter items as NAME|SHOP_URL|IMAGE_PATH (empty line to finish):")
        while True:
            line = typer.prompt(f"Item {len(outfit.items) + 1}", default="",
                                show_default=False)
            if not line.strip():
                break
            specs.append(line)
    if not specs:
        _fail("An outfit needs at least one item")

    for spec in specs:
        parts = [p.strip() for p in spec.split("|")]
        clothing = ClothingItem(name=parts[0])
        if len(parts) > 1 and parts[1]:
            clothing.url = parts[1]
        if len(parts) > 2 and parts[2]:
            dest = _import_ref(Path(parts[2]), project.outfit_refs_dir(outfit))
            clothing.image = str(dest.relative_to(project.root))
        outfit.items.append(clothing)

    project.save()
    with_images = sum(1 for i in outfit.items if i.image)
    typer.secho(f"{outfit.id}: '{name}' — {len(outfit.items)} item(s), "
                f"{with_images} with reference photos", fg=typer.colors.GREEN)


DEFAULT_POSES = [
    "standing, facing the camera, full outfit visible head to toe",
    "three-quarter turn, looking over the shoulder, showcasing the outfit from a different angle",
]


@app.command("add-outfit-scenes")
def add_outfit_scenes(
    ctx: typer.Context,
    outfit_id: str,
    character: str = typer.Option(None, help="Character id (default: the only one)"),
    pose: list[str] = typer.Option(None, "--pose", help="Pose (repeatable; default: two standard poses)"),
    setting: str = typer.Option("", help="Scene setting, e.g. 'sunlit cafe'"),
):
    """Create the pose scenes for an outfit (two standard poses by default)."""
    from .profile import resolve_character

    project, profile = _load_with_profile(ctx)
    outfit = project.find_outfit(outfit_id)

    if character is None:
        if len(project.characters) == 1:
            character = project.characters[0].id
        elif project.characters:
            _fail("Multiple characters — pick one with --character "
                  f"({', '.join(c.id for c in project.characters)})")
        elif profile and profile.main_character:
            character = profile.main_character.id
    if character:
        try:
            resolve_character(project, profile, character)
        except KeyError as exc:
            _fail(str(exc).strip("'\""))

    poses = list(pose or DEFAULT_POSES)
    base = f"{outfit.name}" + (f" in {setting}" if setting else "")
    created = []
    for p in poses:
        scene = project.add_scene(base, character_id=character,
                                  outfit_id=outfit.id, pose=p)
        created.append(scene.id)
    project.save()
    typer.secho(f"Created {', '.join(created)} for {outfit.id}"
                + (f" with {character}" if character else ""),
                fg=typer.colors.GREEN)


@app.command()
def links(ctx: typer.Context, outfit_id: str = typer.Argument(None)):
    """Print a paste-ready shop-links block (pipe to pbcopy)."""
    project = _load(ctx)
    outfits = [project.find_outfit(outfit_id)] if outfit_id else project.outfits
    if not outfits:
        _fail("No outfits yet — add one with 'sceneforge add-outfit'")
    blocks = []
    for outfit in outfits:
        lines = [outfit.name]
        for item in outfit.items:
            lines.append(f"{item.name} — {item.url}" if item.url else item.name)
        blocks.append("\n".join(lines))
    typer.echo("\n\n".join(blocks))


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
    project, profile = _load_with_profile(ctx)
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
            typer.echo(f"[dry-run] {sc.id} x{needed}: "
                       f"{compose_prompt(project, sc, profile=profile)}")
            refs = ops.scene_reference_images(project, sc, profile=profile)
            if refs:
                typer.echo(f"[dry-run] {sc.id} references: "
                           + ", ".join(str(r.relative_to(project.root)) for r in refs))
        return

    ops.run_images(project, todo, model_key, log=typer.echo, profile=profile)
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
    project, profile = _load_with_profile(ctx)
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
                       f"{compose_prompt(project, sc, profile=profile)}")
        return

    failures = ops.run_clips(project, todo, model_key, log=typer.echo,
                             profile=profile)
    if failures:
        _fail(f"{len(failures)} clip(s) failed: {', '.join(failures)}. "
              "Re-run generate-clips to retry just those.")
    typer.secho("All clips done. Next: sceneforge stitch", fg=typer.colors.GREEN)


# ------------------------------------------------------- takes / export


@app.command()
def takes(
    ctx: typer.Context,
    scene_id: str,
    image: int = typer.Option(None, help="1-based image option (default: the selected one)"),
    count: int = typer.Option(3, help="How many takes to generate"),
    model: str = typer.Option(None, help="Video model (see 'sceneforge models video')"),
    prompt: str = typer.Option(None, help="Override the motion prompt for these takes"),
):
    """Generate several clip takes from one scene image; compare, keep, export."""
    project, profile = _load_with_profile(ctx)
    sc = project.find_scene(scene_id)
    index = (image - 1) if image is not None else sc.selected_image
    if index is None:
        _fail(f"{scene_id} has no selected image — run 'sceneforge select' or pass --image N")
    model_key = model or project.settings.video_model
    resolved = config.resolve_model(model_key, "video")
    typer.echo(f"Generating {count} takes with {model_key} "
               f"(~${count * resolved['price']:.2f})")
    try:
        failures = ops.run_takes(project, sc, index, count, model_key,
                                 prompt_override=prompt, log=typer.echo,
                                 profile=profile)
    except ValueError as exc:
        _fail(str(exc))
    if failures:
        _fail(f"{len(failures)} take(s) failed: {', '.join(failures)}")
    typer.secho("Mark keepers with: sceneforge keep SCENE_ID TAKE_N",
                fg=typer.colors.GREEN)


@app.command()
def keep(
    ctx: typer.Context,
    scene_id: str,
    take: int,
    unkeep: bool = typer.Option(False, help="Unmark instead"),
):
    """Mark a take as a keeper (included in export)."""
    project = _load(ctx)
    sc = project.find_scene(scene_id)
    for clip in sc.clips:
        if clip.take == take:
            clip.kept = not unkeep
            project.save()
            state = "kept" if clip.kept else "unmarked"
            typer.secho(f"{scene_id} take {take}: {state}", fg=typer.colors.GREEN)
            return
    valid = ", ".join(str(c.take) for c in sc.clips if c.take) or "(none)"
    _fail(f"No take {take} on {scene_id}. Takes: {valid}")


@app.command()
def export(
    ctx: typer.Context,
    out: Path = typer.Option(None, help="Export directory (default: <project>/export)"),
):
    """Copy kept takes (+ links.txt) into a stable folder for CapCut."""
    project = _load(ctx)
    try:
        manifest = ops.run_export(project, out)
    except ValueError as exc:
        _fail(str(exc))
    for path in manifest:
        typer.echo(f"  {path.name}")
    typer.secho(f"Exported {len(manifest)} clip(s) to {manifest[0].parent}",
                fg=typer.colors.GREEN)


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

    spent = sum(
        artifact.meta.get("cost_usd", 0.0)
        for sc in project.scenes
        for artifact in [*sc.images, *sc.clips]
    )
    if spent:
        typer.echo(f"Self-hosted GPU spend so far: ${spent:.2f} (from artifact metadata)")


# ---------------------------------------------------------------- studio


@app.command()
def studio(
    directory: Path = typer.Option(
        None, "--dir", help="SCENEFORGE_HOME directory (default: ~/SceneForge)"
    ),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
):
    """Launch SceneForge Studio (JSON API + web app)."""
    import uvicorn

    from .profile import home_dir
    from .server import create_app

    home = (directory or home_dir()).resolve()
    home.mkdir(parents=True, exist_ok=True)
    typer.secho(f"SceneForge Studio on http://{host}:{port} (home: {home})",
                fg=typer.colors.GREEN)
    uvicorn.run(create_app(home), host=host, port=port, log_level="warning")


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
