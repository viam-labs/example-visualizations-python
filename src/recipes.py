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

from viam_visuals import Box, Pose, Scene, SceneEvent, Sphere


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


# ---- registry ----------------------------------------------------------

RECIPES: Dict[str, Recipe] = {
    MarchingBoxes.name: MarchingBoxes(),
    PulsingSpheres.name: PulsingSpheres(),
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
