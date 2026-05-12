"""Tests for animation pose math at fixed t values.

The animation module is a pure function — given an item config, a base
pose, base geometry, and a time, it returns a new pose / geom + the
field-mask paths to emit. These tests pin t to phase-aligned values
(t=0, t=T/4, t=T/2, t=3T/4) so the expected outputs are exact, not
approximate."""
import math

import pytest

from src.animation import (
    SUPPORTED_AXES,
    SUPPORTED_MODES,
    compute_tick,
    is_animated,
)


BASE_POSE = {"x": 0.0, "y": 0.0, "z": 0.0, "ox": 0.0, "oy": 0.0, "oz": 1.0, "theta": 0.0}


# ---------- is_animated ----------

def test_is_animated_false_for_none_mode():
    assert is_animated({"animation": {"mode": "none"}}) is False


def test_is_animated_false_when_animation_key_missing():
    assert is_animated({}) is False


def test_is_animated_true_for_any_non_none_mode():
    for mode in ("orbit", "oscillate", "spin", "pulse"):
        assert is_animated({"animation": {"mode": mode}}) is True


# ---------- none ----------

def test_none_returns_base_unchanged_and_no_paths():
    pose, geom, paths, _ = compute_tick(
        {"type": "box", "animation": {"mode": "none"}},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=10.0,
    )
    assert pose == BASE_POSE
    assert geom == {"dims_mm": {"x": 100, "y": 100, "z": 100}}
    assert paths == []


# ---------- orbit ----------

def test_orbit_at_t_zero_lands_on_positive_x_axis():
    pose, _, paths, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "orbit", "radius_mm": 200, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=0.0,
    )
    assert pose["x"] == pytest.approx(200.0)
    assert pose["y"] == pytest.approx(0.0)
    assert paths == ["poseInObserverFrame.pose.x", "poseInObserverFrame.pose.y"]


def test_orbit_at_quarter_period_lands_on_positive_y_axis():
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "orbit", "radius_mm": 200, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=1.0,  # T/4
    )
    assert pose["x"] == pytest.approx(0.0, abs=1e-9)
    assert pose["y"] == pytest.approx(200.0)


def test_orbit_composes_onto_base_pose():
    """Orbit motion adds to the base x/y, so an item starting at
    (1000, 0, 500) orbits around (1000, 0, 500), not the origin."""
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "orbit", "radius_mm": 100, "period_s": 4}},
        {"x": 1000, "y": 0, "z": 500},
        {"radius_mm": 50},
        t=0.0,
    )
    assert pose["x"] == pytest.approx(1100.0)
    assert pose["y"] == pytest.approx(0.0)
    assert pose["z"] == 500


# ---------- oscillate ----------

def test_oscillate_default_axis_is_y():
    pose, _, paths, _ = compute_tick(
        {"type": "box", "animation": {"mode": "oscillate", "amplitude_mm": 100, "period_s": 4}},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,  # T/4 -> sin = 1, max excursion
    )
    assert pose["y"] == pytest.approx(100.0)
    assert pose["x"] == 0.0
    assert pose["z"] == 0.0
    assert paths == ["poseInObserverFrame.pose.y"]


def test_oscillate_axis_x_moves_only_x():
    pose, _, paths, _ = compute_tick(
        {"type": "box", "animation": {
            "mode": "oscillate", "axis": "x", "amplitude_mm": 250, "period_s": 4,
        }},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,
    )
    assert pose["x"] == pytest.approx(250.0)
    assert pose["y"] == 0.0
    assert paths == ["poseInObserverFrame.pose.x"]


def test_oscillate_axis_z_moves_only_z():
    pose, _, paths, _ = compute_tick(
        {"type": "box", "animation": {
            "mode": "oscillate", "axis": "z", "amplitude_mm": 50, "period_s": 4,
        }},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,
    )
    assert pose["z"] == pytest.approx(50.0)
    assert paths == ["poseInObserverFrame.pose.z"]


def test_oscillate_zero_at_t_zero_and_half_period():
    """sin(0)=0 and sin(pi)=0, so amplitude is zero at t=0 and t=T/2."""
    for t in (0.0, 2.0):
        pose, _, _, _ = compute_tick(
            {"type": "box", "animation": {
                "mode": "oscillate", "amplitude_mm": 100, "period_s": 4,
            }},
            BASE_POSE,
            {"dims_mm": {"x": 100, "y": 100, "z": 100}},
            t=t,
        )
        assert pose["y"] == pytest.approx(0.0, abs=1e-9)


# ---------- spin ----------

