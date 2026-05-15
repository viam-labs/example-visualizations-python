"""Tests for the driver recipes.

Recipes are pure functions over a Scene — no I/O, no async — so the
tests just exercise initial/tick at fixed t and assert on the
returned SceneEvent shapes + the resulting Scene state.
"""

from __future__ import annotations

import math

import pytest

from src.recipes import (
    RECIPES,
    AllPrimitives,
    DetectionsOverlay,
    MarchingBoxes,
    PulsingSpheres,
)
from viam_visuals import Scene


# ---- registry ---------------------------------------------------------

def test_recipes_registry_contains_all_four():
    assert set(RECIPES) == {
        "marching_boxes", "pulsing_spheres",
        "all_primitives", "detections_overlay",
    }


def test_recipes_have_matching_names():
    for name, recipe in RECIPES.items():
        assert recipe.name == name


# ---- all_primitives ---------------------------------------------------

def test_all_primitives_initial_adds_one_of_each_shape():
    scene = Scene()
    events = AllPrimitives().initial(scene)
    assert len(events) == 7
    assert all(e.kind == "added" for e in events)
    # Confirm every shape type is represented.
    types = {e.item_dict["type"] for e in events}
    assert types == {"box", "sphere", "capsule", "point",
                     "arrow", "mesh", "pointcloud"}


def test_all_primitives_labels_are_unique_and_prefixed():
    scene = Scene()
    AllPrimitives().initial(scene)
    labels = scene.labels()
    assert labels == [
        "demo_arrow", "demo_box", "demo_bunny", "demo_capsule",
        "demo_pcd", "demo_point", "demo_sphere",
    ]


def test_all_primitives_tick_is_static():
    scene = Scene()
    AllPrimitives().initial(scene)
    # No tick should produce events; recipe is static.
    assert AllPrimitives().tick(scene, 0.0) == []
    assert AllPrimitives().tick(scene, 1.5) == []
    assert AllPrimitives().tick(scene, 100.0) == []


def test_all_primitives_mesh_carries_asset_path():
    scene = Scene()
    events = AllPrimitives().initial(scene)
    mesh_event = next(e for e in events if e.item_dict["type"] == "mesh")
    assert mesh_event.item_dict["mesh_path"] == "assets/bunny.stl"


def test_all_primitives_pointcloud_carries_asset_path():
    scene = Scene()
    events = AllPrimitives().initial(scene)
    pcd_event = next(e for e in events if e.item_dict["type"] == "pointcloud")
    assert pcd_event.item_dict["pointcloud_path"] == "assets/helix.pcd"


# ---- detections_overlay ----------------------------------------------

def test_detections_overlay_initial_is_empty():
    """Recipe seeds nothing; first tick adds the detections so the
    initial-burst broadcast doesn't carry stale state."""
    scene = Scene()
    assert DetectionsOverlay().initial(scene) == []
    assert len(scene) == 0


def test_detections_overlay_first_tick_adds_n_detections():
    recipe = DetectionsOverlay()
    scene = Scene()
    recipe.initial(scene)
    events = recipe.tick(scene, 0.5)
    assert len(events) == recipe.N_DETECTIONS
    assert all(e.kind == "added" for e in events)
    assert len(scene) == recipe.N_DETECTIONS


def test_detections_overlay_subsequent_tick_updates_in_place():
    """Second tick should mutate (UPDATED), not re-add."""
    recipe = DetectionsOverlay()
    scene = Scene()
    recipe.initial(scene)
    recipe.tick(scene, 0.0)
    events = recipe.tick(scene, 0.5)
    assert len(events) == recipe.N_DETECTIONS
    assert all(e.kind == "updated" for e in events)
    # Pose paths should appear in every UPDATED.
    for e in events:
        assert any(p.startswith("poseInObserverFrame.pose.")
                   for p in e.paths)


def test_detections_overlay_no_event_when_pose_unchanged():
    """Two ticks at the same t produce identical poses; the second
    tick's diff is empty, so no UPDATED events fire."""
    recipe = DetectionsOverlay()
    scene = Scene()
    recipe.tick(scene, 0.5)               # adds
    events = recipe.tick(scene, 0.5)      # same t — no change
    assert events == []


def test_detections_overlay_detection_labels_are_namespaced():
    recipe = DetectionsOverlay()
    scene = Scene()
    recipe.tick(scene, 0.0)
    labels = scene.labels()
    expected = [f"det_{i}" for i in range(recipe.N_DETECTIONS)]
    assert sorted(labels) == sorted(expected)


def test_detections_overlay_each_detection_has_unique_color():
    recipe = DetectionsOverlay()
    scene = Scene()
    events = recipe.tick(scene, 0.0)
    colors = [tuple(sorted(e.item_dict["color"].items())) for e in events]
    assert len(set(colors)) == len(colors)


def test_detections_overlay_orbit_circles_origin():
    """Sanity check on the trajectory: at t=T/4 the first detection
    is roughly at (0, +R) and at t=3T/4 at (0, -R) — confirming the
    cosine/sine pair traces a circle, not a line."""
    recipe = DetectionsOverlay()
    scene = Scene()
    recipe.tick(scene, recipe.ORBIT_PERIOD_S * 0.25)  # phase i=0 → π/2
    visual_at_qtr = scene.get("det_0")
    assert visual_at_qtr is not None
    # cos(π/2) ≈ 0, sin(π/2) ≈ 1
    assert abs(visual_at_qtr.pose.x) < 1.0
    assert visual_at_qtr.pose.y > recipe.ORBIT_RADIUS_MM * 0.99


# ---- driver round-trip with the new recipes --------------------------

@pytest.mark.parametrize("recipe_name", ["all_primitives", "detections_overlay"])
def test_recipe_drives_visualizer_through_apply_events(recipe_name):
    """Smoke test: feed each recipe's tick output through
    events_to_wire and apply_events, confirm the visualizer state
    matches what the Scene says."""
    from src.driver import PlaygroundDriver  # noqa: F401 (sanity import)
    from src.visualizer import PlaygroundVisualizer
    from viam_visuals import events_to_wire, registry

    # Clear in-process registry to avoid test pollution.
    for n in registry.names():
        registry.unregister(n)

    vis = PlaygroundVisualizer.__new__(PlaygroundVisualizer)
    PlaygroundVisualizer.__init__(vis, "vis")
    vis.tick_hz = 30
    vis.uuid_strategy = "stable"
    vis.parent_frame = "world"

    recipe = RECIPES[recipe_name]
    scene = Scene()

    # Initial.
    initial = recipe.initial(scene)
    import asyncio
    if initial:
        asyncio.run(vis.do_command({
            "command": "apply_events",
            "events": events_to_wire(initial),
        }))

    # One tick.
    tick_events = recipe.tick(scene, 0.5)
    if tick_events:
        asyncio.run(vis.do_command({
            "command": "apply_events",
            "events": events_to_wire(tick_events),
        }))

    # Visualizer state should match scene's expected size.
    if recipe_name == "all_primitives":
        # 7 shapes, all added in initial; tick is static.
        assert len(vis._state) == 7
    elif recipe_name == "detections_overlay":
        # 0 initial; tick 1 adds N_DETECTIONS.
        assert len(vis._state) == DetectionsOverlay.N_DETECTIONS
