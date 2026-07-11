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


def _sniff(head: bytes) -> tuple[str, bool] | tuple[None, bool]:
    for magic, suffix in _IMAGE_MAGIC.items():
        if head.startswith(magic):
            return suffix, False
    if head[:2] == b"\xff\xd8":
        return ".jpg", False
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp", False
    if head[4:12] in (b"ftypheic", b"ftypmif1", b"ftypavif"):
        return ".jpg", True  # needs conversion
    if head[4:8] == b"ftyp":
        return ".mp4", False
    return None, False


_EXT_MAP = {".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpg",
            ".webp": ".webp", ".mp4": ".mp4", ".heic": ".jpg"}


async def save_upload(file: UploadFile, dest_dir: Path,
                      kinds: tuple[str, ...] = ("image",)) -> Path:
    data = await file.read()
    suffix, needs_convert = _sniff(data[:16])
    if suffix is None and file.filename and len(data) > 100:
        ext = Path(file.filename).suffix.lower()
        suffix = _EXT_MAP.get(ext)
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
    if needs_convert:
        import subprocess
        src = dest.with_suffix(".avif")
        dest.rename(src)
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            src.unlink()
        else:
            src.rename(dest)
    return dest
