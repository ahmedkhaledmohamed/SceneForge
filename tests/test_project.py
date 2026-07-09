import pytest

from sceneforge.project import ClipArtifact, ImageArtifact, Project, find_project_root


def test_roundtrip(tmp_path):
    project = Project(name="My Video", concept="a test", root=tmp_path)
    scene = project.add_scene("first scene")
    scene.images.append(ImageArtifact(file="images/scene-01/opt-1.png",
                                      prompt="p", model="fake-image"))
    scene.selected_image = 0
    scene.clips.append(ClipArtifact(file="clips/scene-01.mp4", prompt="p",
                                    source_image="images/scene-01/opt-1.png",
                                    model="fake-video", duration_s=4.0,
                                    status="completed"))
    project.save()

    loaded = Project.load(tmp_path)
    assert loaded.name == "My Video"
    assert loaded.scenes[0].id == "scene-01"
    assert loaded.scenes[0].selected_image_file == "images/scene-01/opt-1.png"
    assert loaded.scenes[0].completed_clip.duration_s == 4.0


def test_scene_ids_are_sequential(tmp_path):
    project = Project(name="t", root=tmp_path)
    ids = [project.add_scene(f"s{i}").id for i in range(3)]
    assert ids == ["scene-01", "scene-02", "scene-03"]


def test_find_scene_unknown_raises(tmp_path):
    project = Project(name="t", root=tmp_path)
    with pytest.raises(KeyError):
        project.find_scene("scene-99")


def test_completed_clip_prefers_latest(tmp_path):
    project = Project(name="t", root=tmp_path)
    scene = project.add_scene("s")
    scene.clips.append(ClipArtifact(file="a.mp4", prompt="p", source_image=None,
                                    model="m", status="failed", error="boom"))
    assert scene.completed_clip is None
    scene.clips.append(ClipArtifact(file="b.mp4", prompt="p", source_image=None,
                                    model="m", status="completed"))
    assert scene.completed_clip.file == "b.mp4"


def test_find_project_root_walks_up(tmp_path):
    root = tmp_path / "proj"
    nested = root / "images" / "scene-01"
    nested.mkdir(parents=True)
    Project(name="t", root=root).save()
    assert find_project_root(nested) == root
    assert find_project_root(tmp_path) is None
