"""Tests for src/presets.py — the named scene bundles."""
import pytest

from src.animation import SUPPORTED_AXES, SUPPORTED_MODES
from src.geometries import SUPPORTED_TYPES
from src.presets import (
    PRESET_NAMES,
    PRESETS,
    primitives,
    color_wheel,
    load,
    mesh_gallery,
    orientation_vectors,
    reference_frame_demo,
)


# ---------- primitives ----------

def test_primitives_emits_one_of_every_supported_type():
    """The default scene is the user's first impression — every
    primitive type must be represented exactly once (with the box +
    mesh+ply + mesh+stl counted as separate mesh entries)."""
    items = primitives()
    types = [it["type"] for it in items]
    # 1 box, 1 sphere, 1 capsule, 1 point, 2 mesh (ply + stl), 1 pointcloud.
    assert types.count("box") == 1
    assert types.count("sphere") == 1
    assert types.count("capsule") == 1
    assert types.count("point") == 1
    assert types.count("mesh") == 2
    assert types.count("pointcloud") == 1
    assert set(types) == set(SUPPORTED_TYPES)


def test_primitives_has_unique_labels():
    items = primitives()
    labels = [it["label"] for it in items]
    assert len(labels) == len(set(labels))


def test_primitives_are_static():
    """First-install scene should be static — animation is opt-in via
    DoCommand or item override."""
    items = primitives()
    for it in items:
        assert it["animation"]["mode"] == "none"


def test_primitives_spaced_along_x():
    """Items are spaced along X so they don't visually overlap."""
    items = primitives()
    xs = [it["pose"]["x"] for it in items]
    # Strictly increasing.
    assert xs == sorted(xs)
    assert len(set(xs)) == len(xs)


def test_primitives_each_solid_item_has_color():
    """The default scene relies on color to distinguish primitives, so
    every SOLID item must carry a color override (not just rely on the
    viewer's default fill).

    Point clouds are the exception: they omit `color` on purpose so
    the viewer falls back to the embedded per-point PCD RGB instead
    of overriding it with a uniform tint. See
    LESSONS.md::pcd-colors-precedence."""
    for it in primitives():
        if it["type"] == "pointcloud":
            assert "color" not in it, (
                "pointcloud preset items must omit `color` so the "
                "embedded PCD RGB renders; setting color overrides it "
                "with a uniform tint"
            )
            continue
        assert "color" in it
        c = it["color"]
        for ch in ("r", "g", "b"):
            assert 0 <= c[ch] <= 255


def test_primitives_mesh_items_reference_asset_paths():
    items = primitives()
    mesh_items = [it for it in items if it["type"] == "mesh"]
    paths = [it["mesh_path"] for it in mesh_items]
    assert any(p.endswith(".ply") for p in paths)
    assert any(p.endswith(".stl") for p in paths)


def test_primitives_pointcloud_item_references_pcd():
    items = primitives()
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

def test_orientation_vectors_uses_arrow_mesh_not_capsules():
    """Orientation viz needs ASYMMETRIC geometry — a capsule is
    rotationally symmetric along its length axis, so the user can't
    tell which end points which way. The arrow mesh (shaft + cone tip)
    fixes that."""
    items = orientation_vectors()
    for it in items:
        assert it["type"] == "mesh", (
            f"{it['label']!r} is a {it['type']!r}; orientation viz "
            "requires asymmetric geometry (the arrow mesh) so the "
            "pointing direction is unambiguous"
        )
        assert it["mesh_path"].endswith("arrow.ply"), (
            f"{it['label']!r} mesh_path is {it['mesh_path']!r}; "
            "expected the shipped arrow.ply asset"
        )


def test_orientation_vectors_covers_x_y_z_and_theta_demo():
    labels = {it["label"] for it in orientation_vectors()}
    # Must include each axis demo and at least one theta-sweep demo.
    assert "ov_+X" in labels
    assert "ov_+Y" in labels
    assert "ov_+Z" in labels
    assert any("theta" in l.lower() for l in labels)


# ---------- reference_frame_demo ----------

def test_reference_frame_demo_items_form_parent_chain():
    """The anchor item has no parent_frame override (defaults to
    service's parent_frame). The three axis capsules + the attached
    mesh all reference the anchor's label as parent_frame. This is the
    Viam-frame-system part of the demo — if any of the child entries
    don't reference the anchor, the chain breaks."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    anchor = by_label["spinning_frame"]
    # Anchor has no parent_frame field (or its parent is whatever the
    # service default is — not another emitted item).
    assert "parent_frame" not in anchor or anchor.get("parent_frame") in (None, "")
    # Children parent to the anchor.
    for child_label in (
        "spinning_frame_axis_x",
        "spinning_frame_axis_y",
        "spinning_frame_axis_z",
        "spinning_frame_attached_mesh",
    ):
        assert by_label[child_label]["parent_frame"] == "spinning_frame", (
            f"{child_label} must parent to spinning_frame for the "
            "frame-composition demo to work"
        )


def test_reference_frame_demo_axis_capsules_use_distinct_colors():
    """Axes need to be distinguishable at a glance — using the
    near-universal X=red, Y=green, Z=blue convention. If two axes
    end up the same color the demo loses its teaching value."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    rx = by_label["spinning_frame_axis_x"]["color"]
    gy = by_label["spinning_frame_axis_y"]["color"]
    bz = by_label["spinning_frame_axis_z"]["color"]
    # Dominant channel check, not exact: X red dominant, Y green, Z blue.
    assert rx["r"] > rx["g"] and rx["r"] > rx["b"]
    assert gy["g"] > gy["r"] and gy["g"] > gy["b"]
    assert bz["b"] > bz["r"] and bz["b"] > bz["g"]


def test_reference_frame_demo_anchor_and_attached_mesh_both_spin():
    """Both rotations must be present for the user to see frame
    composition: the anchor spins (its children inherit), and the
    attached mesh ALSO spins on its own axis (so the user sees both
    rotations compose)."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    assert by_label["spinning_frame"]["animation"]["mode"] == "spin"
    assert by_label["spinning_frame_attached_mesh"]["animation"]["mode"] == "spin"


def test_reference_frame_demo_static_axes():
    """The axis capsules themselves are static — they appear to spin
    only because their parent (the anchor) spins via the frame system.
    Making them animate independently would muddle the teaching point."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    for axis in ("spinning_frame_axis_x", "spinning_frame_axis_y", "spinning_frame_axis_z"):
        assert by_label[axis]["animation"]["mode"] == "none"


# ---------- registry + load ----------

def test_presets_registry_matches_names_constant():
    assert set(PRESETS.keys()) == set(PRESET_NAMES)


def test_load_returns_items_for_known_preset():
    items = load("primitives")
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
