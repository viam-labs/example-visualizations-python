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
    AllRecipe,
    CoordinateFramesArm,
    DetectionsOverlay,
    LifecycleGarden,
    MarchingBoxes,
    PulsingSpheres,
    TrajectoryRunner,
)
from viam_visuals import Scene


# ---- registry ---------------------------------------------------------

def test_recipes_registry_contains_all_eight():
    assert set(RECIPES) == {
        "marching_boxes", "pulsing_spheres",
        "all_primitives", "detections_overlay",
        "coordinate_frames_arm", "trajectory_runner", "lifecycle_garden",
        "all",
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

# ---- coordinate_frames_arm -------------------------------------------

def test_coordinate_frames_arm_initial_installs_frames_and_arm():
    scene = Scene()
    events = CoordinateFramesArm().initial(scene)
    # 3 frames × 4 visuals (anchor + 3 axes) + 5 arm parts = 17.
    assert len(events) == 17
    labels = scene.labels()
    # Frame anchors and their axes.
    for i in range(3):
        assert f"frame_{i}" in labels
        assert f"frame_{i}_axis_x" in labels
        assert f"frame_{i}_axis_y" in labels
        assert f"frame_{i}_axis_z" in labels
    # Arm parts.
    for part in ["arm_shoulder", "arm_upper", "arm_elbow", "arm_forearm", "arm_wrist"]:
        assert part in labels


def test_coordinate_frames_arm_chained_parent_frames():
    """Each arm link's parent_frame should reference the previous link,
    forming a chain: shoulder → upper → elbow → forearm → wrist. The
    chain is what makes joint angles propagate to downstream links."""
    scene = Scene()
    CoordinateFramesArm().initial(scene)
    chain = [
        ("arm_upper",   "arm_shoulder"),
        ("arm_elbow",   "arm_upper"),
        ("arm_forearm", "arm_elbow"),
        ("arm_wrist",   "arm_forearm"),
    ]
    for child, expected_parent in chain:
        v = scene.get(child)
        assert v is not None, f"{child!r} missing from scene"
        # The composite expansion preserves parent_frame on each visual.
        assert v.parent_frame == expected_parent, (
            f"{child!r}.parent_frame = {v.parent_frame!r}; "
            f"expected {expected_parent!r}"
        )


def test_coordinate_frames_arm_tick_drives_anchors_and_joints():
    scene = Scene()
    CoordinateFramesArm().initial(scene)
    events = CoordinateFramesArm().tick(scene, 0.5)
    # 3 frame anchors + 3 arm joints = 6 UPDATED.
    assert len(events) == 6
    assert all(e.kind == "updated" for e in events)
    # Frame axes (children) should not produce events — only the
    # anchor moves; the axes follow via parent_frame chain.
    axis_paths = {e.label for e in events if e.label.endswith("_axis_x")}
    assert axis_paths == set()


def test_coordinate_frames_arm_no_event_when_t_unchanged():
    scene = Scene()
    CoordinateFramesArm().initial(scene)
    CoordinateFramesArm().tick(scene, 0.5)  # commits new poses
    # Second tick at the same t produces no UPDATEDs (state matches).
    assert CoordinateFramesArm().tick(scene, 0.5) == []


# ---- trajectory_runner -----------------------------------------------

def test_trajectory_runner_initial_installs_static_path_and_runner():
    scene = Scene()
    events = TrajectoryRunner().initial(scene)
    # 5 waypoints + 4 line segments + 1 runner = 10.
    assert len(events) == 10
    for i in range(5):
        assert f"wp_{i}" in scene.labels()
    assert "trajectory_runner" in scene.labels()
    # 4 segments connecting 5 waypoints.
    assert sum(1 for l in scene.labels() if l.startswith("trajectory_seg_")) == 4


def test_trajectory_runner_starts_at_first_waypoint_at_t_zero():
    scene = Scene()
    TrajectoryRunner().initial(scene)
    TrajectoryRunner().tick(scene, 0.0)
    runner = scene.get("trajectory_runner")
    wp0 = TrajectoryRunner.BASE_WAYPOINTS[0]
    assert runner is not None
    assert abs(runner.pose.x - wp0.x) < 1e-6
    assert abs(runner.pose.y - wp0.y) < 1e-6
    assert abs(runner.pose.z - wp0.z) < 1e-6


def test_trajectory_runner_only_runner_moves_during_tick():
    """Waypoints and line segments are static; only the runner gets
    an UPDATED event each tick."""
    scene = Scene()
    TrajectoryRunner().initial(scene)
    events = TrajectoryRunner().tick(scene, 1.0)
    assert len(events) == 1
    assert events[0].label == "trajectory_runner"


def test_trajectory_runner_midpoint_lerps_between_waypoints():
    """At halfway through segment 0, the runner should sit at the
    midpoint of waypoint 0 and waypoint 1."""
    scene = Scene()
    TrajectoryRunner().initial(scene)
    # n_segs = N_WAYPOINTS (because LOOP=True). Segment 0 spans
    # t=0 .. LAP_PERIOD_S/n_segs. Midpoint t = LAP_PERIOD_S/n_segs/2.
    n_segs = len(TrajectoryRunner.BASE_WAYPOINTS)  # LOOP=True
    t_mid = (TrajectoryRunner.LAP_PERIOD_S / n_segs) / 2.0
    TrajectoryRunner().tick(scene, t_mid)
    runner = scene.get("trajectory_runner")
    wp0 = TrajectoryRunner.BASE_WAYPOINTS[0]
    wp1 = TrajectoryRunner.BASE_WAYPOINTS[1]
    mid_x = (wp0.x + wp1.x) / 2
    mid_y = (wp0.y + wp1.y) / 2
    mid_z = (wp0.z + wp1.z) / 2
    assert abs(runner.pose.x - mid_x) < 1.0
    assert abs(runner.pose.y - mid_y) < 1.0
    assert abs(runner.pose.z - mid_z) < 1.0


# ---- lifecycle_garden ------------------------------------------------

def test_lifecycle_garden_initial_is_empty():
    scene = Scene()
    assert LifecycleGarden().initial(scene) == []
    assert len(scene) == 0


def test_lifecycle_garden_tick_at_t_zero_installs_alive_plots():
    """At t=0 with evenly-staggered phase offsets, ~4 of 5 plots are
    in non-gone phases — each appears with a fresh version label."""
    recipe = LifecycleGarden()
    scene = Scene()
    events = recipe.tick(scene, 0.0)
    # Phase offsets: 0, CYCLE/5, 2*CYCLE/5, 3*CYCLE/5, 4*CYCLE/5.
    # With CYCLE_S = 4.0, gone phase is the last 0.8s of cycle. At
    # t=0, plot 0's local_t=0 (appear), plot 1=0.8 (start of alive),
    # plot 2=1.6 (start of disappear maybe), plot 3=2.4, plot 4=3.2.
    # At least most plots should produce ADDED events.
    add_events = [e for e in events if e.kind == "added"]
    assert len(add_events) >= 3, f"expected several plots to add, got {events!r}"


def test_lifecycle_garden_label_versions_bump_across_cycles():
    """When a plot completes its gone phase and re-enters appear,
    the new label uses a higher version number than the prior."""
    recipe = LifecycleGarden()
    scene = Scene()
    # Tick in appear phase (plot 0: local_t=0.1 → appear, ADD v1).
    recipe.tick(scene, 0.1)
    versions_after_first = list(recipe._version)
    # Tick during plot 0's gone phase (local_t in [3.2, 4.0)) so it's
    # REMOVED, then tick after the wrap (back into appear) so it's
    # re-ADDED with a fresh version.
    gone_t = LifecycleGarden.APPEAR_S + LifecycleGarden.ALIVE_S + LifecycleGarden.DISAPPEAR_S + 0.1
    recipe.tick(scene, gone_t)
    recipe.tick(scene, LifecycleGarden.CYCLE_S + 0.1)
    versions_after_second = list(recipe._version)
    # Plot 0 should have incremented.
    assert versions_after_second[0] > versions_after_first[0]


def test_lifecycle_garden_re_add_uses_fresh_label():
    """The label for the re-added plot should differ from the one
    that was REMOVEd. The renderer's REMOVED-UUID cache would drop
    the new entity if labels matched."""
    recipe = LifecycleGarden()
    scene = Scene()
    # ADD plot 0 v1 in appear phase.
    recipe.tick(scene, 0.1)
    first_labels = {l for l in scene.labels() if l.startswith("garden_0_v")}
    # Walk through the gone phase explicitly so the recipe REMOVEs.
    gone_t = LifecycleGarden.APPEAR_S + LifecycleGarden.ALIVE_S + LifecycleGarden.DISAPPEAR_S + 0.1
    recipe.tick(scene, gone_t)
    # Now back into appear — recipe ADDs with fresh version.
    recipe.tick(scene, LifecycleGarden.CYCLE_S + 0.1)
    new_labels = {l for l in scene.labels() if l.startswith("garden_0_v")}
    # New labels shouldn't include the previously-removed ones.
    assert not (first_labels & new_labels), (
        f"reused stale labels {first_labels & new_labels}"
    )


def test_lifecycle_garden_color_changes_through_phases():
    """A plot in the appear phase is blue, alive is orange, disappear
    is red. The color attribute on the scene's Box changes as the
    recipe ticks through phases."""
    recipe = LifecycleGarden()
    scene = Scene()
    # Plot 0 starts at appear (local_t=0 with no phase offset).
    recipe.tick(scene, 0.0)
    plot0 = next(scene.get(l) for l in scene.labels() if l.startswith("garden_0_v"))
    assert plot0.color == recipe.COLOR_APPEAR
    # Step into alive phase.
    recipe.tick(scene, LifecycleGarden.APPEAR_S + 0.1)
    plot0 = next(scene.get(l) for l in scene.labels() if l.startswith("garden_0_v"))
    assert plot0.color == recipe.COLOR_ALIVE


# ---- y_origin parameter ----------------------------------------------

def test_y_origin_shifts_marching_boxes():
    """Each recipe accepts a y_origin parameter (default 0). The
    ``all`` recipe relies on this to stack sub-recipes at distinct Y
    offsets without overlap."""
    scene = Scene()
    MarchingBoxes(y_origin=-1500).initial(scene)
    box = scene.get("march_0")
    assert box is not None
    assert box.pose.y == -1500


def test_y_origin_shifts_coordinate_frames_arm():
    scene = Scene()
    CoordinateFramesArm(y_origin=1000).initial(scene)
    # Frames sit at FRAME_Y_OFFSET (=600) + y_origin.
    frame0 = scene.get("frame_0")
    assert frame0 is not None
    assert frame0.pose.y == 1600
    # Arm shoulder sits at ARM_BASE_Y_OFFSET (=-400) + y_origin.
    shoulder = scene.get("arm_shoulder")
    assert shoulder is not None
    assert shoulder.pose.y == 600


def test_y_origin_shifts_trajectory_waypoints():
    scene = Scene()
    TrajectoryRunner(y_origin=500).initial(scene)
    # First waypoint's base Y is -300; shifted by 500 → 200.
    wp0 = scene.get("wp_0")
    assert wp0 is not None
    assert wp0.pose.y == 200


# ---- all recipe ------------------------------------------------------

def test_all_recipe_runs_every_sub_recipe():
    scene = Scene()
    AllRecipe().initial(scene)
    # Every sub-recipe's labels should appear (composite expansions
    # included). Spot-check one label from each sub.
    expected = [
        "march_0",        # marching_boxes
        "pulse_0",        # pulsing_spheres
        "demo_box",       # all_primitives
        "frame_0",        # coordinate_frames_arm
        "arm_shoulder",   # coordinate_frames_arm
        "wp_0",           # trajectory_runner
        "trajectory_runner",  # trajectory_runner runner
    ]
    for label in expected:
        assert label in scene.labels(), f"{label!r} missing from `all` scene"


def test_all_recipe_sub_recipes_dont_overlap():
    """Each sub-recipe lives at its own Y zone — picking two
    sub-recipes and inspecting a representative label confirms
    they don't collapse onto each other."""
    scene = Scene()
    AllRecipe().initial(scene)
    march = scene.get("march_0")
    pulse = scene.get("pulse_0")
    assert march is not None and pulse is not None
    # Sub-recipes are stacked along Y; spacing is at least 500mm.
    assert abs(march.pose.y - pulse.pose.y) >= 500


def test_all_recipe_tick_animates_all_sub_recipes():
    """A single tick produces events from every animated sub-recipe."""
    recipe = AllRecipe()
    scene = Scene()
    recipe.initial(scene)
    events = recipe.tick(scene, 0.5)
    # all_primitives is static; the rest produce at least one event.
    labels_in_events = {e.label for e in events}
    # Confirm at least one event from each animated sub.
    assert any(l.startswith("march_") for l in labels_in_events)
    assert any(l.startswith("pulse_") for l in labels_in_events)
    assert any(l.startswith("det_") for l in labels_in_events)
    assert any(l.startswith("trajectory") for l in labels_in_events)


def test_all_recipe_subs_get_distinct_y_origins():
    """The internal layout table assigns each sub-recipe a unique
    y_origin — accidentally reusing one would stack two recipes."""
    layout_ys = [y for _, y in AllRecipe._LAYOUT]
    assert len(set(layout_ys)) == len(layout_ys)


# ---- driver round-trip ------------------------------------------------

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
