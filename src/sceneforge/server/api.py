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
        doc["spent_usd"] = round(
            sum(img.meta.get("cost_usd", 0.0) for sc in project.scenes for img in sc.images)
            + sum(c.meta.get("cost_usd", 0.0) for c in project.clips),
        4)
        doc["profile_characters"] = [asdict(c) for c in profile.characters] if profile else []
        return doc

    def start_job_or_409(prof: str, slug: str, name: str, fn) -> dict:
        profile = load_profile(prof)

        def wrapped(log, job):
            config.set_active_profile(profile)
            try:
                return fn(log, job)
            finally:
                config.set_active_profile(None)

        if not jobs.start(job_key(prof, slug), name, wrapped):
            raise _err(409, "conflict", "A job is already running for this project")
        return {"started": name}

    # ----------------------------------------------------------- models

    @router.get("/models")
    def models():
        return dict(config.MODELS)

    @router.get("/shot-types")
    def shot_types():
        return dict(config.SHOT_TYPES)

    @router.get("/recommend-model")
    def recommend_model_endpoint(shot_type: str = "", budget: float | None = None):
        model = config.recommend_model(shot_type=shot_type, budget_remaining=budget)
        return {"model": model, "price": config.MODELS.get(model, {}).get("price", 0)}

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
                "openrouter": mask(profile.keys.openrouter),
                "runpod_api": mask(profile.keys.runpod_api),
                "runpod_endpoint": profile.keys.runpod_endpoint,
            },
            "has_together": bool(profile.keys.together),
            "has_openrouter": bool(profile.keys.openrouter),
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
        if "openrouter" in keys:
            profile.keys.openrouter = keys["openrouter"]
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
                "clips": sum(1 for c in p.clips if c.status == "completed"),
                "kept": sum(1 for c in p.clips if c.kept),
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
                for img in sc.images:
                    spent += img.meta.get("cost_usd", 0.0)
                    models_used[img.model] = models_used.get(img.model, 0) + 1
            for c in p.clips:
                if c.status == "completed":
                    clips_completed += 1
                if c.kept:
                    clips_kept += 1
                spent += c.meta.get("cost_usd", 0.0)
                if c.model:
                    models_used[c.model] = models_used.get(c.model, 0) + 1
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
        if "budget_usd" in payload:
            project.budget_usd = float(payload["budget_usd"])
        for field_name in ("anchor", "suffix", "mood", "palette", "lighting"):
            if field_name in payload:
                setattr(project.style, field_name, payload[field_name])
        for field_name in ("image_model", "video_model", "image_options",
                           "clip_speed", "crossfade"):
            if field_name in payload:
                setattr(project.settings, field_name, payload[field_name])
        if "auto_enhance" in payload:
            project.settings.auto_enhance = bool(payload["auto_enhance"])
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

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/enhance-prompt")
    def enhance_scene_prompt(prof: str, slug: str, sid: str):
        from ..prompts import enhance_prompt
        profile = load_profile(prof)
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        try:
            enhanced = enhance_prompt(project, scene, profile=profile)
        except Exception as exc:
            raise _err(500, "enhance_failed", str(exc))
        return {"enhanced_prompt": enhanced, "original": scene.description}

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

    @router.post("/profiles/{prof}/projects/{slug}/generate-shot-list")
    def generate_shot_list_endpoint(prof: str, slug: str, payload: dict):
        from ..prompts import generate_shot_list
        project = load_project(prof, slug)
        concept = payload.get("concept") or project.concept
        if not concept:
            raise _err(400, "invalid", "No concept provided")
        num_scenes = int(payload.get("num_scenes", 8))
        style_anchor = project.style.anchor or ""
        character_desc = ""
        profile = load_profile(prof)
        char_id = payload.get("character_id")
        if char_id:
            try:
                char = profile.find_character(char_id)
                character_desc = f"{char.name} ({char.description})" if char.description else char.name
            except (KeyError, Exception):
                pass
        shots = generate_shot_list(concept, style_anchor=style_anchor,
                                   character_desc=character_desc,
                                   num_scenes=num_scenes)
        return {"shots": shots}

    @router.post("/profiles/{prof}/projects/{slug}/apply-shot-list",
                 status_code=201)
    def apply_shot_list(prof: str, slug: str, payload: dict):
        project = load_project(prof, slug)
        shots = payload.get("shots", [])
        if not shots:
            raise _err(400, "invalid", "No shots provided")
        character_id = payload.get("character_id")
        created = []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            desc = (shot.get("description") or "").strip()
            if not desc:
                continue
            scene = project.add_scene(desc, character_id=character_id)
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
        if index is None:
            scene.selected_image = None
            project.save()
            return asdict(scene)
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

    # ---------------------------------------------------------- upgrade

    @router.post("/profiles/{prof}/projects/{slug}/scenes/{sid}/images/{img_idx}/upgrade",
                 status_code=202)
    def upgrade_image(prof: str, slug: str, sid: str, img_idx: int, payload: dict = {}):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        scene = find_or_404(project.find_scene, sid)
        if not 0 <= img_idx < len(scene.images):
            raise _err(404, "not_found", f"No image {img_idx} on {sid}")
        source = scene.images[img_idx]
        upgrade_model = payload.get("model", "nano-banana-pro")
        if source.model == upgrade_model:
            raise _err(400, "invalid", f"Image already uses {upgrade_model}")
        try:
            config.resolve_model(upgrade_model, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))

        def job(log):
            todo = ops.plan_images([scene], 1, force=True)
            count = ops.run_images(project, todo, upgrade_model, log=log, profile=profile)
            if count > 0:
                new_img = scene.images[-1]
                new_img.upgraded_from = source.model
                project.save()
                log(f"upgraded from {source.model} → {upgrade_model}")

        return start_job_or_409(prof, slug,
                                f"upgrade {sid} img {img_idx} → {upgrade_model}", job)

    @router.post("/profiles/{prof}/projects/{slug}/clips/{cid}/upgrade",
                 status_code=202)
    def upgrade_clip(prof: str, slug: str, cid: str, payload: dict = {}):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        if clip.status != "completed":
            raise _err(400, "invalid", "Can only upgrade completed clips")
        upgrade_model = payload.get("model", "seedance-2.0-or")
        if clip.model == upgrade_model:
            raise _err(400, "invalid", f"Clip already uses {upgrade_model}")
        try:
            config.resolve_model(upgrade_model, "video")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))

        new_clip = project.add_clip(
            source_images=clip.source_images,
            prompt=clip.prompt,
            model=upgrade_model,
        )
        new_clip.seconds = clip.seconds
        new_clip.upgraded_from = clip.id
        project.save()

        def job(log):
            from ..backends import get_video_backend
            resolved = config.resolve_model(upgrade_model, "video")
            backend = get_video_backend(upgrade_model, log)
            image = (project.root / new_clip.source_images[0]) if new_clip.source_images else None
            out = project.clips_dir / f"{new_clip.id}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            prompt = new_clip.prompt or "gentle motion"
            log(f"{new_clip.id}: upgrading from {clip.model} → {upgrade_model}...")
            try:
                result = backend.generate_clip(
                    prompt, out, image=image,
                    width=project.settings.width,
                    height=project.settings.height,
                    seconds=new_clip.seconds or None,
                    timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
                )
                new_clip.file = str(out.relative_to(project.root))
                new_clip.status = "completed"
                new_clip.duration_s = result.duration_s
                new_clip.job_id = result.job_id
                new_clip.meta = result.meta
                if "cost_usd" not in new_clip.meta:
                    new_clip.meta["cost_usd"] = config.MODELS.get(upgrade_model, {}).get("price", 0)
                log(f"{new_clip.id}: done ({result.duration_s:.1f}s)")
            except Exception as exc:
                new_clip.status = "failed"
                new_clip.error = str(exc)
                log(f"{new_clip.id}: FAILED — {exc}")
            project.save()

        return start_job_or_409(prof, slug,
                                f"upgrade {cid} → {upgrade_model}", job)

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
        estimated = sum(n for _, n in todo) * config.MODELS.get(model_key, {}).get("price", 0)
        current_spend = sum(img.meta.get("cost_usd", 0) for sc in project.scenes for img in sc.images) \
                      + sum(c.meta.get("cost_usd", 0) for c in project.clips)
        if project.budget_usd > 0 and current_spend + estimated > project.budget_usd:
            raise _err(400, "budget",
                       f"This would exceed the project budget "
                       f"(${current_spend:.2f} spent + ~${estimated:.2f} = ${current_spend + estimated:.2f}, "
                       f"budget: ${project.budget_usd:.2f})")
        return start_job_or_409(
            prof, slug, f"generate images ({model_key})",
            lambda log, _job: ops.run_images(project, todo, model_key, log=log,
                                             profile=profile),
        )

    @router.post("/profiles/{prof}/projects/{slug}/generate-all-scenes",
                 status_code=202)
    def generate_all_scenes(prof: str, slug: str, payload: dict):
        """Batch-generate images for every scene that still needs them."""
        profile = load_profile(prof)
        project = load_project(prof, slug)
        model_key = payload.get("model") or project.settings.image_model
        try:
            config.resolve_model(model_key, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        options = payload.get("options") or project.settings.image_options
        todo = ops.plan_images(project.scenes, options, force=False)
        if not todo:
            return {"started": None, "note": "all scenes already have images"}
        total_images = sum(n for _, n in todo)
        price = config.MODELS.get(model_key, {}).get("price", 0)
        estimated = total_images * price
        current_spend = sum(
            img.meta.get("cost_usd", 0) for sc in project.scenes for img in sc.images
        ) + sum(c.meta.get("cost_usd", 0) for c in project.clips)
        if project.budget_usd > 0 and current_spend + estimated > project.budget_usd:
            raise _err(400, "budget",
                       f"Batch would exceed budget "
                       f"(${current_spend:.2f} spent + ~${estimated:.2f} = "
                       f"${current_spend + estimated:.2f}, "
                       f"budget: ${project.budget_usd:.2f})")

        def job(log, bg_job):
            bg_job.progress("starting", completed=0, total=len(todo))
            succeeded = 0
            failed_scenes = []
            for i, (sc, needed) in enumerate(todo):
                bg_job.progress(sc.id, completed=i, total=len(todo))
                log(f"--- {sc.id} ({i + 1}/{len(todo)}) ---")
                try:
                    ops.run_images(project, [(sc, needed)], model_key,
                                   log=log, profile=profile)
                    bg_job.results.append({
                        "scene_id": sc.id, "status": "ok", "images": needed,
                    })
                    succeeded += 1
                except Exception as exc:
                    bg_job.results.append({
                        "scene_id": sc.id, "status": "failed",
                        "error": str(exc),
                    })
                    failed_scenes.append(sc.id)
                    log(f"{sc.id}: FAILED — {exc}")
            bg_job.progress("done", completed=len(todo))
            if failed_scenes:
                log(f"{succeeded}/{len(todo)} scenes OK, "
                    f"{len(failed_scenes)} failed: {', '.join(failed_scenes)}")
                if succeeded == 0:
                    raise RuntimeError(f"All {len(todo)} scenes failed")

        return start_job_or_409(
            prof, slug,
            f"batch images: {len(todo)} scenes ({model_key})", job)

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
            lambda log, _job: ops.run_images(project, todo, model_key, log=log,
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

        def job(log, _job):
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

        def job(log, _job):
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

    # ----------------------------------------------------------- clips

    @router.get("/profiles/{prof}/projects/{slug}/clips")
    def list_clips(prof: str, slug: str):
        project = load_project(prof, slug)
        return [asdict(c) for c in project.clips]

    @router.post("/profiles/{prof}/projects/{slug}/clips", status_code=201)
    def create_clip(prof: str, slug: str, payload: dict):
        from ..project import Clip
        project = load_project(prof, slug)
        sources = payload.get("source_images", [])
        if not sources:
            raise _err(400, "invalid", "At least one source image is required")
        clip = project.add_clip(
            source_images=sources,
            prompt=payload.get("prompt", ""),
            model=payload.get("model") or project.settings.video_model,
        )
        clip.seconds = int(payload.get("seconds", 5))
        shot_type = (payload.get("shot_type") or "").strip()
        if shot_type and shot_type not in config.SHOT_TYPES:
            raise _err(400, "invalid", f"Unknown shot type '{shot_type}'")
        clip.shot_type = shot_type
        project.save()
        return asdict(clip)

    @router.post("/profiles/{prof}/projects/{slug}/clips/{cid}/generate",
                 status_code=202)
    def generate_clip(prof: str, slug: str, cid: str):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        if clip.status == "completed":
            raise _err(400, "invalid", "Clip already generated")
        model_key = clip.model or project.settings.video_model
        if model_key == "auto":
            spent = sum(img.meta.get("cost_usd", 0) for sc in project.scenes for img in sc.images) \
                  + sum(c.meta.get("cost_usd", 0) for c in project.clips)
            budget_left = (project.budget_usd - spent) if project.budget_usd > 0 else None
            model_key = config.recommend_model(
                shot_type=clip.shot_type, budget_remaining=budget_left)
            clip.model = model_key
            project.save()
        try:
            config.resolve_model(model_key, "video")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))

        def job(log, _job):
            from ..backends import get_video_backend
            resolved = config.resolve_model(model_key, "video")
            backend = get_video_backend(model_key, log)
            image = (project.root / clip.source_images[0]) if clip.source_images else None
            out = project.clips_dir / f"{clip.id}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            prompt = clip.prompt or "gentle motion"
            log(f"{clip.id}: generating...")
            try:
                result = backend.generate_clip(
                    prompt, out, image=image,
                    width=project.settings.width,
                    height=project.settings.height,
                    seconds=clip.seconds or None,
                    timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
                )
                clip.file = str(out.relative_to(project.root))
                clip.status = "completed"
                clip.duration_s = result.duration_s
                clip.job_id = result.job_id
                clip.meta = result.meta
                if "cost_usd" not in clip.meta:
                    clip.meta["cost_usd"] = config.MODELS.get(model_key, {}).get("price", 0)
                log(f"{clip.id}: done ({result.duration_s:.1f}s)")
            except Exception as exc:
                clip.status = "failed"
                clip.error = str(exc)
                log(f"{clip.id}: FAILED — {exc}")
            project.save()

        return start_job_or_409(prof, slug, f"generate {clip.id} ({model_key})", job)

    @router.post("/profiles/{prof}/projects/{slug}/generate-all-clips-batch",
                 status_code=202)
    def generate_all_clips_batch(prof: str, slug: str, payload: dict):
        """Create clips from scenes with selected images but no completed clip,
        then generate them all in sequence as a background job."""
        profile = load_profile(prof)
        project = load_project(prof, slug)
        model_override = payload.get("model", "auto")
        seconds = int(payload.get("seconds", 5))

        # Find scenes that have a selected image but no completed clip
        # A scene "has a completed clip" if any project-level clip uses that
        # scene's selected image file as a source.
        completed_sources = set()
        for c in project.clips:
            if c.status == "completed":
                for src in c.source_images:
                    completed_sources.add(src)

        eligible = []
        for sc in project.scenes:
            if sc.selected_image is None:
                continue
            img_file = sc.images[sc.selected_image].file
            if img_file in completed_sources:
                continue
            eligible.append((sc, img_file))

        if not eligible:
            return {"started": None, "note": "no eligible scenes (all have clips or no selection)"}

        # Create new Clip entities for each eligible scene
        created_clips = []
        default_model = project.settings.video_model
        for sc, img_file in eligible:
            clip = project.add_clip(
                source_images=[img_file],
                prompt="",
                model=model_override,
            )
            clip.seconds = seconds
            created_clips.append(clip)
        project.save()

        def job(log, bg_job):
            from ..backends import get_video_backend
            bg_job.progress("starting", completed=0, total=len(created_clips))
            for i, clip in enumerate(created_clips):
                clip_model = clip.model
                if clip_model == "auto":
                    spent = (
                        sum(img.meta.get("cost_usd", 0) for s in project.scenes for img in s.images)
                        + sum(c.meta.get("cost_usd", 0) for c in project.clips)
                    )
                    budget_left = (project.budget_usd - spent) if project.budget_usd > 0 else None
                    clip_model = config.recommend_model(
                        shot_type=clip.shot_type, budget_remaining=budget_left,
                        fallback=default_model)
                    clip.model = clip_model
                    log(f"{clip.id}: auto -> {clip_model}")
                bg_job.progress(clip.id, completed=i, total=len(created_clips))
                resolved = config.resolve_model(clip_model, "video")
                backend = get_video_backend(clip_model, log)
                image = (project.root / clip.source_images[0]) if clip.source_images else None
                out = project.clips_dir / f"{clip.id}.mp4"
                out.parent.mkdir(parents=True, exist_ok=True)
                prompt = clip.prompt or "gentle motion"
                log(f"{clip.id}: generating ({clip_model})...")
                try:
                    result = backend.generate_clip(
                        prompt, out, image=image,
                        seconds=clip.seconds or None,
                        width=project.settings.width,
                        height=project.settings.height,
                        timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
                    )
                    clip.file = str(out.relative_to(project.root))
                    clip.status = "completed"
                    clip.duration_s = result.duration_s
                    clip.meta = result.meta
                    if "cost_usd" not in clip.meta:
                        clip.meta["cost_usd"] = config.MODELS.get(clip_model, {}).get("price", 0)
                    bg_job.results.append({
                        "clip_id": clip.id, "status": "ok",
                    })
                    log(f"{clip.id}: done ({result.duration_s:.1f}s)")
                except Exception as exc:
                    clip.status = "failed"
                    clip.error = str(exc)
                    bg_job.results.append({
                        "clip_id": clip.id, "status": "failed", "error": str(exc),
                    })
                    log(f"{clip.id}: FAILED -- {exc}")
                project.save()
            bg_job.progress("done", completed=len(created_clips))

        return start_job_or_409(
            prof, slug,
            f"batch clips: {len(created_clips)} from scenes", job)

    @router.post("/profiles/{prof}/projects/{slug}/clips/generate-all",
                 status_code=202)
    def generate_all_clips(prof: str, slug: str):
        profile = load_profile(prof)
        project = load_project(prof, slug)
        pending = [c for c in project.clips if c.status == "pending"]
        if not pending:
            return {"started": None, "note": "no pending clips"}
        default_model = project.settings.video_model

        def job(log, _job):
            from ..backends import get_video_backend
            for clip in pending:
                clip_model = clip.model or default_model
                if clip_model == "auto":
                    spent = sum(img.meta.get("cost_usd", 0) for sc in project.scenes for img in sc.images) \
                          + sum(c.meta.get("cost_usd", 0) for c in project.clips)
                    budget_left = (project.budget_usd - spent) if project.budget_usd > 0 else None
                    clip_model = config.recommend_model(
                        shot_type=clip.shot_type, budget_remaining=budget_left)
                    clip.model = clip_model
                    log(f"{clip.id}: auto → {clip_model} (shot: {clip.shot_type or 'none'})")
                resolved = config.resolve_model(clip_model, "video")
                backend = get_video_backend(clip_model, log)
                image = (project.root / clip.source_images[0]) if clip.source_images else None
                out = project.clips_dir / f"{clip.id}.mp4"
                out.parent.mkdir(parents=True, exist_ok=True)
                prompt = clip.prompt or "gentle motion"
                log(f"{clip.id}: generating ({clip_model})...")
                try:
                    result = backend.generate_clip(
                        prompt, out, image=image,
                        seconds=clip.seconds or None,
                        width=project.settings.width,
                        height=project.settings.height,
                        timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
                    )
                    clip.file = str(out.relative_to(project.root))
                    clip.status = "completed"
                    clip.duration_s = result.duration_s
                    clip.meta = result.meta
                    if "cost_usd" not in clip.meta:
                        clip.meta["cost_usd"] = config.MODELS.get(clip_model, {}).get("price", 0)
                    log(f"{clip.id}: done ({result.duration_s:.1f}s)")
                except Exception as exc:
                    clip.status = "failed"
                    clip.error = str(exc)
                    log(f"{clip.id}: FAILED — {exc}")
                project.save()

        return start_job_or_409(prof, slug,
                                f"generate {len(pending)} clips ({default_model})", job)

    @router.delete("/profiles/{prof}/projects/{slug}/clips/{cid}")
    def delete_clip(prof: str, slug: str, cid: str):
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        project.clips.remove(clip)
        project.save()
        return {"deleted": cid}

    @router.patch("/profiles/{prof}/projects/{slug}/clips/{cid}")
    def patch_clip(prof: str, slug: str, cid: str, payload: dict):
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        if "prompt" in payload:
            clip.prompt = payload["prompt"]
        if "model" in payload:
            clip.model = payload["model"]
        if "source_images" in payload:
            clip.source_images = payload["source_images"]
        if "seconds" in payload:
            clip.seconds = int(payload["seconds"])
        if "shot_type" in payload:
            st = (payload["shot_type"] or "").strip()
            if st and st not in config.SHOT_TYPES:
                raise _err(400, "invalid", f"Unknown shot type '{st}'")
            clip.shot_type = st
        project.save()
        return asdict(clip)

    @router.post("/profiles/{prof}/projects/{slug}/clips/{cid}/reset")
    def reset_clip(prof: str, slug: str, cid: str):
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        clip.status = "pending"
        clip.file = ""
        clip.error = None
        clip.duration_s = None
        clip.job_id = None
        project.save()
        return asdict(clip)

    @router.post("/profiles/{prof}/projects/{slug}/clips/{cid}/keep")
    def keep_clip_v2(prof: str, slug: str, cid: str, payload: dict):
        project = load_project(prof, slug)
        clip = find_or_404(project.find_clip, cid)
        clip.kept = bool(payload.get("kept", True))
        project.save()
        return asdict(clip)

    # --------------------------------------------------------- produce

    @router.post("/profiles/{prof}/projects/{slug}/produce",
                 status_code=202)
    def produce(prof: str, slug: str, payload: dict):
        """Full pipeline: generate images → auto-select → create & generate clips."""
        profile = load_profile(prof)
        project = load_project(prof, slug)
        if not project.scenes:
            raise _err(400, "invalid", "Project has no scenes")

        image_model = payload.get("image_model") or project.settings.image_model
        video_model = payload.get("video_model") or project.settings.video_model
        seconds = int(payload.get("seconds", 5))

        try:
            config.resolve_model(image_model, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        if video_model != "auto":
            try:
                config.resolve_model(video_model, "video")
            except ValueError as exc:
                raise _err(400, "invalid", str(exc))

        # Budget estimate
        options = project.settings.image_options
        scenes_needing_images = [
            sc for sc in project.scenes if len(sc.images) < options
        ]
        images_needed = sum(
            max(0, options - len(sc.images)) for sc in scenes_needing_images
        )
        img_price = config.MODELS.get(image_model, {}).get("price", 0)
        vid_price = config.MODELS.get(video_model, {}).get("price", 0) if video_model != "auto" else 0
        # Scenes that will eventually need clips: those without a completed
        # project-level clip whose source is their selected image.
        completed_sources = set()
        for c in project.clips:
            if c.status == "completed":
                for src in c.source_images:
                    completed_sources.add(src)
        clip_eligible = 0
        for sc in project.scenes:
            if sc.selected_image is not None:
                img_file = sc.images[sc.selected_image].file
                if img_file not in completed_sources:
                    clip_eligible += 1
            elif sc.images:
                # Will be auto-selected, then needs clip
                img_file = sc.images[0].file
                if img_file not in completed_sources:
                    clip_eligible += 1
            elif images_needed > 0:
                # Will get images generated, auto-selected, then needs clip
                clip_eligible += 1

        estimated_cost = images_needed * img_price + clip_eligible * vid_price
        current_spend = sum(
            img.meta.get("cost_usd", 0)
            for sc in project.scenes for img in sc.images
        ) + sum(c.meta.get("cost_usd", 0) for c in project.clips)

        if project.budget_usd > 0 and current_spend + estimated_cost > project.budget_usd:
            raise _err(400, "budget",
                       f"Produce would exceed budget "
                       f"(${current_spend:.2f} spent + ~${estimated_cost:.2f} = "
                       f"${current_spend + estimated_cost:.2f}, "
                       f"budget: ${project.budget_usd:.2f})")

        def job(log, bg_job):
            # Stage 1/3: Generate images for scenes that need them
            log("Stage 1/3: Generating images...")
            todo = ops.plan_images(project.scenes, options, force=False)
            if todo:
                bg_job.progress("images", completed=0, total=3)
                total_images = sum(n for _, n in todo)
                log(f"  {len(todo)} scene(s), {total_images} image(s) to generate")
                ops.run_images(project, todo, image_model, log=log, profile=profile)
            else:
                log("  all scenes already have images")

            # Stage 2/3: Auto-select first image for unselected scenes
            log("Stage 2/3: Auto-selecting...")
            bg_job.progress("select", completed=1, total=3)
            selected_count = 0
            for sc in project.scenes:
                if sc.selected_image is None and sc.images:
                    sc.selected_image = 0
                    selected_count += 1
            if selected_count:
                project.save()
                log(f"  auto-selected {selected_count} scene(s)")
            else:
                log("  all scenes already have selections")

            # Stage 3/3: Create and generate clips
            log("Stage 3/3: Generating clips...")
            bg_job.progress("clips", completed=2, total=3)

            # Reload completed sources after stages 1-2
            clip_completed_sources = set()
            for c in project.clips:
                if c.status == "completed":
                    for src in c.source_images:
                        clip_completed_sources.add(src)

            eligible = []
            default_model = project.settings.video_model
            for sc in project.scenes:
                if sc.selected_image is None:
                    continue
                img_file = sc.images[sc.selected_image].file
                if img_file in clip_completed_sources:
                    continue
                eligible.append((sc, img_file))

            if not eligible:
                log("  all scenes already have clips")
            else:
                log(f"  {len(eligible)} clip(s) to generate")
                from ..backends import get_video_backend
                created_clips = []
                for sc, img_file in eligible:
                    clip = project.add_clip(
                        source_images=[img_file],
                        prompt="",
                        model=video_model,
                    )
                    clip.seconds = seconds
                    created_clips.append(clip)
                project.save()

                for i, clip in enumerate(created_clips):
                    clip_model = clip.model
                    if clip_model == "auto":
                        spent = (
                            sum(img.meta.get("cost_usd", 0)
                                for s in project.scenes for img in s.images)
                            + sum(c.meta.get("cost_usd", 0) for c in project.clips)
                        )
                        budget_left = (project.budget_usd - spent) if project.budget_usd > 0 else None
                        clip_model = config.recommend_model(
                            shot_type=clip.shot_type,
                            budget_remaining=budget_left,
                            fallback=default_model)
                        clip.model = clip_model
                        log(f"  {clip.id}: auto -> {clip_model}")
                    resolved = config.resolve_model(clip_model, "video")
                    backend = get_video_backend(clip_model, log)
                    image = (project.root / clip.source_images[0]) if clip.source_images else None
                    out = project.clips_dir / f"{clip.id}.mp4"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    prompt = clip.prompt or "gentle motion"
                    log(f"  {clip.id}: generating ({clip_model})...")
                    try:
                        result = backend.generate_clip(
                            prompt, out, image=image,
                            seconds=clip.seconds or None,
                            width=project.settings.width,
                            height=project.settings.height,
                            timeout_s=resolved.get("timeout_s", config.VIDEO_TIMEOUT_S),
                        )
                        clip.file = str(out.relative_to(project.root))
                        clip.status = "completed"
                        clip.duration_s = result.duration_s
                        clip.meta = result.meta
                        if "cost_usd" not in clip.meta:
                            clip.meta["cost_usd"] = config.MODELS.get(clip_model, {}).get("price", 0)
                        bg_job.results.append({
                            "clip_id": clip.id, "status": "ok",
                        })
                        log(f"  {clip.id}: done ({result.duration_s:.1f}s)")
                    except Exception as exc:
                        clip.status = "failed"
                        clip.error = str(exc)
                        bg_job.results.append({
                            "clip_id": clip.id, "status": "failed",
                            "error": str(exc),
                        })
                        log(f"  {clip.id}: FAILED -- {exc}")
                    project.save()

            bg_job.progress("done", completed=3, total=3)
            log("Produce complete.")

        return {
            **start_job_or_409(prof, slug, "produce (full pipeline)", job),
            "estimate": {
                "images": images_needed,
                "clips": clip_eligible,
                "cost_usd": round(estimated_cost, 4),
            },
        }

    # ---------------------------------------------------------- direct

    @router.post("/profiles/{prof}/projects/{slug}/direct",
                 status_code=202)
    def direct(prof: str, slug: str, payload: dict):
        """AI Director: concept → shot list → images → auto-select → clips."""
        from ..prompts import generate_shot_list

        profile = load_profile(prof)
        project = load_project(prof, slug)
        if not project.concept:
            raise _err(400, "invalid", "Project has no concept — set one first")

        num_scenes = int(payload.get("num_scenes", 8))
        image_model = payload.get("image_model") or project.settings.image_model
        video_model = payload.get("video_model") or project.settings.video_model
        seconds = int(payload.get("seconds", 5))
        character_id = payload.get("character_id")

        try:
            config.resolve_model(image_model, "image")
        except ValueError as exc:
            raise _err(400, "invalid", str(exc))
        if video_model != "auto":
            try:
                config.resolve_model(video_model, "video")
            except ValueError as exc:
                raise _err(400, "invalid", str(exc))

        # Budget estimate: num_scenes images + num_scenes clips
        options = project.settings.image_options
        img_price = config.MODELS.get(image_model, {}).get("price", 0)
        vid_price = config.MODELS.get(video_model, {}).get("price", 0) if video_model != "auto" else 0
        images_needed = num_scenes * options
        estimated_cost = images_needed * img_price + num_scenes * vid_price
        current_spend = sum(
            img.meta.get("cost_usd", 0)
            for sc in project.scenes for img in sc.images
        ) + sum(c.meta.get("cost_usd", 0) for c in project.clips)

        if project.budget_usd > 0 and current_spend + estimated_cost > project.budget_usd:
            raise _err(400, "budget",
                       f"Director would exceed budget "
                       f"(${current_spend:.2f} spent + ~${estimated_cost:.2f} = "
                       f"${current_spend + estimated_cost:.2f}, "
                       f"budget: ${project.budget_usd:.2f})")

        def job(log, bg_job):
            # Stage 1/5: Generate shot list from concept
            log("Stage 1/5: Planning shot list...")
            bg_job.progress("shot-list", completed=0, total=5)
            style_anchor = project.style.anchor or ""
            character_desc = ""
            if character_id:
                try:
                    char = profile.find_character(character_id)
                    character_desc = (
                        f"{char.name} ({char.description})"
                        if char.description else char.name
                    )
                except (KeyError, Exception):
                    pass
            shots = generate_shot_list(
                project.concept,
                style_anchor=style_anchor,
                character_desc=character_desc,
                num_scenes=num_scenes,
            )
            log(f"  planned {len(shots)} shots")

            # Stage 2/5: Create scenes from the shot list
            log("Stage 2/5: Creating scenes...")
            bg_job.progress("scenes", completed=1, total=5)
            for shot in shots:
                desc = (shot.get("description") or "").strip()
                if desc:
                    project.add_scene(desc, character_id=character_id)
            project.save()
            log(f"  created {len(project.scenes)} scenes")

            # Stage 3/5: Generate images for all scenes
            log("Stage 3/5: Generating images...")
            bg_job.progress("images", completed=2, total=5)
            todo = ops.plan_images(project.scenes, options, force=False)
            if todo:
                total_images = sum(n for _, n in todo)
                log(f"  {len(todo)} scene(s), {total_images} image(s) to generate")
                ops.run_images(project, todo, image_model, log=log,
                               profile=profile)
            else:
                log("  all scenes already have images")

            # Stage 4/5: Auto-select first image per scene
            log("Stage 4/5: Auto-selecting...")
            bg_job.progress("select", completed=3, total=5)
            selected_count = 0
            for sc in project.scenes:
                if sc.selected_image is None and sc.images:
                    sc.selected_image = 0
                    selected_count += 1
            if selected_count:
                project.save()
                log(f"  auto-selected {selected_count} scene(s)")
            else:
                log("  all scenes already have selections")

            # Stage 5/5: Create and generate clips
            log("Stage 5/5: Generating clips...")
            bg_job.progress("clips", completed=4, total=5)

            clip_completed_sources = set()
            for c in project.clips:
                if c.status == "completed":
                    for src in c.source_images:
                        clip_completed_sources.add(src)

            eligible = []
            default_model = project.settings.video_model
            for sc in project.scenes:
                if sc.selected_image is None:
                    continue
                img_file = sc.images[sc.selected_image].file
                if img_file in clip_completed_sources:
                    continue
                eligible.append((sc, img_file))

            if not eligible:
                log("  all scenes already have clips")
            else:
                log(f"  {len(eligible)} clip(s) to generate")
                from ..backends import get_video_backend
                created_clips = []
                for sc, img_file in eligible:
                    clip = project.add_clip(
                        source_images=[img_file],
                        prompt="",
                        model=video_model,
                    )
                    clip.seconds = seconds
                    created_clips.append(clip)
                project.save()

                for i, clip in enumerate(created_clips):
                    clip_model = clip.model
                    if clip_model == "auto":
                        spent = (
                            sum(img.meta.get("cost_usd", 0)
                                for s in project.scenes for img in s.images)
                            + sum(c.meta.get("cost_usd", 0)
                                  for c in project.clips)
                        )
                        budget_left = (
                            (project.budget_usd - spent)
                            if project.budget_usd > 0 else None
                        )
                        clip_model = config.recommend_model(
                            shot_type=clip.shot_type,
                            budget_remaining=budget_left,
                            fallback=default_model)
                        clip.model = clip_model
                        log(f"  {clip.id}: auto -> {clip_model}")
                    resolved = config.resolve_model(clip_model, "video")
                    backend = get_video_backend(clip_model, log)
                    image = (
                        (project.root / clip.source_images[0])
                        if clip.source_images else None
                    )
                    out = project.clips_dir / f"{clip.id}.mp4"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    prompt = clip.prompt or "gentle motion"
                    log(f"  {clip.id}: generating ({clip_model})...")
                    try:
                        result = backend.generate_clip(
                            prompt, out, image=image,
                            seconds=clip.seconds or None,
                            width=project.settings.width,
                            height=project.settings.height,
                            timeout_s=resolved.get("timeout_s",
                                                   config.VIDEO_TIMEOUT_S),
                        )
                        clip.file = str(out.relative_to(project.root))
                        clip.status = "completed"
                        clip.duration_s = result.duration_s
                        clip.meta = result.meta
                        if "cost_usd" not in clip.meta:
                            clip.meta["cost_usd"] = config.MODELS.get(
                                clip_model, {}).get("price", 0)
                        bg_job.results.append({
                            "clip_id": clip.id, "status": "ok",
                        })
                        log(f"  {clip.id}: done ({result.duration_s:.1f}s)")
                    except Exception as exc:
                        clip.status = "failed"
                        clip.error = str(exc)
                        bg_job.results.append({
                            "clip_id": clip.id, "status": "failed",
                            "error": str(exc),
                        })
                        log(f"  {clip.id}: FAILED -- {exc}")
                    project.save()

            bg_job.progress("done", completed=5, total=5)
            log("Director complete.")

        return {
            **start_job_or_409(prof, slug, "direct (AI director)", job),
            "estimate": {
                "num_scenes": num_scenes,
                "images": images_needed,
                "clips": num_scenes,
                "cost_usd": round(estimated_cost, 4),
            },
        }

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

        def job(log, _job):
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