def test_spin_at_quarter_period_is_90_degrees():
    pose, _, paths, _ = compute_tick(
        {"type": "capsule", "animation": {"mode": "spin", "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 30, "length_mm": 200},
        t=1.0,
    )
    assert pose["theta"] == pytest.approx(90.0)
    assert paths == ["poseInObserverFrame.pose.theta"]


def test_spin_wraps_modulo_360():
    pose, _, _, _ = compute_tick(
        {"type": "box", "animation": {"mode": "spin", "period_s": 4}},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=4.5,  # 1 full period + T/8 -> 45°
    )
    assert pose["theta"] == pytest.approx(45.0)


# ---------- swing ----------

def test_swing_at_t_zero_is_at_base_theta():
    """At t=0, sin(0)=0, so swing yields base_theta unchanged. Joints
    starting "at rest" should be at their configured angle, not at
    an extreme."""
    pose, _, paths, _ = compute_tick(
        {"type": "capsule", "animation": {"mode": "swing", "amplitude_deg": 60, "period_s": 4}},
        {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 1, "oz": 0, "theta": 30},
        {"radius_mm": 20, "length_mm": 100},
        t=0.0,
    )
    assert pose["theta"] == pytest.approx(30.0)
    assert paths == ["poseInObserverFrame.pose.theta"]


def test_swing_at_quarter_period_reaches_max_amplitude():
    """At t=T/4, sin(pi/2)=1, full amplitude reached. The amplitude
    is added to base theta, not the absolute angle."""
    pose, _, _, _ = compute_tick(
        {"type": "capsule", "animation": {"mode": "swing", "amplitude_deg": 60, "period_s": 4}},
        {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 30},
        {"radius_mm": 20, "length_mm": 100},
        t=1.0,
    )
    assert pose["theta"] == pytest.approx(90.0)


def test_swing_at_three_quarter_period_reaches_negative_amplitude():
    """At t=3T/4, sin(3pi/2)=-1, theta = base - amplitude."""
    pose, _, _, _ = compute_tick(
        {"type": "capsule", "animation": {"mode": "swing", "amplitude_deg": 45, "period_s": 8}},
        {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        {"radius_mm": 20, "length_mm": 100},
        t=6.0,
    )
    assert pose["theta"] == pytest.approx(-45.0)


def test_swing_preserves_translation_and_orientation_vector():
    """Like spin, swing should only modulate theta; translation and
    (ox, oy, oz) pass through."""
    pose, _, _, _ = compute_tick(
        {"type": "box", "animation": {"mode": "swing", "amplitude_deg": 60, "period_s": 4}},
        {"x": 100, "y": 200, "z": 300, "ox": 0, "oy": 1, "oz": 0, "theta": 0},
        {"dims_mm": {"x": 50, "y": 50, "z": 50}},
        t=1.0,
    )
    assert (pose["x"], pose["y"], pose["z"]) == (100, 200, 300)
    assert (pose["ox"], pose["oy"], pose["oz"]) == (0, 1, 0)


# ---------- spin (continued) ----------

def test_spin_preserves_translation_and_orientation_vector():
    pose, _, _, _ = compute_tick(
        {"type": "box", "animation": {"mode": "spin", "period_s": 4}},
        {"x": 100, "y": 200, "z": 300, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,
    )
    assert (pose["x"], pose["y"], pose["z"]) == (100, 200, 300)
    assert (pose["ox"], pose["oy"], pose["oz"]) == (0, 0, 1)


# ---------- pulse ----------

def test_pulse_on_sphere_modulates_radius():
    _, geom, paths, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "pulse", "amplitude_mm": 20, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=1.0,  # T/4 -> sin = 1, max bulge
    )
    assert geom["radius_mm"] == pytest.approx(70.0)
    assert paths == ["physicalObject.geometryType.value.radiusMm"]


def test_pulse_clamps_radius_above_zero():
    """A pulse amplitude larger than the base radius would otherwise
    drive the radius negative. The viewer would reject a negative
    radius, so we clamp."""
    _, geom, _, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "pulse", "amplitude_mm": 100, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=3.0,  # 3T/4 -> sin = -1, max contraction; would be -50mm
    )
    assert geom["radius_mm"] > 0


def test_pulse_on_capsule_modulates_both_radius_and_length():
    _, geom, paths, _ = compute_tick(
        {"type": "capsule", "animation": {"mode": "pulse", "amplitude_mm": 30, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50, "length_mm": 200},
        t=1.0,
    )
    assert geom["radius_mm"] == pytest.approx(80.0)
    assert geom["length_mm"] == pytest.approx(230.0)
    assert paths == [
        "physicalObject.geometryType.value.radiusMm",
        "physicalObject.geometryType.value.lengthMm",
    ]


def test_pulse_on_box_modulates_all_three_dims():
    _, geom, paths, _ = compute_tick(
        {"type": "box", "animation": {"mode": "pulse", "amplitude_mm": 50, "period_s": 4}},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 200, "z": 300}},
        t=1.0,
    )
    assert geom["dims_mm"]["x"] == pytest.approx(150.0)
    assert geom["dims_mm"]["y"] == pytest.approx(250.0)
    assert geom["dims_mm"]["z"] == pytest.approx(350.0)
    assert paths == [
        "physicalObject.geometryType.value.dimsMm.x",
        "physicalObject.geometryType.value.dimsMm.y",
        "physicalObject.geometryType.value.dimsMm.z",
    ]


def test_pulse_on_unsupported_type_is_noop():
    """point/mesh/pointcloud don't have a sensible scalable dim under
    the field-mask convention — pulse degrades to no-op rather than
    silently corrupting the message."""
    for t in ("point", "mesh", "pointcloud"):
        _, geom, paths, _ = compute_tick(
            {"type": t, "animation": {"mode": "pulse", "amplitude_mm": 25, "period_s": 4}},
            BASE_POSE,
            {"radius_mm": 50},
            t=1.0,
        )
        assert paths == []


# ---------- module surface sanity ----------

# ---------- trajectory ----------

def _trajectory_waypoints():
    """Three-waypoint sample: position-only along Y axis, identity
    orientation throughout. Easy to reason about analytically."""
    return [
        {"x": 0, "y":   0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        {"x": 0, "y": 200, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        {"x": 0, "y": 400, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
    ]


def test_trajectory_at_t_zero_is_at_first_waypoint():
    pose, _, paths, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory",
            "waypoints": _trajectory_waypoints(),
            "duration_s": 4.0,
            "loop": True,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=0.0,
    )
    assert pose["x"] == 0
    assert pose["y"] == pytest.approx(0.0)
    assert pose["z"] == 0
    # Trajectory animation emits all 7 pose paths every tick.
    assert set(paths) == {
        "poseInObserverFrame.pose.x",
        "poseInObserverFrame.pose.y",
        "poseInObserverFrame.pose.z",
        "poseInObserverFrame.pose.oX",
        "poseInObserverFrame.pose.oY",
        "poseInObserverFrame.pose.oZ",
        "poseInObserverFrame.pose.theta",
    }


def test_trajectory_at_midway_through_first_segment():
    """duration=4, 2 segments → 2s per segment. At t=1.0 we should
    be halfway through segment 0: y between waypoints 0 and 1."""
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory",
            "waypoints": _trajectory_waypoints(),
            "duration_s": 4.0,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=1.0,
    )
    assert pose["y"] == pytest.approx(100.0)


def test_trajectory_at_end_of_first_segment_hits_waypoint_one():
    """At t=2.0 (= duration/2), we've finished segment 0 and just
    reached waypoint 1."""
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory",
            "waypoints": _trajectory_waypoints(),
            "duration_s": 4.0,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=2.0,
    )
    assert pose["y"] == pytest.approx(200.0)


def test_trajectory_loops_back_to_start():
    """With loop=True, at t=duration we wrap back to waypoint 0."""
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory",
            "waypoints": _trajectory_waypoints(),
            "duration_s": 4.0,
            "loop": True,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=4.0,  # == duration → wraps to t=0
    )
    assert pose["y"] == pytest.approx(0.0)


