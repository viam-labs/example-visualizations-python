"""Preset scene definitions — named bundles of items the user can load
via DoCommand or the top-level ``preset`` config field. Each preset is
a function returning a list of item dicts in the same shape as the
``items`` config array. Returning dicts (not protos) keeps presets
serializable for the ``snapshot`` DoCommand round-trip.

Presets:

  - ``primitives``: one of each supported primitive, spaced along X,
    distinct colors, static. This is the default first-install scene.
  - ``color_wheel``: ten spheres arranged around a circle, HSV-swept hue.
  - ``mesh_gallery``: bunny PLY + cube STL + helix point cloud, side by
    side. Useful for inspecting the three "file-asset" primitives at once.
  - ``orientation_vectors``: same arrow mesh replicated at OX/OY/OZ
    permutations with a theta-sweep demo. Arrows (not capsules)
    because the asymmetric shaft+tip geometry makes the pointing
    direction unambiguous; a capsule is rotationally symmetric along
    its length axis and the user can't tell which end is which.
"""
import colorsys
import math
from typing import Any, List, Mapping


PRESET_NAMES = (
    "all",
    "primitives",
    "color_wheel",
    "mesh_gallery",
    "orientation_vectors",
    "reference_frame_demo",
)

# Default spacing between primitives in the row-style preset (mm).
PRIMITIVE_ROW_SPACING_MM = 400.0


