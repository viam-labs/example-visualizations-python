"""Preset scene definitions — named bundles of items the user can load
via DoCommand or the top-level ``preset`` config field. Each preset is
a function returning a list of item dicts in the same shape as the
``items`` config array. Returning dicts (not protos) keeps presets
serializable for the ``snapshot`` DoCommand round-trip.

Presets:

  - ``primitives``: every supported primitive plus a tour of more
    complex meshes (torus, teapot) and a point cloud. Single row
    along X — the default first-install scene and the canonical
    "show me what this module renders" reference.
  - ``color_wheel``: ten spheres arranged around a circle, HSV-swept hue.
  - ``orientation_vectors``: small sphere markers at axis-aligned
    orientation vectors carrying ``show_axes_helper: True`` so the
    viewer renders an RGB XYZ triad at each entity's origin.
  - ``reference_frame_demo``: chained parent-frame composition probe.
  - ``robot_arm``: stylized articulated arm built from primitives.
  - ``all``: every preset above, stacked along Y. One-stop tour.
"""
import colorsys
import math
from typing import Any, List, Mapping


PRESET_NAMES = (
    "all",
    "primitives",
    "color_wheel",
    "orientation_vectors",
    "reference_frame_demo",
    "robot_arm",
)

# Default spacing between primitives in the row-style preset (mm).
PRIMITIVE_ROW_SPACING_MM = 400.0


