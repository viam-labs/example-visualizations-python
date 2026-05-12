"""Animation modes for the scene-primitives playground.

An item's `animation` block selects a mode and per-mode params. At each
tick, ``compute_tick`` returns the per-item pose + geometry overrides
for time `t` (seconds since the animation started) plus the field-mask
paths the viewer needs to know about in the UPDATED event. Paths match
the conventions used by rdk/services/worldstatestore/fake/moving_geos_world.go:

  - ``poseInObserverFrame.pose.x``, ``...y``, ``...z`` for translation
  - ``poseInObserverFrame.pose.theta`` for in-plane rotation
  - ``physicalObject.geometryType.value.radiusMm`` / ``...lengthMm`` /
    ``...dimsMm.x|y|z`` for dimension modulation

Modes (all parameters in mm and seconds):

  - ``none``: static; never ticks.
  - ``orbit``: rotate position around the local Z axis at ``radius_mm``
    and ``period_s``. Translation only; the geometry itself doesn't
    spin. Useful for sphere/point because they're orientation-agnostic.
  - ``oscillate``: sinusoidal translation along ``axis`` (``x``, ``y``,
    or ``z``) with ``amplitude_mm`` and ``period_s``.
  - ``spin``: rotate the item about its own Z axis at ``period_s``.
    Updates only `theta`. Continuous rotation through 360°. Best for
    "always-on" demos (color wheels, decorative spinners).
  - ``swing``: like ``spin`` but bounded — oscillates `theta` in
    ``[base - amplitude_deg, base + amplitude_deg]`` over `period_s`.
    Use for joints that move through a range of motion (arm joints,
    wrist rotation) rather than spinning continuously in one
    direction.
  - ``pulse``: modulate the primary dimension (radius for sphere /
    capsule / point, dims_mm.x|y|z for box) between
    ``amplitude_mm`` ± ``base``. ``base`` is computed from the item's
    static dim/radius at start time.
  - ``trajectory``: interpolate pose across a list of ``waypoints``.
    Each waypoint is a pose dict (x, y, z, ox, oy, oz, theta). Over
    ``duration_s`` seconds the entity walks from waypoint 0 → 1 → 2
    → ... → N-1, interpolating position linearly and orientation by
    lerping the orientation vector + theta then renormalizing. With
    ``loop: true`` (default) the walk repeats indefinitely; with
    ``loop: false`` the entity stops at the final waypoint.

The animation module is purely functional; the service threads the
elapsed time and base pose in. Tests can pin t to known values.
"""
import math
from typing import Any, Iterable, List, Mapping, Optional, Tuple


# Field-mask paths used in the UPDATED event. These must match the
# renderer's exact conventions or the viewer will silently no-op.
PATH_THETA = "poseInObserverFrame.pose.theta"
PATH_X = "poseInObserverFrame.pose.x"
PATH_Y = "poseInObserverFrame.pose.y"
PATH_Z = "poseInObserverFrame.pose.z"
PATH_SPHERE_RADIUS = "physicalObject.geometryType.value.radiusMm"
PATH_CAPSULE_RADIUS = "physicalObject.geometryType.value.radiusMm"
PATH_CAPSULE_LENGTH = "physicalObject.geometryType.value.lengthMm"
PATH_BOX_DIMS_X = "physicalObject.geometryType.value.dimsMm.x"
PATH_BOX_DIMS_Y = "physicalObject.geometryType.value.dimsMm.y"
PATH_BOX_DIMS_Z = "physicalObject.geometryType.value.dimsMm.z"

SUPPORTED_MODES = (
    "none", "orbit", "oscillate", "spin", "swing", "pulse", "trajectory",
)
SUPPORTED_AXES = ("x", "y", "z")

# Field-mask paths for the orientation vector components. Not used by
# any other mode today; the trajectory mode is the first to interpolate
# the OX/OY/OZ components via UPDATED events. Whether the viewer honors
# these is unverified — the RDK fake only ever updates theta. If the
# trajectory orientation looks frozen mid-segment, switch the item's
# uuid_strategy to "versioned" so the whole pose is re-emitted each tick.
PATH_OX = "poseInObserverFrame.pose.oX"
PATH_OY = "poseInObserverFrame.pose.oY"
PATH_OZ = "poseInObserverFrame.pose.oZ"


