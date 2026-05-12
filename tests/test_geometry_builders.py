"""Unit tests for src/geometries.py — the pure proto builders."""
from pathlib import Path

import pytest
from viam.utils import struct_to_dict

from src.geometries import (
    SUPPORTED_MESH_CONTENT_TYPES,
    SUPPORTED_TYPES,
    build_box,
    build_capsule,
    build_mesh,
    build_metadata,
    build_point,
    build_pointcloud,
    build_pose,
    build_sphere,
    infer_mesh_content_type,
    load_mesh_bytes_as_ply,
    read_asset,
    stl_to_ply,
)


# ---------- build_metadata ----------
#
# Schema MUST match viamrobotics/visualization::draw/transform.go::MetadataToStruct
# and protos/draw/v1/metadata.proto. The RDK fake's old shape was wrong
# and silently no-op'd through 0.0.5.

import base64 as _b64


def test_build_metadata_color_packs_as_base64_rgb_bytes():
    md = build_metadata(color={"r": 255, "g": 128, "b": 0})
    d = struct_to_dict(md)
    # colors is a base64 string of 3 packed bytes [R, G, B].
    assert d["colors"] == _b64.b64encode(bytes([255, 128, 0])).decode("ascii")
    # color_format = 1 (COLOR_FORMAT_RGB), the only value defined.
    assert d["color_format"] == 1.0


def test_build_metadata_opacity_packs_as_base64_alpha_byte():
    """opacity 0..1 becomes a single uint8 byte 0..255."""
    md = build_metadata(opacity=0.5)
    d = struct_to_dict(md)
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
    assert d["colors"] == _b64.b64encode(bytes([10, 20, 30])).decode("ascii")
    assert d["color_format"] == 1.0
    assert d["opacities"] == _b64.b64encode(bytes([round(0.4 * 255)])).decode("ascii")


def test_build_metadata_returns_none_when_nothing_set():
    assert build_metadata() is None
    assert build_metadata(color=None, opacity=None) is None


def test_build_metadata_show_axes_helper_only_emitted_when_true():
    """Avoid emitting noisy fields the viewer would treat as explicit
    'false' overrides — only set the flag when the user actually wants
    the XYZ triad rendered at the entity origin."""
    md_off = build_metadata(color={"r": 0, "g": 0, "b": 0}, show_axes_helper=False)
    md_on = build_metadata(color={"r": 0, "g": 0, "b": 0}, show_axes_helper=True)
    assert "show_axes_helper" not in struct_to_dict(md_off)
    assert struct_to_dict(md_on)["show_axes_helper"] is True


def test_build_metadata_invisible_only_emitted_when_true():
    md_off = build_metadata(color={"r": 0, "g": 0, "b": 0}, invisible=False)
    md_on = build_metadata(color={"r": 0, "g": 0, "b": 0}, invisible=True)
    assert "invisible" not in struct_to_dict(md_off)
    assert struct_to_dict(md_on)["invisible"] is True


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
        "box", "sphere", "capsule", "point", "mesh", "pointcloud",
    }


def test_supported_mesh_content_types_is_lowercase():
    """The renderer only accepts lowercase 'ply' and 'stl' (see
    rdk/spatialmath/mesh.go). Validate config rejects uppercase
    variants downstream."""
    for ct in SUPPORTED_MESH_CONTENT_TYPES:
        assert ct == ct.lower()
