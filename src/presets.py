"""Preset scene definitions — named bundles of items the user can load
via DoCommand or the top-level ``preset`` config field. Each preset is
a function returning a list of item dicts in the same shape as the
``items`` config array. Returning dicts (not protos) keeps presets
serializable for the ``snapshot`` DoCommand round-trip.

Presets:

  - ``primitives``: every supported primitive plus a tour of more
    complex meshes (torus, teapot) and a point cloud. Single row
    along X — the default first-install scene.
  - ``orientation_vectors``: small sphere markers at axis-aligned
    orientation vectors carrying ``show_axes_helper: True`` so the
    viewer renders an RGB XYZ triad at each entity's origin.
  - ``frame_composition``: two chained-parent-frame demos side by
    side. **Spinning frame demo:** anchor sphere + RGB axes triad +
    attached mesh + a ring of hue-swept spheres orbiting the mesh.
    **Arm demo:** articulated kinematic chain with a 2-finger
    gripper. Probes whether the renderer composes poses through
    chained ``parent_frame`` links.
  - ``all``: every preset above, stacked along Y. One-stop tour.

The hue-swept color wheel that used to be a standalone preset now
lives only as children of the spinning anchor inside
``frame_composition``; static-ring demand was low enough that the
duplicate didn't earn its keep.
"""
import colorsys
import math
from typing import Any, List, Mapping


