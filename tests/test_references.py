"""Reference-image flow: characters/outfits schema, ref ordering,
truncation, prompt clauses, CLI commands, links export. All offline."""

import json

from typer.testing import CliRunner

from sceneforge import ops
from sceneforge.cli import app
from sceneforge.project import (
    Character,
    ClothingItem,
    Outfit,
    Project,
    Scene,
)
from sceneforge.prompts import DEFAULT_SUFFIX, OUTFIT_SUFFIX, compose_prompt

runner = CliRunner()


def make_outfit_project(tmp_path):
    project = Project(name="looks", root=tmp_path)
    project.style.anchor = "soft studio light"
    project.style.suffix = DEFAULT_SUFFIX
    character = Character(id="char-1", name="Mila",
                          reference_images=["refs/characters/char-1/front.png",
                                            "refs/characters/char-1/face.png"])
    project.characters.append(character)
    outfit = Outfit(id="outfit-1", name="Spring cafe look", items=[
        ClothingItem(name="Linen skirt", url="https://shop/skirt",
                     image="refs/outfits/outfit-1/skirt.jpg"),
        ClothingItem(name="Knit cardigan", url="https://shop/cardigan",
                     image="refs/outfits/outfit-1/cardigan.jpg"),
        ClothingItem(name="Hair clip", url="https://shop/clip"),  # no photo
    ])
    project.outfits.append(outfit)
    for rel in [*character.reference_images,
                *[i.image for i in outfit.items if i.image]]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"img")
    scene = project.add_scene("Spring cafe look", character_id="char-1",
                              outfit_id="outfit-1", pose="standing, facing camera")
    project.save()
    return project, scene


# ---------------------------------------------------------------- ordering


def test_reference_order_character_then_items(tmp_path):
    project, scene = make_outfit_project(tmp_path)
    refs = ops.scene_reference_images(project, scene)
    names = [r.name for r in refs]
    assert names == ["front.png", "face.png", "skirt.jpg", "cardigan.jpg"]


def test_style_reference_comes_last(tmp_path):
    project, scene = make_outfit_project(tmp_path)
    (tmp_path / "style.png").write_bytes(b"img")
    project.style.reference_image = "style.png"
    refs = ops.scene_reference_images(project, scene)
    assert refs[-1].name == "style.png"


def test_truncation_drops_from_tail_with_warning(tmp_path, monkeypatch):
    project, scene = make_outfit_project(tmp_path)
    logs = []
    captured = {}

    class CappedBackend:
        model = {"key": "capped", "max_refs": 3}
        max_reference_images = 3

        def generate_image(self, prompt, out_path, *, width, height,
                           reference_images=None, seed=None):
            captured["refs"] = reference_images
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"png")
            from sceneforge.backends.base import ImageResult
            return ImageResult(path=out_path, prompt=prompt, model="capped")

    monkeypatch.setattr(ops, "get_image_backend", lambda k, log=print: CappedBackend())
    ops.run_images(project, [(scene, 1)], "capped", log=logs.append)

    assert [r.name for r in captured["refs"]] == ["front.png", "face.png", "skirt.jpg"]
    assert any("dropping from the tail" in line and "cardigan.jpg" in line
               for line in logs)


def test_refs_recorded_in_artifact_meta(tmp_path):
    project, scene = make_outfit_project(tmp_path)
    ops.run_images(project, [(scene, 1)], "fake-image", log=lambda m: None)
    meta = scene.images[0].meta
    assert meta["reference_images"] == ["front.png", "face.png",
                                        "skirt.jpg", "cardigan.jpg"]


# ---------------------------------------------------------------- prompts


def test_prompt_has_character_and_garment_clauses(tmp_path):
    project, scene = make_outfit_project(tmp_path)
    prompt = compose_prompt(project, scene)
    assert "first 2 reference images" in prompt
    assert "'Mila'" in prompt
    assert "(1) Linen skirt, (2) Knit cardigan" in prompt  # only items with photos
    assert "Pose: standing, facing camera" in prompt


def test_outfit_scene_suffix_allows_logos(tmp_path):
    project, scene = make_outfit_project(tmp_path)
    prompt = compose_prompt(project, scene)
    assert "no logos" not in prompt
    assert "no added text" in prompt
    # non-outfit scenes keep the strict default
    plain = project.add_scene("a plain scene")
    assert "no logos" in compose_prompt(project, plain)


# ---------------------------------------------------------------- schema


