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
import math
import struct
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

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


SUPPORTED_TYPES = ("box", "sphere", "capsule", "point", "arrow", "mesh", "pointcloud")
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


def extract_ply_vertex_colors(
    ply_bytes: bytes,
) -> Optional[List[Tuple[int, int, int]]]:
    """Parse an ASCII PLY and return per-vertex (R, G, B) tuples if
    the file carries ``property uchar red/green/blue`` alongside
    ``property float x/y/z``. Returns ``None`` if the PLY doesn't
    have vertex colors or can't be parsed.

    Why this exists: the Viam 3D scene viewer reads
    ``Transform.metadata.colors`` for per-vertex coloring, not PLY's
    own embedded vertex colors. PLY's color attributes get dropped
    by both the RDK's reader (``rdk/spatialmath/mesh.go:140-152``,
    which extracts only x/y/z) and the viewer. Transcoding from PLY
    → metadata.colors makes vertex-colored PLY assets render
    correctly without forcing users to author the colors twice.

    Binary PLY is not currently supported — only ascii. PLY ascii is
    what this module ships and is the simplest path for procedural
    generation. If/when binary PLY input is needed, this function
    should grow a format branch.
    """
    try:
        text = ply_bytes.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None
    if not text.startswith("ply\n"):
        return None
    if "format ascii" not in text.split("end_header", 1)[0]:
        return None  # binary PLY — out of scope

    lines = text.split("\n")
    vertex_count = 0
    vertex_properties: List[str] = []
    parsing_vertex_element = False
    header_end_line = None
    for i, line in enumerate(lines):
        if line == "end_header":
            header_end_line = i + 1
            break
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            parsing_vertex_element = True
        elif line.startswith("element "):
            parsing_vertex_element = False
        elif parsing_vertex_element and line.startswith("property "):
            vertex_properties.append(line.split()[-1])
    if header_end_line is None or vertex_count == 0:
        return None

    # All three color channels must be present.
    try:
        r_idx = vertex_properties.index("red")
        g_idx = vertex_properties.index("green")
        b_idx = vertex_properties.index("blue")
    except ValueError:
        return None

    colors: List[Tuple[int, int, int]] = []
    for i in range(vertex_count):
        line_idx = header_end_line + i
        if line_idx >= len(lines):
            return None
        parts = lines[line_idx].split()
        if len(parts) < len(vertex_properties):
            return None
        try:
            colors.append((
                int(parts[r_idx]),
                int(parts[g_idx]),
                int(parts[b_idx]),
            ))
        except (ValueError, IndexError):
            return None
    return colors if colors else None


