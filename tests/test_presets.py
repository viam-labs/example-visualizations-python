"""Tests for src/presets.py — the named scene bundles."""
import math

import pytest

from src.animation import SUPPORTED_AXES, SUPPORTED_MODES
from src.geometries import SUPPORTED_TYPES
from src.presets import (
    PRESET_NAMES,
    PRESETS,
    primitives,
    color_wheel,
    force_vector_demo,
    frame_composition,
    geometry_morph,
    load,
    orientation_vectors,
    reference_frame_demo,
    robot_arm,
    trajectory_preview,
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
    # The "colorful sphere" lives as a point cloud, not a mesh —
    # meshes only honor a single uniform color from metadata.colors,
    # so a high-resolution colored surface has to be a point cloud
    # to render correctly. See LESSONS.md::mesh-metadata-colors-
    # only-uses-first-color.
    assert types.count("mesh") == 4
    assert types.count("pointcloud") == 2  # helix + colorful_sphere
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
    most items carry a color override. Two exceptions:

      - Point clouds: omit `color` so the viewer falls back to the
        embedded per-point PCD RGB. See LESSONS.md::pcd-colors-precedence.
      - Per-vertex-colored meshes (e.g. assets/colorful_sphere.ply):
        omit `color` so the PLY's embedded vertex colors render
        instead of being overridden by a uniform metadata tint.
    """
    omit_color_paths = {"assets/colorful_sphere.ply"}
    for it in primitives():
        if it["type"] == "pointcloud":
            assert "color" not in it
            continue
        if it.get("mesh_path") in omit_color_paths:
            assert "color" not in it, (
                f"{it['label']!r} uses {it['mesh_path']!r} which has "
                "embedded per-vertex colors; setting `color` would "
                "override them with a uniform tint"
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
    previous one, ending in a 2-finger claw mounted on the wrist.
    Locks the chain so a missing link can't sneak through."""
    items = robot_arm()
    by_label = {it["label"]: it for it in items}
    expected_chain = [
        ("arm_base", None),
        ("arm_shoulder", "arm_base"),
        ("arm_upper", "arm_shoulder"),
        ("arm_elbow", "arm_upper"),
        ("arm_forearm", "arm_elbow"),
        ("arm_wrist", "arm_forearm"),
        ("claw_palm", "arm_wrist"),
        ("claw_left_finger", "claw_palm"),
        ("claw_right_finger", "claw_palm"),
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


def test_robot_arm_joint_motions_use_swing_not_spin():
    """Real arm joints sweep through a range of motion; they don't
    rotate continuously like a fan. The arm should use the `swing`
    mode on each rotating joint so the user sees realistic back-and-
    forth movement, and so the wrist's roll is visible against the
    two-finger gripper."""
    by_label = {it["label"]: it for it in robot_arm()}
    for joint in ("arm_base", "arm_elbow", "arm_wrist"):
        anim = by_label[joint]["animation"]
        assert anim["mode"] == "swing", (
            f"{joint!r} should use bounded swing motion (RoM), not "
            f"continuous spin; got {anim['mode']!r}"
        )
        assert anim.get("amplitude_deg", 0) > 0, (
            f"{joint!r} swing animation needs a positive amplitude_deg"
        )


def test_robot_arm_claw_fingers_open_and_close_in_phase():
    """Both fingers must move IN PHASE so the gripper opens and
    closes as a unit. Left has -amplitude, right has +amplitude,
    same period — both reach max-open at t=3T/4 (negative sin
    extremum)."""
    by_label = {it["label"]: it for it in robot_arm()}
    left = by_label["claw_left_finger"]["animation"]
    right = by_label["claw_right_finger"]["animation"]
    assert left["mode"] == "oscillate"
    assert right["mode"] == "oscillate"
    assert left["axis"] == "x" and right["axis"] == "x"
    assert left["period_s"] == right["period_s"]
    # Opposite signs.
    assert left["amplitude_mm"] * right["amplitude_mm"] < 0, (
        "fingers must have opposite-sign amplitudes so they move "
        "apart and together rather than sliding in the same direction"
    )


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


def test_reference_frame_demo_wheel_hub_parented_to_mesh_with_identity_orientation():
    """The wheel rotates around its OWN axis (the ring's
    perpendicular). The wheel_hub carries identity orientation
    (OZ=1) so the ring lies in the hub's local XY plane and the spin
    animation rotates around the local Z — i.e., the ring's natural
    perpendicular. Parent stays on the mesh so the wheel still
    orbits the mesh's position.

    Earlier versions of this demo used OY=1 on the hub to land the
    wheel rotation on a "third axis". The user asked for the simpler
    visual: rotate around the circle's own axis. If anyone restores
    the OY=1 rotation, this test fires."""
    items = reference_frame_demo()
    by_label = {it["label"]: it for it in items}
    hub = by_label.get("spinning_frame_wheel_hub")
    assert hub is not None, "expected an intermediate wheel_hub"
    assert hub["parent_frame"] == "spinning_frame_attached_mesh", (
        "wheel_hub must parent to the mesh so the wheel orbits the "
        "mesh, not the anchor"
    )
    # Identity orientation: OZ=1, others 0.
    pose = hub["pose"]
    assert pose["ox"] == 0
    assert pose["oy"] == 0
    assert pose["oz"] == 1, (
        "wheel_hub must have identity orientation (OZ=1) so the "
        "spin axis is the ring's own perpendicular"
    )
    # And the hub spins (otherwise the wheel doesn't rotate).
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
    assert "claw_palm" in labels  # end of the arm chain


def test_frame_composition_offsets_bases_along_x_only():
    """The merged preset shifts the spinning_frame anchor to negative
    X and the arm_base to positive X so they don't visually overlap.
    Child items (with parent_frame set) are NOT translated — they
    inherit through the frame system."""
    items = frame_composition()
    by_label = {it["label"]: it for it in items}
    # Bases were shifted.
    assert by_label["spinning_frame"]["pose"]["x"] < -500
    assert by_label["arm_base"]["pose"]["x"] > 500
    # A child (parent_frame=spinning_frame) keeps its local pose —
    # children sit at their configured local offset, not at the
    # post-translation anchor X. Just confirm the value matches
    # whatever the preset configures (could change as we tune
    # spacing; what matters is the offset wasn't accidentally
    # applied to the child).
    mesh_local_x = by_label["spinning_frame_attached_mesh"]["pose"]["x"]
    anchor_world_x = by_label["spinning_frame"]["pose"]["x"]
    # If the helper accidentally translated children too, mesh.x
    # would have been shifted by the same -1000.
    assert mesh_local_x > anchor_world_x + 200, (
        "child mesh appears to have been translated with the anchor; "
        "_offset_base_items should only shift parent-less items"
    )


# ---------- trajectory_preview ----------

def test_trajectory_preview_has_runner_waypoints_and_line_segments():
    """Three component categories: waypoint markers, line segments,
    and exactly one moving runner."""
    items = trajectory_preview()
    labels = [it["label"] for it in items]
    wp_count = sum(1 for L in labels if L.startswith("traj_wp_"))
    seg_count = sum(1 for L in labels if L.startswith("traj_seg_"))
    runner_count = sum(1 for L in labels if L == "traj_runner")
    assert wp_count >= 2, "need at least 2 waypoints for a trajectory"
    # Line segments connect adjacent waypoints, so seg count = wp - 1.
    assert seg_count == wp_count - 1, (
        f"segments ({seg_count}) should equal waypoints-1 ({wp_count - 1})"
    )
    assert runner_count == 1, "exactly one runner item drives the demo"


def test_trajectory_preview_waypoints_have_axes_helper():
    """Each waypoint marker must have show_axes_helper=True so the
    viewer renders the orientation triad — that's the point of the
    waypoint visualization."""
    items = trajectory_preview()
    waypoints = [it for it in items if it["label"].startswith("traj_wp_")]
    for wp in waypoints:
        assert wp.get("show_axes_helper") is True


def test_trajectory_preview_runner_uses_trajectory_animation():
    """The runner must be animated with mode=trajectory, and its
    waypoints list must match the waypoint markers' poses (same
    interpolated path)."""
    items = trajectory_preview()
    by_label = {it["label"]: it for it in items}
    runner = by_label["traj_runner"]
    anim = runner["animation"]
    assert anim["mode"] == "trajectory"
    assert isinstance(anim["waypoints"], list)
    wp_items = sorted(
        (it for it in items if it["label"].startswith("traj_wp_")),
        key=lambda it: it["label"],
    )
    assert len(anim["waypoints"]) == len(wp_items)
    # Each waypoint in the animation's list lines up with the
    # corresponding marker's pose.
    for wp_anim, wp_marker in zip(anim["waypoints"], wp_items):
        for k in ("x", "y", "z"):
            assert wp_anim[k] == pytest.approx(wp_marker["pose"][k])


def test_trajectory_preview_runner_also_has_axes_helper():
    """The moving frame also needs the axes helper so its
    interpolated orientation is visible mid-flight."""
    items = trajectory_preview()
    by_label = {it["label"]: it for it in items}
    assert by_label["traj_runner"].get("show_axes_helper") is True


def test_trajectory_preview_line_segments_align_with_segment_directions():
    """Each segment capsule's orientation vector should point from
    its starting waypoint toward the next — that's what makes a
    capsule rendered with arbitrary radius read as a straight line
    on the trajectory."""
    items = trajectory_preview()
    waypoints = sorted(
        (it for it in items if it["label"].startswith("traj_wp_")),
        key=lambda it: it["label"],
    )
    segments = sorted(
        (it for it in items if it["label"].startswith("traj_seg_")),
        key=lambda it: it["label"],
    )
    for i, seg in enumerate(segments):
        a = waypoints[i]["pose"]
        b = waypoints[i + 1]["pose"]
        dx, dy, dz = b["x"] - a["x"], b["y"] - a["y"], b["z"] - a["z"]
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        ox_expected, oy_expected, oz_expected = dx / norm, dy / norm, dz / norm
        seg_pose = seg["pose"]
        assert seg_pose["ox"] == pytest.approx(ox_expected, abs=1e-6)
        assert seg_pose["oy"] == pytest.approx(oy_expected, abs=1e-6)
        assert seg_pose["oz"] == pytest.approx(oz_expected, abs=1e-6)


# ---------- geometry_morph ----------

def test_geometry_morph_includes_all_four_animation_modes():
    """The row showcases four distinct attribute-animation patterns;
    each must be present. Modes: pulse on sphere (size), pulse on
    box (single-axis stretch), breathe (opacity), flicker (on/off
    toggle)."""
    items = geometry_morph()
    by_label = {it["label"]: it for it in items}
    assert by_label["morph_pulse_sphere"]["animation"]["mode"] == "pulse"
    assert by_label["morph_stretch_box"]["animation"]["mode"] == "pulse"
    assert by_label["morph_stretch_box"]["animation"]["axis"] == "z"
    assert by_label["morph_breathe_capsule"]["animation"]["mode"] == "breathe"
    # Any one of the grid items uses flicker.
    grid_items = [v for k, v in by_label.items() if k.startswith("morph_grid_")]
    assert len(grid_items) == 25, f"expected 5×5 grid, got {len(grid_items)}"
    for g in grid_items:
        assert g["animation"]["mode"] == "flicker"


def test_geometry_morph_grid_phase_offsets_vary_per_cell():
    """A diagonal wave needs distinct phase_offset_s per cell.
    If everyone shared a phase, the grid would flicker as one
    block — visually less interesting and not a wave."""
    items = geometry_morph()
    grid_items = [it for it in items if it["label"].startswith("morph_grid_")]
    offsets = {it["animation"]["phase_offset_s"] for it in grid_items}
    # Diagonal pattern: (row+col) ∈ [0, 8] gives 9 distinct offset
    # buckets across the 25 cells.
    assert len(offsets) == 9


# ---------- force_vector_demo ----------

def test_force_vector_demo_is_a_single_animated_arrow():
    """Standalone preset is exactly one arrow with force_vector
    animation. Compositional simplicity is the point — the visual
    interest comes from the animation, not from item count."""
    items = force_vector_demo()
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "arrow"
    assert item["animation"]["mode"] == "force_vector"


def test_force_vector_demo_animation_carries_all_four_attributes():
    """The animation config must specify all four changing attributes:
    length amplitude, radius amplitude, tilt (drives orientation
    precession), and color speed."""
    anim = force_vector_demo()[0]["animation"]
    assert "length_amplitude_mm" in anim
    assert "radius_amplitude_mm" in anim
    assert "tilt_deg" in anim
    # color_speed has a default so it might be implicit, but the
    # period_s is what actually drives the hue cycle.
    assert "period_s" in anim


# ---------- all preset trajectory-shift behavior ----------

def test_all_preset_shifts_trajectory_animation_waypoints():
    """When the `all` preset offsets the trajectory_preview items
    in X+Y, the waypoints INSIDE the runner's animation must shift
    too — otherwise the runner walks the un-shifted path while the
    markers and line segments live at the shifted location, and the
    demo desyncs."""
    items = load("all")
    # Find the runner in the all-preset items (label is unchanged).
    runner = next(
        (it for it in items if it["label"] == "traj_runner"),
        None,
    )
    assert runner is not None, "trajectory_preview missing from all preset"
    anim_waypoints = runner["animation"]["waypoints"]
    # The runner's static pose lines up with its first waypoint (we
    # set it to dict(waypoints[0]) in trajectory_preview).
    rp = runner["pose"]
    awp0 = anim_waypoints[0]
    assert rp["x"] == pytest.approx(awp0["x"])
    assert rp["y"] == pytest.approx(awp0["y"])
    assert rp["z"] == pytest.approx(awp0["z"])
    # And the runner sits well to the +X side and on the
    # frame_composition row (+Y), matching the all-preset layout.
    assert rp["x"] > 2000.0, "trajectory should be x-shifted in all preset"
    assert rp["y"] > 1500.0, "trajectory should sit on the +Y row"


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
