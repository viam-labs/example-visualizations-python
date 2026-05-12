"""Unit tests for src/geometries.py — the pure proto builders."""
from pathlib import Path

import pytest
from viam.utils import struct_to_dict

from src.geometries import (
    SUPPORTED_MESH_CONTENT_TYPES,
    SUPPORTED_TYPES,
    arrow_ply_bytes,
    build_arrow,
    build_box,
    build_capsule,
    build_mesh,
    build_metadata,
    build_pcd_chunk,
    build_point,
    build_pointcloud,
    build_pose,
    build_sphere,
    extract_ply_vertex_colors,
    infer_mesh_content_type,
    load_mesh_bytes_as_ply,
    parse_pcd_binary,
    read_asset,
    stl_to_ply,
)


# ---------- build_metadata ----------
#
# Schema MUST match viamrobotics/visualization::draw/transform.go::MetadataToStruct
# and protos/draw/v1/metadata.proto. The library ALWAYS emits all five
# keys (colors, color_format, opacities, show_axes_helper, invisible);
# omitting any of them makes the viewer skip the entity entirely. This
# bit us at 0.0.9 when point clouds went invisible because we'd
# stopped emitting `colors` for items without a user-set color.

import base64 as _b64


def _all_required_keys_present(d):
    """Lock in the schema contract: the five keys the library always emits."""
    for k in ("colors", "color_format", "opacities", "show_axes_helper", "invisible"):
        assert k in d, f"missing required metadata key {k!r}; have {sorted(d.keys())}"


def test_build_metadata_with_no_args_still_emits_all_required_keys():
    """The viewer treats a struct missing any of these keys as
    invalid and skips the entity. Empty `colors` is the signal to
    fall back to embedded RGB / viewer default — NOT the absence of
    the key."""
    md = build_metadata()
    d = struct_to_dict(md)
    _all_required_keys_present(d)
    assert d["colors"] == ""
    assert d["color_format"] == 1.0
    # Default opacity is fully opaque (alpha=255).
    assert d["opacities"] == _b64.b64encode(bytes([255])).decode("ascii")
    assert d["show_axes_helper"] is False
    assert d["invisible"] is False


def test_build_metadata_color_packs_as_base64_rgb_bytes():
    md = build_metadata(color={"r": 255, "g": 128, "b": 0})
    d = struct_to_dict(md)
    _all_required_keys_present(d)
    assert d["colors"] == _b64.b64encode(bytes([255, 128, 0])).decode("ascii")
    assert d["color_format"] == 1.0


def test_build_metadata_opacity_packs_as_base64_alpha_byte():
    """opacity 0..1 becomes a single uint8 byte 0..255."""
    md = build_metadata(opacity=0.5)
    d = struct_to_dict(md)
    _all_required_keys_present(d)
    # 0.5 * 255 = 127.5 → rounds to 128.
    assert d["opacities"] == _b64.b64encode(bytes([128])).decode("ascii")


def test_build_metadata_opacity_endpoints():
    assert struct_to_dict(build_metadata(opacity=0.0))["opacities"] == \
        _b64.b64encode(bytes([0])).decode("ascii")
    assert struct_to_dict(build_metadata(opacity=1.0))["opacities"] == \
        _b64.b64encode(bytes([255])).decode("ascii")


def test_build_metadata_color_and_opacity_together():
    md = build_metadata(color={"r": 10, "g": 20, "b": 30}, opacity=0.4)
    d = struct_to_dict(md)
    _all_required_keys_present(d)
    assert d["colors"] == _b64.b64encode(bytes([10, 20, 30])).decode("ascii")
    assert d["color_format"] == 1.0
    assert d["opacities"] == _b64.b64encode(bytes([round(0.4 * 255)])).decode("ascii")