def build_metadata(
    color: Optional[Mapping[str, Any]] = None,
    opacity: Optional[float] = None,
    show_axes_helper: bool = False,
    invisible: bool = False,
    vertex_colors: Optional[List[Tuple[int, int, int]]] = None,
    chunks: Optional[Mapping[str, Any]] = None,
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
    # Match viamrobotics/visualization::draw/transform.go::MetadataToStruct
    # EXACTLY: always emit colors, color_format, opacities,
    # show_axes_helper, invisible. Omitting any of them produced an
    # invisible point cloud in 0.0.9 — the renderer apparently treats
    # absent keys as an invalid metadata struct rather than "use
    # defaults". With empty `colors` and opacity 255, the renderer
    # falls back to embedded per-point RGB on point clouds and a
    # viewer-default fill on solids. Never returns None now.
    fields: dict = {}
    if vertex_colors:
        # Per-vertex colors take precedence over uniform `color`.
        # Pack N RGB triples; library's MetadataToStruct expects
        # exactly this format.
        packed = bytearray()
        for c in vertex_colors:
            packed.append(_clamp_u8(c[0]))
            packed.append(_clamp_u8(c[1]))
            packed.append(_clamp_u8(c[2]))
        fields["colors"] = base64.b64encode(bytes(packed)).decode("ascii")
    elif color is not None:
        rgb_bytes = bytes([
            _clamp_u8(color.get("r", 0)),
            _clamp_u8(color.get("g", 0)),
            _clamp_u8(color.get("b", 0)),
        ])
        fields["colors"] = base64.b64encode(rgb_bytes).decode("ascii")
    else:
        # Empty colors → viewer falls back to its default fill for
        # solids. (For point clouds this used to fall back to PCD
        # embedded RGB; for meshes it appears to fall back to a
        # default-dark fill, NOT to PLY-embedded colors.)
        fields["colors"] = ""
    fields["color_format"] = 1.0  # COLOR_FORMAT_RGB
    alpha = 255 if opacity is None else _clamp_u8(round(float(opacity) * 255))
    fields["opacities"] = base64.b64encode(bytes([alpha])).decode("ascii")
    fields["show_axes_helper"] = bool(show_axes_helper)
    fields["invisible"] = bool(invisible)
    if chunks:
        # `chunks` is a sub-struct declaring chunked delivery of a
        # large entity (currently only used by point clouds). Schema
        # is from the visualization library's e2e fixture and is
        # EXPERIMENTAL — see LESSONS.md::chunked-delivery-schema for
        # the open question (the visualization repo lists `chunks`
        # in protos/draw/v1/metadata.proto but we have no
        # field-level reference for the inner shape, so this is a
        # best-effort match). If the viewer ignores these, the
        # initial Transform still carries a valid first-chunk PCD
        # that renders standalone.
        fields["chunks"] = dict(chunks)
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


def arrow_ply_bytes(
    length_mm: float,
    shaft_radius_mm: float,
    tip_radius_mm: Optional[float] = None,
    tip_length_mm: Optional[float] = None,
    sides: int = 12,
) -> bytes:
    """Procedural arrow mesh along local +Z, returned as ASCII PLY bytes.

    Coordinates are written in METERS (RDK PLY reader multiplies by
    1000 to convert to mm). ``tip_radius_mm`` defaults to 2× the shaft
    radius and ``tip_length_mm`` defaults to 28% of total length —
    proportions chosen so the arrow head reads clearly without
    overwhelming the shaft. Used both by the shipped ``assets/arrow.ply``
    generator and by the ``arrow`` primitive type at runtime.
    """
    if tip_radius_mm is None:
        tip_radius_mm = 2.0 * shaft_radius_mm
    if tip_length_mm is None:
        tip_length_mm = max(0.05 * length_mm, 0.28 * length_mm)
    shaft_length_mm = max(0.0, length_mm - tip_length_mm)

    verts: List[Tuple[float, float, float]] = []
    # v0: shaft bottom center (for the cap fan).
    verts.append((0.0, 0.0, 0.0))
    # v[1..sides]: shaft bottom ring at z=0, shaft_radius.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            shaft_radius_mm * math.cos(theta),
            shaft_radius_mm * math.sin(theta),
            0.0,
        ))
    # v[1+sides..2*sides]: shaft top ring at z=shaft_length, shaft_radius.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            shaft_radius_mm * math.cos(theta),
            shaft_radius_mm * math.sin(theta),
            shaft_length_mm,
        ))
    # v[1+2*sides..3*sides]: cone base ring at z=shaft_length, tip_radius.
    for i in range(sides):
        theta = 2 * math.pi * i / sides
        verts.append((
            tip_radius_mm * math.cos(theta),
            tip_radius_mm * math.sin(theta),
            shaft_length_mm,
        ))
    # apex.
    apex_idx = 1 + 3 * sides
    verts.append((0.0, 0.0, shaft_length_mm + tip_length_mm))

    bot_ring_start = 1
    top_ring_start = 1 + sides
    cone_ring_start = 1 + 2 * sides

    faces: List[Tuple[int, ...]] = []
    # Shaft bottom cap fan around v0.
    for i in range(sides):
        v_curr = bot_ring_start + i
        v_next = bot_ring_start + (i + 1) % sides
        faces.append((0, v_next, v_curr))
    # Shaft side quads → triangles.
    for i in range(sides):
        b = bot_ring_start + i
        bn = bot_ring_start + (i + 1) % sides
        t = top_ring_start + i
        tn = top_ring_start + (i + 1) % sides
        faces.append((b, bn, t))
        faces.append((bn, tn, t))
    # Washer between shaft top (narrow) and cone base (wide).
    for i in range(sides):
        inner = top_ring_start + i
        inner_next = top_ring_start + (i + 1) % sides
        outer = cone_ring_start + i
        outer_next = cone_ring_start + (i + 1) % sides
        faces.append((inner, outer, inner_next))
        faces.append((inner_next, outer, outer_next))
    # Cone side triangles.
    for i in range(sides):
        b = cone_ring_start + i
        bn = cone_ring_start + (i + 1) % sides
        faces.append((b, bn, apex_idx))

    return _ply_ascii_bytes(verts, faces)


