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


# ---------------------------------------------------------------- shot list

SHOT_LIST_SYSTEM = (
    "You are a creative director for social media content. Given a concept, "
    "generate a shot list for a photo/video series. For each shot, provide: "
    "description (what's in the scene), composition (camera angle/framing), "
    "shot_type (one of: hero, detail, transition, broll, wide, overhead), "
    "and a suggested prompt for AI image generation. "
    'Output as JSON: {"shots": [{"description": "...", "composition": "...", '
    '"shot_type": "...", "prompt": "..."}]}'
)

SHOT_LIST_USER = """Concept: {concept}
{style_line}{character_line}
Generate exactly {num_scenes} shots for a short social-media content series.
Return only the JSON object."""


def generate_shot_list(
    concept: str,
    style_anchor: str = "",
    character_desc: str = "",
    num_scenes: int = 8,
    model: str | None = None,
) -> list[dict]:
    """Call the LLM to produce a structured shot list from a concept."""
    from .config import DEFAULT_LLM_MODEL, TOGETHER_BASE_URL, together_api_key
    from openai import OpenAI

    model = model or DEFAULT_LLM_MODEL
    client = OpenAI(api_key=together_api_key(), base_url=TOGETHER_BASE_URL)

    style_line = f"Visual style: {style_anchor}\n" if style_anchor else ""
    character_line = f"Character: {character_desc}\n" if character_desc else ""
    user_prompt = SHOT_LIST_USER.format(
        concept=concept,
        style_line=style_line,
        character_line=character_line,
        num_scenes=num_scenes,
    )
    messages = [
        {"role": "system", "content": SHOT_LIST_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for _ in range(2):
        response = client.chat.completions.create(
            model=model, messages=messages, temperature=0.7,
        )
        raw = response.choices[0].message.content
        try:
            return _parse_shot_list(raw)
        except ValueError as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"That was invalid ({exc}). Output only the JSON object.",
            })
    raise ValueError(f"Shot list generation failed after retry: {last_error}")


def _parse_shot_list(raw: str) -> list[dict]:
    """Extract and validate the shots array from an LLM response."""
    import json
    import re

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in: {raw[:200]}")
        text = match.group(0)

    data = json.loads(text)
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("Expected a non-empty 'shots' array")

    valid_types = {"hero", "detail", "transition", "broll", "wide", "overhead"}
    result = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ValueError(f"Shot {i + 1} is not an object")
        desc = (shot.get("description") or "").strip()
        if not desc:
            raise ValueError(f"Shot {i + 1} has no description")
        shot_type = (shot.get("shot_type") or "").strip().lower()
        if shot_type not in valid_types:
            shot_type = "broll"  # safe fallback
        result.append({
            "description": desc,
            "composition": (shot.get("composition") or "").strip(),
            "shot_type": shot_type,
            "prompt": (shot.get("prompt") or "").strip(),
        })
    return result