def is_animated(item: Mapping[str, Any]) -> bool:
    """True iff this item ticks. Static items are emitted once on
    add/reconfigure and never again."""
    mode = (item.get("animation") or {}).get("mode", "none")
    return mode != "none"


def compute_tick(
    item: Mapping[str, Any],
    base_pose: Mapping[str, float],
    base_geom: Mapping[str, Any],
    t: float,
) -> Tuple[Mapping[str, float], Mapping[str, Any], List[str]]:
    """Compute per-tick overrides for an animated item.

    Args:
      item: the full item config dict; only item["animation"] and
            item["type"] are read.
      base_pose: the static pose dict (x, y, z, ox, oy, oz, theta) the
            item was created with. Animation deltas compose onto this.
      base_geom: shape-specific base dims — for sphere/capsule/point,
            keys are ``radius_mm`` (and ``length_mm`` for capsule); for
            box, key is ``dims_mm`` (a dict {x, y, z}).
      t: seconds since the animation started.

    Returns:
      (new_pose, new_geom, updated_fields)
        new_pose: full pose dict — fields not touched by the animation
                  pass through from base_pose.
        new_geom: geometry overrides keyed the same way as base_geom.
                  Fields not touched pass through.
        updated_fields: ordered list of field-mask paths to set on the
                  UPDATED change event.
    """
    anim = item.get("animation") or {}
    mode = anim.get("mode", "none")
    new_pose = dict(base_pose)
    new_geom = _copy_geom(base_geom)
    paths: List[str] = []

    if mode == "none":
        return new_pose, new_geom, paths

    if mode == "orbit":
        radius_mm = float(anim.get("radius_mm", 100.0))
        period_s = float(anim.get("period_s", 5.0))
        if period_s <= 0:
            period_s = 5.0
        angle = 2 * math.pi * t / period_s
        new_pose["x"] = float(base_pose.get("x", 0.0)) + radius_mm * math.cos(angle)
        new_pose["y"] = float(base_pose.get("y", 0.0)) + radius_mm * math.sin(angle)
        paths = [PATH_X, PATH_Y]
        return new_pose, new_geom, paths

    if mode == "oscillate":
        axis = anim.get("axis", "y")
        if axis not in SUPPORTED_AXES:
            axis = "y"
        amplitude_mm = float(anim.get("amplitude_mm", 100.0))
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        delta = amplitude_mm * math.sin(2 * math.pi * t / period_s)
        new_pose[axis] = float(base_pose.get(axis, 0.0)) + delta
        paths = [
            {"x": PATH_X, "y": PATH_Y, "z": PATH_Z}[axis],
        ]
        return new_pose, new_geom, paths

    if mode == "spin":
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        theta = (360.0 * t / period_s) % 360.0
        new_pose["theta"] = theta
        paths = [PATH_THETA]
        return new_pose, new_geom, paths

    if mode == "swing":
        amplitude_deg = float(anim.get("amplitude_deg", 45.0))
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        base_theta = float(base_pose.get("theta", 0.0))
        theta = base_theta + amplitude_deg * math.sin(2 * math.pi * t / period_s)
        new_pose["theta"] = theta
        paths = [PATH_THETA]
        return new_pose, new_geom, paths

    if mode == "pulse":
        amplitude_mm = float(anim.get("amplitude_mm", 25.0))
        period_s = float(anim.get("period_s", 3.0))
        if period_s <= 0:
            period_s = 3.0
        delta = amplitude_mm * math.sin(2 * math.pi * t / period_s)
        item_type = item.get("type")
        if item_type == "sphere":
            new_geom["radius_mm"] = max(
                0.1, float(base_geom.get("radius_mm", 50.0)) + delta
            )
            paths = [PATH_SPHERE_RADIUS]
        elif item_type == "capsule":
            new_geom["radius_mm"] = max(
                0.1, float(base_geom.get("radius_mm", 50.0)) + delta
            )
            new_geom["length_mm"] = max(
                0.1, float(base_geom.get("length_mm", 200.0)) + delta
            )
            paths = [PATH_CAPSULE_RADIUS, PATH_CAPSULE_LENGTH]
        elif item_type == "box":
            base_dims = base_geom.get("dims_mm", {"x": 100, "y": 100, "z": 100})
            new_dims = {
                "x": max(0.1, float(base_dims.get("x", 100)) + delta),
                "y": max(0.1, float(base_dims.get("y", 100)) + delta),
                "z": max(0.1, float(base_dims.get("z", 100)) + delta),
            }
            new_geom["dims_mm"] = new_dims
            paths = [PATH_BOX_DIMS_X, PATH_BOX_DIMS_Y, PATH_BOX_DIMS_Z]
        else:
            # pulse on point/mesh/pointcloud is a no-op — those have
            # no scalable primary dim under the field-mask convention.
            paths = []
        return new_pose, new_geom, paths

    if mode == "trajectory":
        waypoints = anim.get("waypoints") or []
        if len(waypoints) < 2:
            return new_pose, new_geom, paths
        duration_s = float(anim.get("duration_s", 8.0))
        if duration_s <= 0:
            duration_s = 8.0
        loop = bool(anim.get("loop", True))
        # Progress along the full trajectory, in [0, 1].
        if loop:
            progress = (t % duration_s) / duration_s
        else:
            progress = max(0.0, min(1.0, t / duration_s))
        # Map progress onto segment + alpha within segment.
        n_segments = len(waypoints) - 1
        segment_progress = progress * n_segments
        segment_idx = int(segment_progress)
        if segment_idx >= n_segments:
            segment_idx = n_segments - 1
            alpha = 1.0
        else:
            alpha = segment_progress - segment_idx
        a = waypoints[segment_idx]
        b = waypoints[segment_idx + 1]
        # Position: straight linear interpolation.
        new_pose["x"] = _lerp(a.get("x", 0.0), b.get("x", 0.0), alpha)
        new_pose["y"] = _lerp(a.get("y", 0.0), b.get("y", 0.0), alpha)
        new_pose["z"] = _lerp(a.get("z", 0.0), b.get("z", 0.0), alpha)
        # Orientation vector: lerp components, then renormalize.
        ox = _lerp(a.get("ox", 0.0), b.get("ox", 0.0), alpha)
        oy = _lerp(a.get("oy", 0.0), b.get("oy", 0.0), alpha)
        oz = _lerp(a.get("oz", 1.0), b.get("oz", 1.0), alpha)
        norm = math.sqrt(ox * ox + oy * oy + oz * oz)
        if norm > 1e-9:
            new_pose["ox"] = ox / norm
            new_pose["oy"] = oy / norm
            new_pose["oz"] = oz / norm
        else:
            new_pose["ox"], new_pose["oy"], new_pose["oz"] = 0.0, 0.0, 1.0
        new_pose["theta"] = _lerp(a.get("theta", 0.0), b.get("theta", 0.0), alpha)
        paths = [
            PATH_X, PATH_Y, PATH_Z,
            PATH_OX, PATH_OY, PATH_OZ,
            PATH_THETA,
        ]
        return new_pose, new_geom, paths

    # Unknown mode: treat as static. validate_config should have
    # rejected it before we got here.
    return new_pose, new_geom, paths


def _lerp(a: float, b: float, alpha: float) -> float:
    """Linear interpolation. alpha=0 → a, alpha=1 → b."""
    return a + alpha * (b - a)


def _copy_geom(base_geom: Mapping[str, Any]) -> dict:
    """Shallow copy with a deep copy of nested dims_mm so callers can
    mutate freely without aliasing the base."""
    out = dict(base_geom)
    if "dims_mm" in out and isinstance(out["dims_mm"], Mapping):
        out["dims_mm"] = dict(out["dims_mm"])
    return out
