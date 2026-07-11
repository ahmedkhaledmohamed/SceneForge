"""Local web UI: FastAPI + htmx over the same ops the CLI uses.

Run with `sceneforge ui [--dir PROJECTS_DIR]` and open the printed URL.
Generation runs as one background job per project; the page polls the
job status and refreshes when it finishes. The CLI and UI can be used
interchangeably on the same projects — state lives in project.json.
"""

import html
import threading
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import config, ops
from .project import PROJECT_FILE, Project


class Job:
    def __init__(self, name: str):
        self.name = name
        self.status = "running"  # running | done | failed
        self.log: list[str] = []
        self.reload_sent = False


class JobManager:
    """One background job per project at a time."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, slug: str) -> Job | None:
        return self._jobs.get(slug)

    def start(self, slug: str, name: str, fn) -> bool:
        with self._lock:
            existing = self._jobs.get(slug)
            if existing and existing.status == "running":
                return False
            job = Job(name)
            self._jobs[slug] = job

        def runner():
            try:
                fn(job.log.append)
                job.status = "done"
            except Exception as exc:  # surfaced in the job banner
                job.log.append(str(exc))
                job.status = "failed"

        threading.Thread(target=runner, daemon=True).start()
        return True


STYLE = """
body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto;
       max-width: 1100px; padding: 0 1rem; color: #222; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