def test_trajectory_no_loop_pins_at_final_waypoint():
    """With loop=False, after duration the entity stays at waypoint N-1."""
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory",
            "waypoints": _trajectory_waypoints(),
            "duration_s": 4.0,
            "loop": False,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=10.0,
    )
    assert pose["y"] == pytest.approx(400.0)


def test_trajectory_interpolates_orientation_vector():
    """Two waypoints with different orientation vectors. Halfway
    through, the entity's orientation vector should be the lerp of
    the two, normalized."""
    wps = [
        {"x": 0, "y": 0, "z": 0, "ox": 1, "oy": 0, "oz": 0, "theta": 0},  # local +Z along world +X
        {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},  # local +Z along world +Z
    ]
    pose, _, _, _ = compute_tick(
        {"type": "sphere", "animation": {
            "mode": "trajectory", "waypoints": wps, "duration_s": 2.0,
        }},
        BASE_POSE,
        {"radius_mm": 50},
        t=1.0,
    )
    # Midway: lerp gives (0.5, 0, 0.5), normalized magnitude = sqrt(0.5).
    norm = math.sqrt(pose["ox"] ** 2 + pose["oy"] ** 2 + pose["oz"] ** 2)
    assert norm == pytest.approx(1.0, abs=1e-6)
    # Equal magnitudes for ox and oz, both positive.
    assert pose["ox"] == pytest.approx(pose["oz"])
    assert pose["oy"] == pytest.approx(0.0)
    assert pose["ox"] > 0


