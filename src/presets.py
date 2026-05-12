"""Preset scene definitions — named bundles of items the user can load
via DoCommand or the top-level ``preset`` config field. Each preset is
a function returning a list of item dicts in the same shape as the
``items`` config array. Returning dicts (not protos) keeps presets
serializable for the ``snapshot`` DoCommand round-trip.

Presets:

  - ``all_primitives``: one of each supported primitive, spaced along X,
    distinct colors, static. This is the default first-install scene.
  - ``color_wheel``: ten spheres arranged around a circle, HSV-swept hue.
  - ``mesh_gallery``: bunny PLY + cube STL + helix point cloud, side by
    side. Useful for inspecting the three "file-asset" primitives at once.
  - ``orientation_vectors``: same capsule replicated at OX/OY/OZ
    permutations with theta sweeps — teaches Viam's orientation-vector
    convention by showing what each axis does.
"""
import colorsys
import math
from typing import Any, List, Mapping


PRESET_NAMES = (
    "all_primitives",
    "color_wheel",
    "mesh_gallery",
    "orientation_vectors",
)

# Default spacing between primitives in the row-style preset (mm).
PRIMITIVE_ROW_SPACING_MM = 400.0


def _identity_pose(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Mapping[str, Any]:
    return {"x": x, "y": y, "z": z, "ox": 0, "oy": 0, "oz": 1, "theta": 0}


def all_primitives() -> List[Mapping[str, Any]]:
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
            "mesh_path": "assets/bunny.ply",
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
        {
            "type": "pointcloud",
            "label": "demo_pointcloud",
            "pose": _identity_pose(x=3 * sp),
            "pointcloud_path": "assets/helix.pcd",
            "color": {"r": 70, "g": 240, "b": 240},
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
            "mesh_path": "assets/bunny.ply",
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
        {
            "type": "pointcloud",
            "label": "gallery_pcd",
            "pose": _identity_pose(x=sp),
            "pointcloud_path": "assets/helix.pcd",
            "color": {"r": 220, "g": 220, "b": 220},
            "opacity": 1.0,
            "animation": {"mode": "none"},
        },
    ]


def orientation_vectors() -> List[Mapping[str, Any]]:
    """The same capsule replicated at axis-aligned orientation vectors
    so the user can see how OX/OY/OZ + theta combine. The capsule's
    length axis is the most legible primitive for this — sphere is
    rotation-invariant, box requires reading dim labels."""
    base_pose = lambda ox, oy, oz, theta, x: {
        "x": x, "y": 0, "z": 0,
        "ox": ox, "oy": oy, "oz": oz, "theta": theta,
    }
    items = []
    sp = PRIMITIVE_ROW_SPACING_MM
    # +Z (identity) — capsule extends upward.
    items.append({
        "type": "capsule",
        "label": "ov_+Z",
        "pose": base_pose(0, 0, 1, 0, -2 * sp),
        "radius_mm": 35,
        "length_mm": 250,
        "color": {"r": 60, "g": 180, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +X — capsule extends along world X.
    items.append({
        "type": "capsule",
        "label": "ov_+X",
        "pose": base_pose(1, 0, 0, 90, -sp),
        "radius_mm": 35,
        "length_mm": 250,
        "color": {"r": 230, "g": 25, "b": 75},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +Y — capsule extends along world Y.
    items.append({
        "type": "capsule",
        "label": "ov_+Y",
        "pose": base_pose(0, 1, 0, 90, 0),
        "radius_mm": 35,
        "length_mm": 250,
        "color": {"r": 0, "g": 130, "b": 200},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # 45° in XY: OX=OY=1/sqrt(2). Same OZ=0 plane but tilted.
    s = 1.0 / math.sqrt(2.0)
    items.append({
        "type": "capsule",
        "label": "ov_+XY",
        "pose": base_pose(s, s, 0, 90, sp),
        "radius_mm": 35,
        "length_mm": 250,
        "color": {"r": 245, "g": 130, "b": 49},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    # +Z with theta=45 — same axis, in-plane rotation. Highlights that
    # theta is the spin around the orientation vector, not a tilt.
    items.append({
        "type": "capsule",
        "label": "ov_+Z_theta45",
        "pose": base_pose(0, 0, 1, 45, 2 * sp),
        "radius_mm": 35,
        "length_mm": 250,
        "color": {"r": 145, "g": 30, "b": 180},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    })
    return items


PRESETS = {
    "all_primitives": all_primitives,
    "color_wheel": color_wheel,
    "mesh_gallery": mesh_gallery,
    "orientation_vectors": orientation_vectors,
}


def load(name: str) -> List[Mapping[str, Any]]:
    fn = PRESETS.get(name)
    if fn is None:
        raise ValueError(
            f"unknown preset {name!r}; available: {sorted(PRESETS.keys())}"
        )
    return fn()
