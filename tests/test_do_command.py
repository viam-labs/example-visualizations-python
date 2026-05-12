"""Tests for SceneSprites.do_command — the playground surface.

Each verb is tested for: happy path, missing payload, idempotency
where applicable, and the side effects on internal state. The async
nature of do_command + the subscriber fanout is exercised by
test_service.py — these tests focus on the dispatch table and the
mutation logic.
"""
import pytest

from src.service import (
    DEFAULT_PARENT_FRAME,
    DEFAULT_TICK_HZ,
    DEFAULT_UUID_STRATEGY,
    SceneSprites,
)


def _bare_service():
    """Construct the service bypassing new() so tests don't need a
    Viam framework to drive lifecycle."""
    s = SceneSprites.__new__(SceneSprites)
    SceneSprites.__init__(s, "test")
    s.tick_hz = DEFAULT_TICK_HZ
    s.uuid_strategy = DEFAULT_UUID_STRATEGY
    s.parent_frame = DEFAULT_PARENT_FRAME
    return s


def _box_item(label="b1", **overrides):
    item = {
        "type": "box",
        "label": label,
        "pose": {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        "dims_mm": {"x": 100, "y": 100, "z": 100},
        "color": {"r": 255, "g": 0, "b": 0},
        "opacity": 1.0,
        "animation": {"mode": "none"},
    }
    item.update(overrides)
    return item


# ---------- list ----------

async def test_list_empty_service_returns_empty():
    s = _bare_service()
    out = await s.do_command({"command": "list"})
    assert out == {"items": []}


async def test_list_returns_one_summary_per_item():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("b1")})
    await s.do_command({"command": "add", "item": _box_item("b2")})
    out = await s.do_command({"command": "list"})
    labels = [it["label"] for it in out["items"]]
    assert sorted(labels) == ["b1", "b2"]
    # Summary carries the playground-relevant fields.
    for it in out["items"]:
        for k in ("label", "type", "uuid", "pose", "animation_mode", "color", "opacity"):
            assert k in it


# ---------- add ----------

async def test_add_installs_item_with_stable_uuid_equal_to_label():
    s = _bare_service()
    out = await s.do_command({"command": "add", "item": _box_item("my_label")})
    assert out["label"] == "my_label"
    # Default UUID strategy is stable -> UUID == label.
    assert out["uuid"] == "my_label"
    assert "my_label" in s._state


async def test_add_versioned_uuid_includes_timestamp_suffix():
    s = _bare_service()
    s.uuid_strategy = "versioned"
    out = await s.do_command({"command": "add", "item": _box_item("v_label")})
    assert out["uuid"].startswith("v_label_")
    assert out["uuid"] != "v_label"


async def test_add_missing_item_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="add requires"):
        await s.do_command({"command": "add"})


async def test_add_duplicate_label_raises():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("dup")})
    with pytest.raises(Exception, match="already exists"):
        await s.do_command({"command": "add", "item": _box_item("dup")})


# ---------- remove ----------

async def test_remove_returns_false_for_unknown_label():
    s = _bare_service()
    out = await s.do_command({"command": "remove", "label": "ghost"})
    assert out == {"removed": False}


async def test_remove_drops_item_and_returns_true():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("gone")})
    out = await s.do_command({"command": "remove", "label": "gone"})
    assert out == {"removed": True}
    assert "gone" not in s._state


async def test_remove_missing_label_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="remove requires"):
        await s.do_command({"command": "remove"})


# ---------- update ----------

async def test_update_color_emits_metadata_color_fieldmask_path():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u1")})
    out = await s.do_command({
        "command": "update",
        "label": "u1",
        "patch": {"color": {"r": 0, "g": 255, "b": 0}},
    })
    assert out["updated_fields"] == ["metadata.color"]
    assert s._state["u1"]["item"]["color"] == {"r": 0, "g": 255, "b": 0}


async def test_update_opacity_emits_metadata_opacity_fieldmask_path():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u2")})
    out = await s.do_command({
        "command": "update", "label": "u2", "patch": {"opacity": 0.25},
    })
    assert out["updated_fields"] == ["metadata.opacity"]
    assert s._state["u2"]["item"]["opacity"] == 0.25


async def test_update_pose_x_emits_pose_x_fieldmask_path():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u3")})
    out = await s.do_command({
        "command": "update", "label": "u3", "patch": {"pose": {"x": 500}},
    })
    assert out["updated_fields"] == ["poseInObserverFrame.pose.x"]
    assert s._state["u3"]["base_pose"]["x"] == 500


async def test_update_pose_multi_axis_emits_one_path_per_axis():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u4")})
    out = await s.do_command({
        "command": "update", "label": "u4",
        "patch": {"pose": {"x": 100, "y": 200}},
    })
    assert set(out["updated_fields"]) == {
        "poseInObserverFrame.pose.x", "poseInObserverFrame.pose.y",
    }


async def test_update_box_dims_emits_all_three_dim_paths():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u5")})
    out = await s.do_command({
        "command": "update", "label": "u5",
        "patch": {"dims_mm": {"x": 200, "y": 300, "z": 50}},
    })
    assert set(out["updated_fields"]) >= {
        "physicalObject.geometryType.value.dimsMm.x",
        "physicalObject.geometryType.value.dimsMm.y",
        "physicalObject.geometryType.value.dimsMm.z",
    }
    assert s._state["u5"]["item"]["dims_mm"] == {"x": 200, "y": 300, "z": 50}