def test_build_metadata_returns_struct_even_when_nothing_set():
    """A canonical "empty" metadata still has all five keys — the
    point cloud disappearance at 0.0.9 was caused by returning None
    here, which left the renderer with no metadata to parse."""
    md = build_metadata()
    assert md is not None
    md_explicit = build_metadata(color=None, opacity=None)
    assert md_explicit is not None


def test_build_metadata_no_color_emits_empty_colors_string():
    """Empty `colors` is the canonical signal to the viewer to fall
    back to embedded per-point RGB (for PCDs) or its default fill (for
    solids). The KEY must still be present."""
    md = build_metadata(opacity=1.0)
    d = struct_to_dict(md)
    assert d["colors"] == ""


def test_build_metadata_show_axes_helper_always_emitted():
    """Library always emits `show_axes_helper`; matching exactly avoids
    parser surprises. The bool itself is the meaningful signal."""
    md_off = build_metadata(color={"r": 0, "g": 0, "b": 0}, show_axes_helper=False)
    md_on = build_metadata(color={"r": 0, "g": 0, "b": 0}, show_axes_helper=True)
    assert struct_to_dict(md_off)["show_axes_helper"] is False
    assert struct_to_dict(md_on)["show_axes_helper"] is True


def test_build_metadata_invisible_always_emitted():
    md_off = build_metadata(color={"r": 0, "g": 0, "b": 0}, invisible=False)
    md_on = build_metadata(color={"r": 0, "g": 0, "b": 0}, invisible=True)
    assert struct_to_dict(md_off)["invisible"] is False
    assert struct_to_dict(md_on)["invisible"] is True


def test_build_metadata_with_vertex_colors_packs_N_triples():
    """Per-vertex colors take precedence over single color and pack
    as base64-encoded RGB byte sequence of length N*3."""
    vcols = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 128, 128)]
    md = build_metadata(vertex_colors=vcols)
    d = struct_to_dict(md)
    raw = _b64.b64decode(d["colors"])
    assert len(raw) == 4 * 3
    assert raw == bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 128, 128, 128])


def test_build_metadata_vertex_colors_override_single_color():
    """If both are given, vertex_colors win (the per-vertex view is
    strictly more specific than a uniform tint)."""
    vcols = [(10, 20, 30), (40, 50, 60)]
    md = build_metadata(color={"r": 200, "g": 200, "b": 200}, vertex_colors=vcols)
    raw = _b64.b64decode(struct_to_dict(md)["colors"])
    assert raw == bytes([10, 20, 30, 40, 50, 60])


def test_build_metadata_clamps_color_to_0_255():
    md = build_metadata(color={"r": -10, "g": 999, "b": 200})
    d = struct_to_dict(md)
    raw = _b64.b64decode(d["colors"])
    assert raw == bytes([0, 255, 200])


def test_build_metadata_color_missing_channels_default_to_zero():
    md = build_metadata(color={"r": 100})
    d = struct_to_dict(md)
    raw = _b64.b64decode(d["colors"])
    assert raw == bytes([100, 0, 0])


# ---------- build_pose ----------

def test_build_pose_default_is_identity():
    p = build_pose({})
    assert (p.x, p.y, p.z) == (0.0, 0.0, 0.0)
    # Identity-orientation convention: OZ=1, others 0.
    assert (p.o_x, p.o_y, p.o_z, p.theta) == (0.0, 0.0, 1.0, 0.0)


def test_build_pose_reads_xyz_and_orientation():
    p = build_pose({"x": 100, "y": -50, "z": 25, "ox": 0, "oy": 1, "oz": 0, "theta": 90})
    assert (p.x, p.y, p.z) == (100.0, -50.0, 25.0)
    assert (p.o_x, p.o_y, p.o_z, p.theta) == (0.0, 1.0, 0.0, 90.0)


def test_build_pose_handles_partial_orientation_without_clobbering_intent():
    """If the user gives ox or oy, don't auto-fill oz=1 — that would
    silently break their intent."""
    p = build_pose({"ox": 1.0})
    assert (p.o_x, p.o_y, p.o_z) == (1.0, 0.0, 0.0)


