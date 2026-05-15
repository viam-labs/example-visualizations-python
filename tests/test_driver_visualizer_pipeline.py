"""End-to-end tests for the playground-driver → playground-visualizer
pipeline. Both run in the same process; the driver looks up the
visualizer via the in-process registry and calls its do_command
directly (no gRPC)."""

from __future__ import annotations

import asyncio
import time

import pytest
from google.protobuf.struct_pb2 import Struct, Value
from viam.proto.app.robot import ComponentConfig

from src.driver import PlaygroundDriver
from src.visualizer import PlaygroundVisualizer
from viam_visuals import registry


def _config(attrs: dict, name: str = "test") -> ComponentConfig:
    s = Struct()
    for k, v in attrs.items():
        if isinstance(v, bool):
            s.fields[k].bool_value = v
        elif isinstance(v, (int, float)):
            s.fields[k].number_value = float(v)
        elif isinstance(v, str):
            s.fields[k].string_value = v
    return ComponentConfig(name=name, attributes=s)


def setup_function(_):
    for n in registry.names():
        registry.unregister(n)


async def _make_visualizer(name="vis") -> PlaygroundVisualizer:
    vis = PlaygroundVisualizer.__new__(PlaygroundVisualizer)
    PlaygroundVisualizer.__init__(vis, name)
    vis.reconfigure(_config({}, name=name), {})
    return vis


async def _make_driver(
    vis_name="vis", recipe="marching_boxes", tick_hz=10.0, namespace="",
) -> PlaygroundDriver:
    d = PlaygroundDriver.__new__(PlaygroundDriver)
    PlaygroundDriver.__init__(d, "drv")
    attrs = {
        "visualizer": vis_name,
        "recipe": recipe,
        "tick_hz": tick_hz,
    }
    if namespace:
        attrs["namespace"] = namespace
    await d.reconfigure(_config(attrs, name="drv"), {})
    return d


# ---- validation -------------------------------------------------------

def test_driver_validate_requires_visualizer():
    with pytest.raises(Exception, match="'visualizer' is required"):
        PlaygroundDriver.validate_config(_config({"recipe": "marching_boxes"}))


def test_driver_validate_rejects_unknown_recipe():
    with pytest.raises(Exception, match="unknown recipe"):
        PlaygroundDriver.validate_config(_config({
            "visualizer": "vis", "recipe": "made_up",
        }))


def test_driver_validate_rejects_invalid_tick_hz():
    with pytest.raises(Exception, match="tick_hz"):
        PlaygroundDriver.validate_config(_config({
            "visualizer": "vis", "recipe": "marching_boxes", "tick_hz": 100.0,
        }))


def test_driver_validate_accepts_good_config():
    deps_req, deps_opt = PlaygroundDriver.validate_config(_config({
        "visualizer": "vis", "recipe": "marching_boxes", "tick_hz": 5.0,
    }))
    assert (list(deps_req), list(deps_opt)) == ([], [])


# ---- reconfigure / registry lookup -----------------------------------

async def test_driver_fails_when_visualizer_not_registered():
    d = PlaygroundDriver.__new__(PlaygroundDriver)
    PlaygroundDriver.__init__(d, "drv")
    with pytest.raises(Exception, match="not found in the in-process registry"):
        await d.reconfigure(
            _config({"visualizer": "ghost", "recipe": "marching_boxes"}),
            {},
        )


async def test_driver_seeds_visualizer_with_initial_scene():
    vis = await _make_visualizer()
    d = await _make_driver(tick_hz=10.0)
    # MarchingBoxes installs 5 boxes.
    assert len(vis._state) == 5
    # All are boxes with the expected label prefix.
    for label, st in vis._state.items():
        assert label.startswith("march_")
        assert st["item"]["type"] == "box"
    await d.close()


async def test_driver_tick_pushes_pose_updates():
    vis = await _make_visualizer()
    d = await _make_driver(tick_hz=20.0)
    # Capture initial y position of one box.
    initial_y = vis._state["march_0"]["base_pose"]["y"]
    # Wait two tick periods.
    await asyncio.sleep(0.2)
    # Same label should still be present (UPDATED, not ADDED/REMOVED).
    assert "march_0" in vis._state
    # Y should have changed (sin wave is rarely 0 at random t).
    after_y = vis._state["march_0"]["base_pose"]["y"]
    # Very tight chance the sample lands exactly at sin=0, so allow
    # some flakiness by sampling again if needed.
    if after_y == initial_y:
        await asyncio.sleep(0.1)
        after_y = vis._state["march_0"]["base_pose"]["y"]
    assert after_y != initial_y, "tick didn't update the box pose"
    await d.close()


async def test_driver_uses_in_process_reference_not_grpc_stub():
    """The driver's _visualizer attribute should be the actual
    PlaygroundVisualizer instance, proving the registry path
    short-circuited the gRPC stub path."""
    vis = await _make_visualizer()
    d = await _make_driver()
    assert d._visualizer is vis
    await d.close()


# ---- namespace --------------------------------------------------------

async def test_driver_namespace_prefixes_labels_on_visualizer():
    vis = await _make_visualizer()
    d = await _make_driver(namespace="ns1")
    # MarchingBoxes initial puts march_0..4 — with namespace, labels
    # become "ns1/march_0".."ns1/march_4" on the visualizer.
    assert "ns1/march_0" in vis._state
    assert "march_0" not in vis._state
    await d.close()


async def test_two_drivers_with_namespaces_coexist():
    vis = await _make_visualizer()
    d1 = await _make_driver(namespace="a")
    d2 = await _make_driver(recipe="pulsing_spheres", namespace="b")
    # 5 march_ from a, 3 pulse_ from b = 8 total.
    assert len(vis._state) == 8
    assert any(l.startswith("a/march_") for l in vis._state)
    assert any(l.startswith("b/pulse_") for l in vis._state)
    await d1.close()
    await d2.close()


# ---- DoCommand surface ------------------------------------------------

async def test_driver_info_command():
    vis = await _make_visualizer()
    d = await _make_driver()
    info = await d.do_command({"command": "info"})
    assert info["visualizer"] == "vis"
    assert info["recipe"] == "marching_boxes"
    assert info["scene_size"] == 5
    assert info["visualizer_type"] == "PlaygroundVisualizer"
    assert info["tick_running"] is True
    await d.close()


async def test_driver_recipes_command_lists_known_recipes():
    vis = await _make_visualizer()
    d = await _make_driver()
    out = await d.do_command({"command": "recipes"})
    assert "marching_boxes" in out["recipes"]
    assert "pulsing_spheres" in out["recipes"]
    await d.close()


async def test_driver_close_clears_visualizer_state():
    vis = await _make_visualizer()
    d = await _make_driver(namespace="cleanup_test")
    # 5 boxes added.
    assert any(l.startswith("cleanup_test/") for l in vis._state)
    await d.close()
    # After close, our labels should be gone (other namespaces untouched).
    assert not any(l.startswith("cleanup_test/") for l in vis._state)
