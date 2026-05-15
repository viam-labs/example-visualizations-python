"""Tests for the playground-visualizer model."""

from __future__ import annotations

import pytest
from google.protobuf.struct_pb2 import Struct, Value
from viam.proto.app.robot import ComponentConfig

from src.visualizer import PlaygroundVisualizer
from viam_visuals import registry


def _config(attrs: dict) -> ComponentConfig:
    """Build a ComponentConfig with the given attributes dict."""
    s = Struct()
    for k, v in attrs.items():
        if isinstance(v, bool):
            s.fields[k].bool_value = v
        elif isinstance(v, (int, float)):
            s.fields[k].number_value = float(v)
        elif isinstance(v, str):
            s.fields[k].string_value = v
        elif isinstance(v, list):
            s.fields[k].list_value.append(*v) if v else s.fields[k].list_value.append("")
        elif isinstance(v, dict):
            sub = Struct()
            for kk, vv in v.items():
                sub.fields[kk].string_value = str(vv)
            s.fields[k].struct_value.CopyFrom(sub)
    return ComponentConfig(name="vis", attributes=s)


def setup_function(_):
    for n in registry.names():
        registry.unregister(n)


# ---- validate_config --------------------------------------------------

def test_validate_config_rejects_items():
    cfg = ComponentConfig(name="vis", attributes=Struct())
    cfg.attributes.fields["items"].list_value.values.append(Value(string_value="x"))
    with pytest.raises(Exception, match="doesn't accept 'items'"):
        PlaygroundVisualizer.validate_config(cfg)


def test_validate_config_rejects_preset():
    cfg = _config({"preset": "all"})
    with pytest.raises(Exception, match="doesn't accept 'preset'"):
        PlaygroundVisualizer.validate_config(cfg)


def test_validate_config_accepts_empty():
    cfg = _config({})
    deps_req, deps_opt = PlaygroundVisualizer.validate_config(cfg)
    assert (list(deps_req), list(deps_opt)) == ([], [])


def test_validate_config_accepts_visualizer_knobs():
    cfg = _config({
        "tick_hz": 10.0,
        "uuid_strategy": "versioned",
        "parent_frame": "scene",
    })
    deps_req, deps_opt = PlaygroundVisualizer.validate_config(cfg)
    assert (list(deps_req), list(deps_opt)) == ([], [])


def test_validate_config_rejects_invalid_tick_hz():
    cfg = _config({"tick_hz": 100.0})
    with pytest.raises(Exception, match="tick_hz"):
        PlaygroundVisualizer.validate_config(cfg)


def test_validate_config_rejects_invalid_uuid_strategy():
    cfg = _config({"uuid_strategy": "made_up"})
    with pytest.raises(Exception, match="uuid_strategy"):
        PlaygroundVisualizer.validate_config(cfg)


# ---- model identity ---------------------------------------------------

def test_model_name():
    assert str(PlaygroundVisualizer.MODEL) == (
        "viam:example-visualizations-python:playground-visualizer"
    )


def test_default_preset_is_none():
    """Visualizer must not auto-load a preset on construction."""
    assert PlaygroundVisualizer.DEFAULT_PRESET is None


# ---- apply_events through the visualizer -----------------------------

async def test_apply_events_through_visualizer():
    """The visualizer reuses SceneSprites' apply_events. Sanity check
    that the inheritance chain doesn't shadow the verb."""
    vis = PlaygroundVisualizer.__new__(PlaygroundVisualizer)
    PlaygroundVisualizer.__init__(vis, "vis_test")
    vis.tick_hz = 30.0
    vis.uuid_strategy = "stable"
    vis.parent_frame = "world"

    item = {
        "type": "box", "label": "obj_a",
        "pose": {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        "dims_mm": {"x": 100, "y": 100, "z": 100},
        "color": {"r": 255, "g": 0, "b": 0}, "opacity": 1.0,
        "animation": {"mode": "none"},
    }
    result = await vis.do_command({
        "command": "apply_events",
        "events": [{"kind": "added", "label": "obj_a", "item": item}],
    })
    assert result["added"] == 1
    assert "obj_a" in vis._state
