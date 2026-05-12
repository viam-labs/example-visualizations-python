"""Tests for src/presets.py — the named scene bundles."""
import pytest

from src.animation import SUPPORTED_AXES, SUPPORTED_MODES
from src.geometries import SUPPORTED_TYPES
from src.presets import (
    PRESET_NAMES,
    PRESETS,
    primitives,
    color_wheel,
    frame_composition,
    load,
    orientation_vectors,
    reference_frame_demo,
    robot_arm,
)


# ---------- primitives ----------

def test_primitives_emits_one_of_every_supported_type():
    """The default scene is every primitive type at least once + a
    tour of more complex meshes (torus, teapot) so users see both
    "minimal example" and "real-mesh example" in one preset. mesh
    appears 4× now: icosahedron PLY, bunny STL, torus PLY, teapot PLY."""
    items = primitives()
    types = [it["type"] for it in items]
    assert types.count("box") == 1
    assert types.count("sphere") == 1
    assert types.count("capsule") == 1
    assert types.count("point") == 1
    assert types.count("arrow") == 1
    # 4 meshes: icosahedron PLY, bunny STL, torus PLY, teapot PLY.
    assert types.count("mesh") == 4
    assert types.count("pointcloud") == 1
    assert set(types) == set(SUPPORTED_TYPES)


def test_primitives_includes_torus_and_teapot():
    """The "more complex meshes" — both must be in primitives now
    that mesh_gallery has been merged in."""
    paths = [it.get("mesh_path") for it in primitives() if it.get("mesh_path")]
    assert any(p.endswith("torus.ply") for p in paths)
    assert any(p.endswith("teapot.ply") for p in paths)


def test_primitives_includes_actual_bunny_stl():
    """The STL slot is the Stanford bunny, not a cube. Test pins
    this so the asset path doesn't silently regress to a placeholder."""
    paths = [it.get("mesh_path") for it in primitives() if it.get("mesh_path")]
    assert any(p.endswith("bunny.stl") for p in paths)


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

# ---------- robot_arm ----------

def test_robot_arm_forms_a_parent_frame_chain():
    """The arm is a kinematic chain: each link parents to the
    previous one. Confirms the chain is wired correctly so changes
    upstream propagate downstream via the frame system."""
    items = robot_arm()
    by_label = {it["label"]: it for it in items}
    expected_chain = [
        ("arm_base", None),
        ("arm_shoulder", "arm_base"),
        ("arm_upper", "arm_shoulder"),
        ("arm_elbow", "arm_upper"),
        ("arm_forearm", "arm_elbow"),
        ("arm_wrist", "arm_forearm"),
        ("arm_end_effector", "arm_wrist"),
    ]
    for label, expected_parent in expected_chain:
        assert label in by_label, f"missing arm link {label!r}"
        actual_parent = by_label[label].get("parent_frame")
        if expected_parent is None:
            assert actual_parent in (None, "", "world")
        else:
            assert actual_parent == expected_parent, (
                f"{label!r} should parent to {expected_parent!r}, "
                f"got {actual_parent!r}"
            )


def test_robot_arm_end_effector_is_an_arrow():
    """End effector uses the asymmetric arrow primitive so users
    can see which direction the tool is pointing at any tick."""
    by_label = {it["label"]: it for it in robot_arm()}
    assert by_label["arm_end_effector"]["type"] == "arrow"


# ---------- orientation_vectors ----------

def test_orientation_vectors_uses_show_axes_helper_coordinate_frames():
    """Orientation viz uses ``show_axes_helper: True`` on small
    sphere markers — the viewer renders an RGB XYZ triad at each
    entity's origin rotated to match its orientation. This shows ALL
    three axes at once (vs a single arrow), which is what users
    actually want when reading 'which way is this oriented'."""
    items = orientation_vectors()
    for it in items:
        assert it["type"] == "sphere", (
            f"{it['label']!r} is a {it['type']!r}; orientation viz "
            "items should be sphere hosts carrying show_axes_helper"
        )
        assert it.get("show_axes_helper") is True, (
            f"{it['label']!r} missing show_axes_helper=True; without "
            "it the viewer renders no axes triad"
        )


