"""Pure builders that turn a normalized item dict into the proto pieces
the WorldStateStore service emits — a `Geometry`, an optional
`metadata` `Struct`, and a `Pose`.

Each item dict carries a primitive `type`, a `label`, a `pose`, optional
`color`/`opacity`, and the shape-specific fields (`dims_mm`,
`radius_mm`, `length_mm`, `mesh_path`, `pointcloud_path`). The builders
do no validation — that lives in service.validate_config. They do not
read files for the mesh/pointcloud builders either; the caller passes
the bytes in, so tests can drive the builders without touching disk.
"""
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from google.protobuf.struct_pb2 import Struct
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
from viam.utils import dict_to_struct


SUPPORTED_TYPES = ("box", "sphere", "capsule", "point", "mesh", "pointcloud")
SUPPORTED_MESH_CONTENT_TYPES = ("ply", "stl")


def build_metadata(
    color: Optional[Mapping[str, Any]] = None,
    opacity: Optional[float] = None,
) -> Optional[Struct]:
    """Encode color + opacity as the nested struct the 3D viewer reads.

    The viewer's metadata convention (matched by
    rdk/services/worldstatestore/fake/moving_geos_world.go): color is a
    nested struct {r, g, b} with 0..255 numbers; opacity is a top-level
    number in [0, 1]. Either may be omitted. Returns None when nothing
    is set, so the caller can leave Transform.metadata unset entirely.
    """
    fields: dict = {}
    if color is not None:
        fields["color"] = {
            "r": float(color.get("r", 0)),
            "g": float(color.get("g", 0)),
            "b": float(color.get("b", 0)),
        }
    if opacity is not None:
        fields["opacity"] = float(opacity)
    if not fields:
        return None
    return dict_to_struct(fields)


def build_pose(pose: Mapping[str, Any]) -> Pose:
    """Build a Pose proto from a config dict. All fields optional;
    missing fields default to a zero pose with OZ=1 (identity rotation
    convention used by Viam's orientation-vector system)."""
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


def build_point(label: str) -> Geometry:
    """A point is a sphere with radius=0 — the 3D viewer renders it as
    a single dot. See spatialmath.NewPoint in the RDK."""
    return Geometry(
        label=label,
        sphere=Sphere(radius_mm=0.0),
    )


def build_mesh(mesh_bytes: bytes, content_type: str, label: str) -> Geometry:
    """Embed mesh bytes into a Geometry. content_type must be lowercase
    'ply' or 'stl' (matches rdk/spatialmath/mesh.go expectations).
    Caller is responsible for reading the file and supplying bytes."""
    return Geometry(
        label=label,
        mesh=Mesh(content_type=content_type, mesh=mesh_bytes),
    )


def build_pointcloud(pcd_bytes: bytes, label: str) -> Geometry:
    """Embed PCD bytes into a Geometry. Use PCDBinary format — ascii
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


def infer_mesh_content_type(asset_path: str) -> str:
    """Map a file extension to the lowercase content_type the renderer
    expects. Raises ValueError for unsupported extensions."""
    ext = Path(asset_path).suffix.lstrip(".").lower()
    if ext not in SUPPORTED_MESH_CONTENT_TYPES:
        raise ValueError(
            f"mesh content type {ext!r} is not supported; "
            f"only {SUPPORTED_MESH_CONTENT_TYPES} are accepted by the viewer"
        )
    return ext
