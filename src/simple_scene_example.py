"""``simple-scene-example`` — the smallest possible world-state-store
service. Publishes three static geometries to the Viam 3D scene
viewer.

READ THIS FIRST if you're learning the ``viam_visuals`` library.
This file is the canonical "I want to add geometries to the 3D
scene viewer and that's it" example. Total length: ~80 lines
including this module docstring.

What it demonstrates
--------------------

1. Subclassing :class:`viam_visuals.SceneServiceBase` to get the
   world-state-store gRPC implementation, state map, subscriber
   fanout, animation tick loop, UUID strategy, and the standard
   DoCommand verbs (``list`` / ``clear`` / ``snapshot`` /
   ``apply_events`` / etc.) for free.

2. Building a scene from typed :class:`viam_visuals.Box` /
   :class:`viam_visuals.Sphere` / :class:`viam_visuals.Capsule`
   values. ``viam_visuals.to_dicts(...)`` is the bridge to the
   wire-format item list the service consumes.

3. Using :func:`viam_visuals.build_basic_geometry` so the
   ``build_geometry`` hook is one line.

What it does NOT demonstrate
----------------------------

* Animations (see :mod:`src.service` for the 11 modes)
* Configurable items / presets (see :mod:`src.service`)
* Meshes and point clouds (see :mod:`src.service`)
* Custom DoCommand verbs (see :mod:`src.service`'s
  ``get_entity_chunk``)
* The driver pattern (see :mod:`src.driver` +
  :mod:`src.visualizer`)

Configure it as a ``rdk:service:world_state_store`` service with
model ``viam:example-visualizations-python:simple-scene-example``.
No attributes are required — the scene is hardcoded.
"""
from __future__ import annotations

from typing import Sequence, Tuple

from viam.proto.app.robot import ComponentConfig
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily

import viam_visuals as viz


class SimpleSceneExample(viz.SceneServiceBase, EasyResource):
    """Minimal WSS service — three fixed geometries, no animation."""

    MODEL = Model(
        ModelFamily("viam", "example-visualizations-python"),
        "simple-scene-example",
    )

    # The base ``reconfigure`` picks the scene source in this order:
    # explicit ``items`` config > named ``preset`` > ``DEFAULT_PRESET``.
    # We point it at our ``load_preset`` override below.
    DEFAULT_PRESET = "main"

    # The three geometries this service publishes. Edit this tuple
    # to change the scene. The viz dataclass constructors validate
    # their parameters at construction — bad inputs surface at
    # import time, not on the wire.
    _SCENE = (
        viz.Box(
            label="demo_box",
            pose=viz.Pose.at(x=-300, y=0, z=100),
            dims_mm=(150, 150, 150),
            color=(230, 25, 75),  # red
        ),
        viz.Sphere(
            label="demo_sphere",
            pose=viz.Pose.at(x=0, y=0, z=100),
            radius_mm=90,
            color=(60, 180, 75),  # green
        ),
        viz.Capsule(
            label="demo_capsule",
            pose=viz.Pose.at(x=300, y=0, z=100),
            radius_mm=50,
            length_mm=200,
            color=(0, 130, 200),  # blue
        ),
    )

    @classmethod
    def validate_config(
        cls, config: ComponentConfig,
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """No attributes are required; return empty dep lists."""
        return [], []

    # ---- Hooks --------------------------------------------------------

    def load_preset(self, name: str):
        """The base ``reconfigure`` calls this with ``DEFAULT_PRESET``
        when no ``items`` are in the config. Return the wire-format
        item list built from the typed visuals above."""
        return viz.to_dicts(*self._SCENE)

    def build_geometry(self, item, override_geom):
        """One-line dispatcher — handles box / sphere / capsule /
        point / arrow. For mesh / pointcloud see ``src/service.py``."""
        return viz.build_basic_geometry(item, override_geom)
