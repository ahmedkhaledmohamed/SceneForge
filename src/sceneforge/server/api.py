"""The Studio JSON API.

Everything is profile-scoped: /profiles/{prof}/projects/{slug}/...
A profile owns global context (characters, style defaults, seeds);
projects live under it and inherit that context. Long-running
generation runs as background jobs (one per project); the client polls
GET .../job. Errors: {"error": {"code": ..., "message": ...}}.
"""

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from .. import config, ops
from ..profile import PROFILE_FILE, Profile, create_profile
from ..project import PROJECT_FILE, ClothingItem, Project
from .jobs import JobManager
from .uploads import save_upload


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def make_router(home: Path) -> APIRouter:
    router = APIRouter()
    jobs = JobManager()

    # ---------------------------------------------------------- helpers

    def profile_root(prof: str) -> Path:
        root = (home / prof).resolve()
        if not root.is_relative_to(home) or not (root / PROFILE_FILE).is_file():
            raise _err(404, "not_found", f"No profile '{prof}'")
        return root

    def load_profile(prof: str) -> Profile:
        return Profile.load(profile_root(prof))

    def project_root(prof: str, slug: str) -> Path:
        base = profile_root(prof) / "projects"
        root = (base / slug).resolve()
        if not root.is_relative_to(base) or not (root / PROJECT_FILE).is_file():
            raise _err(404, "not_found", f"No project '{slug}' in '{prof}'")
        return root

    def load_project(prof: str, slug: str) -> Project:
        return Project.load(project_root(prof, slug))

    def find_or_404(getter, *args):
        try:
            return getter(*args)
        except KeyError as exc:
            raise _err(404, "not_found", str(exc).strip("'\""))

    def job_key(prof: str, slug: str) -> str:
        return f"{prof}/{slug}"

    def project_doc(project: Project, prof: str, slug: str,
                    profile: Profile | None = None) -> dict:
        from ..prompts import compose_prompt

        doc = asdict(project)
        doc.pop("root")
        doc["slug"] = slug
        doc["profile"] = prof
        for scene_doc, scene in zip(doc["scenes"], project.scenes):
            try:
                scene_doc["prompt_preview"] = compose_prompt(
                    project, scene, profile=profile)
            except Exception:
                scene_doc["prompt_preview"] = None
        job = jobs.get(job_key(prof, slug))
        doc["job"] = job.as_dict() if job else None
        doc["spent_usd"] = round(sum(
            artifact.meta.get("cost_usd", 0.0)
            for sc in project.scenes
            for artifact in [*sc.images, *sc.clips]
        ), 4)
        doc["profile_characters"] = [asdict(c) for c in profile.characters] if profile else []
        return doc

    def start_job_or_409(prof: str, slug: str, name: str, fn) -> dict:
        if not jobs.start(job_key(prof, slug), name, fn):
            raise _err(409, "conflict", "A job is already running for this project")
        return {"started": name}

    # ----------------------------------------------------------- models

    @router.get("/models")
    def models():
        return dict(config.MODELS)

    # --------------------------------------------------------- profiles

    @router.get("/profiles")
    def list_profiles():
        out = []
        for pf in sorted(home.glob(f"*/{PROFILE_FILE}")):
            profile = Profile.load(pf.parent)
            out.append({
                "slug": pf.parent.name,
                "name": profile.name,
                "characters": len(profile.characters),
                "seeds": len(profile.seeds),
                "projects": len(list(profile.projects_dir.glob(f"*/{PROJECT_FILE}"))),
            })
        return out

    @router.post("/profiles", status_code=201)
    def new_profile(payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            raise _err(400, "invalid", "Profile name is required")
        try:
            profile = create_profile(name, home)
        except (ValueError, FileExistsError) as exc:
            raise _err(400, "invalid", str(exc))
        return {"slug": profile.root.name, "name": profile.name}

    @router.get("/profiles/{prof}")
    def get_profile(prof: str):
        profile = load_profile(prof)
        doc = asdict(profile)
        doc.pop("root")
        doc["slug"] = prof
        return doc

    @router.patch("/profiles/{prof}")
    def patch_profile(prof: str, payload: dict):
        profile = load_profile(prof)
        for field_name in ("anchor", "suffix", "mood", "palette", "lighting"):
            if field_name in payload:
                setattr(profile.style, field_name, payload[field_name])
        for field_name in ("image_model", "final_image_model", "video_model",
                           "aspect", "image_options"):
            if field_name in payload:
                setattr(profile.defaults, field_name, payload[field_name])
        profile.save()
        return get_profile(prof)

    @router.post("/profiles/{prof}/characters", status_code=201)
    async def add_profile_character(prof: str, name: str = Form(...),
                                    description: str = Form(""),
                                    main: bool = Form(False),
                                    files: list[UploadFile] = File(None)):
        profile = load_profile(prof)
        character = profile.add_character(name, description, main=main)
        for file in files or []:
            dest = await save_upload(file, profile.character_refs_dir(character))
            character.reference_images.append(str(dest.relative_to(profile.root)))
        profile.save()
        return asdict(character)

    @router.post("/profiles/{prof}/characters/{cid}/refs", status_code=201)
    async def add_profile_character_ref(prof: str, cid: str,
                                        files: list[UploadFile] = File(...)):
        profile = load_profile(prof)
        character = find_or_404(profile.find_character, cid)
        for file in files:
            dest = await save_upload(file, profile.character_refs_dir(character))
            character.reference_images.append(str(dest.relative_to(profile.root)))
        profile.save()
        return asdict(character)

    @router.delete("/profiles/{prof}/characters/{cid}")
    def delete_profile_character(prof: str, cid: str):
        profile = load_profile(prof)
        character = find_or_404(profile.find_character, cid)
        profile.characters.remove(character)
        profile.save()
        return {"deleted": cid}

    @router.post("/profiles/{prof}/seeds", status_code=201)
    async def add_seed(prof: str, kind: str = Form("note"),
                       text: str = Form(""), tags: str = Form(""),
                       file: UploadFile | None = File(None)):
        profile = load_profile(prof)
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if file is not None and file.filename:
            dest = await save_upload(file, profile.seeds_dir, kinds=("image", "video"))
            kind = "clip" if dest.suffix == ".mp4" else "image"
            seed = profile.add_seed(kind, file=str(dest.relative_to(profile.root)),
                                    text=text or None, tags=tag_list)
        elif text.strip():
            seed = profile.add_seed("note", text=text.strip(), tags=tag_list)
        else:
            raise _err(400, "invalid", "A seed needs a file or text")
        profile.save()
        return asdict(seed)

    @router.get("/profiles/{prof}/media/{relpath:path}")
    def profile_media(prof: str, relpath: str):
        root = profile_root(prof)
        target = (root / relpath).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise _err(404, "not_found", "Not found")
        return FileResponse(target)

    # --------------------------------------------------------- projects

    @router.get("/profiles/{prof}/projects")
    def list_projects(prof: str):
        profile = load_profile(prof)
        out = []
        for pj in sorted(profile.projects_dir.glob(f"*/{PROJECT_FILE}")):
            slug = pj.parent.name
            p = Project.load(pj.parent)
            out.append({
                "slug": slug,
                "name": p.name,
                "concept": p.concept,
                "scenes": len(p.scenes),
                "outfits": len(p.outfits),
                "clips": sum(1 for sc in p.scenes for c in sc.clips
                             if c.status == "completed"),
                "kept": sum(1 for sc in p.scenes for c in sc.clips if c.kept),
            })
        return out

    @router.post("/profiles/{prof}/projects", status_code=201)
    def new_project(prof: str, payload: dict):
        profile = load_profile(prof)
        name = (payload.get("name") or "").strip()
        if not name:
            raise _err(400, "invalid", "Project name is required")
        try:
            project = ops.create_project(
                name, profile.projects_dir,
                concept=payload.get("concept", ""),
                anchor=payload.get("anchor") or profile.style.anchor,
                suffix=profile.style.suffix or None,
                aspect=payload.get("aspect") or profile.defaults.aspect,
                image_model=payload.get("image_model") or profile.defaults.image_model,
                video_model=payload.get("video_model") or profile.defaults.video_model,
            )
            project.settings.image_options = profile.defaults.image_options
            project.style.reference_image = None
            project.save()
        except (ValueError, FileExistsError) as exc:
            raise _err(400, "invalid", str(exc))
        return project_doc(project, prof, project.root.name, profile=profile)

    @router.get("/profiles/{prof}/projects/{slug}")
    def get_project(prof: str, slug: str):
        profile = load_profile(prof)
        return project_doc(load_project(prof, slug), prof, slug, profile=profile)

    @router.patch("/profiles/{prof}/projects/{slug}")
    def patch_project(prof: str, slug: str, payload: dict):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        if "concept" in payload:
            project.concept = payload["concept"]
        for field_name in ("anchor", "suffix", "mood", "palette", "lighting"):
            if field_name in payload:
                setattr(project.style, field_name, payload[field_name])
        for field_name in ("image_model", "video_model", "image_options",
                           "clip_speed", "crossfade"):
            if field_name in payload:
                setattr(project.settings, field_name, payload[field_name])
        project.save()
        return project_doc(project, prof, slug, profile=profile)

    @router.delete("/profiles/{prof}/projects/{slug}")
    def delete_project(prof: str, slug: str):
        import shutil
        root = project_root(prof, slug)
        shutil.rmtree(root)
        return {"deleted": slug}

    @router.post("/profiles/{prof}/projects/{slug}/duplicate", status_code=201)
    def duplicate_project(prof: str, slug: str, payload: dict):
        profile = load_profile(prof)
        source = load_project(prof, slug)
        new_name = (payload.get("name") or f"{source.name} copy").strip()
        try:
            copy = ops.create_project(
                new_name, profile.projects_dir,
                concept=source.concept,
                anchor=source.style.anchor,
                suffix=source.style.suffix or None,
                aspect=source.settings.aspect,
                image_model=source.settings.image_model,
                video_model=source.settings.video_model,
            )
            copy.settings.image_options = source.settings.image_options
            for outfit in source.outfits:
                o = copy.add_outfit(outfit.name)
                o.items = [ClothingItem(name=i.name, url=i.url, image=i.image)
                           for i in outfit.items]
            for scene in source.scenes:
                copy.add_scene(
                    scene.description,
                    character_id=scene.character_id,
                    outfit_id=scene.outfit_id,
                    pose=scene.pose,
                )
            copy.save()
        except (ValueError, FileExistsError) as exc:
            raise _err(400, "invalid", str(exc))
        return project_doc(copy, prof, copy.root.name, profile=profile)

    # ---------------------------------------- project-level characters

    @router.post("/profiles/{prof}/projects/{slug}/characters", status_code=201)
    async def add_character(prof: str, slug: str, name: str = Form(...),
                            description: str = Form(""),
                            files: list[UploadFile] = File(None)):
        project = load_project(prof, slug)
        character = project.add_character(name, description)
        for file in files or []:
            dest = await save_upload(file, project.character_refs_dir(character))
            character.reference_images.append(str(dest.relative_to(project.root)))
        project.save()
        return asdict(character)

    # ---------------------------------------------------------- outfits

    @router.post("/profiles/{prof}/projects/{slug}/outfits", status_code=201)
    def add_outfit(prof: str, slug: str, payload: dict):
        project = load_project(prof, slug)
        name = (payload.get("name") or "").strip()
        if not name:
            raise _err(400, "invalid", "Outfit name is required")
        outfit = project.add_outfit(name)
        project.save()
        return asdict(outfit)

    @router.post("/profiles/{prof}/projects/{slug}/outfits/{oid}/items",
                 status_code=201)
    async def add_item(prof: str, slug: str, oid: str, name: str = Form(...),
                       url: str = Form(""),
                       image: UploadFile | None = File(None)):
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, oid)
        item = ClothingItem(name=name, url=url or None)
        if image is not None and image.filename:
            dest = await save_upload(image, project.outfit_refs_dir(outfit))
            item.image = str(dest.relative_to(project.root))
        outfit.items.append(item)
        project.save()
        return asdict(outfit)

    @router.delete("/profiles/{prof}/projects/{slug}/outfits/{oid}")
    def delete_outfit(prof: str, slug: str, oid: str):
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, oid)
        project.outfits.remove(outfit)
        project.save()
        return {"deleted": oid}

    @router.delete("/profiles/{prof}/projects/{slug}/outfits/{oid}/items/{index}")
    def delete_item(prof: str, slug: str, oid: str, index: int):
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, oid)
        if not 0 <= index < len(outfit.items):
            raise _err(404, "not_found", f"No item {index} on {oid}")
        outfit.items.pop(index)
        project.save()
        return asdict(outfit)

    @router.get("/profiles/{prof}/projects/{slug}/outfits/{oid}/links",
                response_class=PlainTextResponse)
    def outfit_links(prof: str, slug: str, oid: str):
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, oid)
        lines = [outfit.name] + [
            f"{item.name} — {item.url}" if item.url else item.name
            for item in outfit.items
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------- scenes

    @router.post("/profiles/{prof}/projects/{slug}/brainstorm")
    def brainstorm(prof: str, slug: str, payload: dict):
        from ..breakdown import generate_scenes
        project = load_project(prof, slug)
        concept = payload.get("concept") or project.concept
        anchor = payload.get("anchor") or project.style.anchor
        count = int(payload.get("count", 6))
        if not concept:
            raise _err(400, "invalid", "Project has no concept to brainstorm from")
        descriptions = generate_scenes(concept, anchor, count)
        return {"descriptions": descriptions}

    @router.post("/profiles/{prof}/projects/{slug}/scenes/bulk", status_code=201)
    def add_scenes_bulk(prof: str, slug: str, payload: dict):
        project = load_project(prof, slug)
        descriptions = payload.get("descriptions", [])
        if not descriptions:
            raise _err(400, "invalid", "No scene descriptions provided")
        character_id = payload.get("character_id")
        created = []
        for desc in descriptions:
            if isinstance(desc, str) and desc.strip():
                scene = project.add_scene(desc.strip(), character_id=character_id)
                created.append(asdict(scene))
        project.save()
        return created

    @router.post("/profiles/{prof}/projects/{slug}/scenes", status_code=201)
    def add_scene(prof: str, slug: str, payload: dict):
        project = load_project(prof, slug)
        description = (payload.get("description") or "").strip()
        if not description:
            raise _err(400, "invalid", "Scene description is required")
        scene = project.add_scene(
            description,
            pose=payload.get("pose"),
            character_id=payload.get("character_id"),
            outfit_id=payload.get("outfit_id"),
        )
        project.save()
        return asdict(scene)

    @router.post("/profiles/{prof}/projects/{slug}/scenes/from-outfit",
                 status_code=201)
    def scenes_from_outfit(prof: str, slug: str, payload: dict):
        from ..cli import DEFAULT_POSES
        from ..profile import resolve_character

        profile = load_profile(prof)
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, payload.get("outfit_id", ""))
        character_id = payload.get("character_id")
        if character_id is None:
            if len(project.characters) == 1:
                character_id = project.characters[0].id
            elif profile.main_character:
                character_id = profile.main_character.id
        if character_id:
            find_or_404(resolve_character, project, profile, character_id)
        setting = payload.get("setting") or ""
        base_desc = outfit.name + (f" in {setting}" if setting else "")
        created = []
        for pose in payload.get("poses") or DEFAULT_POSES:
            scene = project.add_scene(base_desc, character_id=character_id,
                                      outfit_id=outfit.id, pose=pose)
            created.append(asdict(scene))
        project.save()
        return created

    @router.post("/profiles/{prof}/projects/{slug}/outfits/{oid}/process",
                 status_code=202)
    def process_outfit(prof: str, slug: str, oid: str, payload: dict):
        """One-click: create pose scenes + generate images for an outfit."""
        from ..cli import DEFAULT_POSES
        from ..profile import resolve_character

        profile = load_profile(prof)
        project = load_project(prof, slug)
        outfit = find_or_404(project.find_outfit, oid)
        model_key = payload.get("model") or project.settings.image_model
        try:
            config.resolve_model(model_key, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))

        character_id = payload.get("character_id")
        if character_id is None:
            if len(project.characters) == 1:
                character_id = project.characters[0].id
            elif profile.main_character:
                character_id = profile.main_character.id
        if character_id:
            find_or_404(resolve_character, project, profile, character_id)

        existing = [s for s in project.scenes if s.outfit_id == outfit.id]
        if not existing:
            setting = payload.get("setting") or ""
            base_desc = outfit.name + (f" in {setting}" if setting else "")
            for pose in payload.get("poses") or DEFAULT_POSES:
                project.add_scene(base_desc, character_id=character_id,
                                  outfit_id=outfit.id, pose=pose)
            project.save()

        scenes = [s for s in project.scenes if s.outfit_id == outfit.id]
        options = payload.get("options") or project.settings.image_options
        todo = ops.plan_images(scenes, options, force=False)
        if not todo:
            return {"started": None, "note": "scenes already have images"}

        def job(log):
            ops.run_images(project, todo, model_key, log=log, profile=profile)
            for sc in scenes:
                if sc.selected_image is None and sc.images:
                    sc.selected_image = 0
                    log(f"{sc.id}: auto-selected opt-1")
            project.save()

        return start_job_or_409(
            prof, slug, f"process {outfit.name} ({model_key})", job)

    @router.delete("/profiles/{prof}/projects/{slug}/scenes/{sid}")
    def delete_scene(prof: str, slug: str, sid: str):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        project.scenes.remove(scene)
        project.save()
        return {"deleted": sid}

    @router.put("/profiles/{prof}/projects/{slug}/scenes/reorder")
    def reorder_scenes(prof: str, slug: str, payload: dict):
        project = load_project(prof, slug)
        order = payload.get("scene_ids", [])
        by_id = {s.id: s for s in project.scenes}
        if set(order) != set(by_id):
            raise _err(400, "invalid", "scene_ids must contain all scene IDs exactly once")
        project.scenes = [by_id[sid] for sid in order]
        project.save()
        return {"order": order}

    @router.patch("/profiles/{prof}/projects/{slug}/scenes/{sid}")
    def patch_scene(prof: str, slug: str, sid: str, payload: dict):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        for field_name in ("description", "pose", "style_override",
                           "character_id", "outfit_id"):
            if field_name in payload:
                setattr(scene, field_name, payload[field_name])
        project.save()
        return asdict(scene)

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/select")
    def select_image(prof: str, slug: str, sid: str, payload: dict):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        index = payload.get("image_index")
        if not isinstance(index, int) or not 0 <= index < len(scene.images):
            raise _err(400, "invalid",
                       f"{sid} has {len(scene.images)} image option(s)")
        scene.selected_image = index
        project.save()
        return asdict(scene)

    # ---------------------------------------------------------- import

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/import-image",
                 status_code=201)
    async def import_image(prof: str, slug: str, sid: str,
                           file: UploadFile = File(...)):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        dest = await save_upload(file, project.images_dir(scene))
        from ..project import ImageArtifact
        scene.images.append(ImageArtifact(
            file=str(dest.relative_to(project.root)),
            prompt="(imported)",
            model="import",
            meta={"imported": True},
        ))
        project.save()
        return project_doc(load_project(prof, slug), prof, slug,
                           profile=load_profile(prof))

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/import-clip",
                 status_code=201)
    async def import_clip(prof: str, slug: str, sid: str,
                          file: UploadFile = File(...)):
        from ..project import ClipArtifact
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        dest = await save_upload(file, project.clips_dir / scene.id,
                                 kinds=("video",))
        take_num = max((c.take for c in scene.clips if c.take), default=0) + 1
        scene.clips.append(ClipArtifact(
            file=str(dest.relative_to(project.root)),
            prompt="(imported)",
            source_image=None,
            model="import",
            status="completed",
            meta={"imported": True},
            take=take_num,
        ))
        project.save()
        return project_doc(load_project(prof, slug), prof, slug,
                           profile=load_profile(prof))

    # ------------------------------------------------------- generation

    @router.post("/profiles/{prof}/projects/{slug}/generate-images",
                 status_code=202)
    def generate_images(prof: str, slug: str, payload: dict):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        model_key = payload.get("model") or project.settings.image_model
        try:
            config.resolve_model(model_key, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        scene_ids = payload.get("scene_ids")
        scenes = ([find_or_404(project.find_scene, sid) for sid in scene_ids]
                  if scene_ids else project.scenes)
        options = payload.get("options") or project.settings.image_options
        todo = ops.plan_images(scenes, options, force=bool(payload.get("force")))
        if not todo:
            return {"started": None, "note": "nothing to generate"}
        return start_job_or_409(
            prof, slug, f"generate images ({model_key})",
            lambda log: ops.run_images(project, todo, model_key, log=log,
                                       profile=profile),
        )

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/regenerate-image",
                 status_code=202)
    def regenerate_image(prof: str, slug: str, sid: str, payload: dict):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        model_key = payload.get("model") or project.settings.image_model
        options = payload.get("options") or 1
        todo = ops.plan_images([scene], options, force=True)
        return start_job_or_409(
            prof, slug, f"regenerate {sid} ({model_key})",
            lambda log: ops.run_images(project, todo, model_key, log=log,
                                       profile=profile),
        )

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/takes",
                 status_code=202)
    def generate_takes(prof: str, slug: str, sid: str, payload: dict):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        model_key = payload.get("model") or project.settings.video_model
        try:
            config.resolve_model(model_key, "video")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        image_index = payload.get("image_index", scene.selected_image)
        if image_index is None:
            raise _err(400, "invalid", f"{sid} has no selected image")
        count = int(payload.get("count", 3))

        def job(log):
            failures = ops.run_takes(
                project, scene, image_index, count, model_key,
                prompt_override=payload.get("prompt_override"),
                log=log, profile=profile,
            )
            if failures:
                raise RuntimeError(f"{len(failures)} take(s) failed")

        return start_job_or_409(prof, slug,
                                f"{count} takes for {sid} ({model_key})", job)

    @router.post("/profiles/{prof}/projects/{slug}/generate-takes-all",
                 status_code=202)
    def generate_takes_all(prof: str, slug: str, payload: dict):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        model_key = payload.get("model") or project.settings.video_model
        try:
            config.resolve_model(model_key, "video")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        count = int(payload.get("count", 2))
        ready = [sc for sc in project.scenes if sc.selected_image is not None]
        if not ready:
            raise _err(400, "invalid", "No scenes have a selected image")

        def job(log):
            total_failures = []
            for sc in ready:
                log(f"--- {sc.id} ---")
                failures = ops.run_takes(
                    project, sc, sc.selected_image, count, model_key,
                    log=log, profile=profile,
                )
                total_failures.extend(failures)
            if total_failures:
                raise RuntimeError(
                    f"{len(total_failures)} take(s) failed: "
                    + ", ".join(total_failures))

        return start_job_or_409(
            prof, slug,
            f"{count} takes x {len(ready)} scenes ({model_key})", job)

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/clips/{index}/keep")
    def keep_clip(prof: str, slug: str, sid: str, index: int, payload: dict):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        if not 0 <= index < len(scene.clips):
            raise _err(404, "not_found", f"No clip {index} on {sid}")
        scene.clips[index].kept = bool(payload.get("kept", True))
        project.save()
        return asdict(scene.clips[index])

    @router.get("/profiles/{prof}/projects/{slug}/job")
    def job_status(prof: str, slug: str):
        project_root(prof, slug)
        job = jobs.get(job_key(prof, slug))
        return job.as_dict() if job else {"name": None, "status": "idle", "log": []}

    # --------------------------------------------------- export / stitch

    @router.post("/profiles/{prof}/projects/{slug}/export")
    def export(prof: str, slug: str):
        project = load_project(prof, slug)
        try:
            manifest = ops.run_export(project)
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        return {"dir": str(manifest[0].parent),
                "files": [p.name for p in manifest]}

    @router.get("/profiles/{prof}/projects/{slug}/export.zip")
    def export_zip(prof: str, slug: str):
        project = load_project(prof, slug)
        try:
            manifest = ops.run_export(project)
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for path in manifest:
                zf.write(path, path.name)
            links = manifest[0].parent / "links.txt"
            if links.is_file():
                zf.write(links, "links.txt")
        return Response(
            buffer.getvalue(), media_type="application/zip",
            headers={"Content-Disposition":
                     f"attachment; filename={slug}-export.zip"},
        )

    @router.post("/profiles/{prof}/projects/{slug}/stitch", status_code=202)
    def stitch(prof: str, slug: str):
        project = load_project(prof, slug)

        def job(log):
            out_path, duration = ops.run_stitch(project)
            log(f"final video: {out_path.name} ({duration:.1f}s)")

        return start_job_or_409(prof, slug, "stitch final video", job)

    # ---------------------------------------------------------- history

    @router.get("/profiles/{prof}/projects/{slug}/history")
    def history(prof: str, slug: str, type: str | None = None,
                outfit: str | None = None, model: str | None = None):
        project = load_project(prof, slug)
        rows = []
        for sc in project.scenes:
            for img in sc.images:
                rows.append({"type": "image", "scene_id": sc.id,
                             "outfit_id": sc.outfit_id, "file": img.file,
                             "prompt": img.prompt, "model": img.model,
                             "cost_usd": img.meta.get("cost_usd"),
                             "references": img.meta.get("reference_images", []),
                             "created_at": img.created_at})
            for clip in sc.clips:
                rows.append({"type": "clip", "scene_id": sc.id,
                             "outfit_id": sc.outfit_id, "file": clip.file,
                             "prompt": clip.prompt, "model": clip.model,
                             "status": clip.status, "take": clip.take,
                             "kept": clip.kept,
                             "cost_usd": clip.meta.get("cost_usd"),
                             "created_at": clip.created_at})
        if type:
            rows = [r for r in rows if r["type"] == type]
        if outfit:
            rows = [r for r in rows if r["outfit_id"] == outfit]
        if model:
            rows = [r for r in rows if r["model"] == model]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows

    # ------------------------------------------------------------ media

    @router.get("/profiles/{prof}/projects/{slug}/media/{relpath:path}")
    def media(prof: str, slug: str, relpath: str):
        root = project_root(prof, slug)
        target = (root / relpath).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise _err(404, "not_found", "Not found")
        return FileResponse(target)

    return router