# ---------- build_box ----------

def test_build_box_carries_dims_and_label():
    g = build_box({"x": 100, "y": 200, "z": 50}, label="my_box")
    assert g.label == "my_box"
    assert g.box.dims_mm.x == 100.0
    assert g.box.dims_mm.y == 200.0
    assert g.box.dims_mm.z == 50.0


# ---------- build_sphere ----------

def test_build_sphere_carries_radius_and_label():
    g = build_sphere(75.0, label="ball")
    assert g.label == "ball"
    assert g.sphere.radius_mm == 75.0


# ---------- build_capsule ----------

def test_build_capsule_carries_radius_length_and_label():
    g = build_capsule(40.0, 200.0, label="pill")
    assert g.label == "pill"
    assert g.capsule.radius_mm == 40.0
    assert g.capsule.length_mm == 200.0


# ---------- build_point ----------

def test_build_point_emits_visible_marker_not_zero_radius():
    """RDK convention says a point is a radius-0 sphere, but the viewer
    skips zero-radius geometries — leaving the user with nothing to
    see. We use a small but visible marker radius instead."""
    from src.geometries import POINT_MARKER_RADIUS_MM
    g = build_point(label="dot")
    assert g.label == "dot"
    assert g.sphere.radius_mm == POINT_MARKER_RADIUS_MM
    assert g.sphere.radius_mm > 0


def test_point_marker_is_small_enough_to_read_as_a_point():
    """The marker should be visible but small enough that it reads as
    a point rather than a sphere. Pin a sensible upper bound."""
    from src.geometries import POINT_MARKER_RADIUS_MM
    assert 1.0 <= POINT_MARKER_RADIUS_MM <= 20.0


# ---------- build_arrow ----------

def test_build_arrow_emits_a_ply_mesh():
    """The arrow primitive is procedural mesh — caller doesn't need to
    ship an asset. Mesh content_type must be 'ply' for the viewer."""
    g = build_arrow(length_mm=200, radius_mm=10, label="arr")
    assert g.label == "arr"
    assert g.mesh.content_type == "ply"
    # Bytes look like an ASCII PLY header.
    assert g.mesh.mesh.startswith(b"ply\n")


def test_arrow_ply_bytes_meter_scale():
    """The arrow PLY is written in METERS (RDK reader convention).
    A 200 mm arrow has vertex magnitudes ≤ 0.2 m in the file."""
    ply = arrow_ply_bytes(length_mm=200, shaft_radius_mm=10).decode("ascii")
    body = ply.split("end_header", 1)[1].strip().splitlines()
    verts = []
    for line in body:
        parts = line.split()
        if len(parts) == 3:
            try:
                verts.append(tuple(float(p) for p in parts))
            except ValueError:
                break
        else:
            break
    max_mag = max(abs(c) for v in verts for c in v)
    assert max_mag < 1.0
    assert max_mag > 0.05


def test_arrow_ply_bytes_points_along_local_plus_z():
    """All vertices have z ≥ 0 (arrow base at z=0, apex at z=length)."""
    ply = arrow_ply_bytes(length_mm=200, shaft_radius_mm=10).decode("ascii")
    body = ply.split("end_header", 1)[1].strip().splitlines()
    verts = []
    for line in body:
        parts = line.split()
        if len(parts) == 3:
            try:
                verts.append(tuple(float(p) for p in parts))
            except ValueError:
                break
        else:
            break
    min_z = min(v[2] for v in verts)
    assert min_z >= -1e-9, f"arrow has vertex below z=0: {min_z}"


# ---------- build_mesh ----------

def test_build_mesh_embeds_bytes_and_requires_ply():
    """The viewer only renders PLY. STL must be converted via
    stl_to_ply before reaching build_mesh."""
    g = build_mesh(b"\x80PLYBYTES", "ply", label="bunny")
    assert g.label == "bunny"
    assert g.mesh.mesh == b"\x80PLYBYTES"
    assert g.mesh.content_type == "ply"


