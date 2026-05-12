"""Tests for src/presets.py — the named scene bundles."""
import pytest

from src.animation import SUPPORTED_AXES, SUPPORTED_MODES
from src.geometries import SUPPORTED_TYPES
from src.presets import (
    PRESET_NAMES,
    PRESETS,
    all_primitives,
    color_wheel,
    load,
    mesh_gallery,
    orientation_vectors,
)


# ---------- all_primitives ----------

def test_all_primitives_emits_one_of_every_supported_type():
    """The default scene is the user's first impression — every
    primitive type must be represented exactly once (with the box +
    mesh+ply + mesh+stl counted as separate mesh entries)."""
    items = all_primitives()
    types = [it["type"] for it in items]
    # 1 box, 1 sphere, 1 capsule, 1 point, 2 mesh (ply + stl), 1 pointcloud.
    assert types.count("box") == 1
    assert types.count("sphere") == 1
    assert types.count("capsule") == 1
    assert types.count("point") == 1
    assert types.count("mesh") == 2
    assert types.count("pointcloud") == 1
    assert set(types) == set(SUPPORTED_TYPES)


def test_all_primitives_has_unique_labels():
    items = all_primitives()
    labels = [it["label"] for it in items]
    assert len(labels) == len(set(labels))


def test_all_primitives_are_static():
    """First-install scene should be static — animation is opt-in via
    DoCommand or item override."""
    items = all_primitives()
    for it in items:
        assert it["animation"]["mode"] == "none"


def test_all_primitives_spaced_along_x():
    """Items are spaced along X so they don't visually overlap."""
    items = all_primitives()
    xs = [it["pose"]["x"] for it in items]
    # Strictly increasing.
    assert xs == sorted(xs)
    assert len(set(xs)) == len(xs)


def test_all_primitives_each_has_color():
    """The default scene relies on color to distinguish primitives,
    so every item must carry a color override (not just rely on the
    viewer's default fill)."""
    for it in all_primitives():
        assert "color" in it
        c = it["color"]
        for ch in ("r", "g", "b"):
            assert 0 <= c[ch] <= 255


def test_all_primitives_mesh_items_reference_asset_paths():
    items = all_primitives()
    mesh_items = [it for it in items if it["type"] == "mesh"]
    paths = [it["mesh_path"] for it in mesh_items]
    assert any(p.endswith(".ply") for p in paths)
    assert any(p.endswith(".stl") for p in paths)


def test_all_primitives_pointcloud_item_references_pcd():
    items = all_primitives()
    pc = [it for it in items if it["type"] == "pointcloud"][0]
    assert pc["pointcloud_path"].endswith(".pcd")


# ---------- color_wheel ----------

def test_color_wheel_default_has_ten_spheres():
    items = color_wheel()
    assert len(items) == 10
    assert all(it["type"] == "sphere" for it in items)


def test_color_wheel_count_param_changes_count():
    items = color_wheel(count=4)
    assert len(items) == 4


def test_color_wheel_hue_sweeps_so_colors_differ():
    items = color_wheel()
    colors = [(it["color"]["r"], it["color"]["g"], it["color"]["b"]) for it in items]
    assert len(set(colors)) == len(colors)


def test_color_wheel_positions_form_a_ring():
    """All items at the same Z=0 and equidistant from the origin in XY."""
    items = color_wheel(count=8, ring_radius_mm=200)
    for it in items:
        x, y = it["pose"]["x"], it["pose"]["y"]
        r = (x ** 2 + y ** 2) ** 0.5
        assert r == pytest.approx(200, abs=1e-6)
        assert it["pose"]["z"] == 0


# ---------- mesh_gallery ----------

def test_mesh_gallery_has_two_meshes_plus_one_pointcloud():
    items = mesh_gallery()
    types = [it["type"] for it in items]
    assert types.count("mesh") == 2
    assert types.count("pointcloud") == 1


# ---------- orientation_vectors ----------

def test_orientation_vectors_all_capsules():
    """The orientation-vector teaching preset uses capsules because
    their length axis makes the orientation visible (vs sphere which
    is rotation-invariant)."""
    items = orientation_vectors()
    for it in items:
        assert it["type"] == "capsule"


def test_orientation_vectors_covers_x_y_z_and_theta_demo():
    labels = {it["label"] for it in orientation_vectors()}
    # Must include each axis demo and at least one theta-sweep demo.
    assert "ov_+X" in labels
    assert "ov_+Y" in labels
    assert "ov_+Z" in labels
    assert any("theta" in l.lower() for l in labels)


# ---------- registry + load ----------

def test_presets_registry_matches_names_constant():
    assert set(PRESETS.keys()) == set(PRESET_NAMES)


def test_load_returns_items_for_known_preset():
    items = load("all_primitives")
    assert isinstance(items, list)
    assert len(items) > 0


def test_load_raises_for_unknown_preset():
    with pytest.raises(ValueError, match="unknown preset"):
        load("not_a_real_preset")


# ---------- shape sanity: every preset emits valid item shapes ----------

@pytest.mark.parametrize("preset_name", list(PRESET_NAMES))
def test_every_preset_item_has_required_fields(preset_name):
    """Each item across every preset must carry the fields the
    service depends on (type, label, pose, animation) so loading a
    preset never crashes the reconfigure path."""
    items = load(preset_name)
    for it in items:
        assert it["type"] in SUPPORTED_TYPES
        assert isinstance(it["label"], str) and it["label"]
        assert "pose" in it
        assert it["animation"]["mode"] in SUPPORTED_MODES
