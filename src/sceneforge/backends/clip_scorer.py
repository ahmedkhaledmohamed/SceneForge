"""CLIP-based visual consistency scoring.

Uses Together AI's embedding endpoint to compute CLIP embeddings for
images, then measures pairwise cosine similarity across a project's
selected/kept scene images.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path


def _image_to_data_uri(path: Path) -> str:
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    suffix = path.suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}.get(suffix.lstrip("."), "image/png")
    return f"data:{mime};base64,{b64}"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embeddings(images: list[Path], api_key: str) -> list[list[float]]:
    import openai
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.together.xyz/v1",
    )
    embeddings = []
    for img_path in images:
        data_uri = _image_to_data_uri(img_path)
        response = client.embeddings.create(
            model="togethercomputer/m2-bert-80M-2k-retrieval",
            input=[data_uri],
        )
        embeddings.append(response.data[0].embedding)
    return embeddings


def score_consistency(images: list[Path], embeddings: list[list[float]] | None = None,
                      api_key: str = "") -> float:
    if len(images) < 2:
        return 1.0

    if embeddings is None:
        embeddings = get_embeddings(images, api_key)

    similarities = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            similarities.append(_cosine_similarity(embeddings[i], embeddings[j]))

    return round(sum(similarities) / len(similarities), 4) if similarities else 1.0


def find_outliers(images: list[Path], threshold: float = 0.7,
                  embeddings: list[list[float]] | None = None,
                  api_key: str = "") -> list[int]:
    if len(images) < 2:
        return []

    if embeddings is None:
        embeddings = get_embeddings(images, api_key)

    outliers = []
    for i in range(len(embeddings)):
        sims = []
        for j in range(len(embeddings)):
            if i != j:
                sims.append(_cosine_similarity(embeddings[i], embeddings[j]))
        avg_sim = sum(sims) / len(sims) if sims else 1.0
        if avg_sim < threshold:
            outliers.append(i)

    return outliers


def score_project_consistency(
    project, api_key: str = "", embeddings: list[list[float]] | None = None,
) -> dict:
    images: list[Path] = []
    scene_ids: list[str] = []

    for scene in project.scenes:
        if scene.selected_image is not None and scene.selected_image < len(scene.images):
            img = scene.images[scene.selected_image]
            img_path = project.root / img.file
            if img_path.is_file():
                images.append(img_path)
                scene_ids.append(scene.id)

    if len(images) < 2:
        return {"score": 1.0, "outliers": [], "images_scored": len(images)}

    if embeddings is None:
        embeddings = get_embeddings(images, api_key)

    score = score_consistency(images, embeddings=embeddings)
    outlier_indices = find_outliers(images, embeddings=embeddings)

    outliers = []
    for idx in outlier_indices:
        avg_sim = 0.0
        sims = []
        for j in range(len(embeddings)):
            if j != idx:
                sims.append(_cosine_similarity(embeddings[idx], embeddings[j]))
        avg_sim = sum(sims) / len(sims) if sims else 0.0
        outliers.append({
            "scene_id": scene_ids[idx],
            "similarity": round(avg_sim, 4),
        })

    return {
        "score": score,
        "outliers": outliers,
        "images_scored": len(images),
    }