# ---------- force_vector ----------

def test_force_vector_modulates_length_radius_orientation_and_emits_color():
    """All four attributes change simultaneously: length, radius,
    orientation vector, and color override. The mode is designed
    for the arrow primitive."""
    base_geom = {"length_mm": 200, "radius_mm": 10}
    pose, geom, paths, meta = compute_tick(
        {"type": "arrow", "animation": {
            "mode": "force_vector",
            "period_s": 4.0,
            "length_amplitude_mm": 60,
            "radius_amplitude_mm": 4,
            "tilt_deg": 45,
        }},
        BASE_POSE,
        base_geom,
        t=1.0,  # T/4 → sin = 1 → max length
    )
    # Length at max excursion: 200 + 60 = 260.
    assert geom["length_mm"] == pytest.approx(260.0)
    # Radius is phase-offset by π/3; sin(π/2 + π/3) = sin(5π/6) = 0.5.
    assert geom["radius_mm"] == pytest.approx(10 + 4 * 0.5, abs=1e-6)
    # Orientation: precession_angle = T/4 * (1 rev / period) = π/2, so
    # tip is at +Y in the cone. ox=sin(45°)·0, oy=sin(45°)·1, oz=cos(45°).
    assert pose["ox"] == pytest.approx(0.0, abs=1e-6)
    assert pose["oy"] == pytest.approx(math.sin(math.radians(45)), abs=1e-6)
    assert pose["oz"] == pytest.approx(math.cos(math.radians(45)))
    # Metadata override contains a color tuple.
    assert meta is not None
    assert "color" in meta
    color = meta["color"]
    assert len(color) == 3
    assert all(0 <= c <= 255 for c in color)
    # Field-mask paths cover all four changing attributes.
    assert "physicalObject.geometryType.value.lengthMm" in paths
    assert "physicalObject.geometryType.value.radiusMm" in paths
    assert "poseInObserverFrame.pose.oX" in paths
    assert "poseInObserverFrame.pose.oY" in paths
    assert "poseInObserverFrame.pose.oZ" in paths
    assert "metadata.color" in paths


def test_force_vector_color_cycles_through_hue():
    """At t=0 hue=0 (red), at t=period_s hue wraps to 0 again. At
    t=period_s/3 hue=1/3 (green-ish)."""
    item = {"type": "arrow", "animation": {
        "mode": "force_vector", "period_s": 6.0,
    }}
    base_geom = {"length_mm": 200, "radius_mm": 10}
    # t=0 → hue 0 → red dominant.
    _, _, _, meta0 = compute_tick(item, BASE_POSE, base_geom, t=0.0)
    color0 = meta0["color"]
    assert color0[0] > color0[1] and color0[0] > color0[2]
    # t = period_s / 3 → hue 1/3 → green dominant.
    _, _, _, meta_third = compute_tick(item, BASE_POSE, base_geom, t=2.0)
    color_third = meta_third["color"]
    assert color_third[1] > color_third[0] and color_third[1] > color_third[2]


def test_force_vector_orientation_traces_a_cone():
    """At any t, the orientation vector should be a unit vector with
    |oz| = cos(tilt). The tip path is a circle at altitude cos(tilt)."""
    item = {"type": "arrow", "animation": {
        "mode": "force_vector", "period_s": 4.0, "tilt_deg": 30,
    }}
    base_geom = {"length_mm": 200, "radius_mm": 10}
    expected_oz = math.cos(math.radians(30))
    for t in (0.0, 0.5, 1.0, 2.5, 3.7):
        pose, _, _, _ = compute_tick(item, BASE_POSE, base_geom, t=t)
        norm = math.sqrt(pose["ox"] ** 2 + pose["oy"] ** 2 + pose["oz"] ** 2)
        assert norm == pytest.approx(1.0, abs=1e-6)
        assert pose["oz"] == pytest.approx(expected_oz, abs=1e-6)


# ---------- pulse with axis param (box single-dim stretching) ----------

def test_pulse_box_axis_z_modulates_only_z_dim():
    """With axis='z', only dimsMm.z changes — the box stretches
    along Z while X and Y stay fixed. Use this for "length grows
    over time" without making the box bloat in all directions."""
    _, geom, paths, _ = compute_tick(
        {"type": "box", "animation": {
            "mode": "pulse", "axis": "z",
            "amplitude_mm": 100, "period_s": 4,
        }},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,  # T/4 → max excursion
    )
    assert geom["dims_mm"]["x"] == 100
    assert geom["dims_mm"]["y"] == 100
    assert geom["dims_mm"]["z"] == pytest.approx(200)
    # Only the z field-mask path is emitted.
    assert paths == ["physicalObject.geometryType.value.dimsMm.z"]


