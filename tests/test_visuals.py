"""Tests for ``src/visuals.py`` — the OO API.

Covers the contract that ``Visual.to_item_dict()`` produces dicts
the service layer accepts unchanged, plus construction-time
validation rejects bad params before they reach the wire."""

import pytest

from src.visuals import (
    Arrow,
    Box,
    Capsule,
    Mesh,
    Point,
    PointCloud,
    Pose,
    Sphere,
    Visual,
)


# ---------- Pose ---------------------------------------------------------

def test_pose_identity_is_default():
    p = Pose.identity()
    assert p.x == 0 and p.y == 0 and p.z == 0
    assert p.ox == 0 and p.oy == 0 and p.oz == 1.0
    assert p.theta == 0


def test_pose_at_sets_position():
    p = Pose.at(x=100, y=-50, z=25)
    d = p.to_dict()
    assert d == {"x": 100, "y": -50, "z": 25,
                 "ox": 0, "oy": 0, "oz": 1.0, "theta": 0}


def test_pose_dataclass_full_constructor():
    p = Pose(x=1, y=2, z=3, ox=0.7, oy=0.7, oz=0, theta=1.5)
    d = p.to_dict()
    assert d["ox"] == 0.7 and d["oy"] == 0.7 and d["oz"] == 0
    assert d["theta"] == 1.5


# ---------- Box ----------------------------------------------------------

def test_box_dict_matches_hand_written_shape():
    b = Box("demo_box", pose=Pose.at(x=-1600),
            dims_mm=(150, 150, 150), color=(230, 25, 75), opacity=1.0)
    d = b.to_item_dict()
    # Field-by-field — order doesn't matter for dict equality.
    assert d["type"] == "box"
    assert d["label"] == "demo_box"
    assert d["pose"] == {"x": -1600, "y": 0, "z": 0,
                         "ox": 0, "oy": 0, "oz": 1.0, "theta": 0}
    assert d["dims_mm"] == {"x": 150.0, "y": 150.0, "z": 150.0}
    assert d["color"] == {"r": 230, "g": 25, "b": 75}
    assert d["opacity"] == 1.0
    assert d["animation"] == {"mode": "none"}


def test_box_rejects_non_positive_dims():
    with pytest.raises(ValueError):
        Box("x", dims_mm=(150, 0, 150))
    with pytest.raises(ValueError):
        Box("x", dims_mm=(150, -1, 150))


def test_box_rejects_wrong_dims_arity():
    with pytest.raises(ValueError):
        Box("x", dims_mm=(150, 150))  # only 2 components


# ---------- Sphere -------------------------------------------------------

def test_sphere_dict_matches():
    s = Sphere("demo_sphere", radius_mm=90, color=(60, 180, 75), opacity=1.0)
    d = s.to_item_dict()
    assert d["type"] == "sphere"
    assert d["radius_mm"] == 90.0
    assert d["color"] == {"r": 60, "g": 180, "b": 75}


def test_sphere_rejects_non_positive_radius():
    with pytest.raises(ValueError):
        Sphere("x", radius_mm=0)


# ---------- Capsule ------------------------------------------------------

def test_capsule_dict_matches():
    c = Capsule("demo_capsule", radius_mm=50, length_mm=200,
                color=(0, 130, 200), opacity=1.0)
    d = c.to_item_dict()
    assert d["type"] == "capsule"
    assert d["radius_mm"] == 50.0
    assert d["length_mm"] == 200.0


def test_capsule_rejects_non_positive_dims():
    with pytest.raises(ValueError):
        Capsule("x", radius_mm=50, length_mm=0)
    with pytest.raises(ValueError):
        Capsule("x", radius_mm=0, length_mm=200)


# ---------- Point --------------------------------------------------------

def test_point_dict_has_no_shape_fields():
    p = Point("demo_point", color=(255, 225, 25), opacity=1.0)
    d = p.to_item_dict()
    assert d["type"] == "point"
    assert "radius_mm" not in d
    assert "dims_mm" not in d


# ---------- Arrow --------------------------------------------------------

def test_arrow_dict_matches():
    a = Arrow("demo_arrow", length_mm=220, radius_mm=12,
              color=(145, 30, 180), opacity=1.0)
    d = a.to_item_dict()
    assert d["type"] == "arrow"
    assert d["length_mm"] == 220.0
    assert d["radius_mm"] == 12.0


