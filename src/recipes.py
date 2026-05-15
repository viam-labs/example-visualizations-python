"""Driver recipes — domain-logic generators that mutate a Scene.

A recipe pairs an :meth:`initial` (seed the scene) with a
:meth:`tick` (mutate at the driver's cadence). The driver
serializes the returned events and ships them to its visualizer.

Recipes are the "what to draw" side of the split. They're written
against the :class:`viam_visuals.Scene` API — no proto, no gRPC,
no field-mask paths. The library handles everything below the
:meth:`Scene.add` / :meth:`Scene.update` calls.

Add a new recipe by:

  1. Writing a class with ``initial(scene)`` and ``tick(scene, t)``
  2. Registering it in :data:`RECIPES` below

The driver picks one by name via its ``recipe`` config attribute.
"""
from __future__ import annotations

import math
from typing import Dict, List, Protocol

from viam_visuals import (
    Arrow,
    BoundingBox,
    Box,
    Capsule,
    Mesh,
    Point,
    PointCloud,
    Pose,
    Scene,
    SceneEvent,
    Sphere,
)


class Recipe(Protocol):
    """Two-method contract every recipe satisfies."""

    name: str

    def initial(self, scene: Scene) -> List[SceneEvent]:
        """Seed the scene with the recipe's initial visuals. Called
        once at driver startup (and on reconfigure). Returns the
        ADDED events the driver pushes to the visualizer."""
        ...

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        """Mutate the scene's state at time ``t`` (seconds since
        driver start). Returns the events to push — typically a list
        of UPDATEDs, occasionally ADDED/REMOVED if the recipe varies
        scene-graph membership over time. Return ``[]`` for no-op
        ticks (e.g. nothing changed this frame)."""
        ...


# ---- marching_boxes -----------------------------------------------------

class MarchingBoxes:
    """Five boxes in a row along X, each bobbing in Y on a sine wave.

    Simplest possible recipe — proves the pipeline end-to-end. Five
    boxes is enough to see the phase offsets land at different
    heights at a given instant, which makes it obvious the driver is
    actually streaming updates rather than the visualizer caching a
    static scene.
    """

    name = "marching_boxes"

    N_BOXES = 5
    SPACING_MM = 250
    AMPLITUDE_MM = 150
    PERIOD_S = 3.0

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_BOXES):
            x = (i - (self.N_BOXES - 1) / 2.0) * self.SPACING_MM
            box = Box(
                label=f"march_{i}",
                pose=Pose.at(x=x, y=0, z=100),
                dims_mm=(120, 120, 120),
                color=_rainbow(i / self.N_BOXES),
            )
            events.extend(scene.add(box))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        out: List[SceneEvent] = []
        for i in range(self.N_BOXES):
            label = f"march_{i}"
            box = scene.get(label)
            if box is None:
                continue
            x = (i - (self.N_BOXES - 1) / 2.0) * self.SPACING_MM
            phase = (2 * math.pi) * i / self.N_BOXES
            y = self.AMPLITUDE_MM * math.sin(2 * math.pi * t / self.PERIOD_S + phase)
            box.pose = Pose.at(x=x, y=y, z=100)
            out.extend(scene.update(box))
        return out


# ---- pulsing_spheres ---------------------------------------------------

class PulsingSpheres:
    """Three spheres pulsing their radius on phase-offset sine waves.

    Exercises a different field-mask path
    (``physicalObject.geometryType.value.radiusMm``) and confirms
    the visualizer rebuilds the geometry proto, not just the pose.
    """

    name = "pulsing_spheres"

    N_SPHERES = 3
    SPACING_MM = 400
    R_BASE = 80
    R_AMPLITUDE = 30
    PERIOD_S = 2.5

    def initial(self, scene: Scene) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_SPHERES):
            x = (i - (self.N_SPHERES - 1) / 2.0) * self.SPACING_MM
            sphere = Sphere(
                label=f"pulse_{i}",
                pose=Pose.at(x=x, y=0, z=120),
                radius_mm=self.R_BASE,
                color=_rainbow(0.7 * i / max(1, self.N_SPHERES - 1)),
            )
            events.extend(scene.add(sphere))
        return events

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        out: List[SceneEvent] = []
        for i in range(self.N_SPHERES):
            sp = scene.get(f"pulse_{i}")
            if sp is None:
                continue
            phase = (2 * math.pi) * i / self.N_SPHERES
            r = self.R_BASE + self.R_AMPLITUDE * math.sin(
                2 * math.pi * t / self.PERIOD_S + phase
            )
            sp.radius_mm = r
            out.extend(scene.update(sp))
        return out


# ---- all_primitives ----------------------------------------------------