PRESET_NAMES = (
    "all",
    "primitives",
    "orientation_vectors",
    "frame_composition",
    "trajectory_preview",
    "force_vector_demo",
    "geometry_morph",
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
        # Colorful sphere — point cloud, not mesh, because the viewer
        # renders per-point PCD colors but renders meshes with a
        # single uniform tint regardless of how many colors we send
        # in metadata.colors. See LESSONS.md::
        # mesh-metadata-colors-only-uses-first-color for the
        # confirmed-from-empirical-evidence limit. The
        # colorful_sphere.ply asset still exists as a reference for
        # the misbehavior but isn't used in any preset.
        {
            "type": "pointcloud",
            "label": "demo_colorful_sphere",
            "pose": _identity_pose(x=5 * sp),
            "pointcloud_path": "assets/colorful_sphere.pcd",
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
            "pose": _identity_pose(x=6 * sp),
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
    naturally falls out of the world-state-store API.

    Chain (each link parents to the previous):

      arm_base → arm_shoulder → arm_upper → arm_elbow → arm_forearm
        → arm_wrist → claw_palm → {claw_left_finger, claw_right_finger}

    Joint motion uses ``swing`` (bounded RoM) rather than ``spin``
    (continuous rotation) so the arm sweeps back and forth like a
    real teaching example rather than spinning endlessly:

      - arm_base    swings ±75° around Z   (shoulder yaw)
      - arm_elbow   swings ±50° around local axis  (elbow flexion)
      - arm_wrist   swings ±90° around local Z      (tool roll)
      - claw fingers oscillate ±10 mm apart/together (gripper open/close)

    The 2-finger gripper at the end makes the wrist's rotation
    visible: a single arrow would have an invisible roll about its
    own axis, but the parallel fingers visibly rotate as a pair when
    the wrist sweeps. A Viam-relevant scene for users building real
    arm modules.
    """
    LINK_RADIUS = 25.0
    BASE_HEIGHT = 80.0
    UPPER_LENGTH = 220.0
    FOREARM_LENGTH = 180.0
    JOINT_RADIUS = 35.0
    PALM_THICKNESS = 10.0
    FINGER_LENGTH = 70.0
    FINGER_THICKNESS = 8.0
    items: List[Mapping[str, Any]] = []
    # Base — stout capsule, swings on Z (a real base joint never
    # rotates a full revolution; it sweeps through its work envelope).
    items.append({
        "type": "capsule",
        "label": "arm_base",
        "pose": _identity_pose(x=0, y=0, z=BASE_HEIGHT / 2),
        "radius_mm": LINK_RADIUS * 1.6,
        "length_mm": BASE_HEIGHT,
        "color": {"r": 70, "g": 70, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "swing", "amplitude_deg": 75.0, "period_s": 8},
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
    # in world +Y → makes the arm reach forward when the base is at
    # neutral, and sweep around as the base swings).
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
    # Elbow joint — sphere at the far end of the upper arm. Swings
    # in a bounded RoM (real elbows don't spin all the way around).
    items.append({
        "type": "sphere",
        "label": "arm_elbow",
        "parent_frame": "arm_upper",
        "pose": {"x": 0, "y": 0, "z": UPPER_LENGTH / 2 + LINK_RADIUS,
                 "ox": 0, "oy": 1, "oz": 0, "theta": -60},
        "radius_mm": JOINT_RADIUS * 0.8,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "swing", "amplitude_deg": 50.0, "period_s": 5},
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
    # Wrist joint — swings on its local Z (= the forearm direction)
    # so the tool *rolls* about the forearm. A symmetric end-effector
    # (a sphere, a capsule along the same axis) would hide this
    # rotation; the 2-finger claw below makes it visible.
    items.append({
        "type": "sphere",
        "label": "arm_wrist",
        "parent_frame": "arm_forearm",
        "pose": {"x": 0, "y": 0, "z": FOREARM_LENGTH / 2 + LINK_RADIUS * 0.6,
                 "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        "radius_mm": JOINT_RADIUS * 0.65,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "swing", "amplitude_deg": 90.0, "period_s": 6},
    })
    # Claw palm — small flat box mounted on the wrist. Anchors the
    # two fingers; rotates with the wrist's swing.
    items.append({
        "type": "box",
        "label": "claw_palm",
        "parent_frame": "arm_wrist",
        "pose": _identity_pose(z=JOINT_RADIUS * 0.6 + PALM_THICKNESS / 2),
        "dims_mm": {"x": 70.0, "y": 28.0, "z": PALM_THICKNESS},
        "color": {"r": 220, "g": 220, "b": 70},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # Left finger — thin tall box offset to -X of the palm; oscillates
    # in X to open/close. Negative amplitude on x makes "low time"
    # = open (further from center) and "high time" = closed (closer
    # to center); both fingers are in phase so they open and close
    # together. (Right finger uses +amplitude → mirror motion.)
    items.append({
        "type": "box",
        "label": "claw_left_finger",
        "parent_frame": "claw_palm",
        "pose": _identity_pose(
            x=-22.0,
            z=PALM_THICKNESS / 2 + FINGER_LENGTH / 2,
        ),
        "dims_mm": {"x": FINGER_THICKNESS, "y": FINGER_THICKNESS, "z": FINGER_LENGTH},
        "color": {"r": 220, "g": 220, "b": 70},
        "opacity": 1.0,
        "animation": {
            "mode": "oscillate",
            "axis": "x",
            "amplitude_mm": -10.0,
            "period_s": 3,
        },
    })
    items.append({
        "type": "box",
        "label": "claw_right_finger",
        "parent_frame": "claw_palm",
        "pose": _identity_pose(
            x=22.0,
            z=PALM_THICKNESS / 2 + FINGER_LENGTH / 2,
        ),
        "dims_mm": {"x": FINGER_THICKNESS, "y": FINGER_THICKNESS, "z": FINGER_LENGTH},
        "color": {"r": 220, "g": 220, "b": 70},
        "opacity": 1.0,
        "animation": {
            "mode": "oscillate",
            "axis": "x",
            "amplitude_mm": 10.0,
            "period_s": 3,
        },
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
    """Compose poses through the Viam reference frame system across
    three distinct rotation axes.

    Parent-child chain:

      spinning_frame                       (anchor, spin around Z)
      ├─ spinning_frame_axis_x|y|z         (RGB triad — orbits Z with anchor)
      └─ spinning_frame_attached_mesh      (icosahedron — orbits Z with
                                            anchor AND spins on its own Z)
          └─ spinning_frame_wheel_hub      (invisible, OY=1 orientation,
                                            spin around its local Z = Y axis)
              └─ spinning_frame_wheel_NN   (10 hue-swept spheres orbit
                                            in the hub's local XY plane)

    Three independent spins, each around the local +Z of the
    entity carrying the animation:

      1. Anchor spin → drives the axes triad's orbit.
      2. Mesh's own spin → rotates the icosahedron in place at the
         far end of the triad.
      3. Wheel hub's spin → rotates the color wheel ring around the
         ring's own perpendicular axis (i.e., the circle spins
         "around its own axis" rather than around some external
         axis we rotated it into).

    Renderer behavior probe: this is the only place in this module
    (or in any reference world-state-store module I found in the RDK
    or viam-labs) where an emitted Transform's
    ``pose_in_observer_frame.reference_frame`` matches the
    ``reference_frame`` of another emitted Transform — AND the chain
    is now two levels deep (wheel → wheel_hub → mesh → anchor). If
    the viewer composes through both levels, the whole assembly
    moves coherently. If it doesn't, the wheel ring or hub renders
    in world space and the demo looks broken at a specific level.
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
        # Position offset chosen to keep clear of the axes triad
        # (200 mm out) and the orbiting color wheel (220 mm hub
        # radius).
        {
            "type": "mesh",
            "label": "spinning_frame_attached_mesh",
            "parent_frame": "spinning_frame",
            "pose": {"x": 700, "y": 0, "z": 0,
                     "ox": 0, "oy": 0, "oz": 1, "theta": 0},
            "mesh_path": "assets/icosahedron.ply",
            "color": {"r": 240, "g": 200, "b": 50},
            "opacity": 1.0,
            "animation": {"mode": "spin", "period_s": 2},
        },
        # Wheel hub — invisible intermediate parent for the orbiting
        # color wheel. Identity orientation (OZ=1) puts the wheel
        # ring in the hub's local XY plane, and the spin animation
        # rotates around the hub's local Z — i.e., the ring's natural
        # perpendicular. So the visible motion is the circle rotating
        # around its own axis, not around some external axis.
        #
        # The hub stays parented to the mesh so the wheel still
        # orbits the mesh (and inherits the mesh + anchor rotations);
        # the hub adds its OWN spin on top, distinguishing the
        # wheel's motion from inherited parent motion.
        #
        # Tiny radius + opacity 0 keeps the hub invisible. (We don't
        # use `invisible: true` because we haven't verified the
        # viewer keeps an invisible parent's frame in the composition
        # tree.)
        {
            "type": "sphere",
            "label": "spinning_frame_wheel_hub",
            "parent_frame": "spinning_frame_attached_mesh",
            "pose": {"x": 0, "y": 0, "z": 0,
                     "ox": 0, "oy": 0, "oz": 1, "theta": 0},
            "radius_mm": 4,
            "color": {"r": 255, "g": 255, "b": 255},
            "opacity": 0.0,
            "animation": {"mode": "spin", "period_s": 10},
        },
        # Color wheel — children of wheel_hub, ring in hub's local
        # XY plane. As wheel_hub's theta animates, the spheres rotate
        # around the hub's local Z — the perpendicular to their ring
        # plane. The wheel's rotation axis IS the wheel's own axis.
        *_color_wheel_children(
            "spinning_frame_wheel_hub",
            count=10,
            ring_radius_mm=220.0,
            sphere_radius_mm=24.0,
        ),
    ]


def _color_wheel_children(
    parent_label: str,
    count: int = 10,
    ring_radius_mm: float = 300.0,
    sphere_radius_mm: float = 30.0,
    z_mm: float = 0.0,
) -> List[Mapping[str, Any]]:
    """Generate ``count`` small hue-swept spheres in a ring parented to
    ``parent_label``. Sphere positions are in the parent's local XY
    plane; if the parent spins around its Z, the ring orbits with it
    via the frame-composition chain.

    Labels follow ``<parent_label>_wheel_NN`` so duplicates don't
    collide if multiple wheels share a scene.
    """
    items: List[Mapping[str, Any]] = []
    for i in range(count):
        hue = i / count
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        angle = 2 * math.pi * i / count
        items.append({
            "type": "sphere",
            "label": f"{parent_label}_wheel_{i:02d}",
            "parent_frame": parent_label,
            "pose": {
                "x": ring_radius_mm * math.cos(angle),
                "y": ring_radius_mm * math.sin(angle),
                "z": z_mm,
                "ox": 0, "oy": 0, "oz": 1, "theta": 0,
            },
            "radius_mm": sphere_radius_mm,
            "color": {"r": int(255 * r), "g": int(255 * g), "b": int(255 * b)},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        })
    return items


def _offset_base_items(
    items: List[Mapping[str, Any]],
    axis: str,
    delta: float,
) -> List[Mapping[str, Any]]:
    """Translate "base" items (those whose ``parent_frame`` is unset
    or ``"world"``) along ``axis`` by ``delta``. Items parented to
    another emitted Transform are left alone — they inherit the
    offset through the frame chain (if the renderer composes through
    chained parents). Used by combined presets so the included
    sub-presets don't overlap visually.

    For trajectory animations, the waypoint coordinates inside
    ``animation.waypoints`` are shifted too — otherwise the runner
    would walk an un-shifted path while its static base pose was
    translated to a different location, leaving the line and markers
    disconnected from the actual motion.
    """
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis must be x|y|z, got {axis!r}")
    out: List[Mapping[str, Any]] = []
    for it in items:
        pf = it.get("parent_frame")
        new_it = dict(it)
        if pf in (None, "", "world"):
            new_pose = dict(it.get("pose") or {})
            new_pose[axis] = float(new_pose.get(axis, 0.0)) + delta
            new_it["pose"] = new_pose
            anim = it.get("animation") or {}
            if (
                anim.get("mode") == "trajectory"
                and isinstance(anim.get("waypoints"), list)
            ):
                new_anim = dict(anim)
                new_anim["waypoints"] = [
                    {**wp, axis: float(wp.get(axis, 0.0)) + delta}
                    for wp in anim["waypoints"]
                ]
                new_it["animation"] = new_anim
        out.append(new_it)
    return out


def _offset_base_items_y(
    items: List[Mapping[str, Any]],
    dy: float,
) -> List[Mapping[str, Any]]:
    """Backward-compatible alias — delegates to _offset_base_items."""
    return _offset_base_items(items, "y", dy)


def frame_composition() -> List[Mapping[str, Any]]:
    """Two demonstrations of chained ``parent_frame`` composition in
    one row: a spinning frame triad on the left, an articulated robot
    arm on the right. Both depend on the same renderer behavior — a
    child item's ``parent_frame`` matching the ``reference_frame`` of
    another emitted Transform — and so render correctly iff the
    viewer composes through that chain.

    Layout (X axis):

      - spinning_frame demo at x = -1000  (axes triad + attached mesh,
        anchor spins so the children inherit rotation)
      - arm_base demo       at x = +1000  (base + shoulder + upper arm
        + elbow + forearm + wrist + end-effector arrow, kinematic
        chain driven by the spinning base and elbow)
    """
    items: List[Mapping[str, Any]] = []
    items.extend(_offset_base_items(reference_frame_demo(), "x", -1000.0))
    items.extend(_offset_base_items(robot_arm(), "x", 1000.0))
    return items


def all_preset() -> List[Mapping[str, Any]]:
    """Every other preset, stacked along Y at ~1.8 m intervals so they
    don't visually collide. Load this once and you've seen every
    primitive, color, orientation convention, and the chained-frame
    composition demo in one viewport.

    Row layout (Y from negative to positive). Spacing tightened to
    1200 mm; the previous 1800 mm row gap left too much empty space
    between rows.

      - orientation_vectors  y = -row
      - primitives           y =   0
      - geometry_morph       y = +row, x ∈ [0, +1700]
                                 (pulsing sphere, stretching box,
                                  breathing capsule, flickering grid)
      - force_vector_demo    y = +row, x = +2300
                                 (on the morph row — its arrow
                                  changes radius+length+orientation+
                                  color, matching the "geometry &
                                  property changes" theme of the row)
      - frame_composition    y = +2*row, x ∈ [-1000, +1500]
                                 (spinning frame + orbiting wheel + arm)
      - trajectory_preview   y = +2*row, x ∈ [+2500, +3500]
                                 (alongside the arm + spinning frame
                                  on the "moving items" row)
    """
    row = 1200.0
    items: List[Mapping[str, Any]] = []
    items.extend(_offset_base_items_y(orientation_vectors(), -row))
    items.extend(_offset_base_items_y(primitives(), 0.0))
    # Morph row with force_vector tucked in alongside the four
    # geometry/property demos. force_vector demos all four of those
    # categories at once (geometry size + orientation + color), so
    # it belongs visually with the rest of the row.
    items.extend(_offset_base_items_y(geometry_morph(), row))
    fv = _offset_base_items(force_vector_demo(), "x", 2300.0)
    fv = _offset_base_items(fv, "y", row)
    items.extend(fv)
    # Moving-items row: arm + spinning frame + trajectory.
    items.extend(_offset_base_items_y(frame_composition(), 2 * row))
    traj = _offset_base_items(trajectory_preview(), "x", 2500.0)
    traj = _offset_base_items(traj, "y", 2 * row)
    items.extend(traj)
    return items


def trajectory_preview() -> List[Mapping[str, Any]]:
    """Visualize a multi-waypoint trajectory in the 3D scene:

      - a thin blue line drawn as a chain of capsules connecting the
        waypoints (since the world-state-store API has no first-class
        line primitive — see LESSONS.md);
      - a translucent sphere with ``show_axes_helper: True`` at each
        waypoint, oriented along the trajectory tangent, so the user
        sees the planned pose at each setpoint;
      - a brighter sphere (also with axes helper) that animates from
        waypoint 0 through to the last waypoint and loops back via
        the new ``trajectory`` animation mode. At every instant the
        runner's pose is the linear interpolation between the two
        flanking waypoints, so it passes through each setpoint with
        the right rotation.

    The trajectory's positions are an ascending 3D arc — useful as a
    canned demo for "this is what a motion plan preview looks like".
    Each waypoint's orientation is computed as the tangent of the
    centered-difference at that index, so the runner faces along
    the path direction as it travels.
    """
    # Hand-picked positions tracing a smooth ascending arc, plus
    # per-waypoint theta values for visible banking around the
    # tangent direction. The 0 → 120 → 240 → 120 → 0 pattern gives
    # the runner two full rotation halves to traverse — clearly
    # visible per-segment rotation on top of the tangent-aligned
    # facing.
    positions = [
        {"x":    0, "y":    0, "z":    0, "theta":   0},
        {"x":  300, "y":  150, "z":  200, "theta": 120},
        {"x":  500, "y":  300, "z":  300, "theta": 240},
        {"x":  700, "y":  150, "z":  200, "theta": 120},
        {"x": 1000, "y":    0, "z":    0, "theta":   0},
    ]
    waypoints = _waypoints_with_tangent_orientations(positions)

    items: List[Mapping[str, Any]] = []

    # Waypoint markers — small translucent spheres with axes helpers.
    for i, wp in enumerate(waypoints):
        items.append({
            "type": "sphere",
            "label": f"traj_wp_{i:02d}",
            "pose": dict(wp),
            "radius_mm": 18,
            "color": {"r": 200, "g": 200, "b": 220},
            "opacity": 0.45,
            "show_axes_helper": True,
            "animation": {"mode": "none"},
        })

    # Line segments connecting adjacent waypoints — thin capsules
    # whose local +Z is aligned to the segment direction. (The wire
    # format has no first-class line; we synthesize from capsules.)
    for i in range(len(waypoints) - 1):
        a = waypoints[i]
        b = waypoints[i + 1]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        dz = b["z"] - a["z"]
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if seg_len < 1e-6:
            continue
        midpoint = {
            "x": (a["x"] + b["x"]) / 2.0,
            "y": (a["y"] + b["y"]) / 2.0,
            "z": (a["z"] + b["z"]) / 2.0,
        }
        items.append({
            "type": "capsule",
            "label": f"traj_seg_{i:02d}",
            "pose": {
                **midpoint,
                "ox": dx / seg_len,
                "oy": dy / seg_len,
                "oz": dz / seg_len,
                "theta": 0,
            },
            "radius_mm": 5,
            "length_mm": seg_len,
            "color": {"r": 100, "g": 130, "b": 240},
            "opacity": 0.95,
            "animation": {"mode": "none"},
        })

    # The "runner" — moving frame that walks the trajectory and
    # passes through each waypoint with the interpolated rotation.
    # Kept smaller than the original (45 → 28 mm) so it reads as a
    # moving cursor rather than dominating the scene; opacity stays
    # high so the bright red marker is still the focal point.
    items.append({
        "type": "sphere",
        "label": "traj_runner",
        "pose": dict(waypoints[0]),
        "radius_mm": 28,
        "color": {"r": 230, "g": 40, "b": 80},
        "opacity": 0.9,
        "show_axes_helper": True,
        "animation": {
            "mode": "trajectory",
            "waypoints": [dict(wp) for wp in waypoints],
            "duration_s": 12.0,
            "loop": True,
        },
    })

    return items


def geometry_morph() -> List[Mapping[str, Any]]:
    """A row of items demonstrating geometry + metadata animation
    that goes beyond pose:

      - sphere pulsing in radius (the simplest size animation)
      - box stretching along a single axis (length grows / shrinks)
      - capsule breathing in opacity (metadata animation)
      - 5×5 grid of small spheres each flickering on/off with a
        phase-staggered duty cycle, so the grid reads as a wave of
        appearing-and-disappearing dots

    The grid is the showpiece — it exercises both the new flicker
    mode (per-item opacity 0 vs 1 toggling) and a phase-offset
    pattern that gives the row a coordinated rolling appearance.
    """
    items: List[Mapping[str, Any]] = []
    slot_x = 0.0

    # Pulsing sphere.
    items.append({
        "type": "sphere",
        "label": "morph_pulse_sphere",
        "pose": _identity_pose(x=slot_x),
        "radius_mm": 70,
        "color": {"r": 230, "g": 60, "b": 100},
        "opacity": 1.0,
        "animation": {
            "mode": "pulse",
            "amplitude_mm": 35,
            "period_s": 3,
        },
    })
    slot_x += 350

    # Box stretching along Z only (length).
    items.append({
        "type": "box",
        "label": "morph_stretch_box",
        "pose": _identity_pose(x=slot_x),
        "dims_mm": {"x": 100, "y": 100, "z": 150},
        "color": {"r": 100, "g": 180, "b": 230},
        "opacity": 1.0,
        "animation": {
            "mode": "pulse",
            "axis": "z",
            "amplitude_mm": 100,
            "period_s": 4,
        },
    })
    slot_x += 350

    # Capsule breathing in opacity. Period dropped from 4 s to 1.5 s
    # so the change is obvious at a glance — at 4 s the cycle was
    # slow enough to read as "static, ish".
    items.append({
        "type": "capsule",
        "label": "morph_breathe_capsule",
        "pose": _identity_pose(x=slot_x),
        "radius_mm": 45,
        "length_mm": 240,
        "color": {"r": 220, "g": 200, "b": 60},
        "opacity": 0.7,
        "animation": {
            "mode": "breathe",
            "amplitude": 0.55,
            "period_s": 1.5,
        },
    })
    slot_x += 380

    # 5×5 grid of flickering spheres. Phase-offset by grid position
    # so the wave rolls diagonally across the grid.
    grid_n = 5
    grid_spacing = 80.0
    period_s = 4.0
    grid_origin_x = slot_x + 60  # left edge of the grid
    for row_idx in range(grid_n):
        for col_idx in range(grid_n):
            # Diagonal wave: phase advances with (row + col).
            phase_offset = (row_idx + col_idx) / (2 * grid_n - 1) * period_s
            items.append({
                "type": "sphere",
                "label": f"morph_grid_{row_idx}{col_idx}",
                "pose": _identity_pose(
                    x=grid_origin_x + col_idx * grid_spacing,
                    y=row_idx * grid_spacing,
                    z=0,
                ),
                "radius_mm": 22,
                "color": {"r": 80, "g": 200, "b": 140},
                "opacity": 1.0,
                "animation": {
                    "mode": "flicker",
                    "period_s": period_s,
                    "duty_cycle": 0.55,
                    "phase_offset_s": phase_offset,
                },
            })

    return items


def force_vector_demo() -> List[Mapping[str, Any]]:
    """A virtual force vector at the origin — one ``arrow`` primitive
    with the ``force_vector`` animation mode driving all four visible
    attributes simultaneously:

      - ``length_mm`` oscillates ±80 mm around a 220 mm base
      - ``radius_mm`` oscillates ±5 mm around 10 mm, phase-offset
        from length so the arrow's "fatness" isn't synchronized with
        its "magnitude"
      - orientation precesses around world +Z at a fixed 45° tilt
        (the arrow's local +Z traces a cone)
      - metadata color cycles through HSV hue

    Useful for previewing wrench / force vector visualizations in
    motion-planning UIs. Standalone preset; placed alongside the
    arm, spinning frame, and trajectory in the ``all`` row layout.
    """
    return [{
        "type": "arrow",
        "label": "force_vector",
        "pose": _identity_pose(),
        "length_mm": 220,
        "radius_mm": 10,
        "color": {"r": 230, "g": 60, "b": 100},
        "opacity": 1.0,
        "animation": {
            "mode": "force_vector",
            "period_s": 5.0,
            "length_amplitude_mm": 80,
            "radius_amplitude_mm": 5,
            "tilt_deg": 45,
            "precession_speed": 1.0,
            "color_speed": 0.7,
        },
    }]


def _waypoints_with_tangent_orientations(
    positions: List[Mapping[str, float]],
) -> List[Mapping[str, Any]]:
    """Given a list of position waypoints, attach an orientation
    vector so the entity's local +Z points along the trajectory
    tangent at that waypoint. Tangents are centered differences in
    the interior; forward / backward differences at the endpoints.

    Any ``theta`` field in the input passes through unchanged (defaults
    to 0). theta supplies a "banking" rotation around the tangent —
    useful for making the runner visibly rotate between waypoints
    when the tangent direction itself doesn't change much."""
    n = len(positions)
    out: List[Mapping[str, Any]] = []
    for i, p in enumerate(positions):
        if i == 0:
            tx = positions[1]["x"] - p["x"]
            ty = positions[1]["y"] - p["y"]
            tz = positions[1]["z"] - p["z"]
        elif i == n - 1:
            tx = p["x"] - positions[i - 1]["x"]
            ty = p["y"] - positions[i - 1]["y"]
            tz = p["z"] - positions[i - 1]["z"]
        else:
            tx = positions[i + 1]["x"] - positions[i - 1]["x"]
            ty = positions[i + 1]["y"] - positions[i - 1]["y"]
            tz = positions[i + 1]["z"] - positions[i - 1]["z"]
        norm = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
        out.append({
            "x": float(p["x"]),
            "y": float(p["y"]),
            "z": float(p["z"]),
            "ox": tx / norm,
            "oy": ty / norm,
            "oz": tz / norm,
            "theta": float(p.get("theta", 0.0)),
        })
    return out


PRESETS = {
    "all": all_preset,
    "primitives": primitives,
    "orientation_vectors": orientation_vectors,
    "frame_composition": frame_composition,
    "trajectory_preview": trajectory_preview,
    "force_vector_demo": force_vector_demo,
    "geometry_morph": geometry_morph,
}


def load(name: str) -> List[Mapping[str, Any]]:
    fn = PRESETS.get(name)
    if fn is None:
        raise ValueError(
            f"unknown preset {name!r}; available: {sorted(PRESETS.keys())}"
        )
    return fn()