async def test_update_sphere_radius():
    s = _bare_service()
    sphere = {
        "type": "sphere", "label": "u6",
        "pose": {"x": 0, "y": 0, "z": 0, "oz": 1},
        "radius_mm": 50, "animation": {"mode": "none"},
    }
    await s.do_command({"command": "add", "item": sphere})
    out = await s.do_command({
        "command": "update", "label": "u6", "patch": {"radius_mm": 120},
    })
    assert "physicalObject.geometryType.value.radiusMm" in out["updated_fields"]
    assert s._state["u6"]["item"]["radius_mm"] == 120


async def test_update_mesh_path_swaps_file_at_runtime(tmp_path):
    """mesh_path updates are how a user swaps which mesh renders
    without reconfiguring the whole service. The geometry rebuild
    happens inside update; we just confirm the state mutated."""
    s = _bare_service()
    # Use the shipped assets so file IO works without monkeying with
    # the module dir.
    mesh_item = {
        "type": "mesh", "label": "u7",
        "pose": {"x": 0, "y": 0, "z": 0, "oz": 1},
        "mesh_path": "assets/icosahedron.ply",
        "animation": {"mode": "none"},
    }
    await s.do_command({"command": "add", "item": mesh_item})
    out = await s.do_command({
        "command": "update", "label": "u7",
        "patch": {"mesh_path": "assets/bunny.stl"},
    })
    assert "physicalObject.mesh" in out["updated_fields"]
    assert s._state["u7"]["item"]["mesh_path"] == "assets/bunny.stl"


async def test_update_unknown_label_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="unknown label"):
        await s.do_command({
            "command": "update", "label": "ghost", "patch": {"opacity": 0.5},
        })


async def test_update_missing_patch_raises():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("u8")})
    with pytest.raises(Exception, match="patch"):
        await s.do_command({"command": "update", "label": "u8"})


# ---------- clear ----------

async def test_clear_returns_removed_count_and_empties_state():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("a")})
    await s.do_command({"command": "add", "item": _box_item("b")})
    out = await s.do_command({"command": "clear"})
    assert out == {"removed_count": 2}
    assert s._state == {}


# ---------- preset ----------

async def test_preset_replaces_existing_items():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("manual")})
    out = await s.do_command({"command": "preset", "name": "color_wheel"})
    assert out["loaded"] == "color_wheel"
    assert out["count"] == 10
    # The manually-added item is gone — preset is a hard reset.
    assert "manual" not in s._state
    # Ten new sphere labels are present.
    assert all(s._state[label]["item"]["type"] == "sphere" for label in s._state)


async def test_preset_unknown_name_raises():
    s = _bare_service()
    with pytest.raises(Exception):
        await s.do_command({"command": "preset", "name": "not_a_real_preset"})


async def test_preset_primitives_loads_eight_items():
    s = _bare_service()
    out = await s.do_command({"command": "preset", "name": "primitives"})
    assert out["count"] == 8


# ---------- snapshot ----------

async def test_snapshot_returns_pasteable_config():
    """A snapshot should roundtrip — passing the returned ``config`` to
    validate_config + reconfigure should reproduce the same scene."""
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("snap_box")})
    await s.do_command({"command": "add", "item": _box_item("snap_box_2",
        pose={"x": 200, "y": 0, "z": 0, "oz": 1})})
    out = await s.do_command({"command": "snapshot"})
    cfg = out["config"]
    # Top-level service params present.
    assert cfg["tick_hz"] == DEFAULT_TICK_HZ
    assert cfg["uuid_strategy"] == DEFAULT_UUID_STRATEGY
    assert cfg["parent_frame"] == DEFAULT_PARENT_FRAME
    # Items survive.
    labels = [it["label"] for it in cfg["items"]]
    assert sorted(labels) == ["snap_box", "snap_box_2"]


async def test_snapshot_roundtrips_through_validate_config():
    """Hardens the snapshot/restore contract: a snapshot's items must
    pass validate_config so the user can paste it back into machine
    config without surprises."""
    from viam.proto.app.robot import ComponentConfig
    from viam.utils import dict_to_struct

    s = _bare_service()
    await s.do_command({"command": "preset", "name": "primitives"})
    snap = (await s.do_command({"command": "snapshot"}))["config"]
    cfg = ComponentConfig(attributes=dict_to_struct(snap))
    SceneSprites.validate_config(cfg)


# ---------- set_uuid_strategy ----------

async def test_set_uuid_strategy_toggles_runtime_setting():
    s = _bare_service()
    assert s.uuid_strategy == "stable"
    out = await s.do_command({"command": "set_uuid_strategy", "strategy": "versioned"})
    assert out == {"strategy": "versioned"}
    assert s.uuid_strategy == "versioned"


async def test_set_uuid_strategy_unknown_value_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="one of"):
        await s.do_command({"command": "set_uuid_strategy", "strategy": "shuffle"})


# ---------- default / debug ----------

async def test_no_command_returns_debug_snapshot():
    s = _bare_service()
    out = await s.do_command({})
    # Debug snapshot is a dict with these specific keys.
    assert "tick_hz" in out
    assert "uuid_strategy" in out
    assert "item_count" in out
    assert "subscriber_count" in out


async def test_unknown_command_returns_debug_snapshot():
    """Unrecognized commands return the debug snapshot, matching the
    apriltag-tracker convention."""
    s = _bare_service()
    out = await s.do_command({"command": "wat"})
    assert "tick_hz" in out
