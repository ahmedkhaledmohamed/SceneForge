"""Multipart upload handling: validate by magic bytes, cap size,
sanitize names, avoid collisions. Destinations follow the same refs/
conventions the CLI's _import_ref uses."""

from pathlib import Path

from fastapi import HTTPException, UploadFile

from ..util import slugify

IMAGE_MAX_BYTES = 25 * 1024 * 1024
VIDEO_MAX_BYTES = 200 * 1024 * 1024

_IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
}


def _sniff(head: bytes) -> str | None:
    for magic, suffix in _IMAGE_MAGIC.items():
        if head.startswith(magic):
            return suffix
    if head[:2] == b"\xff\xd8":
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[4:8] == b"ftyp":
        return ".mp4"
    if head[4:12] == b"ftypheic" or head[4:12] == b"ftypmif1":
        return ".jpg"
    return None


async def save_upload(file: UploadFile, dest_dir: Path,
                      kinds: tuple[str, ...] = ("image",)) -> Path:
    data = await file.read()
    suffix = _sniff(data[:16])
    kind = "video" if suffix == ".mp4" else "image" if suffix else None
    if kind is None or kind not in kinds:
        raise HTTPException(400, detail={
            "code": "invalid",
            "message": f"'{file.filename}' is not an accepted "
                       f"{' or '.join(kinds)} file (png/jpg/webp/mp4)",
        })
    limit = VIDEO_MAX_BYTES if kind == "video" else IMAGE_MAX_BYTES
    if len(data) > limit:
        raise HTTPException(400, detail={
            "code": "invalid",
            "message": f"'{file.filename}' exceeds {limit // (1024 * 1024)}MB",
        })

    stem = slugify(Path(file.filename or "upload").stem) or "upload"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}{suffix}"
    n = 2
    while dest.exists():
        dest = dest_dir / f"{stem}-{n}{suffix}"
        n += 1
    dest.write_bytes(data)
    return dest
