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
    pose, geom, paths = compute_tick(
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
    pose, _, paths = compute_tick(
        {"type": "sphere", "animation": {"mode": "orbit", "radius_mm": 200, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=0.0,
    )
    assert pose["x"] == pytest.approx(200.0)
    assert pose["y"] == pytest.approx(0.0)
    assert paths == ["poseInObserverFrame.pose.x", "poseInObserverFrame.pose.y"]


def test_orbit_at_quarter_period_lands_on_positive_y_axis():
    pose, _, _ = compute_tick(
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
    pose, _, _ = compute_tick(
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
    pose, _, paths = compute_tick(
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
    pose, _, paths = compute_tick(
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
    pose, _, paths = compute_tick(
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
        pose, _, _ = compute_tick(
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
    pose, _, paths = compute_tick(
        {"type": "capsule", "animation": {"mode": "spin", "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 30, "length_mm": 200},
        t=1.0,
    )
    assert pose["theta"] == pytest.approx(90.0)
    assert paths == ["poseInObserverFrame.pose.theta"]


def test_spin_wraps_modulo_360():
    pose, _, _ = compute_tick(
        {"type": "box", "animation": {"mode": "spin", "period_s": 4}},
        BASE_POSE,
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=4.5,  # 1 full period + T/8 -> 45°
    )
    assert pose["theta"] == pytest.approx(45.0)


def test_spin_preserves_translation_and_orientation_vector():
    pose, _, _ = compute_tick(
        {"type": "box", "animation": {"mode": "spin", "period_s": 4}},
        {"x": 100, "y": 200, "z": 300, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        {"dims_mm": {"x": 100, "y": 100, "z": 100}},
        t=1.0,
    )
    assert (pose["x"], pose["y"], pose["z"]) == (100, 200, 300)
    assert (pose["ox"], pose["oy"], pose["oz"]) == (0, 0, 1)


# ---------- pulse ----------

def test_pulse_on_sphere_modulates_radius():
    _, geom, paths = compute_tick(
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
    _, geom, _ = compute_tick(
        {"type": "sphere", "animation": {"mode": "pulse", "amplitude_mm": 100, "period_s": 4}},
        BASE_POSE,
        {"radius_mm": 50},
        t=3.0,  # 3T/4 -> sin = -1, max contraction; would be -50mm
    )
    assert geom["radius_mm"] > 0


def test_pulse_on_capsule_modulates_both_radius_and_length():
    _, geom, paths = compute_tick(
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
    _, geom, paths = compute_tick(
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
        _, geom, paths = compute_tick(
            {"type": t, "animation": {"mode": "pulse", "amplitude_mm": 25, "period_s": 4}},
            BASE_POSE,
            {"radius_mm": 50},
            t=1.0,
        )
        assert paths == []


# ---------- module surface sanity ----------

def test_supported_modes_constant():
    assert set(SUPPORTED_MODES) == {"none", "orbit", "oscillate", "spin", "pulse"}


def test_supported_axes_constant():
    assert set(SUPPORTED_AXES) == {"x", "y", "z"}
