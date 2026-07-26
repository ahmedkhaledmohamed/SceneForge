"""Project backup — full zip export/import for portability."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from .project import PROJECT_FILE, Project


def export_project_zip(project: Project) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # project.json
        zf.write(project.path, PROJECT_FILE)

        # scene refs
        for scene in project.scenes:
            refs_dir = project.scene_refs_dir(scene)
            if refs_dir.is_dir():
                for f in refs_dir.iterdir():
                    if f.is_file():
                        zf.write(f, str(f.relative_to(project.root)))

            # selected/kept images only
            if scene.selected_image is not None and scene.selected_image < len(scene.images):
                img = scene.images[scene.selected_image]
                img_path = project.root / img.file
                if img_path.is_file():
                    zf.write(img_path, img.file)

        # kept clips
        for clip in project.clips:
            if clip.kept and clip.file:
                clip_path = project.root / clip.file
                if clip_path.is_file():
                    zf.write(clip_path, clip.file)
            if clip.audio_file:
                audio_path = project.root / clip.audio_file
                if audio_path.is_file():
                    zf.write(audio_path, clip.audio_file)

        # manifest
        manifest = {
            "version": 1,
            "export_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "project_name": project.name,
            "concept": project.concept,
            "scenes": len(project.scenes),
            "clips_kept": sum(1 for c in project.clips if c.kept),
            "images": sum(len(s.images) for s in project.scenes),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()


def import_project_zip(zip_data: bytes, projects_dir: Path,
                       new_name: str | None = None) -> Project:
    from .util import slugify

    buf = BytesIO(zip_data)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        if PROJECT_FILE not in names:
            raise ValueError("Invalid backup: missing project.json")

        project_data = json.loads(zf.read(PROJECT_FILE))
        name = new_name or project_data.get("name", "imported")
        slug = slugify(name)

        # Avoid collisions
        target = projects_dir / slug
        n = 2
        while target.exists():
            slug = f"{slugify(name)}-{n}"
            target = projects_dir / slug
            n += 1

        target.mkdir(parents=True, exist_ok=True)

        # Extract all files
        for entry in names:
            if entry == "manifest.json":
                continue
            out_path = target / entry
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(zf.read(entry))

    return Project.load(target)


def export_all_projects_zip(profile_root: Path) -> bytes:
    from .project import PROJECT_FILE as PF

    projects_dir = profile_root / "projects"
    buf = BytesIO()
    project_count = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pj_file in sorted(projects_dir.glob(f"*/{PF}")):
            project = Project.load(pj_file.parent)
            slug = pj_file.parent.name
            project_count += 1

            # project.json
            zf.write(pj_file, f"{slug}/{PF}")

            # scene refs
            for scene in project.scenes:
                refs_dir = project.scene_refs_dir(scene)
                if refs_dir.is_dir():
                    for f in refs_dir.iterdir():
                        if f.is_file():
                            zf.write(f, f"{slug}/{f.relative_to(project.root)}")

            # kept clips
            for clip in project.clips:
                if clip.kept and clip.file:
                    clip_path = project.root / clip.file
                    if clip_path.is_file():
                        zf.write(clip_path, f"{slug}/{clip.file}")

        manifest = {
            "version": 1,
            "export_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "projects": project_count,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()