def test_build_mesh_rejects_non_ply_content_type():
    """Surface the renderer-only-takes-PLY constraint at the build
    site rather than letting it silently fail in the viewer."""
    with pytest.raises(ValueError, match="ply"):
        build_mesh(b"\x00stlbytes", "stl", label="cube")


# ---------- stl_to_ply ----------

def _build_minimal_stl_bytes(triangles):
    """Build a binary STL containing the given list of triangles, each
    a 3-tuple of (x,y,z) tuples. Header 80 bytes, count uint32, then
    per-tri: 12 zero bytes (normal) + 36 bytes (3 vertices) + 2 bytes."""
    import struct as _s
    buf = bytearray(80)
    buf += _s.pack("<I", len(triangles))
    for tri in triangles:
        buf += _s.pack("<fff", 0.0, 0.0, 0.0)  # normal
        for (x, y, z) in tri:
            buf += _s.pack("<fff", x, y, z)
        buf += _s.pack("<H", 0)  # attribute
    return bytes(buf)


def test_stl_to_ply_one_triangle_roundtrip():
    stl = _build_minimal_stl_bytes([
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ])
    ply = stl_to_ply(stl).decode("ascii")
    assert ply.startswith("ply\n")
    assert "format ascii 1.0" in ply
    assert "element vertex 3" in ply
    assert "element face 1" in ply
    # Vertex coords preserved.
    assert "0.000000 0.000000 0.000000" in ply
    assert "1.000000 0.000000 0.000000" in ply
    assert "0.000000 1.000000 0.000000" in ply
    # Face references the three vertices.
    assert "3 0 1 2" in ply


def test_stl_to_ply_twelve_triangles_emits_36_vertices():
    """No-dedup conversion: each triangle's three vertices become three
    fresh vertex entries. 12 triangles → 36 vertices, 12 faces."""
    tris = [
        ((float(i), 0.0, 0.0), (0.0, float(i), 0.0), (0.0, 0.0, float(i)))
        for i in range(1, 13)
    ]
    ply = stl_to_ply(_build_minimal_stl_bytes(tris)).decode("ascii")
    assert "element vertex 36" in ply
    assert "element face 12" in ply


def test_stl_to_ply_rejects_short_input():
    with pytest.raises(ValueError, match="too small"):
        stl_to_ply(b"\x00" * 50)


def test_stl_to_ply_rejects_truncated_input():
    """Header claims 5 triangles but only one is present."""
    import struct as _s
    buf = bytearray(80) + _s.pack("<I", 5) + b"\x00" * 50  # only 1 tri
    with pytest.raises(ValueError, match="truncated"):
        stl_to_ply(bytes(buf))


# ---------- load_mesh_bytes_as_ply ----------

def test_load_mesh_bytes_as_ply_passes_ply_through():
    ply_in = b"ply\nformat ascii 1.0\nend_header\n"
    out = load_mesh_bytes_as_ply(ply_in, "asset.ply")
    assert out == ply_in


def test_load_mesh_bytes_as_ply_converts_stl():
    stl = _build_minimal_stl_bytes([
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ])
    out = load_mesh_bytes_as_ply(stl, "asset.stl")
    assert out.startswith(b"ply\n")


# ---------- extract_ply_vertex_colors ----------

def test_extract_ply_vertex_colors_on_uncolored_ply():
    """An ASCII PLY without color properties returns None — no
    transcoding to attempt."""
    plain_ply = (
        b"ply\nformat ascii 1.0\n"
        b"element vertex 2\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"element face 0\n"
        b"property list uchar int vertex_indices\n"
        b"end_header\n"
        b"0.0 0.0 0.0\n0.1 0.1 0.1\n"
    )
    assert extract_ply_vertex_colors(plain_ply) is None