def _identity_pose(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Mapping[str, Any]:
    return {"x": x, "y": y, "z": z, "ox": 0, "oy": 0, "oz": 1, "theta": 0}


def primitives() -> List[Mapping[str, Any]]:
    """One of every supported primitive in a row along X. Colors are
    distinct rainbow stops so each primitive is identifiable at a
    glance. All static."""
    sp = PRIMITIVE_ROW_SPACING_MM
    return [
        {
            "type": "box",
            "label": "demo_box",
            "pose": _identity_pose(x=-3 * sp),
            "dims_mm": {"x": 150, "y": 150, "z": 150},
            "color": {"r": 230, "g": 25, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "sphere",
            "label": "demo_sphere",
            "pose": _identity_pose(x=-2 * sp),
            "radius_mm": 90,
            "color": {"r": 60, "g": 180, "b": 75},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "capsule",
            "label": "demo_capsule",
            "pose": _identity_pose(x=-1 * sp),
            "radius_mm": 50,
            "length_mm": 200,
            "color": {"r": 0, "g": 130, "b": 200},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "point",
            "label": "demo_point",
            "pose": _identity_pose(x=0),
            "color": {"r": 255, "g": 225, "b": 25},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "mesh",
            "label": "demo_mesh_ply",
            "pose": _identity_pose(x=1 * sp),
            "mesh_path": "assets/icosahedron.ply",
            "color": {"r": 240, "g": 50, "b": 230},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "mesh",
            "label": "demo_mesh_stl",
            "pose": _identity_pose(x=2 * sp),
            "mesh_path": "assets/cube.stl",
            "color": {"r": 245, "g": 130, "b": 49},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # NOTE: no `color` here on purpose — when metadata.colors is
        # set on a point cloud item, the viewer uses it as a uniform
        # tint and IGNORES the per-point RGB embedded in the PCD body.
        # Omitting color lets the helix's per-point colors render.
        # See LESSONS.md::pcd-colors-precedence.
        {
            "type": "pointcloud",
            "label": "demo_pointcloud",
            "pose": _identity_pose(x=3 * sp),
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


def mesh_gallery() -> List[Mapping[str, Any]]:
    """Three file-asset primitives side by side: PLY mesh, STL mesh,
    binary PCD point cloud."""
    sp = PRIMITIVE_ROW_SPACING_MM
    return [
        {
            "type": "mesh",
            "label": "gallery_ply",
            "pose": _identity_pose(x=-sp),
            "mesh_path": "assets/icosahedron.ply",
            "color": {"r": 220, "g": 220, "b": 220},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        {
            "type": "mesh",
            "label": "gallery_stl",
            "pose": _identity_pose(x=0),
            "mesh_path": "assets/cube.stl",
            "color": {"r": 220, "g": 220, "b": 220},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
        # No `color` so the embedded per-point PCD RGB shows through;
        # metadata.colors would override it with a uniform tint.
        {
            "type": "pointcloud",
            "label": "gallery_pcd",
            "pose": _identity_pose(x=sp),
            "pointcloud_path": "assets/helix.pcd",
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
    ]


def orientation_vectors() -> List[Mapping[str, Any]]:
    """An arrow mesh replicated at axis-aligned orientation vectors so
    the user can see how OX/OY/OZ + theta combine.

    Arrows beat capsules here because a capsule is rotationally
    symmetric along its length axis — you can tell it's lying along
    +X but not which end points which way. The arrow's wide cone tip
    + narrow shaft makes the pointing direction unmistakable.

    The arrow mesh extends along its local +Z axis (see
    ``scripts/generate_assets.py::write_arrow_ply``). The pose's
    orientation vector ``(OX, OY, OZ)`` rotates the local +Z to that
    world direction, so the arrow points in the configured direction.
    """
    base_pose = lambda ox, oy, oz, theta, x: {
        "x": x, "y": 0, "z": 0,
        "ox": ox, "oy": oy, "oz": oz, "theta": theta,
    }
    sp = PRIMITIVE_ROW_SPACING_MM
    mesh_path = "assets/arrow.ply"
    items = []
    # +Z (identity) — arrow points upward.
    items.append({
        "type": "mesh",
        "label": "ov_+Z",
        "pose": base_pose(0, 0, 1, 0, -2 * sp),
        "mesh_path": mesh_path,
        "color": {"r": 60, "g": 180, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +X — arrow points along world +X.
    items.append({
        "type": "mesh",
        "label": "ov_+X",
        "pose": base_pose(1, 0, 0, 0, -sp),
        "mesh_path": mesh_path,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +Y — arrow points along world +Y.
    items.append({
        "type": "mesh",
        "label": "ov_+Y",
        "pose": base_pose(0, 1, 0, 0, 0),
        "mesh_path": mesh_path,
        "color": {"r": 0, "g": 130, "b": 200},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # 45° in XY plane: arrow points equally along X and Y.
    s = 1.0 / math.sqrt(2.0)
    items.append({
        "type": "mesh",
        "label": "ov_+XY",
        "pose": base_pose(s, s, 0, 0, sp),
        "mesh_path": mesh_path,
        "color": {"r": 245, "g": 130, "b": 49},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +Z with theta=45 — same axis as ov_+Z, but rotated 45° around
    # that axis. Highlights that theta is the spin about the
    # orientation vector, not a tilt of it. With the arrow mesh this
    # is visible because the asymmetric cross-section of the cone tip
    # rotates with theta even though the pointing direction doesn't.
    items.append({
        "type": "mesh",
        "label": "ov_+Z_theta45",
        "pose": base_pose(0, 0, 1, 45, 2 * sp),
        "mesh_path": mesh_path,
        "color": {"r": 145, "g": 30, "b": 180},
        "opacity": 1.0,
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

      - orientation_vectors  y = -3600
      - color_wheel          y = -1800
      - primitives           y =     0
      - mesh_gallery         y = +1800
      - reference_frame_demo y = +3600
    """
    row = 1800.0
    items: List[Mapping[str, Any]] = []
    items.extend(_offset_base_items_y(orientation_vectors(), -2 * row))
    items.extend(_offset_base_items_y(color_wheel(), -row))
    items.extend(_offset_base_items_y(primitives(), 0.0))
    items.extend(_offset_base_items_y(mesh_gallery(), row))
    items.extend(_offset_base_items_y(reference_frame_demo(), 2 * row))
    return items


PRESETS = {
    "all": all_preset,
    "primitives": primitives,
    "color_wheel": color_wheel,
    "mesh_gallery": mesh_gallery,
    "orientation_vectors": orientation_vectors,
    "reference_frame_demo": reference_frame_demo,
}


def load(name: str) -> List[Mapping[str, Any]]:
    fn = PRESETS.get(name)
    if fn is None:
        raise ValueError(
            f"unknown preset {name!r}; available: {sorted(PRESETS.keys())}"
        )
    return fn()
