"""Animation modes for the example-visualizations-python playground.

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
  - ``force_vector``: simulate a virtual force arrow with all four
    visible attributes changing — ``length_mm``, ``radius_mm``,
    orientation (precesses around world +Z at a fixed ``tilt_deg``),
    and metadata color (hue cycles through HSV). Designed for the
    ``arrow`` primitive type. Params: ``period_s`` (base time unit),
    ``length_amplitude_mm`` (length oscillates ±this around base),
    ``radius_amplitude_mm`` (radius oscillates ±this), ``tilt_deg``
    (cone half-angle the arrow's local +Z traces), ``precession_speed``
    (orientation revolutions per ``period_s``, default 1), and
    ``color_speed`` (HSV hue revolutions per ``period_s``, default 1).

The animation module is purely functional; the service threads the
elapsed time and base pose in. Tests can pin t to known values.
"""
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


# Field-mask paths used in the UPDATED event. The official
# worldstatestore guide says these should be snake_case proto field
# names, BUT empirically the renderer at this commit only honors the
# camelCase variants the RDK fake uses
# (rdk/services/worldstatestore/fake/moving_geos_world.go:207,228,255).
# Snake_case paths cause the viewer to silently drop every UPDATED
# event — verified by trying it in 0.0.32: animations stopped
# entirely. Filed as bug #13 with the viz team; reverting to
# camelCase until the renderer accepts snake_case.
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
    "force_vector", "breathe", "flicker", "lifecycle",
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

# Metadata field-mask paths. The RDK fake uses nested
# "metadata.color" / "metadata.opacity". Sticking with that —
# coarse "metadata" was untested and the 0.0.32 try of snake_case
# already burned us.
PATH_METADATA_COLOR = "metadata.color"
PATH_METADATA_OPACITY = "metadata.opacity"