def test_extract_ply_vertex_colors_on_colored_ply():
    """An ASCII PLY with red/green/blue properties returns the
    per-vertex (R, G, B) tuples in order."""
    colored = (
        b"ply\nformat ascii 1.0\n"
        b"element vertex 3\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"property uchar red\nproperty uchar green\nproperty uchar blue\n"
        b"element face 0\n"
        b"property list uchar int vertex_indices\n"
        b"end_header\n"
        b"0.0 0.0 0.0 255 0 0\n"
        b"0.1 0.0 0.0 0 255 0\n"
        b"0.0 0.1 0.0 0 0 255\n"
    )
    assert extract_ply_vertex_colors(colored) == [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
    ]


def test_extract_ply_vertex_colors_handles_property_reorder():
    """The red/green/blue properties might appear in a different
    order in the header. The function uses property names, not
    positions, so any order works."""
    colored = (
        b"ply\nformat ascii 1.0\n"
        b"element vertex 2\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"property uchar blue\nproperty uchar green\nproperty uchar red\n"
        b"element face 0\n"
        b"property list uchar int vertex_indices\n"
        b"end_header\n"
        b"0 0 0 100 50 25\n"  # blue=100, green=50, red=25
        b"1 0 0 0 0 0\n"
    )
    assert extract_ply_vertex_colors(colored)[0] == (25, 50, 100)


def test_extract_ply_vertex_colors_on_actual_colorful_sphere():
    """End-to-end: the shipped colorful_sphere.ply asset has
    per-vertex colors. The extractor should pick them up."""
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "assets" / "colorful_sphere.ply"
    if not path.exists():
        pytest.skip("colorful_sphere.ply not generated; run `make assets`")
    colors = extract_ply_vertex_colors(path.read_bytes())
    assert colors is not None
    # 4-level subdivision icosphere: 2562 vertices.
    assert len(colors) == 2562
    # All channels in valid range, at least some color variation.
    distinct = {c for c in colors[:100]}
    assert len(distinct) > 10, "expected many distinct hues across vertices"


# ---------- build_pointcloud ----------

def test_build_pointcloud_embeds_bytes():
    g = build_pointcloud(b"PCDDATA", label="cloud")
    assert g.label == "cloud"
    assert g.pointcloud.point_cloud == b"PCDDATA"


# ---------- read_asset ----------

def test_read_asset_resolves_relative_to_module_dir(tmp_path):
    asset = tmp_path / "thing.bin"
    asset.write_bytes(b"hello")
    data = read_asset("thing.bin", module_dir=tmp_path)
    assert data == b"hello"


def test_read_asset_honors_absolute_paths(tmp_path):
    asset = tmp_path / "abs.bin"
    asset.write_bytes(b"abs!")
    # Module dir is irrelevant when an absolute path is given.
    data = read_asset(str(asset), module_dir=Path("/nonexistent"))
    assert data == b"abs!"


def test_read_asset_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_asset("missing.bin", module_dir=tmp_path)


# ---------- infer_mesh_content_type ----------

@pytest.mark.parametrize("path,expected", [
    ("bunny.ply", "ply"),
    ("cube.stl", "stl"),
    ("/abs/path/foo.PLY", "ply"),
    ("/abs/path/foo.Stl", "stl"),
])
def test_infer_mesh_content_type_accepts_known_extensions(path, expected):
    assert infer_mesh_content_type(path) == expected


@pytest.mark.parametrize("path", [
    "model.gltf",
    "model.glb",
    "model.obj",
    "model.fbx",
    "model",  # no extension
])
def test_infer_mesh_content_type_rejects_unknown(path):
    with pytest.raises(ValueError, match="not supported"):
        infer_mesh_content_type(path)


# ---------- module surface sanity ----------

def test_supported_types_constant_covers_all_builders():
    assert set(SUPPORTED_TYPES) == {
        "box", "sphere", "capsule", "point", "arrow", "mesh", "pointcloud",
    }


