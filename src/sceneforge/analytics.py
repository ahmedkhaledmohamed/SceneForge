"""Generation analytics — cost, quality, and model performance stats."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .project import Project, PROJECT_FILE


def _week_key(iso_date: str) -> str:
    """Return YYYY-Www from an ISO date string."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
    except Exception:
        return "unknown"


def project_analytics(project: Project) -> dict:
    spend_by_model: dict[str, float] = defaultdict(float)
    images_by_model: dict[str, int] = defaultdict(int)
    clips_by_model: dict[str, int] = defaultdict(int)
    clips_kept_by_model: dict[str, int] = defaultdict(int)
    clips_failed_by_model: dict[str, int] = defaultdict(int)
    total_images = 0
    total_clips = 0
    total_kept = 0
    total_spend = 0.0

    for scene in project.scenes:
        for img in scene.images:
            cost = img.meta.get("cost_usd", 0.0) or 0.0
            spend_by_model[img.model] += cost
            images_by_model[img.model] += 1
            total_images += 1
            total_spend += cost

    for clip in project.clips:
        cost = clip.meta.get("cost_usd", 0.0) or 0.0
        spend_by_model[clip.model] += cost
        clips_by_model[clip.model] += 1
        total_clips += 1
        total_spend += cost
        if clip.kept:
            clips_kept_by_model[clip.model] += 1
            total_kept += 1
        if clip.status == "failed":
            clips_failed_by_model[clip.model] += 1

    model_stats = {}
    all_models = set(spend_by_model) | set(clips_by_model) | set(images_by_model)
    for model in sorted(all_models):
        total_model_clips = clips_by_model.get(model, 0)
        kept_model = clips_kept_by_model.get(model, 0)
        failed_model = clips_failed_by_model.get(model, 0)
        completed = total_model_clips - failed_model
        model_stats[model] = {
            "images": images_by_model.get(model, 0),
            "clips": total_model_clips,
            "clips_kept": kept_model,
            "clips_failed": failed_model,
            "keep_rate": round(kept_model / total_model_clips, 3) if total_model_clips else 0,
            "success_rate": round(completed / total_model_clips, 3) if total_model_clips else 0,
            "spend_usd": round(spend_by_model.get(model, 0), 4),
            "cost_per_kept": round(spend_by_model.get(model, 0) / kept_model, 4) if kept_model else None,
        }

    return {
        "total_images": total_images,
        "total_clips": total_clips,
        "total_kept": total_kept,
        "total_spend_usd": round(total_spend, 4),
        "avg_cost_per_kept": round(total_spend / total_kept, 4) if total_kept else None,
        "models": model_stats,
    }


def profile_analytics(profile_root: Path) -> dict:
    projects_dir = profile_root / "projects"
    spend_by_model: dict[str, float] = defaultdict(float)
    spend_by_week: dict[str, float] = defaultdict(float)
    clips_by_model: dict[str, int] = defaultdict(int)
    clips_kept_by_model: dict[str, int] = defaultdict(int)
    clips_failed_by_model: dict[str, int] = defaultdict(int)
    images_by_model: dict[str, int] = defaultdict(int)
    total_spend = 0.0
    total_images = 0
    total_clips = 0
    total_kept = 0
    project_count = 0

    for pj in sorted(projects_dir.glob(f"*/{PROJECT_FILE}")):
        project = Project.load(pj.parent)
        project_count += 1

        for scene in project.scenes:
            for img in scene.images:
                cost = img.meta.get("cost_usd", 0.0) or 0.0
                spend_by_model[img.model] += cost
                images_by_model[img.model] += 1
                total_images += 1
                total_spend += cost
                week = _week_key(img.created_at)
                spend_by_week[week] += cost

        for clip in project.clips:
            cost = clip.meta.get("cost_usd", 0.0) or 0.0
            spend_by_model[clip.model] += cost
            clips_by_model[clip.model] += 1
            total_clips += 1
            total_spend += cost
            week = _week_key(clip.created_at)
            spend_by_week[week] += cost
            if clip.kept:
                clips_kept_by_model[clip.model] += 1
                total_kept += 1
            if clip.status == "failed":
                clips_failed_by_model[clip.model] += 1

    model_stats = {}
    all_models = set(spend_by_model) | set(clips_by_model) | set(images_by_model)
    for model in sorted(all_models):
        total_model_clips = clips_by_model.get(model, 0)
        kept_model = clips_kept_by_model.get(model, 0)
        failed_model = clips_failed_by_model.get(model, 0)
        completed = total_model_clips - failed_model
        model_stats[model] = {
            "images": images_by_model.get(model, 0),
            "clips": total_model_clips,
            "clips_kept": kept_model,
            "clips_failed": failed_model,
            "keep_rate": round(kept_model / total_model_clips, 3) if total_model_clips else 0,
            "success_rate": round(completed / total_model_clips, 3) if total_model_clips else 0,
            "spend_usd": round(spend_by_model.get(model, 0), 4),
            "cost_per_kept": round(spend_by_model.get(model, 0) / kept_model, 4) if kept_model else None,
        }

    # Spend trend: last 4 weeks sorted
    sorted_weeks = sorted(spend_by_week.keys())[-4:]
    spend_trend = [
        {"week": w, "spend_usd": round(spend_by_week[w], 4)}
        for w in sorted_weeks
    ]

    # Best value model: lowest cost per kept clip
    best_value = None
    best_cost = float("inf")
    for model, stats in model_stats.items():
        if stats["cost_per_kept"] is not None and stats["cost_per_kept"] < best_cost:
            best_cost = stats["cost_per_kept"]
            best_value = model

    return {
        "projects": project_count,
        "total_images": total_images,
        "total_clips": total_clips,
        "total_kept": total_kept,
        "total_spend_usd": round(total_spend, 4),
        "avg_cost_per_kept": round(total_spend / total_kept, 4) if total_kept else None,
        "best_value_model": best_value,
        "models": model_stats,
        "spend_trend": spend_trend,
    }