def test_orientation_vectors_covers_x_y_z_and_theta_demo():
    labels = {it["label"] for it in orientation_vectors()}
    # Must include each axis demo and at least one theta-sweep demo.
    assert "frame_+X" in labels
    assert "frame_+Y" in labels
    assert "frame_+Z" in labels
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


def test_reference_frame_demo_wheel_hub_parented_to_mesh_with_y_axis_orientation():
    """The wheel orbit axis MUST differ from the other two rotations
    in the demo. We achieve that with an intermediate wheel_hub
    parented to the MESH (not the anchor) with OY=1 orientation, so
    its local Z (and thus its spin axis) is world Y rather than Z.

    Anchor spin → Z, mesh spin → Z, wheel via hub → Y. If anyone
    changes this back to parent_frame: spinning_frame the wheel ends
    up on the SAME axis as the anchor's spin and the "third axis"
    teaching point is lost."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    hub = by_label.get("spinning_frame_wheel_hub")
    assert hub is not None, "expected an intermediate wheel_hub"
    assert hub["parent_frame"] == "spinning_frame_attached_mesh", (
        "wheel_hub must parent to the MESH (not the anchor) so the "
        "wheel orbits around the mesh — see the demo docstring"
    )
    # OY=1 + OX=0 + OZ=0 puts local Z along world Y.
    pose = hub["pose"]
    assert pose["ox"] == 0
    assert pose["oy"] == 1
    assert pose["oz"] == 0
    # And the hub spins (otherwise the orbit doesn't happen).
    assert hub["animation"]["mode"] == "spin"


def test_reference_frame_demo_wheel_children_parent_to_hub():
    """The hue-swept ring spheres parent to the wheel_hub so they
    inherit its OY=1 orientation + spin animation. Without this they
    fall back to orbiting whichever frame they're attached to and
    the axis-distinct teaching point regresses."""
    items = reference_frame_demo()
    wheel = [
        it for it in items
        if it["label"].startswith("spinning_frame_wheel_")
        and it["label"] != "spinning_frame_wheel_hub"
    ]
    assert len(wheel) == 10, f"expected 10 wheel spheres, got {len(wheel)}"
    for it in wheel:
        assert it["type"] == "sphere"
        assert it["parent_frame"] == "spinning_frame_wheel_hub", (
            "wheel spheres must parent to wheel_hub so they inherit "
            "its rotated orientation; otherwise they orbit around Z "
            "instead of Y"
        )
    # Hue sweep: distinct colors.
    colors = {(it["color"]["r"], it["color"]["g"], it["color"]["b"]) for it in wheel}
    assert len(colors) == len(wheel)


# ---------- frame_composition ----------

def test_frame_composition_includes_both_demos():
    """The merged preset must carry both the spinning_frame anchor
    (from reference_frame_demo) and the arm_base (from robot_arm).
    Labels are the load-bearing identifiers in the parent-frame
    chains — if either is missing, the children break."""
    labels = {it["label"] for it in frame_composition()}
    assert "spinning_frame" in labels
    assert "arm_base" in labels
    # And the chained children from both demos.
    assert "spinning_frame_attached_mesh" in labels
    assert "arm_end_effector" in labels


def test_frame_composition_offsets_bases_along_x_only():
    """The merged preset shifts the spinning_frame anchor to negative
    X and the arm_base to positive X so they don't visually overlap.
    Child items (with parent_frame set) are NOT translated — they
    inherit through the frame system. Tests both halves of that."""
    items = frame_composition()
    by_label = {it["label"]: it for it in items}
    # Bases were shifted.
    assert by_label["spinning_frame"]["pose"]["x"] < -500
    assert by_label["arm_base"]["pose"]["x"] > 500
    # A child (parent_frame=spinning_frame) keeps its local pose.
    # In reference_frame_demo the attached mesh sits at local x=350.
    assert by_label["spinning_frame_attached_mesh"]["pose"]["x"] == pytest.approx(350)


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
