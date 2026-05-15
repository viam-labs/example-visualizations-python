"""Tests for SceneServiceBase.apply_events — the batched event verb
the driver→visualizer pipeline depends on."""

from __future__ import annotations

import pytest

from src.service import (
    DEFAULT_PARENT_FRAME,
    DEFAULT_TICK_HZ,
    DEFAULT_UUID_STRATEGY,
    SceneSprites,
)
from viam_visuals import Pose, Scene, Box, Sphere, events_to_wire


def _bare_service():
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


# ---- happy path -------------------------------------------------------

async def test_apply_events_adds_installs_item_and_broadcasts():
    s = _bare_service()
    result = await s.do_command({
        "command": "apply_events",
        "events": [
            {"kind": "added", "label": "b1", "item": _box_item("b1")},
        ],
    })
    assert result["applied"] == 1
    assert result["added"] == 1
    assert result["errors"] == []
    assert "b1" in s._state


async def test_apply_events_updated_replaces_state_and_uses_given_paths():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("b1")})

    new_item = _box_item("b1", color={"r": 0, "g": 255, "b": 0})
    new_item["pose"]["x"] = 200
    result = await s.do_command({
        "command": "apply_events",
        "events": [{
            "kind": "updated",
            "label": "b1",
            "item": new_item,
            "paths": ["poseInObserverFrame.pose.x", "metadata.colors"],
        }],
    })
    assert result["updated"] == 1
    assert s._state["b1"]["item"]["color"] == {"r": 0, "g": 255, "b": 0}
    assert s._state["b1"]["base_pose"]["x"] == 200


async def test_apply_events_removed_drops_state():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("b1")})

    result = await s.do_command({
        "command": "apply_events",
        "events": [{"kind": "removed", "label": "b1"}],
    })
    assert result["removed"] == 1
    assert "b1" not in s._state


async def test_apply_events_mixed_batch():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _box_item("b_existing")})

    new = _box_item("b_existing")
    new["pose"]["y"] = 50
    result = await s.do_command({
        "command": "apply_events",
        "events": [
            {"kind": "added", "label": "b_new", "item": _box_item("b_new")},
            {"kind": "updated", "label": "b_existing", "item": new,
             "paths": ["poseInObserverFrame.pose.y"]},
            {"kind": "removed", "label": "b_existing"},
        ],
    })
    assert result["added"] == 1
    assert result["updated"] == 1
    assert result["removed"] == 1
    assert "b_new" in s._state
    assert "b_existing" not in s._state


# ---- namespace --------------------------------------------------------

async def test_namespace_prefixes_labels():
    s = _bare_service()
    result = await s.do_command({
        "command": "apply_events",
        "namespace": "driver1",
        "events": [
            {"kind": "added", "label": "obj_a", "item": _box_item("obj_a")},
        ],
    })
    assert result["added"] == 1
    assert "driver1/obj_a" in s._state
    assert "obj_a" not in s._state


async def test_namespace_isolates_drivers():
    """Two drivers pushing the same label coexist with namespacing."""
    s = _bare_service()
    await s.do_command({
        "command": "apply_events",
        "namespace": "driver_red",
        "events": [{"kind": "added", "label": "x", "item": _box_item("x")}],
    })
    await s.do_command({
        "command": "apply_events",
        "namespace": "driver_blue",
        "events": [{"kind": "added", "label": "x", "item": _box_item("x")}],
    })
    assert "driver_red/x" in s._state
    assert "driver_blue/x" in s._state


# ---- errors -----------------------------------------------------------

async def test_apply_events_records_errors_per_event_without_aborting():
    s = _bare_service()
    result = await s.do_command({
        "command": "apply_events",
        "events": [
            {"kind": "added", "label": "good", "item": _box_item("good")},
            {"kind": "updated", "label": "ghost", "item": _box_item("ghost"),
             "paths": []},                                # unknown label
            {"kind": "added", "label": "good", "item": _box_item("good")},  # dup
            {"kind": "added", "label": "also_good", "item": _box_item("also_good")},
        ],
    })
    assert result["added"] == 2
    assert len(result["errors"]) == 2
    assert "good" in s._state
    assert "also_good" in s._state


async def test_apply_events_unknown_kind_records_error():
    s = _bare_service()
    result = await s.do_command({
        "command": "apply_events",
        "events": [{"kind": "wat", "label": "x"}],
    })
    assert result["applied"] == 0
    assert len(result["errors"]) == 1


async def test_apply_events_missing_label_records_error():
    s = _bare_service()
    result = await s.do_command({
        "command": "apply_events",
        "events": [{"kind": "added", "item": _box_item("b")}],
    })
    assert result["applied"] == 0
    assert len(result["errors"]) == 1


async def test_apply_events_non_list_events_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="apply_events requires 'events'"):
        await s.do_command({"command": "apply_events", "events": "nope"})


# ---- Scene → wire round-trip ------------------------------------------

async def test_scene_events_round_trip_through_apply_events():
    """The library's headline integration: driver builds a Scene,
    serializes events_to_wire, ships to visualizer's apply_events,
    visualizer's state matches what the Scene produced."""
    s = _bare_service()
    scene = Scene()

    box = Box("demo_box", dims_mm=(100, 100, 100))
    sphere = Sphere("demo_sphere", radius_mm=50, pose=Pose.at(x=300))

    add_events = scene.add(box, sphere)
    result = await s.do_command({
        "command": "apply_events",
        "events": events_to_wire(add_events),
    })
    assert result["added"] == 2

    # Mutate and re-push.
    box.pose = Pose.at(x=-200, y=100)
    update_events = scene.update(box)
    result2 = await s.do_command({
        "command": "apply_events",
        "events": events_to_wire(update_events),
    })
    assert result2["updated"] == 1
    assert s._state["demo_box"]["base_pose"]["x"] == -200
    assert s._state["demo_box"]["base_pose"]["y"] == 100


async def test_events_to_wire_omits_empty_paths_and_items():
    """REMOVED events have no item/paths; serialization shouldn't
    add empty containers to the wire."""
    from viam_visuals.scene import SceneEvent
    wire = events_to_wire([
        SceneEvent(kind="removed", label="x"),
    ])
    assert wire == [{"kind": "removed", "label": "x"}]