def _ply_ascii_bytes(
    verts_mm: List[Tuple[float, float, float]],
    faces: List[Tuple[int, ...]],
    vertex_colors: Optional[List[Tuple[int, int, int]]] = None,
) -> bytes:
    """Build an ASCII PLY byte buffer from vertices (in mm) and faces.
    Coordinates are divided by 1000 so the file is in meters (the
    convention RDK's PLY reader expects).

    If ``vertex_colors`` is provided (must be the same length as
    ``verts_mm``), per-vertex RGB color properties are emitted in the
    PLY in addition to position. Whether the Viam 3D scene viewer
    honors per-vertex PLY colors is an open question — the RDK's
    PLY reader at ``rdk/spatialmath/mesh.go:140-152`` only extracts
    x/y/z and discards color attributes, but the viewer reads the
    wire bytes directly and may parse colors itself.
    """
    has_colors = vertex_colors is not None
    if has_colors and len(vertex_colors) != len(verts_mm):
        raise ValueError(
            f"vertex_colors length {len(vertex_colors)} != vertex count {len(verts_mm)}"
        )
    header = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(verts_mm)}",
        "property float x",
        "property float y",
        "property float z",
    ]
    if has_colors:
        header.extend([
            "property uchar red",
            "property uchar green",
            "property uchar blue",
        ])
    header.extend([
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ])
    lines = list(header)
    if has_colors:
        for (x, y, z), (r, g, b) in zip(verts_mm, vertex_colors):
            lines.append(
                f"{x / 1000.0:.6f} {y / 1000.0:.6f} {z / 1000.0:.6f} "
                f"{int(r) & 0xFF} {int(g) & 0xFF} {int(b) & 0xFF}"
            )
    else:
        for (x, y, z) in verts_mm:
            lines.append(
                f"{x / 1000.0:.6f} {y / 1000.0:.6f} {z / 1000.0:.6f}"
            )
    for face in faces:
        lines.append(f"{len(face)} " + " ".join(str(i) for i in face))
    return ("\n".join(lines) + "\n").encode("ascii")