class AllPrimitives:
    """One of every supported shape, static.

    Driver-side equivalent of the standalone-playground ``primitives``
    preset. Useful as the "what can I put in a Scene" reference: each
    shape type appears in a labeled row along X. Static — the driver
    pushes ADDED events on startup and nothing thereafter.

    Note that ``Mesh`` and ``PointCloud`` items reference asset paths
    that the *visualizer* resolves at install time. As long as the
    driver and visualizer ship from the same module binary (the
    default with the in-process registry), the visualizer's
    ``read_asset`` hook finds the assets in the module's installed
    directory. Cross-module drivers pointing at this visualizer would
    need the visualizer to know about the requested asset paths.
    """

    name = "all_primitives"

    SPACING_MM = 280

    def initial(self, scene: Scene) -> List[SceneEvent]:
        z = 100
        items = [
            Box(
                label="demo_box",
                pose=Pose.at(x=-3 * self.SPACING_MM, z=z),
                dims_mm=(140, 140, 140),
                color=(230, 25, 75),
            ),
            Sphere(
                label="demo_sphere",
                pose=Pose.at(x=-2 * self.SPACING_MM, z=z),
                radius_mm=80,
                color=(60, 180, 75),
            ),
            Capsule(
                label="demo_capsule",
                pose=Pose.at(x=-1 * self.SPACING_MM, z=z),
                radius_mm=40,
                length_mm=200,
                color=(0, 130, 200),
            ),
            Point(
                label="demo_point",
                pose=Pose.at(x=0, z=z),
                color=(245, 130, 48),
            ),
            Arrow(
                label="demo_arrow",
                pose=Pose.at(x=1 * self.SPACING_MM, z=z),
                length_mm=240,
                radius_mm=20,
                color=(145, 30, 180),
            ),
            Mesh(
                label="demo_bunny",
                pose=Pose.at(x=2 * self.SPACING_MM, z=z),
                mesh_path="assets/bunny.stl",
                color=(70, 240, 240),
            ),
            PointCloud(
                label="demo_pcd",
                pose=Pose.at(x=3 * self.SPACING_MM, z=z),
                pointcloud_path="assets/helix.pcd",
            ),
        ]
        return scene.add(*items)

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        return []  # static — nothing animates


# ---- detections_overlay ------------------------------------------------

class DetectionsOverlay:
    """Simulated object-detection overlay: N wireframe bounding boxes
    drifting around the origin.

    This is the canonical driver-shaped use case — a perception
    module produces detections on every tick and the visualizer
    publishes them to the renderer. The recipe stands in for the
    real detector by walking ``N`` synthetic detections on
    phase-offset circular paths.

    Uses :class:`viam_visuals.BoundingBox` (solid translucent
    variant), one Box per detection. Each tick rebuilds the
    BoundingBox with a fresh center pose; ``scene.add_or_update``
    diffs against the committed wire-format dict so existing
    detections produce UPDATED events with just the pose paths,
    while never-seen labels produce ADDEDs.

    Mirrors the visual style of common perception output (YOLO,
    Google Cloud Vision, etc.) — a colored translucent box over the
    detected region. The translucency keeps the renderer's underlying
    scene visible through the overlay.

    Note: ``wireframe=True`` on BoundingBox composes 12 capsule edges
    via ``parent_frame`` chaining — useful when you have an emitted
    anchor transform at the detection pose, but doesn't honor
    ``pose=`` directly today. The solid variant is the right choice
    here; wireframe is a future direction once an anchor-frame
    pattern is wired into the recipe.
    """

    name = "detections_overlay"

    N_DETECTIONS = 4
    ORBIT_RADIUS_MM = 500
    ORBIT_PERIOD_S = 8.0
    BOX_DIMS_MM = (140, 100, 120)

    def initial(self, scene: Scene) -> List[SceneEvent]:
        # Detections "appear" as soon as the driver ticks. Returning
        # nothing here keeps the initial-burst clean — the renderer
        # sees ADDED events for each bbox on the first tick.
        return []

    def tick(self, scene: Scene, t: float) -> List[SceneEvent]:
        events: List[SceneEvent] = []
        for i in range(self.N_DETECTIONS):
            phase = (2 * math.pi) * i / self.N_DETECTIONS
            angle = 2 * math.pi * t / self.ORBIT_PERIOD_S + phase
            x = self.ORBIT_RADIUS_MM * math.cos(angle)
            y = self.ORBIT_RADIUS_MM * math.sin(angle)
            z = 200
            bbox = BoundingBox(
                label=f"det_{i}",
                pose=Pose.at(x=x, y=y, z=z),
                dims_mm=self.BOX_DIMS_MM,
                color=_rainbow(i / self.N_DETECTIONS),
                opacity=0.4,
            )
            events.extend(scene.add_or_update(bbox))
        return events


# ---- registry ----------------------------------------------------------

RECIPES: Dict[str, Recipe] = {
    MarchingBoxes.name: MarchingBoxes(),
    PulsingSpheres.name: PulsingSpheres(),
    AllPrimitives.name: AllPrimitives(),
    DetectionsOverlay.name: DetectionsOverlay(),
}


# ---- helpers -----------------------------------------------------------

def _rainbow(u: float) -> tuple[int, int, int]:
    """Cheap HSV→RGB at full saturation, full value, varying hue.
    Returns 8-bit RGB. ``u`` in [0, 1]."""
    h = max(0.0, min(1.0, u)) * 6.0
    i = int(h) % 6
    f = h - int(h)
    if i == 0:
        r, g, b = 1.0, f, 0.0
    elif i == 1:
        r, g, b = 1.0 - f, 1.0, 0.0
    elif i == 2:
        r, g, b = 0.0, 1.0, f
    elif i == 3:
        r, g, b = 0.0, 1.0 - f, 1.0
    elif i == 4:
        r, g, b = f, 0.0, 1.0
    else:
        r, g, b = 1.0, 0.0, 1.0 - f
    return (int(r * 255), int(g * 255), int(b * 255))
