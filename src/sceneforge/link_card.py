"""Generate visual product link cards and links overlay files."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .project import Project


def _short_url(url: str, max_len: int = 40) -> str:
    url = url.split("://", 1)[-1]
    url = url.rstrip("/")
    if len(url) > max_len:
        url = url[: max_len - 1] + "…"
    return url


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def collect_product_refs(project: Project) -> list[dict]:
    refs: list[dict] = []
    seen_urls: set[str] = set()
    for scene in project.scenes:
        for ref in scene.refs:
            if ref.url and ref.url not in seen_urls:
                seen_urls.add(ref.url)
                thumb_path = project.scene_refs_dir(scene) / ref.file if ref.file else None
                refs.append({
                    "label": ref.label or "Product",
                    "url": ref.url,
                    "file": str(thumb_path) if thumb_path and thumb_path.is_file() else None,
                    "scene_id": scene.id,
                })
    return refs


def generate_link_card(
    project: Project,
    out_path: Path | None = None,
) -> Path:
    refs = collect_product_refs(project)
    if not refs:
        raise ValueError("No product refs with URLs found in this project")

    card_w = 1080
    padding = 40
    thumb_size = 120
    row_height = thumb_size + 30
    title_height = 80
    card_h = title_height + padding + len(refs) * row_height + padding

    img = Image.new("RGB", (card_w, card_h), "#ffffff")
    draw = ImageDraw.Draw(img)

    title_font = _load_font(32)
    label_font = _load_font(20)
    url_font = _load_font(16)

    draw.rectangle([(0, 0), (card_w, title_height)], fill="#1a1a1a")
    draw.text(
        (card_w // 2, title_height // 2),
        "Shop the Look",
        fill="#ffffff",
        font=title_font,
        anchor="mm",
    )

    y = title_height + padding
    for ref in refs:
        # Thumbnail
        tx = padding
        if ref["file"]:
            try:
                thumb = Image.open(ref["file"])
                thumb.thumbnail((thumb_size, thumb_size))
                img.paste(thumb, (tx, y))
            except Exception:
                draw.rectangle(
                    [(tx, y), (tx + thumb_size, y + thumb_size)],
                    fill="#eeeeee",
                    outline="#cccccc",
                )
        else:
            draw.rectangle(
                [(tx, y), (tx + thumb_size, y + thumb_size)],
                fill="#eeeeee",
                outline="#cccccc",
            )

        text_x = padding + thumb_size + 20
        draw.text((text_x, y + 10), ref["label"], fill="#1a1a1a", font=label_font)
        short = _short_url(ref["url"])
        draw.text((text_x, y + 40), short, fill="#666666", font=url_font)

        y += row_height

    if out_path is None:
        out_path = project.output_dir / "link-card.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def generate_links_text(project: Project) -> str:
    refs = collect_product_refs(project)
    if not refs:
        raise ValueError("No product refs with URLs found in this project")
    lines = []
    for i, ref in enumerate(refs, 1):
        lines.append(f"{i}. {ref['label']}: {ref['url']}")
    return "\n".join(lines)


def generate_links_overlay(
    project: Project,
    out_path: Path | None = None,
) -> Path:
    refs = collect_product_refs(project)
    if not refs:
        raise ValueError("No product refs with URLs found in this project")

    scenes_with_clips: dict[str, float] = {}
    offset = 0.0
    for cid in project.sequence:
        clip = None
        for c in project.clips:
            if c.id == cid:
                clip = c
                break
        if not clip or not clip.duration_s:
            continue
        for scene in project.scenes:
            for r in scene.refs:
                if r.url:
                    if scene.id not in scenes_with_clips:
                        scenes_with_clips[scene.id] = offset
        offset += clip.duration_s

    lines = []
    idx = 1
    for ref in refs:
        start = scenes_with_clips.get(ref["scene_id"], 0.0)
        end = start + 3.0
        sh, sm, ss = int(start // 3600), int(start % 3600 // 60), start % 60
        eh, em, es = int(end // 3600), int(end % 3600 // 60), end % 60
        lines.append(str(idx))
        lines.append(
            f"{sh:02d}:{sm:02d}:{ss:06.3f} --> {eh:02d}:{em:02d}:{es:06.3f}"
        )
        lines.append(ref["label"])
        lines.append("")
        idx += 1

    if out_path is None:
        out_path = project.output_dir / "links-overlay.srt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path