def test_v1_project_loads_with_defaults(tmp_path):
    v1 = {
        "schema_version": 1,
        "name": "Old",
        "concept": "c",
        "style": {"anchor": "a", "suffix": "s"},
        "settings": {},
        "scenes": [{"id": "scene-01", "description": "d",
                    "images": [], "selected_image": None, "clips": []}],
    }
    (tmp_path / "project.json").write_text(json.dumps(v1))
    project = Project.load(tmp_path)
    assert project.characters == [] and project.outfits == []
    assert project.scenes[0].outfit_id is None
    project.save()  # silently upgrades
    from sceneforge.project import SCHEMA_VERSION
    assert json.loads((tmp_path / "project.json").read_text())["schema_version"] == SCHEMA_VERSION


def test_v2_roundtrip(tmp_path):
    project, _ = make_outfit_project(tmp_path)
    loaded = Project.load(tmp_path)
    assert loaded.find_character("char-1").name == "Mila"
    assert loaded.find_outfit("outfit-1").items[0].url == "https://shop/skirt"
    assert loaded.scenes[0].pose == "standing, facing camera"


# ---------------------------------------------------------------- CLI


def make_cli_project(tmp_path):
    result = runner.invoke(app, [
        "create", "Looks", "--concept", "outfit posts", "--anchor", "soft light",
        "--dir", str(tmp_path),
        "--image-model", "fake-image", "--video-model", "fake-video",
    ])
    assert result.exit_code == 0, result.output
    return tmp_path / "looks", ["--project", str(tmp_path / "looks")]


def test_cli_character_outfit_scenes_links(tmp_path):
    root, p = make_cli_project(tmp_path)
    (tmp_path / "doll.png").write_bytes(b"img")
    (tmp_path / "skirt.jpg").write_bytes(b"img")

    result = runner.invoke(app, [*p, "add-character", "Mila",
                                 "--ref", str(tmp_path / "doll.png")])
    assert result.exit_code == 0, result.output
    assert (root / "refs" / "characters" / "char-1" / "doll.png").is_file()

    result = runner.invoke(app, [*p, "add-outfit", "Cafe look",
                                 "--item", f"Linen skirt|https://shop/skirt|{tmp_path / 'skirt.jpg'}",
                                 "--item", "Hair clip|https://shop/clip|"])
    assert result.exit_code == 0, result.output
    assert (root / "refs" / "outfits" / "outfit-1" / "skirt.jpg").is_file()

    result = runner.invoke(app, [*p, "add-outfit-scenes", "outfit-1"])
    assert result.exit_code == 0, result.output
    data = json.loads((root / "project.json").read_text())
    assert len(data["scenes"]) == 2
    assert all(s["outfit_id"] == "outfit-1" and s["character_id"] == "char-1"
               for s in data["scenes"])
    assert data["scenes"][0]["pose"] != data["scenes"][1]["pose"]

    result = runner.invoke(app, [*p, "links"])
    assert result.exit_code == 0
    assert "Linen skirt — https://shop/skirt" in result.output
    assert "Hair clip — https://shop/clip" in result.output

    # end to end: generation with refs on the fake backend
    result = runner.invoke(app, [*p, "generate-images", "--options", "1"])
    assert result.exit_code == 0, result.output
    data = json.loads((root / "project.json").read_text())
    assert data["scenes"][0]["images"][0]["meta"]["reference_images"] == [
        "doll.png", "skirt.jpg"
    ]


def test_together_body_includes_reference_images(tmp_path, monkeypatch):
    import io
    import urllib.request

    from sceneforge.backends.together_image import TogetherImageBackend

    captured = {}

    class CM(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen_cm(req, timeout=0):
        captured["body"] = json.loads(req.data)
        return CM(json.dumps({"data": [{"b64_json": "aGVsbG8="}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_cm)
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")

    ref = tmp_path / "ref.png"
    ref.write_bytes(b"imagebytes")
    backend = TogetherImageBackend({"key": "flux-2-pro", "kind": "image",
                                    "backend": "together",
                                    "id": "black-forest-labs/FLUX.2-pro",
                                    "price": 0.03, "max_refs": 8})
    backend.generate_image("p", tmp_path / "out.png", width=720, height=1280,
                           reference_images=[ref])

    body = captured["body"]
    assert body["model"] == "black-forest-labs/FLUX.2-pro"
    assert "steps" not in body  # FLUX.2 has no steps entry in the registry
    assert len(body["reference_images"]) == 1
    assert body["reference_images"][0].startswith("data:image/png;base64,")