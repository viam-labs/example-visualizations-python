"""Field-mask path string tests — the load-bearing contract with the
3D scene renderer for the stable-UUID + UPDATED code path.

These strings must match exactly what rdk/services/worldstatestore/fake/
moving_geos_world.go emits, or the viewer silently ignores the update.
The test suite locks in the paths as constants so a typo can't slip in.
"""
from src.animation import (
    PATH_BOX_DIMS_X,
    PATH_BOX_DIMS_Y,
    PATH_BOX_DIMS_Z,
    PATH_CAPSULE_LENGTH,
    PATH_CAPSULE_RADIUS,
    PATH_SPHERE_RADIUS,
    PATH_THETA,
    PATH_X,
    PATH_Y,
    PATH_Z,
)


# Paths the RDK fake uses — these are the contract.
RDK_FAKE_THETA = "poseInObserverFrame.pose.theta"
RDK_FAKE_Y = "poseInObserverFrame.pose.y"
RDK_FAKE_CAPSULE_RADIUS = "physicalObject.geometryType.value.radiusMm"
RDK_FAKE_CAPSULE_LENGTH = "physicalObject.geometryType.value.lengthMm"


def test_theta_path_matches_rdk_fake():
    assert PATH_THETA == RDK_FAKE_THETA


def test_y_path_matches_rdk_fake():
    assert PATH_Y == RDK_FAKE_Y


def test_x_z_paths_are_consistent_with_y():
    """Same prefix as the y path, last segment differs only by axis."""
    assert PATH_X == "poseInObserverFrame.pose.x"
    assert PATH_Z == "poseInObserverFrame.pose.z"


def test_capsule_paths_match_rdk_fake():
    assert PATH_CAPSULE_RADIUS == RDK_FAKE_CAPSULE_RADIUS
    assert PATH_CAPSULE_LENGTH == RDK_FAKE_CAPSULE_LENGTH


def test_sphere_radius_path_uses_oneof_value_prefix():
    """Same shape as capsule.radiusMm — the renderer descends through
    the Geometry oneof using `geometryType.value.<field>` regardless of
    which concrete primitive it is."""
    assert PATH_SPHERE_RADIUS == "physicalObject.geometryType.value.radiusMm"


def test_box_dims_paths_descend_into_dims_mm_substruct():
    assert PATH_BOX_DIMS_X == "physicalObject.geometryType.value.dimsMm.x"
    assert PATH_BOX_DIMS_Y == "physicalObject.geometryType.value.dimsMm.y"
    assert PATH_BOX_DIMS_Z == "physicalObject.geometryType.value.dimsMm.z"