def test_pulse_box_default_axis_all_keeps_isotropic_behavior():
    """Backward compat: with no axis param (or axis='all'), pulse
    on a box modulates all three dims simultaneously — the prior
    behavior."""
    _, geom, _, _ = compute_tick(
        {"type": "box", "animation": {
            "mode": "pulse", "amplitude_mm": 50, "period_s": 4,
        }},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,
    )
    assert geom["dims_mm"]["x"] == pytest.approx(150)
    assert geom["dims_mm"]["y"] == pytest.approx(150)
    assert geom["dims_mm"]["z"] == pytest.approx(150)


# ---------- breathe ----------

def test_breathe_oscillates_opacity_around_base():
    """Opacity = base + amplitude · sin(2π t / period). At t=T/4
    we hit the max excursion; clamped to [0, 1]."""
    item = {"type": "capsule", "opacity": 0.7, "animation": {
        "mode": "breathe", "amplitude": 0.3, "period_s": 4,
    }}
    base_geom = {"radius_mm": 50, "length_mm": 200}
    _, _, paths, meta = compute_tick(item, BASE_POSE, base_geom, t=1.0)
    assert meta is not None
    assert meta["opacity"] == pytest.approx(1.0)  # 0.7 + 0.3 clamped
    assert paths == ["metadata.opacity"]


def test_breathe_clamps_opacity_below_zero():
    """At t=3T/4, sin = -1, so opacity = base - amplitude. Clamp
    keeps it ≥ 0."""
    item = {"type": "capsule", "opacity": 0.2, "animation": {
        "mode": "breathe", "amplitude": 0.4, "period_s": 4,
    }}
    base_geom = {"radius_mm": 50, "length_mm": 200}
    _, _, _, meta = compute_tick(item, BASE_POSE, base_geom, t=3.0)
    # 0.2 - 0.4 = -0.2 → clamp to 0.
    assert meta["opacity"] == pytest.approx(0.0)


# ---------- flicker ----------

def test_flicker_signals_scene_membership_not_opacity():
    """Flicker emits ``_in_scene`` so the service can fire real
    REMOVED/ADDED events. We pin the schema here so a regression
    back to opacity-only (where the entity stayed in the scene but
    just went transparent) fails CI."""
    item = {"type": "sphere", "animation": {
        "mode": "flicker", "period_s": 4.0, "duty_cycle": 0.5,
    }}
    base_geom = {"radius_mm": 30}
    # t=0: phase=0 < 0.5 → in scene.
    _, _, paths_on, meta_on = compute_tick(item, BASE_POSE, base_geom, t=0.0)
    assert meta_on["_in_scene"] is True
    # Paths are empty — REMOVED/ADDED don't use field-mask paths.
    assert paths_on == []
    # opacity isn't part of the override; the service drives
    # visibility via scene-graph operations.
    assert "opacity" not in meta_on
    # t=3: phase = 0.75, not < 0.5 → out of scene.
    _, _, _, meta_off = compute_tick(item, BASE_POSE, base_geom, t=3.0)
    assert meta_off["_in_scene"] is False


def test_flicker_phase_offset_shifts_the_cycle():
    """phase_offset_s lets a row of items with the same period
    flicker out-of-phase, producing a wave of removals/insertions."""
    base_geom = {"radius_mm": 30}
    item_a = {"type": "sphere", "animation": {
        "mode": "flicker", "period_s": 4.0,
    }}
    item_b = {"type": "sphere", "animation": {
        "mode": "flicker", "period_s": 4.0, "phase_offset_s": 2.0,
    }}
    # At t=0: A is in-scene (phase 0), B is out (phase 0.5).
    _, _, _, meta_a = compute_tick(item_a, BASE_POSE, base_geom, t=0.0)
    _, _, _, meta_b = compute_tick(item_b, BASE_POSE, base_geom, t=0.0)
    assert meta_a["_in_scene"] is True
    assert meta_b["_in_scene"] is False


def test_supported_modes_constant():
    assert set(SUPPORTED_MODES) == {
        "none", "orbit", "oscillate", "spin", "swing", "pulse", "trajectory",
        "force_vector", "breathe", "flicker",
    }


def test_supported_axes_constant():
    assert set(SUPPORTED_AXES) == {"x", "y", "z"}
