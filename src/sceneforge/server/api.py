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

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

import secrets

from .. import config, ops
from ..profile import PROFILE_FILE, Profile, create_profile
from ..project import PROJECT_FILE, Project, SceneRef
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

    # sessions: {token: profile_slug}
    _sessions: dict[str, str] = {}

    def load_profile(prof: str) -> Profile:
        return Profile.load(profile_root(prof))

    def require_auth(request: Request, prof: str) -> None:
        profile = load_profile(prof)
        if not profile.has_password:
            return
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not token or _sessions.get(token) != prof:
            raise _err(401, "unauthorized", "Login required for this profile")

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
        profile = load_profile(prof)

        def wrapped(log):
            config.set_active_profile(profile)
            try:
                return fn(log)
            finally:
                config.set_active_profile(None)

        if not jobs.start(job_key(prof, slug), name, wrapped):
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
        doc.pop("password_hash", None)
        doc.pop("password_salt", None)
        doc.pop("keys", None)
        doc["slug"] = prof
        doc["has_password"] = profile.has_password
        doc["has_keys"] = bool(profile.keys.together)
        return doc

    @router.delete("/profiles/{prof}")
    def delete_profile(prof: str, request: Request):
        import shutil
        require_auth(request, prof)
        root = profile_root(prof)
        shutil.rmtree(root)
        return {"deleted": prof}

    @router.post("/profiles/{prof}/login")
    def login(prof: str, payload: dict):
        profile = load_profile(prof)
        password = payload.get("password", "")
        if not profile.check_password(password):
            raise _err(401, "unauthorized", "Wrong password")
        token = secrets.token_urlsafe(32)
        _sessions[token] = prof
        return {"token": token}

    @router.post("/profiles/{prof}/logout")
    def logout(request: Request):
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        _sessions.pop(token, None)
        return {"ok": True}

    @router.post("/profiles/{prof}/set-password")
    def set_password(prof: str, request: Request, payload: dict):
        profile = load_profile(prof)
        if profile.has_password:
            require_auth(request, prof)
        password = (payload.get("password") or "").strip()
        if not password:
            raise _err(400, "invalid", "Password is required")
        profile.set_password(password)
        profile.save()
        token = secrets.token_urlsafe(32)
        _sessions[token] = prof
        return {"token": token}

    @router.get("/profiles/{prof}/settings")
    def get_settings(prof: str, request: Request):
        require_auth(request, prof)
        profile = load_profile(prof)

        def mask(s: str) -> str:
            if len(s) <= 8:
                return "***" if s else ""
            return s[:4] + "..." + s[-4:]

        return {
            "keys": {
                "together": mask(profile.keys.together),
                "runpod_api": mask(profile.keys.runpod_api),
                "runpod_endpoint": profile.keys.runpod_endpoint,
            },
            "has_together": bool(profile.keys.together),
            "has_runpod": bool(profile.keys.runpod_api),
        }

    @router.get("/profiles/{prof}/balance")
    def get_balance(prof: str, request: Request):
        require_auth(request, prof)
        profile = load_profile(prof)
        result: dict = {}

        # Together: no public balance API — check if key works
        together_key = profile.keys.together or os.environ.get("TOGETHER_API_KEY")
        if together_key:
            try:
                import urllib.request
                req = urllib.request.Request(
                    "https://api.together.ai/v1/models",
                    headers={"Authorization": f"Bearer {together_key}",
                             "User-Agent": "SceneForge/1.0"},
                )
                urllib.request.urlopen(req, timeout=5)
                result["together"] = {"status": "active", "dashboard": "https://api.together.ai/settings/billing"}
            except Exception:
                result["together"] = {"status": "invalid_key"}
        else:
            result["together"] = {"status": "not_configured"}

        # RunPod: GraphQL balance query
        runpod_key = profile.keys.runpod_api or os.environ.get("RUNPOD_API_KEY")
        if runpod_key:
            try:
                import json as _json
                import urllib.request
                req = urllib.request.Request(
                    "https://api.runpod.io/graphql",
                    data=_json.dumps({"query": "{ myself { id creditBalance currentSpendPerHr } }"}).encode(),
                    headers={"Authorization": f"Bearer {runpod_key}",
                             "Content-Type": "application/json"},
                )
                resp = _json.loads(urllib.request.urlopen(req, timeout=5).read())
                me = resp.get("data", {}).get("myself", {})
                result["runpod"] = {
                    "status": "active",
                    "credit_balance": me.get("creditBalance"),
                    "spend_per_hr": me.get("currentSpendPerHr"),
                }
            except Exception:
                has_endpoint = bool(profile.keys.runpod_endpoint or os.environ.get("RUNPOD_ENDPOINT_ID"))
                result["runpod"] = {"status": "no endpoint configured" if not has_endpoint else "error"}
        else:
            result["runpod"] = {"status": "not_configured"}

        return result

    @router.patch("/profiles/{prof}/settings")
    def patch_settings(prof: str, request: Request, payload: dict):
        require_auth(request, prof)
        profile = load_profile(prof)
        keys = payload.get("keys", {})
        if "together" in keys:
            profile.keys.together = keys["together"]
        if "runpod_api" in keys:
            profile.keys.runpod_api = keys["runpod_api"]
        if "runpod_endpoint" in keys:
            profile.keys.runpod_endpoint = keys["runpod_endpoint"]
        profile.save()
        return get_settings(prof, request)

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
                "refs": sum(len(sc.refs) for sc in p.scenes),
                "clips": sum(1 for sc in p.scenes for c in sc.clips
                             if c.status == "completed"),
                "kept": sum(1 for sc in p.scenes for c in sc.clips if c.kept),
            })
        return out

    @router.get("/profiles/{prof}/stats")
    def profile_stats(prof: str):
        profile = load_profile(prof)
        projects = 0
        scenes = 0
        images = 0
        clips_completed = 0
        clips_kept = 0
        spent = 0.0
        models_used: dict[str, int] = {}
        for pj in profile.projects_dir.glob(f"*/{PROJECT_FILE}"):
            p = Project.load(pj.parent)
            projects += 1
            scenes += len(p.scenes)
            for sc in p.scenes:
                images += len(sc.images)
                for c in sc.clips:
                    if c.status == "completed":
                        clips_completed += 1
                    if c.kept:
                        clips_kept += 1
                for a in [*sc.images, *sc.clips]:
                    spent += a.meta.get("cost_usd", 0.0)
                    m = a.model
                    models_used[m] = models_used.get(m, 0) + 1
        return {
            "projects": projects,
            "scenes": scenes,
            "images": images,
            "clips_completed": clips_completed,
            "clips_kept": clips_kept,
            "spent_usd": round(spent, 4),
            "models_used": models_used,
        }

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
        if "notes" in payload:
            project.notes = payload["notes"]
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
            for scene in source.scenes:
                s = copy.add_scene(
                    scene.description,
                    character_id=scene.character_id,
                    pose=scene.pose,
                )
                s.refs = [SceneRef(file=r.file, role=r.role, label=r.label, url=r.url)
                          for r in scene.refs]
            copy.save()
        except (ValueError, FileExistsError) as exc:
            raise _err(400, "invalid", str(exc))
        return project_doc(copy, prof, copy.root.name, profile=profile)

    # --------------------------------------------- project references

    @router.post("/profiles/{prof}/projects/{slug}/refs", status_code=201)
    async def add_project_ref(prof: str, slug: str,
                              role: str = Form("style"),
                              label: str = Form(""),
                              file: UploadFile = File(...)):
        from ..project import ReferenceImage
        project = load_project(prof, slug)
        dest = await save_upload(file, project.root / "refs" / role)
        ref = ReferenceImage(
            file=str(dest.relative_to(project.root)),
            role=role,
            label=label or dest.stem,
        )
        project.refs.append(ref)
        project.save()
        return asdict(ref)

    @router.delete("/profiles/{prof}/projects/{slug}/refs/{index}")
    def delete_project_ref(prof: str, slug: str, index: int):
        project = load_project(prof, slug)
        if not 0 <= index < len(project.refs):
            raise _err(404, "not_found", f"No ref {index}")
        project.refs.pop(index)
        project.save()
        return {"deleted": index}

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
        )
        project.save()
        return asdict(scene)

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
                           "character_id"):
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

    @router.post("/profiles/{prof}/projects/{slug}/select-all")
    def select_all(prof: str, slug: str):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        count = 0
        for sc in project.scenes:
            if sc.selected_image is None and sc.images:
                sc.selected_image = 0
                count += 1
        project.save()
        return {"selected": count}

    # -------------------------------------------------------- scene refs

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/refs",
                 status_code=201)
    async def add_scene_ref(prof: str, slug: str, sid: str,
                            role: str = Form("garment"),
                            label: str = Form(""),
                            url: str = Form(""),
                            file: UploadFile = File(...)):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        dest = await save_upload(file, project.scene_refs_dir(scene))
        ref = SceneRef(
            file=str(dest.relative_to(project.root)),
            role=role,
            label=label or dest.stem,
            url=url or None,
        )
        scene.refs.append(ref)
        project.save()
        return asdict(ref)

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/refs/bulk",
                 status_code=201)
    async def add_scene_refs_bulk(prof: str, slug: str, sid: str,
                                  files: list[UploadFile] = File(...)):
        from pathlib import Path as P
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        added = []
        for f in files:
            dest = await save_upload(f, project.scene_refs_dir(scene))
            label = P(f.filename or "ref").stem.replace("-", " ").replace("_", " ").title()
            ref = SceneRef(
                file=str(dest.relative_to(project.root)),
                role="garment",
                label=label,
            )
            scene.refs.append(ref)
            added.append(asdict(ref))
        project.save()
        return added

    @router.delete("/profiles/{prof}/projects/{slug}/scenes/{sid}/refs/{index}")
    def delete_scene_ref(prof: str, slug: str, sid: str, index: int):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        if not 0 <= index < len(scene.refs):
            raise _err(404, "not_found", f"No ref {index} on {sid}")
        scene.refs.pop(index)
        project.save()
        return {"deleted": index}

    @router.get("/profiles/{prof}/projects/{slug}/scenes/{sid}/links",
                response_class=PlainTextResponse)
    def scene_links(prof: str, slug: str, sid: str):
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        urls = [r for r in scene.refs if r.url]
        if not urls:
            return ""
        lines = [scene.description[:60]]
        for r in urls:
            lines.append(f"{r.label} — {r.url}" if r.label else str(r.url))
        return "\n".join(lines)

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
                model: str | None = None):
        project = load_project(prof, slug)
        rows = []
        for sc in project.scenes:
            for img in sc.images:
                rows.append({"type": "image", "scene_id": sc.id,
                             "file": img.file,
                             "prompt": img.prompt, "model": img.model,
                             "cost_usd": img.meta.get("cost_usd"),
                             "references": img.meta.get("reference_images", []),
                             "created_at": img.created_at})
            for clip in sc.clips:
                rows.append({"type": "clip", "scene_id": sc.id,
                             "file": clip.file,
                             "prompt": clip.prompt, "model": clip.model,
                             "status": clip.status, "take": clip.take,
                             "kept": clip.kept,
                             "cost_usd": clip.meta.get("cost_usd"),
                             "created_at": clip.created_at})
        if type:
            rows = [r for r in rows if r["type"] == type]
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