a { color: #b05c2a; }
.scene { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.options { display: flex; gap: 12px; flex-wrap: wrap; margin: .5rem 0; }
.opt { text-align: center; }
.opt img { width: 130px; border-radius: 6px; display: block; }
.opt.selected img { outline: 4px solid #b05c2a; }
video { max-width: 220px; border-radius: 6px; }
video.final { max-width: 320px; }
.actions form { display: inline-block; margin-right: 1rem; }
.job { background: #fdf3ec; border: 1px solid #e8c9ae; border-radius: 8px;
       padding: .8rem 1rem; margin: 1rem 0; }
.job.failed { background: #fdecec; border-color: #e8aeae; }
pre { margin: .4rem 0 0; font-size: .8rem; white-space: pre-wrap; }
.muted { color: #777; font-size: .85rem; }
button { background: #b05c2a; color: #fff; border: 0; border-radius: 6px;
         padding: .45rem .9rem; cursor: pointer; }
button.subtle { background: #eee; color: #222; }
select, input[type=number] { padding: .3rem; }
table { border-collapse: collapse; } td, th { padding: .3rem .8rem; text-align: left; }
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<script src='https://unpkg.com/htmx.org@2.0.4'></script>"
        f"<style>{STYLE}</style></head><body>{body}</body></html>"
    )


def _model_select(kind: str, selected: str) -> str:
    opts = []
    for key, m in config.MODELS.items():
        if m["kind"] != kind:
            continue
        sel = " selected" if key == selected else ""
        opts.append(f"<option value='{key}'{sel}>{key} (${m['price']:.2f})</option>")
    return f"<select name='model'>{''.join(opts)}</select>"


def create_app(base_dir: Path) -> FastAPI:
    app = FastAPI(title="SceneForge")
    jobs = JobManager()
    base = base_dir.resolve()

    def root_of(slug: str) -> Path:
        root = (base / slug).resolve()
        if not root.is_relative_to(base) or not (root / PROJECT_FILE).is_file():
            raise HTTPException(404, f"No project '{slug}'")
        return root

    def load(slug: str) -> Project:
        return Project.load(root_of(slug))

    def back(slug: str) -> RedirectResponse:
        return RedirectResponse(f"/p/{slug}", status_code=303)

    # ------------------------------------------------------------ pages

    @app.get("/", response_class=HTMLResponse)
    def index():
        rows = []
        for pj in sorted(base.glob(f"*/{PROJECT_FILE}")):
            slug = pj.parent.name
            p = Project.load(pj.parent)
            done = sum(1 for sc in p.scenes if sc.completed_clip)
            rows.append(
                f"<tr><td><a href='/p/{slug}'>{html.escape(p.name)}</a></td>"
                f"<td>{len(p.scenes)} scenes</td><td>{done} clips</td>"
                f"<td class='muted'>{html.escape(p.concept[:70])}</td></tr>"
            )
        body = (
            f"<h1>SceneForge</h1><p class='muted'>Projects in {html.escape(str(base))} "
            "&mdash; create new ones with <code>sceneforge create</code></p>"
            + (f"<table><tr><th>Project</th><th></th><th></th><th></th></tr>"
               f"{''.join(rows)}</table>" if rows else "<p>No projects found.</p>")
        )
        return _page("SceneForge", body)

    @app.get("/p/{slug}", response_class=HTMLResponse)
    def project_page(slug: str):
        p = load(slug)
        job = jobs.get(slug)

        job_html = ""
        if job and job.status == "running":
            job_html = (
                f"<div class='job' hx-get='/p/{slug}/job' "
                "hx-trigger='every 2s' hx-swap='outerHTML'>"
                f"Running: {html.escape(job.name)}…"
                f"<pre>{html.escape(chr(10).join(job.log[-4:]))}</pre></div>"
            )
        elif job and job.status == "failed":
            job_html = (
                f"<div class='job failed'>Last job failed: {html.escape(job.name)}"
                f"<pre>{html.escape(chr(10).join(job.log[-6:]))}</pre></div>"
            )

        outfits_html = ""

        scenes_html = []
        for sc in p.scenes:
            opts = []
            for i, img in enumerate(sc.images):
                selected = "selected" if sc.selected_image == i else ""
                opts.append(
                    f"<div class='opt {selected}'>"
                    f"<img src='/p/{slug}/media/{img.file}' loading='lazy'>"
                    f"<form method='post' action='/p/{slug}/select'>"
                    f"<input type='hidden' name='scene_id' value='{sc.id}'>"
                    f"<input type='hidden' name='option' value='{i + 1}'>"
                    f"<button class='subtle' type='submit'>"
                    f"{'✓ selected' if selected else f'select {i + 1}'}</button>"
                    "</form></div>"
                )
            clip = sc.completed_clip
            clip_html = (
                f"<video controls preload='metadata' "
                f"src='/p/{slug}/media/{clip.file}'></video>"
                f"<div class='muted'>{clip.model}, {clip.duration_s or 0:.1f}s</div>"
                if clip else "<span class='muted'>no clip yet</span>"
            )
            context_bits = []
            if sc.refs:
                context_bits.append(f"{len(sc.refs)} refs")
            if sc.character_id:
                context_bits.append(sc.character_id)
            if sc.pose:
                context_bits.append(html.escape(sc.pose))
            context_html = (
                f"<div class='muted'>{' · '.join(context_bits)}</div>"
                if context_bits else ""
            )
            scenes_html.append(
                f"<div class='scene'><b>{sc.id}</b> — "
                f"{html.escape(sc.description)}{context_html}"
                f"<div class='options'>{''.join(opts) or '<span class=muted>no images yet</span>'}</div>"
                f"{clip_html}</div>"
            )

        final = p.output_dir / "final.mp4"
        final_html = (
            f"<h2>Final video</h2><video class='final' controls "
            f"src='/p/{slug}/media/output/final.mp4'></video>"
            if final.is_file() else ""
        )

        disabled = "disabled" if job and job.status == "running" else ""
        actions = f"""
        <h2>Actions</h2><div class='actions'>
        <form method='post' action='/p/{slug}/generate-images'>
          <input type='number' name='options' value='{p.settings.image_options}' min='1' max='6' style='width:3.5rem'>
          {_model_select('image', p.settings.image_model)}
          <button {disabled}>Generate images</button>
        </form>
        <form method='post' action='/p/{slug}/generate-clips'>
          {_model_select('video', p.settings.video_model)}
          <label class='muted'><input type='checkbox' name='force' value='1'> redo existing</label>
          <button {disabled}>Generate clips</button>
        </form>
        <form method='post' action='/p/{slug}/stitch'>
          <button {disabled}>Stitch final video</button>
        </form>
        </div>"""

        body = (
            f"<p><a href='/'>&larr; projects</a></p>"
            f"<h1>{html.escape(p.name)} <span class='muted'>{p.settings.aspect}</span></h1>"
            f"<p class='muted'>{html.escape(p.concept)}</p>"
            f"<p class='muted'>style: {html.escape(p.style.anchor)}</p>"
            f"{job_html}{actions}{outfits_html}"
            f"{''.join(scenes_html) or '<p>No scenes yet — add them with <code>sceneforge add-scenes</code></p>'}{final_html}"
        )
        return _page(p.name, body)

    # ------------------------------------------------------------ job poll

    @app.get("/p/{slug}/job", response_class=HTMLResponse)
    def job_status(slug: str):
        job = jobs.get(slug)
        if job is None:
            return HTMLResponse("<div class='job'>no job</div>")
        if job.status == "running":
            return HTMLResponse(
                f"<div class='job' hx-get='/p/{slug}/job' "
                "hx-trigger='every 2s' hx-swap='outerHTML'>"
                f"Running: {html.escape(job.name)}…"
                f"<pre>{html.escape(chr(10).join(job.log[-4:]))}</pre></div>"
            )
        # finished: tell htmx to reload the page once so results appear
        headers = {}
        if not job.reload_sent:
            job.reload_sent = True
            headers["HX-Refresh"] = "true"
        cls = "job failed" if job.status == "failed" else "job"
        return HTMLResponse(
            f"<div class='{cls}'>{job.status}: {html.escape(job.name)}"
            f"<pre>{html.escape(chr(10).join(job.log[-6:]))}</pre></div>",
            headers=headers,
        )

    # ------------------------------------------------------------ mutations

    @app.post("/p/{slug}/select")
    def select(slug: str, scene_id: str = Form(...), option: int = Form(...)):
        p = load(slug)
        try:
            sc = p.find_scene(scene_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
        if not 1 <= option <= len(sc.images):
            raise HTTPException(400, f"{scene_id} has {len(sc.images)} options")
        sc.selected_image = option - 1
        p.save()
        return back(slug)

    def _start_or_409(slug: str, name: str, fn):
        if not jobs.start(slug, name, fn):
            raise HTTPException(409, "A job is already running for this project")
        return back(slug)

    @app.post("/p/{slug}/generate-images")
    def gen_images(slug: str, options: int = Form(3), model: str = Form(...)):
        p = load(slug)
        config.resolve_model(model, "image")
        todo = ops.plan_images(p.scenes, options, force=False)
        if not todo:
            return back(slug)
        return _start_or_409(
            slug, f"generate images ({model})",
            lambda log: ops.run_images(p, todo, model, log=log),
        )

    @app.post("/p/{slug}/generate-clips")
    def gen_clips(slug: str, model: str = Form(...), force: str = Form(None)):
        p = load(slug)
        config.resolve_model(model, "video")
        unselected = ops.unselected_scenes(p.scenes)
        if unselected:
            raise HTTPException(
                400, "Select an image first for: " + ", ".join(unselected)
            )
        todo = ops.plan_clips(p.scenes, force=bool(force))
        if not todo:
            return back(slug)

        def job(log):
            failures = ops.run_clips(p, todo, model, log=log)
            if failures:
                raise RuntimeError(f"{len(failures)} clip(s) failed: {', '.join(failures)}")

        return _start_or_409(slug, f"generate clips ({model})", job)

    @app.post("/p/{slug}/stitch")
    def stitch(slug: str):
        p = load(slug)

        def job(log):
            out_path, duration = ops.run_stitch(p)
            log(f"final video: {out_path.name} ({duration:.1f}s)")

        return _start_or_409(slug, "stitch final video", job)

    # ------------------------------------------------------------ media

    @app.get("/p/{slug}/media/{relpath:path}")
    def media(slug: str, relpath: str):
        root = root_of(slug)
        target = (root / relpath).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "Not found")
        return FileResponse(target)

    return app
