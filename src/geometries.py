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
import base64
import struct
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

# The Viam 3D viewer only renders PLY meshes. STL is accepted as an
# INPUT format (the RDK's STL parser is real), but on the wire to the
# viewer the content_type must be "ply". See the comment in
# rdk/spatialmath/mesh.go: "Meshes are always converted to PLY format
# for compatibility with the visualizer." build_mesh always sends
# content_type="ply"; load_mesh_bytes_as_ply converts STL inputs first.
RENDERER_MESH_CONTENT_TYPE = "ply"

# Radius used for the "point" primitive. Proto-wise a point is a
# sphere with radius=0, but the viewer skips zero-radius geometries.
# A small but visible radius gives the user something to see and is
# still small enough to read as a "marker" rather than a sphere.
POINT_MARKER_RADIUS_MM = 8.0


def build_metadata(
    color: Optional[Mapping[str, Any]] = None,
    opacity: Optional[float] = None,
    show_axes_helper: bool = False,
    invisible: bool = False,
) -> Optional[Struct]:
    """Encode metadata in the schema the 3D viewer actually reads.

    The schema comes from ``viamrobotics/visualization`` (the canonical
    drawing library backing the 3D scene viewer), specifically
    ``draw/transform.go::MetadataToStruct`` and the ``draw.v1.Metadata``
    proto at ``protos/draw/v1/metadata.proto``. The RDK fake's
    ``{color: {r,g,b}, opacity: 0.5}`` shape is OBSOLETE — the viewer
    no longer reads it, which is why color/opacity silently no-op'd
    through 0.0.5. Keys the viewer actually consumes:

      - ``colors`` (string): base64 of packed RGB bytes. 3 bytes per
        color; one color for single-component primitives, N for
        multi-component (point clouds, polylines, etc.). Per
        ``draw/buffer_packer.go::packColors``.
      - ``color_format`` (number): ``1`` for ``COLOR_FORMAT_RGB`` —
        the only format defined in the enum today.
      - ``opacities`` (string): base64 of packed alpha bytes. One byte
        per color, or one byte total if uniform.
      - ``show_axes_helper`` (bool): renders an RGB XYZ triad at the
        entity's origin. Free coordinate-frame visualizer.
      - ``invisible`` (bool): hides the entity by default; user can
        toggle on in the viewer.

    Returns ``None`` only when literally nothing is set. Otherwise
    emits at least ``opacities`` so the viewer has a defined alpha.
    """
    fields: dict = {}
    if color is not None:
        rgb_bytes = bytes([
            _clamp_u8(color.get("r", 0)),
            _clamp_u8(color.get("g", 0)),
            _clamp_u8(color.get("b", 0)),
        ])
        fields["colors"] = base64.b64encode(rgb_bytes).decode("ascii")
        # color_format is required when colors is present; 1 = RGB.
        fields["color_format"] = 1.0
    if opacity is not None:
        alpha = _clamp_u8(round(float(opacity) * 255))
        fields["opacities"] = base64.b64encode(bytes([alpha])).decode("ascii")
    if show_axes_helper:
        fields["show_axes_helper"] = True
    if invisible:
        fields["invisible"] = True
    if not fields:
        return None
    return dict_to_struct(fields)


def _clamp_u8(v: Any) -> int:
    """Clamp any number into the 0..255 range as a uint8."""
    iv = int(v)
    if iv < 0:
        return 0
    if iv > 255:
        return 255
    return iv


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
    """A "point" — proto-wise a sphere with a small but visible radius.

    The Geometry oneof has no Point variant; the RDK calls a
    zero-radius sphere a Point internally (see spatialmath.NewPoint),
    but the viewer doesn't render zero-radius geometries. We use a
    small fixed radius so users can see the primitive."""
    return Geometry(
        label=label,
        sphere=Sphere(radius_mm=POINT_MARKER_RADIUS_MM),
    )


def build_mesh(mesh_bytes: bytes, content_type: str, label: str) -> Geometry:
    """Embed mesh bytes into a Geometry.

    content_type MUST be ``"ply"`` for the viewer to render it. STL
    input must be converted to PLY first via ``stl_to_ply``. The RDK
    parses both formats, but on the wire to the viewer it converts
    everything to PLY; the comment in ``rdk/spatialmath/mesh.go``
    states the visualizer expects PLY only."""
    if content_type != RENDERER_MESH_CONTENT_TYPE:
        raise ValueError(
            f"build_mesh requires content_type {RENDERER_MESH_CONTENT_TYPE!r}; "
            f"got {content_type!r}. STL must be converted via stl_to_ply first."
        )
    return Geometry(
        label=label,
        mesh=Mesh(content_type=content_type, mesh=mesh_bytes),
    )


def stl_to_ply(stl_bytes: bytes) -> bytes:
    """Convert binary STL bytes to ASCII PLY bytes.

    STL is the only other format the RDK can parse, so users who want
    to ship STL assets are a real audience — but the viewer only
    renders PLY on the wire (see ``rdk/spatialmath/mesh.go``: "The
    visualizer expects all meshes to be in PLY format"). We convert
    at load time, no external dependency needed.

    Output is an ASCII PLY with per-triangle vertices (no dedup) —
    fine for small assets, would balloon for production-size meshes.
    Use ``trimesh`` offline if you need a smaller PLY from a large STL.
    """
    if len(stl_bytes) < 84:
        raise ValueError("STL data too small (need >=84 bytes for header)")
    n_tris = struct.unpack("<I", stl_bytes[80:84])[0]
    expected_size = 84 + n_tris * 50
    if len(stl_bytes) < expected_size:
        raise ValueError(
            f"STL truncated: expected {expected_size} bytes for "
            f"{n_tris} triangles, got {len(stl_bytes)}"
        )
    verts = []
    faces = []
    offset = 84
    for _ in range(n_tris):
        offset += 12  # skip per-tri normal
        face_idx = []
        for _v in range(3):
            x, y, z = struct.unpack("<fff", stl_bytes[offset:offset + 12])
            offset += 12
            face_idx.append(len(verts))
            verts.append((x, y, z))
        offset += 2  # skip attribute byte count
        faces.append(tuple(face_idx))
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    for (x, y, z) in verts:
        lines.append(f"{x:.6f} {y:.6f} {z:.6f}")
    for (a, b, c) in faces:
        lines.append(f"3 {a} {b} {c}")
    return ("\n".join(lines) + "\n").encode("ascii")


def load_mesh_bytes_as_ply(asset_bytes: bytes, source_path: str) -> bytes:
    """Read mesh asset bytes, returning PLY bytes regardless of input
    format. Dispatches on the source path's extension."""
    fmt = infer_mesh_content_type(source_path)
    if fmt == "stl":
        return stl_to_ply(asset_bytes)
    return asset_bytes  # already PLY


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