def test_supported_mesh_content_types_is_lowercase():
    """The renderer only accepts lowercase 'ply' and 'stl' (see
    rdk/spatialmath/mesh.go). Validate config rejects uppercase
    variants downstream."""
    for ct in SUPPORTED_MESH_CONTENT_TYPES:
        assert ct == ct.lower()


# ---------- chunked PCD helpers ----------

def _fake_pcd(n_points: int) -> bytes:
    """Build a minimal but valid binary PCD blob with `n_points`
    points, matching the FFFI / 16-byte-stride format the helix asset
    uses. Used by chunked-delivery tests so they don't depend on the
    real asset's exact point count."""
    import struct
    header = (
        "VERSION .7\n"
        "FIELDS x y z rgb\n"
        "SIZE 4 4 4 4\n"
        "TYPE F F F I\n"
        "COUNT 1 1 1 1\n"
        f"WIDTH {n_points}\n"
        "HEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {n_points}\n"
        "DATA binary\n"
    ).encode("ascii")
    body = b"".join(
        struct.pack("<fffI", float(i), 0.0, 0.0, i)
        for i in range(n_points)
    )
    return header + body


def test_parse_pcd_binary_returns_header_body_stride_and_total():
    pcd = _fake_pcd(100)
    header, body, stride, total = parse_pcd_binary(pcd)
    assert header.startswith(b"VERSION ")
    assert header.endswith(b"DATA binary\n")
    assert stride == 16  # FFFI = 4+4+4+4
    assert total == 100
    assert len(body) == 100 * 16


def test_parse_pcd_binary_rejects_missing_data_marker():
    with pytest.raises(ValueError, match="DATA binary"):
        parse_pcd_binary(b"VERSION .7\n")


def test_build_pcd_chunk_returns_first_chunk_with_rewritten_header():
    pcd = _fake_pcd(50)
    header, body, stride, total = parse_pcd_binary(pcd)
    chunk = build_pcd_chunk(header, body, stride, chunk_index=0, chunk_size_points=20)
    # Chunk's WIDTH/POINTS must match the slice length, not the original total.
    assert b"WIDTH 20\n" in chunk
    assert b"POINTS 20\n" in chunk
    assert b"WIDTH 50\n" not in chunk
    # Body length is exactly chunk_size * stride.
    chunk_header, chunk_body, chunk_stride, chunk_total = parse_pcd_binary(chunk)
    assert chunk_stride == 16
    assert chunk_total == 20


def test_build_pcd_chunk_last_chunk_is_partial():
    """When total_points isn't a multiple of chunk_size, the last
    chunk has fewer points but is still a valid standalone PCD."""
    pcd = _fake_pcd(25)
    header, body, stride, total = parse_pcd_binary(pcd)
    # Chunks of 10 → chunks 0,1 have 10 points; chunk 2 has 5.
    chunk = build_pcd_chunk(header, body, stride, chunk_index=2, chunk_size_points=10)
    assert b"POINTS 5\n" in chunk


def test_build_pcd_chunk_out_of_range_raises():
    pcd = _fake_pcd(10)
    header, body, stride, total = parse_pcd_binary(pcd)
    with pytest.raises(ValueError, match="out of range"):
        build_pcd_chunk(header, body, stride, chunk_index=5, chunk_size_points=10)


# ---------- build_metadata with chunks ----------

def test_build_metadata_with_chunks_adds_chunks_substruct():
    md = build_metadata(
        color={"r": 0, "g": 0, "b": 0},
        opacity=1.0,
        chunks={"chunk_size": 100, "total": 5, "stride": 16},
    )
    out = struct_to_dict(md)
    assert "chunks" in out
    assert out["chunks"]["chunk_size"] == 100
    assert out["chunks"]["total"] == 5
    assert out["chunks"]["stride"] == 16


def test_build_metadata_without_chunks_omits_chunks_key():
    md = build_metadata(color={"r": 0, "g": 0, "b": 0}, opacity=1.0)
    out = struct_to_dict(md)
    assert "chunks" not in out
