"""Tests for the SimpleSceneExample minimal model — the canonical
"I just want to add a few geometries" reference.

Bypasses ``SimpleSceneExample.new()`` (which expects a framework-
supplied ComponentConfig) and exercises reconfigure / tick /
build_geometry directly with bare instances.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

import viam_visuals as viz
from src.simple_scene_example import SimpleSceneExample


def _stub_config():
    return SimpleNamespace(name="test", attributes=None)


def _bare_service():
    s = SimpleSceneExample.__new__(SimpleSceneExample)
    SimpleSceneExample.__init__(s, "test")
    return s


def test_reconfigure_installs_all_items():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    expected = {
        "demo_box",
        "demo_sphere",
        "demo_capsule",  # statics
        "moving_box",  # 4-channel animated
        "pivot",
        "pivot_child_sphere",
        "pivot_child_box",  # hierarchical
    }
    assert set(s.scene.labels()) == expected
    assert set(s._state.keys()) == expected


def test_pivot_children_use_pivot_as_parent_frame():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    for label in ("pivot_child_sphere", "pivot_child_box"):
        item = s._state[label]["item"]
        assert item["parent_frame"] == "pivot", (
            f"{label} should be parented to 'pivot', got {item.get('parent_frame')!r}"
        )


def test_scene_tick_rotates_pivot():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    events = list(s.scene_tick(s.scene, 1.0))
    pivot_events = [e for e in events if e.label == "pivot"]
    assert len(pivot_events) >= 1
    # theta should have changed (60 deg/sec * 1s = 60°).
    pivot = s.scene.get("pivot")
    assert abs(pivot.pose.theta - 60.0) < 1e-6


def test_reconfigure_static_items_have_distinct_types():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    types = {entry["item"]["type"] for entry in s._state.values()}
    assert types == {"box", "sphere", "capsule"}


def test_scene_tick_returns_events_for_moving_box():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    events = list(s.scene_tick(s.scene, 0.5))
    # Should produce at least one event (pose + dims change vs.
    # initial state).
    assert len(events) >= 1
    assert events[0].label == "moving_box"
    assert events[0].kind == "updated"


def test_scene_tick_emits_respawn_for_moving_box():
    # Moving box mutates color + opacity every step in addition to
    # pose + dims. Since metadata changes are involved, Scene
    # escalates the event to the respawn signal (paths=[]).
    # SceneServiceBase materializes the respawn as REMOVE + ADD
    # with fresh UUID — carrying the new pose AND new color in one
    # event sequence.
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    events = list(s.scene_tick(s.scene, 0.5))
    moving_events = [e for e in events if e.label == "moving_box"]
    assert len(moving_events) == 1
    assert moving_events[0].kind == "updated"
    assert moving_events[0].paths == []


def test_scene_tick_at_t_zero_still_emits_for_color_change():
    # At t=0, the orbital position and scale formulas equal the
    # initial pose / dims. But color changes from (255,100,0) →
    # hsv(0,1,1) = (255,0,0), so there's always at least a
    # metadata-only event (paths=[] → library respawn intercept).
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    events = list(s.scene_tick(s.scene, 0.0))
    assert len(events) == 1
    assert events[0].label == "moving_box"


def test_validate_config_returns_empty_deps():
    required, optional = SimpleSceneExample.validate_config(_stub_config())
    assert list(required) == []
    assert list(optional) == []


def test_build_geometry_dispatches_for_each_type():
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    for label in ("demo_box", "demo_sphere", "demo_capsule", "moving_box"):
        item = s._state[label]["item"]
        geom = s.build_geometry(item, {})
        assert geom is not None
        assert geom.label == label


def test_color_change_via_scene_update_yields_metadata_respawn_signal():
    """The library's color-respawn intercept: scene.update on a
    color-only change emits UPDATED with paths=[]. The
    SceneServiceBase._apply_events handler translates that to
    REMOVE+ADD with a fresh UUID on the wire — but at the Scene
    level, the user just sees the empty-paths UPDATED."""
    s = _bare_service()
    s.reconfigure(_stub_config(), {})
    box = s.scene.get("demo_box")
    box.color = (0, 255, 0)
    events = list(s.scene.update(box))
    assert len(events) == 1
    assert events[0].kind == "updated"
    assert events[0].paths == []  # metadata-only → respawn signal