# Lifecycle convention colors from the official worldstatestore guide:
# blue at 50% opacity → "appearing", orange at 100% → "alive", red at
# 50% → "disappearing", then absent ("gone"). The viewer uses no
# special rendering for these — they're just a color-coding convention
# that helps human viewers read the lifecycle phase of an entity at a
# glance. Codifying them here keeps the convention reusable across
# presets and downstream modules.
LIFECYCLE_COLOR_APPEARING = (66, 165, 245)
LIFECYCLE_COLOR_ALIVE = (255, 152, 0)
LIFECYCLE_COLOR_DISAPPEARING = (244, 67, 54)
LIFECYCLE_OPACITY_APPEARING = 0.5
LIFECYCLE_OPACITY_ALIVE = 1.0
LIFECYCLE_OPACITY_DISAPPEARING = 0.5


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
) -> Tuple[Mapping[str, float], Mapping[str, Any], List[str], Optional[Dict[str, Any]]]:
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
      (new_pose, new_geom, updated_fields, metadata_overrides)
        new_pose: full pose dict — fields not touched by the animation
                  pass through from base_pose.
        new_geom: geometry overrides keyed the same way as base_geom.
                  Fields not touched pass through.
        updated_fields: ordered list of field-mask paths to set on the
                  UPDATED change event.
        metadata_overrides: ``None`` to leave item metadata
                  (color/opacity/etc) alone, or a dict whose keys
                  override the item's static metadata for this tick.
                  Supported keys: ``"color"`` → ``(r, g, b)`` tuple;
                  ``"opacity"`` → float in ``[0, 1]``. The service
                  rebuilds metadata + emits the matching field-mask
                  paths when these keys are present.
    """
    anim = item.get("animation") or {}
    mode = anim.get("mode", "none")
    new_pose = dict(base_pose)
    new_geom = _copy_geom(base_geom)
    paths: List[str] = []

    if mode == "none":
        return new_pose, new_geom, paths, None

    if mode == "orbit":
        radius_mm = float(anim.get("radius_mm", 100.0))
        period_s = float(anim.get("period_s", 5.0))
        if period_s <= 0:
            period_s = 5.0
        angle = 2 * math.pi * t / period_s
        new_pose["x"] = float(base_pose.get("x", 0.0)) + radius_mm * math.cos(angle)
        new_pose["y"] = float(base_pose.get("y", 0.0)) + radius_mm * math.sin(angle)
        paths = [PATH_X, PATH_Y]
        return new_pose, new_geom, paths, None

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
        return new_pose, new_geom, paths, None

    if mode == "spin":
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        theta = (360.0 * t / period_s) % 360.0
        new_pose["theta"] = theta
        paths = [PATH_THETA]
        return new_pose, new_geom, paths, None

    if mode == "swing":
        amplitude_deg = float(anim.get("amplitude_deg", 45.0))
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        base_theta = float(base_pose.get("theta", 0.0))
        theta = base_theta + amplitude_deg * math.sin(2 * math.pi * t / period_s)
        new_pose["theta"] = theta
        paths = [PATH_THETA]
        return new_pose, new_geom, paths, None

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
            # Optional `axis` param targets just one dimension (the
            # "length grows over time" case for box). Default "all"
            # modulates all three together.
            box_axis = anim.get("axis", "all")
            base_dims = base_geom.get("dims_mm", {"x": 100, "y": 100, "z": 100})
            new_dims = {
                "x": float(base_dims.get("x", 100)),
                "y": float(base_dims.get("y", 100)),
                "z": float(base_dims.get("z", 100)),
            }
            if box_axis in ("x", "y", "z"):
                new_dims[box_axis] = max(0.1, new_dims[box_axis] + delta)
                paths = [
                    {"x": PATH_BOX_DIMS_X, "y": PATH_BOX_DIMS_Y, "z": PATH_BOX_DIMS_Z}[box_axis],
                ]
            else:
                new_dims["x"] = max(0.1, new_dims["x"] + delta)
                new_dims["y"] = max(0.1, new_dims["y"] + delta)
                new_dims["z"] = max(0.1, new_dims["z"] + delta)
                paths = [PATH_BOX_DIMS_X, PATH_BOX_DIMS_Y, PATH_BOX_DIMS_Z]
            new_geom["dims_mm"] = new_dims
        else:
            # pulse on point/mesh/pointcloud is a no-op — those have
            # no scalable primary dim under the field-mask convention.
            paths = []
        return new_pose, new_geom, paths, None

    if mode == "trajectory":
        waypoints = anim.get("waypoints") or []
        if len(waypoints) < 2:
            return new_pose, new_geom, paths, None
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
        return new_pose, new_geom, paths, None

    if mode == "force_vector":
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        # Phase of the base sinusoid.
        phase = 2 * math.pi * t / period_s
        # Length oscillates ±length_amplitude_mm around base length.
        length_amp = float(anim.get("length_amplitude_mm", 60.0))
        base_length = float(base_geom.get("length_mm", 200.0))
        new_geom["length_mm"] = max(0.1, base_length + length_amp * math.sin(phase))
        # Radius oscillates with a phase offset so the "fattening" isn't
        # in sync with the "lengthening" — looks more like a real force
        # changing two independent quantities.
        radius_amp = float(anim.get("radius_amplitude_mm", 4.0))
        base_radius = float(base_geom.get("radius_mm", 10.0))
        new_geom["radius_mm"] = max(
            0.1, base_radius + radius_amp * math.sin(phase + math.pi / 3)
        )
        # Orientation: precess around world +Z at a fixed cone half-
        # angle (``tilt_deg``). The arrow's tip traces a circle at
        # altitude cos(tilt). precession_speed scales the precession
        # rate relative to period_s (1 revolution per period_s by
        # default).
        tilt_rad = math.radians(float(anim.get("tilt_deg", 45.0)))
        precession_speed = float(anim.get("precession_speed", 1.0))
        precession_angle = phase * precession_speed
        new_pose["ox"] = math.sin(tilt_rad) * math.cos(precession_angle)
        new_pose["oy"] = math.sin(tilt_rad) * math.sin(precession_angle)
        new_pose["oz"] = math.cos(tilt_rad)
        new_pose["theta"] = 0.0
        # Color: cycle the hue through HSV at color_speed revolutions
        # per period_s. Full saturation, full value — bright rainbow.
        color_speed = float(anim.get("color_speed", 1.0))
        hue = (t * color_speed / period_s) % 1.0
        color_override = _hsv_to_rgb_u8(hue, 1.0, 1.0)
        paths = [
            PATH_CAPSULE_LENGTH,
            PATH_SPHERE_RADIUS,
            PATH_OX, PATH_OY, PATH_OZ,
            PATH_THETA,
            PATH_METADATA_COLOR,
        ]
        return new_pose, new_geom, paths, {"color": color_override}

    if mode == "breathe":
        # Opacity oscillates smoothly between (base - amplitude) and
        # (base + amplitude), clamped to [0, 1]. base is the item's
        # static opacity (default 1.0 if unset). Used for "fading in
        # and out" demos where geometry stays put but visibility
        # pulses.
        period_s = float(anim.get("period_s", 4.0))
        if period_s <= 0:
            period_s = 4.0
        amplitude = float(anim.get("amplitude", 0.4))
        base_opacity = float(
            (item.get("opacity") if item.get("opacity") is not None else 1.0)
        )
        opacity = base_opacity + amplitude * math.sin(2 * math.pi * t / period_s)
        opacity = max(0.0, min(1.0, opacity))
        paths = [PATH_METADATA_OPACITY]
        return new_pose, new_geom, paths, {"opacity": opacity}

    if mode == "lifecycle":
        # Four-phase entity lifecycle following the official
        # worldstatestore color convention. Each phase has its own
        # duration; the entity cycles through them indefinitely (with
        # `loop` true, default) or stops in the "gone" phase. The
        # "gone" phase emits a REMOVED change (via the same
        # `_in_scene` mechanic flicker uses) so the entity actually
        # leaves the scene rather than just turning transparent.
        appear_s = float(anim.get("appear_s", 1.0))
        alive_s = float(anim.get("alive_s", 2.0))
        disappear_s = float(anim.get("disappear_s", 1.0))
        gone_s = float(anim.get("gone_s", 2.0))
        phase_offset_s = float(anim.get("phase_offset_s", 0.0))
        loop = bool(anim.get("loop", True))
        period_s = appear_s + alive_s + disappear_s + gone_s
        if period_s <= 0:
            return new_pose, new_geom, [], None
        if loop:
            phase_t = (t + phase_offset_s) % period_s
        else:
            phase_t = min(t + phase_offset_s, period_s)
        if phase_t < appear_s:
            color = LIFECYCLE_COLOR_APPEARING
            opacity = LIFECYCLE_OPACITY_APPEARING
            in_scene = True
        elif phase_t < appear_s + alive_s:
            color = LIFECYCLE_COLOR_ALIVE
            opacity = LIFECYCLE_OPACITY_ALIVE
            in_scene = True
        elif phase_t < appear_s + alive_s + disappear_s:
            color = LIFECYCLE_COLOR_DISAPPEARING
            opacity = LIFECYCLE_OPACITY_DISAPPEARING
            in_scene = True
        else:
            # Gone phase: signal REMOVED via _in_scene=False. Color and
            # opacity values don't matter (no transform is emitted).
            color = LIFECYCLE_COLOR_DISAPPEARING
            opacity = 0.0
            in_scene = False
        paths = [PATH_METADATA_COLOR, PATH_METADATA_OPACITY]
        return new_pose, new_geom, paths, {
            "_in_scene": in_scene,
            "color": color,
            "opacity": opacity,
        }

    if mode == "flicker":
        # True scene-graph mutation — the entity is actually REMOVED
        # from the world state when it should be gone and ADDED back
        # when it should be visible, not just made transparent. We
        # signal this via a special ``_in_scene`` key in the metadata
        # override; the service tick interprets the transition and
        # emits REMOVED / ADDED change events accordingly (and
        # ``list_uuids``/``get_transform``/``stream_transform_changes``
        # filter the entity out while it's "removed").
        #
        # period_s is one full off→on cycle; duty_cycle is the fraction
        # of the cycle the entity is in the scene. phase_offset_s
        # shifts the cycle so a grid of items with the same period
        # but different offsets reads as a wave of insertions and
        # removals.
        period_s = float(anim.get("period_s", 3.0))
        if period_s <= 0:
            period_s = 3.0
        duty_cycle = max(0.0, min(1.0, float(anim.get("duty_cycle", 0.5))))
        phase_offset_s = float(anim.get("phase_offset_s", 0.0))
        phase = ((t + phase_offset_s) % period_s) / period_s
        in_scene = phase < duty_cycle
        # Empty paths — REMOVED/ADDED don't use field-mask paths, the
        # service handles transitions specially.
        paths: List[str] = []
        return new_pose, new_geom, paths, {"_in_scene": in_scene}

    # Unknown mode: treat as static. validate_config should have
    # rejected it before we got here.
    return new_pose, new_geom, paths, None


def _hsv_to_rgb_u8(h: float, s: float, v: float) -> Tuple[int, int, int]:
    """HSV (each in [0, 1]) → (R, G, B) bytes in [0, 255]."""
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p = v * (1 - s)
    q = v * (1 - s * f)
    tt = v * (1 - s * (1 - f))
    if i == 0:
        r, g, b = v, tt, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, tt
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = tt, p, v
    else:
        r, g, b = v, p, q
    return (int(r * 255) & 0xFF, int(g * 255) & 0xFF, int(b * 255) & 0xFF)


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
