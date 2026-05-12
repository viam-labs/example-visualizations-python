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
    read_asset,
)


# ---------- build_metadata ----------

def test_build_metadata_with_color_and_opacity_emits_nested_struct():
    md = build_metadata(color={"r": 255, "g": 128, "b": 0}, opacity=0.5)
    assert md is not None
    d = struct_to_dict(md)
    assert d == {"color": {"r": 255.0, "g": 128.0, "b": 0.0}, "opacity": 0.5}


def test_build_metadata_with_only_color():
    md = build_metadata(color={"r": 10, "g": 20, "b": 30})
    assert struct_to_dict(md) == {"color": {"r": 10.0, "g": 20.0, "b": 30.0}}


def test_build_metadata_with_only_opacity():
    md = build_metadata(opacity=0.25)
    assert struct_to_dict(md) == {"opacity": 0.25}


def test_build_metadata_returns_none_when_nothing_set():
    assert build_metadata() is None
    assert build_metadata(color=None, opacity=None) is None


def test_build_metadata_color_defaults_missing_channels_to_zero():
    md = build_metadata(color={"r": 100})
    assert struct_to_dict(md) == {"color": {"r": 100.0, "g": 0.0, "b": 0.0}}


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

def test_build_point_is_sphere_with_zero_radius():
    """Points are zero-radius spheres in the RDK convention — confirms
    we don't accidentally emit something the renderer can't handle."""
    g = build_point(label="dot")
    assert g.label == "dot"
    assert g.sphere.radius_mm == 0.0


# ---------- build_mesh ----------

def test_build_mesh_embeds_bytes_and_lowercase_content_type():
    g = build_mesh(b"\x80PLYBYTES", "ply", label="bunny")
    assert g.label == "bunny"
    assert g.mesh.mesh == b"\x80PLYBYTES"
    assert g.mesh.content_type == "ply"


def test_build_mesh_accepts_stl_content_type():
    g = build_mesh(b"\x00stlbytes", "stl", label="cube")
    assert g.mesh.content_type == "stl"


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