def build_arrow(
    length_mm: float,
    radius_mm: float,
    label: str,
) -> Geometry:
    """First-class arrow primitive. Procedurally generates a PLY mesh
    sized to ``(length_mm, radius_mm)`` and embeds it as a Mesh
    geometry. Arrow points along local +Z; the pose's orientation
    vector aligns local +Z to the desired world direction."""
    ply = arrow_ply_bytes(length_mm=length_mm, shaft_radius_mm=radius_mm)
    # Constructed inline (not via build_mesh) because build_mesh is
    # defined below and we want a single, linear file order.
    return Geometry(
        label=label,
        mesh=Mesh(content_type=RENDERER_MESH_CONTENT_TYPE, mesh=ply),
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


def build_mesh(
    mesh_bytes: bytes,
    content_type: str,
    label: str,
    allow_non_ply: bool = False,
) -> Geometry:
    """Embed mesh bytes into a Geometry.

    content_type MUST be ``"ply"`` for the viewer to render it. STL
    input must be converted to PLY first via ``stl_to_ply``. The RDK
    parses both formats (``NewMeshFromProto`` at
    ``rdk/spatialmath/mesh.go:234-243`` switches on content_type and
    accepts both ``ply`` and ``stl``), but on the wire to the viewer
    it converts everything to PLY; the comment in
    ``rdk/spatialmath/mesh.go`` states the visualizer expects PLY only.

    ``allow_non_ply=True`` is an explicit opt-out of this guard. It
    exists for the playground's ``raw_stl`` demo item, which ships
    raw STL bytes with content_type=``stl`` specifically to show the
    viewer's silent-drop behavior — a bug-demo for the viz team,
    not something production modules should ever do. Every other
    caller leaves the default so the guard catches accidental STL
    emissions."""
    if not allow_non_ply and content_type != RENDERER_MESH_CONTENT_TYPE:
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


def parse_pcd_binary(pcd_bytes: bytes) -> Tuple[bytes, bytes, int, int]:
    """Split a PCDBinary blob into ``(header_bytes, body_bytes, stride,
    total_points)``. Used by chunked-delivery: callers split body_bytes
    on stride boundaries to emit individual chunks.

    Expects the binary PCD format ``pointcloud.ToPCD`` in the RDK
    produces (see scripts/generate_assets.py for the writer side):

      VERSION .7\\n
      FIELDS x y z rgb\\n
      SIZE 4 4 4 4\\n
      TYPE F F F I\\n
      COUNT 1 1 1 1\\n
      WIDTH <N>\\n
      HEIGHT 1\\n
      VIEWPOINT 0 0 0 1 0 0 0\\n
      POINTS <N>\\n
      DATA binary\\n
      <body: N records of (float x, float y, float z, int32 rgb)>

    Raises ``ValueError`` if the header doesn't match. Stride is
    computed from SIZE/COUNT — i.e., the actual bytes per point — so
    it'll be 16 for the FFFI layout.
    """
    marker = b"DATA binary\n"
    idx = pcd_bytes.find(marker)
    if idx < 0:
        raise ValueError("PCD: missing 'DATA binary' marker")
    header_end = idx + len(marker)
    header_bytes = pcd_bytes[:header_end]
    body_bytes = pcd_bytes[header_end:]
    # Compute stride from SIZE and COUNT lines.
    header_text = header_bytes.decode("ascii", errors="replace")
    size_line = next(
        (line for line in header_text.splitlines() if line.startswith("SIZE ")),
        None,
    )
    count_line = next(
        (line for line in header_text.splitlines() if line.startswith("COUNT ")),
        None,
    )
    if size_line is None or count_line is None:
        raise ValueError("PCD: missing SIZE or COUNT")
    sizes = [int(s) for s in size_line[len("SIZE "):].split()]
    counts = [int(c) for c in count_line[len("COUNT "):].split()]
    if len(sizes) != len(counts):
        raise ValueError(f"PCD: SIZE/COUNT length mismatch ({sizes} vs {counts})")
    stride = sum(s * c for s, c in zip(sizes, counts))
    if stride <= 0:
        raise ValueError(f"PCD: invalid stride {stride}")
    total_points = len(body_bytes) // stride
    return header_bytes, body_bytes, stride, total_points


def build_pcd_chunk(
    header_bytes: bytes,
    body_bytes: bytes,
    stride: int,
    chunk_index: int,
    chunk_size_points: int,
) -> bytes:
    """Build a self-contained PCDBinary blob containing only the chunk
    at ``chunk_index``. Rewrites the WIDTH and POINTS fields in the
    header to match the chunk's actual point count so the result is a
    valid standalone PCD the viewer can render in isolation.

    This is what the initial Transform's pointcloud bytes carry under
    chunked delivery: the first chunk is a working PCD all by itself,
    and the viewer requests subsequent chunks via the ``get_entity_chunk``
    DoCommand and stitches them in. Even if the viewer doesn't yet
    understand the chunks metadata, the initial first chunk still
    renders as a smaller-but-correct point cloud.
    """
    total_points = len(body_bytes) // stride
    start = chunk_index * chunk_size_points
    if start >= total_points:
        raise ValueError(
            f"chunk_index {chunk_index} out of range; "
            f"total_points={total_points} chunk_size={chunk_size_points}"
        )
    end = min(start + chunk_size_points, total_points)
    n = end - start
    body_slice = body_bytes[start * stride : end * stride]
    # Rewrite WIDTH and POINTS to match the slice length.
    header_text = header_bytes.decode("ascii", errors="replace")
    new_lines = []
    for line in header_text.split("\n"):
        if line.startswith("WIDTH "):
            new_lines.append(f"WIDTH {n}")
        elif line.startswith("POINTS "):
            new_lines.append(f"POINTS {n}")
        else:
            new_lines.append(line)
    new_header = "\n".join(new_lines).encode("ascii")
    return new_header + body_slice


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
