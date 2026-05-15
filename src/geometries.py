"""Service-side geometry builders.

Turns the item dicts the service consumes into ``commonpb.Geometry``
protos. This is the bridge between the library's typed scene objects
(produced by ``viam_visuals``) and the WorldStateStore wire format.

The pure asset I/O — PLY/STL/PCD parsers, the metadata Struct
builder, the procedural arrow generator — lives in
``viam_visuals._internal``. This module keeps the small set of
viam-proto-emitting builders that need to be co-located with the
service, plus a thin file-system helper for reading assets from the
module directory.

The functions imported from ``viam_visuals._internal`` are re-exported
under their original names so existing call sites in tests and scripts
continue to work unchanged.
"""

from pathlib import Path
from typing import Any, Mapping

from viam.proto.common import (
    Capsule,
    Geometry,
    Mesh,
    Pose,
    PointCloud,
    RectangularPrism,
    Sphere,
    Vector3,
)

# Re-export from the library. These all used to live in this module;
# they moved into viam_visuals/_internal as part of the library
# extraction. Aliases keep existing imports working.
from viam_visuals._internal.constants import (
    POINT_MARKER_RADIUS_MM,
    RENDERER_MESH_CONTENT_TYPE,
    SUPPORTED_MESH_CONTENT_TYPES,
)
from viam_visuals._internal.mesh import (
    arrow_ply_bytes,
    extract_ply_vertex_colors,
    infer_mesh_content_type,
    load_mesh_bytes_as_ply,
    ply_ascii_bytes as _ply_ascii_bytes,
    stl_to_ply,
)
from viam_visuals._internal.metadata import (
    build_metadata,
    clamp_u8 as _clamp_u8,
)
from viam_visuals._internal.pcd import (
    build_pcd_chunk,
    parse_pcd_binary,
)


SUPPORTED_TYPES = ("box", "sphere", "capsule", "point", "arrow", "mesh", "pointcloud")


def build_pose(pose: Mapping[str, Any]) -> Pose:
    """Build a viam ``Pose`` proto from a config dict. All fields
    optional; missing fields default to identity (OZ=1)."""
    if not pose:
        pose = {}
    o_z = pose.get("oz", 1.0 if not any(k in pose for k in ("ox", "oy")) else 0.0)
    return Pose(
        x=float(pose.get("x", 0.0)),
        y=float(pose.get("y", 0.0)),
        z=float(pose.get("z", 0.0)),
        o_x=float(pose.get("ox", 0.0)),
        o_y=float(pose.get("oy", 0.0)),
        o_z=float(o_z),
        theta=float(pose.get("theta", 0.0)),
    )


def build_box(dims_mm: Mapping[str, Any], label: str) -> Geometry:
    return Geometry(
        label=label,
        box=RectangularPrism(dims_mm=Vector3(
            x=float(dims_mm["x"]),
            y=float(dims_mm["y"]),
            z=float(dims_mm["z"]),
        )),
    )


def build_sphere(radius_mm: float, label: str) -> Geometry:
    return Geometry(
        label=label,
        sphere=Sphere(radius_mm=float(radius_mm)),
    )


def build_capsule(radius_mm: float, length_mm: float, label: str) -> Geometry:
    return Geometry(
        label=label,
        capsule=Capsule(
            radius_mm=float(radius_mm),
            length_mm=float(length_mm),
        ),
    )


def build_arrow(length_mm: float, radius_mm: float, label: str) -> Geometry:
    """First-class arrow primitive — procedurally builds a PLY mesh
    and embeds it as a Mesh geometry. Arrow points along local +Z."""
    ply = arrow_ply_bytes(length_mm=length_mm, shaft_radius_mm=radius_mm)
    return Geometry(
        label=label,
        mesh=Mesh(content_type=RENDERER_MESH_CONTENT_TYPE, mesh=ply),
    )


def build_point(label: str) -> Geometry:
    """Marker point — a sphere with a small but visible radius. The
    Geometry oneof has no Point variant, and the viewer skips
    zero-radius geometries; ``POINT_MARKER_RADIUS_MM`` gives the
    primitive a visible footprint."""
    return Geometry(
        label=label,
        sphere=Sphere(radius_mm=POINT_MARKER_RADIUS_MM),
    )


def build_mesh(
    mesh_bytes: bytes,
    content_type: str,
    label: str,
    allow_non_ply: bool = False,
) -> Geometry:
    """Embed mesh bytes into a Geometry.

    ``content_type`` must be ``"ply"`` for the viewer to render the
    geometry. STL input is converted to PLY first via
    :func:`stl_to_ply` (callers go through :func:`load_mesh_bytes_as_ply`
    which dispatches on file extension).

    ``allow_non_ply=True`` is an explicit opt-out for the playground's
    ``raw_stl`` bug-demo (which intentionally ships STL bytes with
    ``content_type="stl"`` to surface the viewer's silent-drop
    behavior). Production callers should leave it ``False``.
    """
    if not allow_non_ply and content_type != RENDERER_MESH_CONTENT_TYPE:
        raise ValueError(
            f"build_mesh requires content_type {RENDERER_MESH_CONTENT_TYPE!r}; "
            f"got {content_type!r}. STL must be converted via stl_to_ply first."
        )
    return Geometry(
        label=label,
        mesh=Mesh(content_type=content_type, mesh=mesh_bytes),
    )


def build_pointcloud(pcd_bytes: bytes, label: str) -> Geometry:
    """Embed PCD bytes into a Geometry. Use PCDBinary format — ASCII
    and binary_compressed have not been verified against the viewer."""
    return Geometry(
        label=label,
        pointcloud=PointCloud(point_cloud=pcd_bytes),
    )


def read_asset(asset_path: str, module_dir: Path) -> bytes:
    """Resolve an asset path relative to the module root and read it.
    Absolute paths are honored as-is."""
    p = Path(asset_path)
    if not p.is_absolute():
        p = module_dir / p
    return p.read_bytes()
