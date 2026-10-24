"""``simple-scene-example`` — the smallest possible world-state-store
service. Publishes three static geometries plus one animated box to
the Viam 3D scene viewer.

READ THIS FIRST if you're learning the ``viam_visuals`` library.
This is the canonical reference for "I want to add geometries to
the Viam 3D scene viewer." Every method that a Viam Python module
author has to write to ship a working WSS service is in this file —
no ``EasyResource`` mixin, no inherited helpers, no hidden magic.

What the library gives you for free
-----------------------------------

By subclassing :class:`viam_visuals.SceneServiceBase`, the gRPC
``WorldStateStore`` implementation, the state map, subscriber
broadcast, animation tick loop, UUID strategy, and the standard
DoCommand verbs (``list`` / ``clear`` / ``snapshot`` /
``apply_events`` / etc.) all just work.

The library also hides the renderer's quirks. A subscriber sees a
clean stream of ADDED / UPDATED / REMOVED events that the viewer
honors — including for color and opacity changes, which the
library translates into a transparent REMOVE + re-ADD with a fresh
UUID under the hood (the viewer's UPDATED handler drops
``metadata.*`` paths; see ``LESSONS.md`` for the full story).

What this file shows
--------------------

1. Manually registering the model with the Viam SDK Registry — the
   step that ``EasyResource`` usually hides.
2. The framework entry points (``new``, ``validate_config``,
   ``reconfigure``).
3. Building a scene from typed :class:`viam_visuals.Box` /
   ``.Sphere`` / ``.Capsule`` values, with :meth:`set_scene` to
   install them.
4. The :meth:`scene_tick` hook: mutate typed objects in place,
   return ``scene.update(...)`` events. The library diffs against
   the committed snapshot, emits the right field-mask paths, and
   broadcasts to subscribers.

The :meth:`scene_tick` method below drives a moving box through four
animations simultaneously: orbital position, sinusoidal scale,
HSV-rainbow color, and pulsing opacity. All four are expressed as
direct mutations on a typed Box object.

What it does NOT show
---------------------

* Configurable items / presets — see ``standalone-playground``.
* Mesh and point-cloud assets — see ``standalone-playground``.
* Custom DoCommand verbs — see ``standalone-playground``'s
  ``get_entity_chunk``.
* The driver pattern — see ``playground-driver`` + ``playground-visualizer``.

Configure as a ``rdk:service:world_state_store`` service with model
``viam:example-visualizations-python:simple-scene-example``. No
attributes are required — the scene is hardcoded.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence, Tuple

import viam_visuals as viz
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Geometry, ResourceName
from viam.resource.base import ResourceBase
from viam.resource.registry import Registry, ResourceCreatorRegistration
from viam.resource.types import Model, ModelFamily
from viam.services.worldstatestore import WorldStateStore

MODEL = Model(
    ModelFamily("viam", "example-visualizations-python"),
    "simple-scene-example",
)


class SimpleSceneExample(viz.SceneServiceBase):
    """Minimal WSS service — three static geometries + one animated box."""

    MODEL = MODEL

    def __init__(self, name: str) -> None:
        super().__init__(name)
        # The moving box: a typed Box object whose fields we mutate
        # on every tick. set_scene() installs it in self.scene;
        # scene_tick() mutates it; scene.update(self.moving_box)
        # emits the diff.
        self.moving_box: viz.Box = viz.Box(
            label="moving_box",
            pose=viz.Pose.at(x=400, y=0, z=200),
            dims_mm=(120, 120, 120),
            color=(255, 100, 0),
            opacity=1.0,
        )
        # Hierarchical layer: a pivot Frame with two children parented
        # to it. Rotating the pivot transports the children — they
        # don't need their own updates. The Frame is an invisible
        # anchor; show_axes_helper=True is the default so the pivot's
        # orientation is visible.
        self.pivot: viz.Frame = viz.Frame(
            label="pivot",
            pose=viz.Pose.at(x=-700, y=0, z=300),
        )
        self.child_sphere: viz.Sphere = viz.Sphere(
            label="pivot_child_sphere",
            pose=viz.Pose.at(x=80, y=0, z=0),  # 80mm along pivot's +X
            parent_frame="pivot",
            radius_mm=30,
            color=(255, 255, 0),  # yellow
        )
        self.child_box: viz.Box = viz.Box(
            label="pivot_child_box",
            pose=viz.Pose.at(x=-80, y=0, z=0),  # 80mm along pivot's -X
            parent_frame="pivot",
            dims_mm=(40, 40, 40),
            color=(255, 0, 255),  # magenta
        )

    # ---- Framework entry points ---------------------------------------

    @classmethod
    def new(
        cls,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ) -> "SimpleSceneExample":
        """Build the instance and run reconfigure. The Viam framework
        does NOT auto-call reconfigure after construction."""
        instance = cls(config.name)
        instance.reconfigure(config, dependencies)
        return instance

    @classmethod
    def validate_config(
        cls,
        config: ComponentConfig,
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """No dependencies, no required attributes."""
        return [], []

    def reconfigure(
        self,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ) -> None:
        """Install the scene with typed Visual objects. The library
        broadcasts ADDED for each item and starts the tick task."""
        self.set_scene(
            # Three static primitives in a row.
            viz.Box(
                "demo_box",
                pose=viz.Pose.at(x=-400, y=0, z=100),
                dims_mm=(150, 150, 150),
                color=(230, 25, 75),  # red
            ),
            viz.Sphere(
                "demo_sphere",
                pose=viz.Pose.at(x=-150, y=0, z=100),
                radius_mm=90,
                color=(60, 180, 75),  # green
            ),
            viz.Capsule(
                "demo_capsule",
                pose=viz.Pose.at(x=100, y=0, z=100),
                radius_mm=50,
                length_mm=200,
                color=(0, 130, 200),  # blue
            ),
            # The animated box (mutated in scene_tick).
            self.moving_box,
            # Hierarchical group: pivot + two children. Only the
            # pivot's pose updates each tick; the children follow.
            self.pivot,
            self.child_sphere,
            self.child_box,
        )

    # ---- Library hooks ------------------------------------------------

    def build_geometry(
        self,
        item: Mapping[str, Any],
        override_geom: Mapping[str, Any],
    ) -> Geometry:
        """Dispatch to the library helper for the standard non-asset
        primitive types."""
        return viz.build_basic_geometry(item, override_geom)

    def scene_tick(self, scene: viz.Scene, t: float) -> Sequence[viz.SceneEvent]:
        """Per-tick state for animated items: mutate typed objects
        in place, return the diff via ``scene.update(...)``.

        Called by the library's tick loop at ``tick_hz`` (default
        30 Hz). ``t`` is elapsed seconds since reconfigure.

        The moving box does four animations simultaneously:

          * **Position**: orbit around its anchor at radius 150 mm,
            period 4 s.
          * **Scale**: pulse symmetrically between 80 mm and 160 mm,
            period 2 s.
          * **Color**: hue cycles through the rainbow at period 6 s.
            The library translates color updates into a renderer-
            visible REMOVE + re-ADD with a fresh UUID — the
            ``metadata.color`` path the viewer would otherwise drop
            never reaches the wire.
          * **Opacity**: sinusoidal between 0.3 and 1.0, period 3 s.
            Same library-side translation as color.
        """
        # --- Moving box: four animations on one Visual --------------
        # Position: orbit around (400, 0, 200) at radius 150 mm,
        # period 4 s — using the viz.orbit_pose helper.
        self.moving_box.pose = viz.orbit_pose(
            base=viz.Pose.at(x=400, y=0, z=200),
            period_s=4.0,
            radius_mm=150.0,
            t=t,
        )
        # Scale: pulse all three dimensions symmetrically between
        # 80 and 160 mm — using the viz.pulse_range helper.
        scale = viz.pulse_range(80, 160, period_s=2.0, t=t)
        self.moving_box.dims_mm = (scale, scale, scale)
        # Color and opacity trigger renderer respawns (the viewer
        # drops metadata.* paths on UPDATED, so the library emits
        # REMOVE + re-ADD with a fresh UUID). Snap to bounded step
        # counts so the respawn rate doesn't pin to tick_hz; see
        # viam_visuals.snap_step.
        hue = viz.snap_step((t / 6) % 1.0, 24)  # 24 hues / 6 s
        self.moving_box.color = viz.hsv_to_rgb(hue)
        op_raw = 0.3 + 0.7 * (1 + math.sin(2 * math.pi * t / 3)) / 2
        self.moving_box.opacity = viz.snap_step(op_raw, 12, lo=0.3, hi=1.0)

        # --- Hierarchical group: only the pivot updates -------------
        # Rotate the pivot around its own +Z. The two children are
        # parented to "pivot" via parent_frame; the renderer composes
        # the parent transform automatically, so they orbit around
        # the pivot without needing their own per-tick updates.
        self.pivot.pose = viz.Pose.at(
            x=-700,
            y=0,
            z=300,
            theta=(t * 60) % 360,  # 60° per second
        )

        events = []
        events.extend(scene.update(self.moving_box))
        events.extend(scene.update(self.pivot))
        return events


# Register the model with the Viam SDK at import time. The Module
# entrypoint (``src/main.py``) imports this module purely for this
# side effect — without it, ``viam-server`` doesn't know the model
# exists when it scans the registry.
Registry.register_resource_creator(
    WorldStateStore.API,
    MODEL,
    ResourceCreatorRegistration(
        SimpleSceneExample.new,
        SimpleSceneExample.validate_config,
    ),
)