def _identity_pose(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Mapping[str, Any]:
    return {"x": x, "y": y, "z": z, "ox": 0, "oy": 0, "oz": 1, "theta": 0}


def primitives() -> List[Mapping[str, Any]]:
    """One of every primitive type plus a tour of more complex meshes
    and a point cloud, in a single row along X. Each item has a
    distinct color so they read clearly at a glance.

    Row layout (left → right):

      demo_box, demo_sphere, demo_capsule, demo_point, demo_arrow,
      demo_icosahedron (PLY), demo_bunny (STL), demo_torus (PLY),
      demo_teapot (PLY), demo_pointcloud (PCD)

    Total span ~3.6 m along X, centered at the origin."""
    sp = PRIMITIVE_ROW_SPACING_MM
    return [
        {
            "type": "box",
            "label": "demo_box",
            "pose": _identity_pose(x=-4 * sp),
            "dims_mm": {"x": 150, "y": 150, "z": 150},
            "color": {"r": 230, "g": 25, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "sphere",
            "label": "demo_sphere",
            "pose": _identity_pose(x=-3 * sp),
            "radius_mm": 90,
            "color": {"r": 60, "g": 180, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "capsule",
            "label": "demo_capsule",
            "pose": _identity_pose(x=-2 * sp),
            "radius_mm": 50,
            "length_mm": 200,
            "color": {"r": 0, "g": 130, "b": 200},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "point",
            "label": "demo_point",
            "pose": _identity_pose(x=-1 * sp),
            "color": {"r": 255, "g": 225, "b": 25},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # Arrow primitive (procedural mesh, asymmetric — direction
        # is unambiguous unlike a capsule).
        {
            "type": "arrow",
            "label": "demo_arrow",
            "pose": _identity_pose(x=0),
            "length_mm": 220,
            "radius_mm": 12,
            "color": {"r": 145, "g": 30, "b": 180},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # PLY mesh — the icosahedron stand-in.
        {
            "type": "mesh",
            "label": "demo_icosahedron",
            "pose": _identity_pose(x=1 * sp),
            "mesh_path": "assets/icosahedron.ply",
            "color": {"r": 240, "g": 50, "b": 230},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # STL mesh — actual Stanford bunny.
        {
            "type": "mesh",
            "label": "demo_bunny",
            "pose": _identity_pose(x=2 * sp),
            "mesh_path": "assets/bunny.stl",
            "color": {"r": 245, "g": 130, "b": 49},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # Procedural torus PLY — "more complex than a primitive shape".
        {
            "type": "mesh",
            "label": "demo_torus",
            "pose": _identity_pose(x=3 * sp),
            "mesh_path": "assets/torus.ply",
            "color": {"r": 70, "g": 240, "b": 240},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # Newell/Utah teapot PLY — the canonical 3D test mesh.
        {
            "type": "mesh",
            "label": "demo_teapot",
            "pose": _identity_pose(x=4 * sp),
            "mesh_path": "assets/teapot.ply",
            "color": {"r": 60, "g": 180, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # NOTE: no `color` on purpose — when metadata.colors is set on
        # a point cloud, the viewer uses it as a uniform tint and
        # IGNORES the per-point RGB embedded in the PCD body. Omitting
        # color lets the helix's per-point colors render.
        # See LESSONS.md::pcd-colors-precedence.
        {
            "type": "pointcloud",
            "label": "demo_pointcloud",
            "pose": _identity_pose(x=5 * sp),
            "pointcloud_path": "assets/helix.pcd",
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
    ]


def color_wheel(count: int = 10, ring_radius_mm: float = 300.0) -> List[Mapping[str, Any]]:
    """``count`` spheres around a circle in the XY plane, hue swept
    uniformly through the color wheel. Visually shows what
    ``metadata.color`` accepts."""
    items = []
    for i in range(count):
        hue = i / count
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        angle = 2 * math.pi * i / count
        items.append({
            "type": "sphere",
            "label": f"wheel_{i:02d}",
            "pose": _identity_pose(
                x=ring_radius_mm * math.cos(angle),
                y=ring_radius_mm * math.sin(angle),
            ),
            "radius_mm": 60,
            "color": {"r": int(255 * r), "g": int(255 * g), "b": int(255 * b)},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        })
    return items


def robot_arm() -> List[Mapping[str, Any]]:
    """Stylized articulated robot arm built from primitives, chained
    via ``parent_frame``. Demonstrates how a kinematic structure
    naturally falls out of the world-state-store API:

      base (cylinder-ish box) → shoulder → upper_arm → elbow → forearm → wrist → end_effector (arrow)

    Each link parents to the previous; an animation on the shoulder
    rotates everything downstream (if the renderer composes through
    chained parents — same probe as ``reference_frame_demo``). A
    Viam-relevant scene for users building real arm modules.
    """
    LINK_RADIUS = 25.0
    BASE_HEIGHT = 80.0
    UPPER_LENGTH = 220.0
    FOREARM_LENGTH = 180.0
    JOINT_RADIUS = 35.0
    EE_LENGTH = 90.0
    items: List[Mapping[str, Any]] = []
    # Base — a stout cylinder (modeled as a capsule for visual
    # interest; could be a box). Spins slowly to drive the chain.
    items.append({
        "type": "capsule",
        "label": "arm_base",
        "pose": _identity_pose(x=0, y=0, z=BASE_HEIGHT / 2),
        "radius_mm": LINK_RADIUS * 1.6,
        "length_mm": BASE_HEIGHT,
        "color": {"r": 70, "g": 70, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "spin", "period_s": 8},
    })
    # Shoulder joint — sphere at top of base.
    items.append({
        "type": "sphere",
        "label": "arm_shoulder",
        "parent_frame": "arm_base",
        # Anchor at the top of the base (capsule centered on its
        # pose, half-height above).
        "pose": {"x": 0, "y": 0, "z": BASE_HEIGHT / 2 + LINK_RADIUS,
                 "ox": 0, "oy": 1, "oz": 0, "theta": 0},
        "radius_mm": JOINT_RADIUS,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # Upper arm — capsule extending out of the shoulder along its
    # local +Z (which, with the shoulder's OY=1 orientation, points
    # in world +Y → makes the arm sweep around as the base spins).
    items.append({
        "type": "capsule",
        "label": "arm_upper",
        "parent_frame": "arm_shoulder",
        "pose": _identity_pose(x=0, y=0, z=UPPER_LENGTH / 2),
        "radius_mm": LINK_RADIUS,
        "length_mm": UPPER_LENGTH,
        "color": {"r": 100, "g": 130, "b": 200},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # Elbow joint — sphere at the far end of the upper arm.
    items.append({
        "type": "sphere",
        "label": "arm_elbow",
        "parent_frame": "arm_upper",
        # The elbow rotates around its own local axis so the forearm
        # swings — slower than the base for a more readable motion.
        "pose": {"x": 0, "y": 0, "z": UPPER_LENGTH / 2 + LINK_RADIUS,
                 "ox": 0, "oy": 1, "oz": 0, "theta": -60},
        "radius_mm": JOINT_RADIUS * 0.8,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "spin", "period_s": 5},
    })
    # Forearm — capsule from elbow outward.
    items.append({
        "type": "capsule",
        "label": "arm_forearm",
        "parent_frame": "arm_elbow",
        "pose": _identity_pose(x=0, y=0, z=FOREARM_LENGTH / 2),
        "radius_mm": LINK_RADIUS * 0.85,
        "length_mm": FOREARM_LENGTH,
        "color": {"r": 100, "g": 180, "b": 110},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # Wrist joint — small sphere at the end of the forearm.
    items.append({
        "type": "sphere",
        "label": "arm_wrist",
        "parent_frame": "arm_forearm",
        "pose": {"x": 0, "y": 0, "z": FOREARM_LENGTH / 2 + LINK_RADIUS * 0.6,
                 "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        "radius_mm": JOINT_RADIUS * 0.65,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # End effector — arrow showing the tool direction. Asymmetric so
    # users can see where the arm is pointing at any tick.
    items.append({
        "type": "arrow",
        "label": "arm_end_effector",
        "parent_frame": "arm_wrist",
        "pose": _identity_pose(z=JOINT_RADIUS * 0.6),
        "length_mm": EE_LENGTH,
        "radius_mm": 7.0,
        "color": {"r": 255, "g": 200, "b": 0},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    return items


def orientation_vectors() -> List[Mapping[str, Any]]:
    """Coordinate frames at axis-aligned orientation vectors.

    Each item is a small sphere host carrying ``show_axes_helper:
    True`` so the viewer renders its built-in RGB XYZ triad at the
    entity's origin, rotated to match the entity's orientation.
    Reading the resulting axes triad tells the user immediately how
    the configured ``(OX, OY, OZ, theta)`` maps to a local frame.

    A coordinate frame is more informative than a single arrow here:
    the user sees all three axes at once and can compare to the
    identity (world) frame. The arrow primitive is great for
    direction; full XYZ helpers are right for orientation.
    """
    base_pose = lambda ox, oy, oz, theta, x: {
        "x": x, "y": 0, "z": 0,
        "ox": ox, "oy": oy, "oz": oz, "theta": theta,
    }
    sp = PRIMITIVE_ROW_SPACING_MM
    # The host sphere is a small partly-transparent marker so the
    # axes triad reads as the primary visual — the sphere just gives
    # the helper something to attach to. Color cycles per item so the
    # user can tell the frames apart from a distance.
    HOST_RADIUS_MM = 18.0
    items = []
    items.append({
        "type": "sphere",
        "label": "frame_+Z",
        "pose": base_pose(0, 0, 1, 0, -2 * sp),
        "radius_mm": HOST_RADIUS_MM,
        "color": {"r": 220, "g": 220, "b": 220},
        "opacity": 0.35,
        "show_axes_helper": True,
        "animation": {"mode": "none"},
    })
    items.append({
        "type": "sphere",
        "label": "frame_+X",
        "pose": base_pose(1, 0, 0, 0, -sp),
        "radius_mm": HOST_RADIUS_MM,
        "color": {"r": 220, "g": 220, "b": 220},
        "opacity": 0.35,
        "show_axes_helper": True,
        "animation": {"mode": "none"},
    })
    items.append({
        "type": "sphere",
        "label": "frame_+Y",
        "pose": base_pose(0, 1, 0, 0, 0),
        "radius_mm": HOST_RADIUS_MM,
        "color": {"r": 220, "g": 220, "b": 220},
        "opacity": 0.35,
        "show_axes_helper": True,
        "animation": {"mode": "none"},
    })
    # 45° in XY plane — local +Z lies between world +X and +Y.
    s = 1.0 / math.sqrt(2.0)
    items.append({
        "type": "sphere",
        "label": "frame_+XY",
        "pose": base_pose(s, s, 0, 0, sp),
        "radius_mm": HOST_RADIUS_MM,
        "color": {"r": 220, "g": 220, "b": 220},
        "opacity": 0.35,
        "show_axes_helper": True,
        "animation": {"mode": "none"},
    })
    # +Z axis with theta=45 — same orientation vector as frame_+Z, but
    # rotated 45° about it. The axes-helper triad should visibly
    # rotate around the Z axis: the +X and +Y arrows of the helper
    # both tilt 45° in the XY plane. Useful for teaching that theta
    # is a spin about the orientation vector, not a tilt of it.
    items.append({
        "type": "sphere",
        "label": "frame_+Z_theta45",
        "pose": base_pose(0, 0, 1, 45, 2 * sp),
        "radius_mm": HOST_RADIUS_MM,
        "color": {"r": 220, "g": 220, "b": 220},
        "opacity": 0.35,
        "show_axes_helper": True,
        "animation": {"mode": "none"},
    })
    return items


def reference_frame_demo() -> List[Mapping[str, Any]]:
    """Compose poses through the Viam reference frame system.

    Emits five items that form a parent-child chain:

      1. ``spinning_frame`` — a small near-transparent sphere at the
         origin that spins around its Z axis. This is the **anchor**;
         other items reference its label as ``parent_frame`` to attach.
      2. ``spinning_frame_axis_x`` (red), ``_axis_y`` (green),
         ``_axis_z`` (blue) — three capsules forming a coordinate
         triad, each parented to ``spinning_frame``. They are static
         relative to the anchor; they spin because the anchor does.
      3. ``spinning_frame_attached_mesh`` — the bunny PLY parented to
         ``spinning_frame``. It also has its own ``spin`` animation,
         so it rotates **both** with the frame and on its own axis.

    This preset is also a renderer-behavior probe: it's the only place
    in this module (or in any other world-state-store reference I
    found in the RDK or viam-labs) where an emitted Transform's
    ``pose_in_observer_frame.reference_frame`` matches the
    ``reference_frame`` of another emitted Transform. If the viewer
    composes through that chain, the axes triad and the mesh both
    orbit the anchor's rotation. If it does not, the children render
    in world space and the demo looks broken.
    """
    axis_length_mm = 200.0
    axis_radius_mm = 12.0
    half = axis_length_mm / 2.0
    return [
        # Anchor. Spinning this frame propagates to its children.
        # show_axes_helper=True tells the viewer to draw its built-in
        # RGB XYZ triad at this entity's origin — a free axes gizmo
        # alongside the explicit colored capsules below, useful for
        # visually confirming the renderer composes through the chain.
        {
            "type": "sphere",
            "label": "spinning_frame",
            "pose": _identity_pose(),
            "radius_mm": 12,
            "color": {"r": 255, "g": 255, "b": 255},
            "opacity": 0.6,
            "show_axes_helper": True,
            "animation": {"mode": "spin", "period_s": 6},
        },
        # +X axis (red).
        {
            "type": "capsule",
            "label": "spinning_frame_axis_x",
            "parent_frame": "spinning_frame",
            "pose": {"x": half, "y": 0, "z": 0,
                     "ox": 1, "oy": 0, "oz": 0, "theta": 0},
            "radius_mm": axis_radius_mm,
            "length_mm": axis_length_mm,
            "color": {"r": 230, "g": 25, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # +Y axis (green).
        {
            "type": "capsule",
            "label": "spinning_frame_axis_y",
            "parent_frame": "spinning_frame",
            "pose": {"x": 0, "y": half, "z": 0,
                     "ox": 0, "oy": 1, "oz": 0, "theta": 0},
            "radius_mm": axis_radius_mm,
            "length_mm": axis_length_mm,
            "color": {"r": 60, "g": 180, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # +Z axis (blue) — capsule's default orientation extends up.
        {
            "type": "capsule",
            "label": "spinning_frame_axis_z",
            "parent_frame": "spinning_frame",
            "pose": {"x": 0, "y": 0, "z": half,
                     "ox": 0, "oy": 0, "oz": 1, "theta": 0},
            "radius_mm": axis_radius_mm,
            "length_mm": axis_length_mm,
            "color": {"r": 0, "g": 130, "b": 200},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # The attached mesh — orbits with the frame AND spins on its
        # own axis at a different rate, so the composition is visible.
        {
            "type": "mesh",
            "label": "spinning_frame_attached_mesh",
            "parent_frame": "spinning_frame",
            "pose": {"x": 350, "y": 0, "z": 0,
                     "ox": 0, "oy": 0, "oz": 1, "theta": 0},
            "mesh_path": "assets/icosahedron.ply",
            "color": {"r": 240, "g": 200, "b": 50},
            "opacity": 1.0,
            "animation": {"mode": "spin", "period_s": 2},
        },
    ]


def _offset_base_items_y(
    items: List[Mapping[str, Any]],
    dy: float,
) -> List[Mapping[str, Any]]:
    """Translate "base" items (those whose ``parent_frame`` is unset
    or ``"world"``) along the Y axis by ``dy``. Items parented to
    another emitted Transform are left alone — they inherit the
    offset through the frame chain (if the renderer composes through
    chained parents). Used by the ``all`` preset to stack other
    presets along Y so their bounding boxes don't overlap visually.
    """
    out: List[Mapping[str, Any]] = []
    for it in items:
        pf = it.get("parent_frame")
        if pf in (None, "", "world"):
            new_pose = dict(it.get("pose") or {})
            new_pose["y"] = float(new_pose.get("y", 0.0)) + dy
            new_it = dict(it)
            new_it["pose"] = new_pose
            out.append(new_it)
        else:
            out.append(dict(it))
    return out


def all_preset() -> List[Mapping[str, Any]]:
    """Every other preset, stacked along Y at ~1.8 m intervals so they
    don't visually collide. Load this once and you've seen every
    primitive, color, orientation convention, and the chained-frame
    composition demo in one viewport.

    Row layout (Y from negative to positive):

      - orientation_vectors  y = -2*row
      - color_wheel          y = -row
      - primitives           y =   0
      - robot_arm            y = +row
      - reference_frame_demo y = +2*row
    """
    row = 1800.0
    items: List[Mapping[str, Any]] = []
    items.extend(_offset_base_items_y(orientation_vectors(), -2 * row))
    items.extend(_offset_base_items_y(color_wheel(), -row))
    items.extend(_offset_base_items_y(primitives(), 0.0))
    items.extend(_offset_base_items_y(robot_arm(), row))
    items.extend(_offset_base_items_y(reference_frame_demo(), 2 * row))
    return items


PRESETS = {
    "all": all_preset,
    "primitives": primitives,
    "color_wheel": color_wheel,
    "orientation_vectors": orientation_vectors,
    "reference_frame_demo": reference_frame_demo,
    "robot_arm": robot_arm,
}


def load(name: str) -> List[Mapping[str, Any]]:
    fn = PRESETS.get(name)
    if fn is None:
        raise ValueError(
            f"unknown preset {name!r}; available: {sorted(PRESETS.keys())}"
        )
    return fn()