def test_arrow_rejects_non_positive_dims():
    with pytest.raises(ValueError):
        Arrow("x", length_mm=220, radius_mm=0)
    with pytest.raises(ValueError):
        Arrow("x", length_mm=0, radius_mm=12)


# ---------- Mesh ---------------------------------------------------------

def test_mesh_basic():
    m = Mesh("demo_bunny", mesh_path="assets/bunny.stl",
             color=(245, 130, 49), opacity=1.0)
    d = m.to_item_dict()
    assert d["type"] == "mesh"
    assert d["mesh_path"] == "assets/bunny.stl"
    assert "raw_stl" not in d


def test_mesh_raw_stl_flag_propagates():
    m = Mesh("demo_bunny_raw_stl", mesh_path="assets/bunny.stl",
            raw_stl=True, color=(245, 130, 49), opacity=1.0)
    d = m.to_item_dict()
    assert d["raw_stl"] is True


def test_mesh_requires_path():
    with pytest.raises(ValueError):
        Mesh("x", mesh_path="")


# ---------- PointCloud ---------------------------------------------------

def test_pointcloud_basic():
    pc = PointCloud("demo_pointcloud", pointcloud_path="assets/helix.pcd",
                    opacity=1.0)
    d = pc.to_item_dict()
    assert d["type"] == "pointcloud"
    assert d["pointcloud_path"] == "assets/helix.pcd"
    assert "chunked" not in d
    assert "chunk_size" not in d
    assert "color" not in d  # absence preserved when None


def test_pointcloud_chunked_flags_propagate():
    pc = PointCloud("demo_chunked", pointcloud_path="assets/helix.pcd",
                    chunked=True, chunk_size=2000, opacity=1.0)
    d = pc.to_item_dict()
    assert d["chunked"] is True
    assert d["chunk_size"] == 2000


def test_pointcloud_rejects_bad_chunk_size():
    with pytest.raises(ValueError):
        PointCloud("x", pointcloud_path="x", chunk_size=0)


# ---------- Cross-cutting -------------------------------------------------

def test_opacity_out_of_range_rejected():
    b = Box("x", dims_mm=(1, 1, 1), opacity=1.5)
    with pytest.raises(ValueError):
        b.to_item_dict()


def test_color_tuple_or_dict_both_accepted():
    b1 = Box("a", dims_mm=(1, 1, 1), color=(230, 25, 75))
    b2 = Box("b", dims_mm=(1, 1, 1), color={"r": 230, "g": 25, "b": 75})
    assert b1.to_item_dict()["color"] == b2.to_item_dict()["color"]


def test_animation_passthrough_when_set():
    s = Sphere("x", radius_mm=10,
               animation={"mode": "spin", "rpm": 15})
    d = s.to_item_dict()
    assert d["animation"] == {"mode": "spin", "rpm": 15}


def test_animation_defaults_to_none_mode_when_unset():
    s = Sphere("x", radius_mm=10)
    d = s.to_item_dict()
    assert d["animation"] == {"mode": "none"}


def test_parent_frame_propagates_when_set():
    s = Sphere("x", radius_mm=10, parent_frame="anchor")
    d = s.to_item_dict()
    assert d["parent_frame"] == "anchor"


def test_show_axes_helper_propagates():
    s = Sphere("x", radius_mm=10, show_axes_helper=True)
    d = s.to_item_dict()
    assert d["show_axes_helper"] is True


def test_invisible_propagates():
    s = Sphere("x", radius_mm=10, invisible=True)
    d = s.to_item_dict()
    assert d["invisible"] is True


def test_label_required():
    s = Sphere("", radius_mm=10)
    with pytest.raises(ValueError):
        s.to_item_dict()


# ---------- Pose accepts dict for back-compat ---------------------------

def test_pose_as_dict_accepted():
    s = Sphere("x", radius_mm=10, pose={"x": 100, "y": 50})
    d = s.to_item_dict()
    # Missing keys fill from identity.
    assert d["pose"] == {"x": 100.0, "y": 50.0, "z": 0.0,
                         "ox": 0.0, "oy": 0.0, "oz": 1.0, "theta": 0.0}
