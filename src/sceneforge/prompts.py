"""Style-context prompt composition and LLM-powered prompt enhancement.

The project-level style anchor is prepended to every generation so all
scenes share one visual language — the core consistency mechanism.
A scene's style_override REPLACES the anchor for that scene only; the
project suffix always applies.

Scenes tied to a character/outfit additionally get identity and
garment-fidelity clauses that refer to the reference images in the
order ops.py sends them: character refs first, then item photos.
"""

from .project import Project, Scene

ENHANCE_SYSTEM = (
    "You are a prompt engineer for AI image generation models (FLUX, Stable Diffusion). "
    "Given a scene description and context, expand it into a detailed, high-quality "
    "generation prompt. Rules:\n"
    "- Keep the user's original intent and subject\n"
    "- Add specific composition, lighting, color, and detail guidance\n"
    "- Include camera angle and framing if not specified\n"
    "- Maintain the style anchor's visual language\n"
    "- Mention garments/outfits by name if provided\n"
    "- Output ONLY the enhanced prompt text, nothing else — no quotes, "
    "no explanation, no markdown"
)

ENHANCE_USER = """Style anchor: {anchor}
Scene description: {description}
{character_line}{garment_line}{suffix_line}
Enhance this into a detailed image generation prompt (40-80 words)."""


def enhance_prompt(project: Project, scene: Scene, profile=None) -> str:
    """Call the LLM to expand a short scene description into a detailed
    image generation prompt, using the scene's context."""
    from .config import DEFAULT_LLM_MODEL, TOGETHER_BASE_URL, together_api_key

    anchor = scene.style_override or project.style.anchor
    character_line = ""
    if scene.character_id:
        try:
            from .profile import resolve_character
            char, _ = resolve_character(project, profile, scene.character_id)
            desc = f" ({char.description})" if char.description else ""
            character_line = f"Character: {char.name}{desc}\n"
        except Exception:
            pass

    garments = [r for r in scene.refs if r.role == "garment" and r.label]
    garment_line = ""
    if garments:
        listing = ", ".join(r.label for r in garments)
        garment_line = f"Garments: {listing}\n"

    suffix_line = f"Suffix constraints: {project.style.suffix}\n" if project.style.suffix else ""

    user_prompt = ENHANCE_USER.format(
        anchor=anchor or "(none set)",
        description=scene.description,
        character_line=character_line,
        garment_line=garment_line,
        suffix_line=suffix_line,
    )

    from openai import OpenAI
    client = OpenAI(api_key=together_api_key(), base_url=TOGETHER_BASE_URL)
    response = client.chat.completions.create(
        model=DEFAULT_LLM_MODEL,
        messages=[
            {"role": "system", "content": ENHANCE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip().strip('"')

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
    garments = [r for r in scene.refs if r.role == "garment" and r.file]
    if not garments:
        return None
    listing = ", ".join(f"({i}) {r.label}" for i, r in enumerate(garments, 1) if r.label)
    if not listing:
        return None
    return (
        "The subject is wearing exactly the clothing items shown in the remaining "
        f"reference images, in order: {listing}. Reproduce every garment "
        "faithfully — fabric texture, exact colors, patterns, prints, logos, "
        "buttons, and silhouette must match the reference photos. Do not "
        "restyle, recolor, or simplify any item"
    )


def compose_prompt(project: Project, scene: Scene, profile=None,
                   enhanced_description: str | None = None) -> str:
    anchor = scene.style_override or project.style.anchor
    description = enhanced_description or scene.description
    if scene.pose:
        description = f"{description.rstrip('.')}. Pose: {scene.pose}"
    suffix = project.style.suffix
    has_garments = any(r.role == "garment" for r in scene.refs)
    if has_garments and suffix == DEFAULT_SUFFIX:
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
