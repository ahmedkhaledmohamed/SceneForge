"""The Studio JSON API (project scope).

Routes operate on project directories under a base dir — same layout the
CLI works with. Long-running generation runs as background jobs (one per
project); the client polls GET .../job. Errors use one shape:
{"error": {"code": ..., "message": ...}} via HTTPException detail dicts.
"""

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from .. import config, ops
from ..project import PROJECT_FILE, ClothingItem, Project
from .jobs import JobManager
from .uploads import save_upload


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def make_router(base: Path) -> APIRouter:
    router = APIRouter()
    jobs = JobManager()

    # ---------------------------------------------------------- helpers

    def root_of(slug: str) -> Path:
        root = (base / slug).resolve()
        if not root.is_relative_to(base) or not (root / PROJECT_FILE).is_file():
            raise _err(404, "not_found", f"No project '{slug}'")
        return root

    def load(slug: str) -> Project:
        return Project.load(root_of(slug))

    def find_or_404(getter, *args):
        try:
            return getter(*args)
        except KeyError as exc:
            raise _err(404, "not_found", str(exc).strip("'\""))

    def project_doc(project: Project, slug: str) -> dict:
        doc = asdict(project)
        doc.pop("root")
        doc["slug"] = slug
        job = jobs.get(slug)
        doc["job"] = job.as_dict() if job else None
        doc["spent_usd"] = round(sum(
            artifact.meta.get("cost_usd", 0.0)
            for sc in project.scenes
            for artifact in [*sc.images, *sc.clips]
        ), 4)
        return doc

    def start_job_or_409(slug: str, name: str, fn) -> dict:
        if not jobs.start(slug, name, fn):
            raise _err(409, "conflict", "A job is already running for this project")
        return {"started": name}

    # ----------------------------------------------------------- models

    @router.get("/models")
    def models():
        return {
            key: {k: v for k, v in model.items()}
            for key, model in config.MODELS.items()
        }

    # --------------------------------------------------------- projects

    @router.get("/projects")
    def list_projects():
        out = []
        for pj in sorted(base.glob(f"*/{PROJECT_FILE}")):
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

    @router.post("/projects", status_code=201)
    def create_project(payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            raise _err(400, "invalid", "Project name is required")
        for kind, key in (("image", "image_model"), ("video", "video_model")):
            if payload.get(key):
                try:
                    config.resolve_model(payload[key], kind)
                except ValueError as exc:
                    raise _err(400, "invalid", str(exc))
        try:
            project = ops.create_project(
                name, base,
                concept=payload.get("concept", ""),
                anchor=payload.get("anchor", ""),
                suffix=payload.get("suffix"),
                aspect=payload.get("aspect", "9:16"),
                image_model=payload.get("image_model"),
                video_model=payload.get("video_model"),
            )
        except (ValueError, FileExistsError) as exc:
            raise _err(400, "invalid", str(exc))
        return project_doc(project, project.root.name)

    @router.get("/projects/{slug}")
    def get_project(slug: str):
        return project_doc(load(slug), slug)

    @router.patch("/projects/{slug}")
    def patch_project(slug: str, payload: dict):
        project = load(slug)
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
        return project_doc(project, slug)

    # ------------------------------------------------------- characters

    @router.post("/projects/{slug}/characters", status_code=201)
    async def add_character(slug: str, name: str = Form(...),
                            description: str = Form(""),
                            files: list[UploadFile] = File(None)):
        project = load(slug)
        character = project.add_character(name, description)
        for file in files or []:
            dest = await save_upload(file, project.character_refs_dir(character))
            character.reference_images.append(str(dest.relative_to(project.root)))
        project.save()
        return asdict(character)

    @router.post("/projects/{slug}/characters/{cid}/refs", status_code=201)
    async def add_character_ref(slug: str, cid: str, files: list[UploadFile]):
        project = load(slug)
        character = find_or_404(project.find_character, cid)
        for file in files:
            dest = await save_upload(file, project.character_refs_dir(character))
            character.reference_images.append(str(dest.relative_to(project.root)))
        project.save()
        return asdict(character)

    # ---------------------------------------------------------- outfits

    @router.post("/projects/{slug}/outfits", status_code=201)
    def add_outfit(slug: str, payload: dict):
        project = load(slug)
        name = (payload.get("name") or "").strip()
        if not name:
            raise _err(400, "invalid", "Outfit name is required")
        outfit = project.add_outfit(name)
        project.save()
        return asdict(outfit)

    @router.post("/projects/{slug}/outfits/{oid}/items", status_code=201)
    async def add_item(slug: str, oid: str, name: str = Form(...),
                       url: str = Form(""), image: UploadFile | None = File(None)):
        project = load(slug)
        outfit = find_or_404(project.find_outfit, oid)
        item = ClothingItem(name=name, url=url or None)
        if image is not None and image.filename:
            dest = await save_upload(image, project.outfit_refs_dir(outfit))
            item.image = str(dest.relative_to(project.root))
        outfit.items.append(item)
        project.save()
        return asdict(outfit)

    @router.delete("/projects/{slug}/outfits/{oid}/items/{index}")
    def delete_item(slug: str, oid: str, index: int):
        project = load(slug)
        outfit = find_or_404(project.find_outfit, oid)
        if not 0 <= index < len(outfit.items):
            raise _err(404, "not_found", f"No item {index} on {oid}")
        outfit.items.pop(index)
        project.save()
        return asdict(outfit)

    @router.get("/projects/{slug}/outfits/{oid}/links", response_class=PlainTextResponse)
    def outfit_links(slug: str, oid: str):
        project = load(slug)
        outfit = find_or_404(project.find_outfit, oid)
        lines = [outfit.name] + [
            f"{item.name} — {item.url}" if item.url else item.name
            for item in outfit.items
        ]
        return "\n".join(lines)

    # ----------------------------------------------------------- scenes

    @router.post("/projects/{slug}/scenes", status_code=201)
    def add_scene(slug: str, payload: dict):
        project = load(slug)
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

    @router.post("/projects/{slug}/scenes/from-outfit", status_code=201)
    def scenes_from_outfit(slug: str, payload: dict):
        from ..cli import DEFAULT_POSES

        project = load(slug)
        outfit = find_or_404(project.find_outfit, payload.get("outfit_id", ""))
        character_id = payload.get("character_id")
        if character_id is None and len(project.characters) == 1:
            character_id = project.characters[0].id
        if character_id:
            find_or_404(project.find_character, character_id)
        setting = payload.get("setting") or ""
        base_desc = outfit.name + (f" in {setting}" if setting else "")
        created = []
        for pose in payload.get("poses") or DEFAULT_POSES:
            scene = project.add_scene(base_desc, character_id=character_id,
                                      outfit_id=outfit.id, pose=pose)
            created.append(asdict(scene))
        project.save()
        return created

    @router.patch("/projects/{slug}/scenes/{sid}")
    def patch_scene(slug: str, sid: str, payload: dict):
        project = load(slug)
        scene = find_or_404(project.find_scene, sid)
        for field_name in ("description", "pose", "style_override",
                           "character_id", "outfit_id"):
            if field_name in payload:
                setattr(scene, field_name, payload[field_name])
        project.save()
        return asdict(scene)

    @router.post("/projects/{slug}/scenes/{sid}/select")
    def select_image(slug: str, sid: str, payload: dict):
        project = load(slug)
        scene = find_or_404(project.find_scene, sid)
        index = payload.get("image_index")
        if not isinstance(index, int) or not 0 <= index < len(scene.images):
            raise _err(400, "invalid",
                       f"{sid} has {len(scene.images)} image option(s)")
        scene.selected_image = index
        project.save()
        return asdict(scene)

    # ------------------------------------------------------- generation

    @router.post("/projects/{slug}/generate-images", status_code=202)
    def generate_images(slug: str, payload: dict):
        project = load(slug)
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
            slug, f"generate images ({model_key})",
            lambda log: ops.run_images(project, todo, model_key, log=log),
        )

    @router.post("/projects/{slug}/scenes/{sid}/regenerate-image", status_code=202)
    def regenerate_image(slug: str, sid: str, payload: dict):
        project = load(slug)
        scene = find_or_404(project.find_scene, sid)
        model_key = payload.get("model") or project.settings.image_model
        options = payload.get("options") or 1
        todo = ops.plan_images([scene], options, force=True)
        return start_job_or_409(
            slug, f"regenerate {sid} ({model_key})",
            lambda log: ops.run_images(project, todo, model_key, log=log),
        )

    @router.post("/projects/{slug}/scenes/{sid}/takes", status_code=202)
    def generate_takes(slug: str, sid: str, payload: dict):
        project = load(slug)
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
            failures = ops.run_takes(project, scene, image_index, count,
                                     model_key,
                                     prompt_override=payload.get("prompt_override"),
                                     log=log)
            if failures:
                raise RuntimeError(f"{len(failures)} take(s) failed")

        return start_job_or_409(slug, f"{count} takes for {sid} ({model_key})", job)

    @router.post("/projects/{slug}/scenes/{sid}/clips/{index}/keep")
    def keep_clip(slug: str, sid: str, index: int, payload: dict):
        project = load(slug)
        scene = find_or_404(project.find_scene, sid)
        if not 0 <= index < len(scene.clips):
            raise _err(404, "not_found", f"No clip {index} on {sid}")
        scene.clips[index].kept = bool(payload.get("kept", True))
        project.save()
        return asdict(scene.clips[index])

    @router.get("/projects/{slug}/job")
    def job_status(slug: str):
        root_of(slug)
        job = jobs.get(slug)
        return job.as_dict() if job else {"name": None, "status": "idle", "log": []}

    # --------------------------------------------------- export / stitch

    @router.post("/projects/{slug}/export")
    def export(slug: str):
        project = load(slug)
        try:
            manifest = ops.run_export(project)
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        return {"dir": str(manifest[0].parent),
                "files": [p.name for p in manifest]}

    @router.get("/projects/{slug}/export.zip")
    def export_zip(slug: str):
        project = load(slug)
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

    @router.post("/projects/{slug}/stitch", status_code=202)
    def stitch(slug: str):
        project = load(slug)

        def job(log):
            out_path, duration = ops.run_stitch(project)
            log(f"final video: {out_path.name} ({duration:.1f}s)")

        return start_job_or_409(slug, "stitch final video", job)

    # ---------------------------------------------------------- history

    @router.get("/projects/{slug}/history")
    def history(slug: str, type: str | None = None, outfit: str | None = None,
                model: str | None = None):
        project = load(slug)
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

    @router.get("/projects/{slug}/media/{relpath:path}")
    def media(slug: str, relpath: str):
        root = root_of(slug)
        target = (root / relpath).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise _err(404, "not_found", "Not found")
        return FileResponse(target)

    return router
