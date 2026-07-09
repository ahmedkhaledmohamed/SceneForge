"""Style-context prompt composition.

The project-level style anchor is prepended to every generation so all
scenes share one visual language — the core consistency mechanism.
A scene's style_override REPLACES the anchor for that scene only; the
project suffix always applies.
"""

from .project import Project, Scene

DEFAULT_SUFFIX = (
    "photorealistic, cinematic composition, vertical framing, "
    "no text, no watermarks, no logos"
)


def build_anchor(mood: str, palette: str, lighting: str, extra: str = "") -> str:
    """Join the style facets gathered at project creation into one anchor."""
    parts = [extra, lighting, palette, mood]
    return ", ".join(p.strip() for p in parts if p.strip())


def compose_prompt(project: Project, scene: Scene) -> str:
    anchor = scene.style_override or project.style.anchor
    parts = [anchor, scene.description, project.style.suffix]
    cleaned = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    if not cleaned:
        raise ValueError(f"Nothing to compose for {scene.id}: empty description and style")
    return ". ".join(cleaned) + "."
