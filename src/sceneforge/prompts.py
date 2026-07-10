"""Style-context prompt composition.

The project-level style anchor is prepended to every generation so all
scenes share one visual language — the core consistency mechanism.
A scene's style_override REPLACES the anchor for that scene only; the
project suffix always applies.

Scenes tied to a character/outfit additionally get identity and
garment-fidelity clauses that refer to the reference images in the
order ops.py sends them: character refs first, then item photos.
"""

from .project import Project, Scene

DEFAULT_SUFFIX = (
    "photorealistic, cinematic composition, vertical framing, "
    "no text, no watermarks, no logos"
)

# Outfit scenes must reproduce garments exactly — including brand logos —
# so the generic "no logos" directive is dropped for them.
OUTFIT_SUFFIX = (
    "photorealistic, cinematic composition, vertical framing, "
    "no added text, no watermarks"
)


def build_anchor(mood: str, palette: str, lighting: str, extra: str = "") -> str:
    """Join the style facets gathered at project creation into one anchor."""
    parts = [extra, lighting, palette, mood]
    return ", ".join(p.strip() for p in parts if p.strip())


def _character_clause(project: Project, scene: Scene, profile=None) -> str | None:
    if not scene.character_id:
        return None
    from .profile import resolve_character
    character, _ = resolve_character(project, profile, scene.character_id)
    n = len(character.reference_images)
    if n == 0:
        return None
    which = "first reference image" if n == 1 else f"first {n} reference images"
    desc = f" ({character.description})" if character.description else ""
    return (
        f"The subject is exactly the character '{character.name}'{desc} shown in "
        f"the {which}: preserve the face, hair, body proportions, and skin tone "
        "precisely"
    )


def _garment_clause(project: Project, scene: Scene) -> str | None:
    if not scene.outfit_id:
        return None
    outfit = project.find_outfit(scene.outfit_id)
    with_images = [item for item in outfit.items if item.image]
    if not with_images:
        return None
    listing = ", ".join(f"({i}) {item.name}" for i, item in enumerate(with_images, 1))
    return (
        "The subject is wearing exactly the clothing items shown in the remaining "
        f"reference images, in order: {listing}. Reproduce every garment "
        "faithfully — fabric texture, exact colors, patterns, prints, logos, "
        "buttons, and silhouette must match the reference photos. Do not "
        "restyle, recolor, or simplify any item"
    )


def compose_prompt(project: Project, scene: Scene, profile=None) -> str:
    anchor = scene.style_override or project.style.anchor
    description = scene.description
    if scene.pose:
        description = f"{description.rstrip('.')}. Pose: {scene.pose}"
    suffix = project.style.suffix
    if scene.outfit_id and suffix == DEFAULT_SUFFIX:
        suffix = OUTFIT_SUFFIX
    parts = [
        anchor,
        description,
        _character_clause(project, scene, profile=profile),
        _garment_clause(project, scene),
        suffix,
    ]
    cleaned = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    if not cleaned:
        raise ValueError(f"Nothing to compose for {scene.id}: empty description and style")
    return ". ".join(cleaned) + "."
