"""``simple-scene-example`` — the smallest possible world-state-store
service. Publishes three static geometries to the Viam 3D scene
viewer.

READ THIS FIRST if you're learning the ``viam_visuals`` library.
This is the canonical "I just want to add a few geometries to the
3D scene viewer" reference. Everything a Viam Python module author
has to write to ship a working WSS service is in this file — no
``EasyResource`` mixin, no inherited helpers from elsewhere in the
example module. Each method below is one a new user would write by
hand.

What the library gives you for free
-----------------------------------

By subclassing :class:`viam_visuals.SceneServiceBase`, the gRPC
``WorldStateStore`` implementation (``list_uuids`` /
``get_transform`` / ``stream_transform_changes``), the state map,
the subscriber broadcast, the animation tick loop, the UUID
strategy, and the standard DoCommand verbs (``list`` / ``clear`` /
``snapshot`` / ``apply_events`` etc.) all just work.

What this file shows
--------------------

* Manually registering the model with the Viam SDK Registry — the
  step that ``EasyResource`` usually hides.
* The four classmethod / instance method entry points the framework
  calls: ``new`` (construct), ``validate_config`` (gate config),
  ``reconfigure`` (build / rebuild the scene), and the inherited
  lifecycle.
* Building a scene from typed :class:`viam_visuals.Box` /
  ``.Sphere`` / ``.Capsule`` values.
* :func:`viam_visuals.build_basic_geometry` so the
  ``build_geometry`` hook is a one-liner.

What it does NOT show
---------------------

* Animations, presets, mesh / pointcloud assets, custom DoCommand
  verbs. The full ``standalone-playground`` model in
  ``src/service.py`` demonstrates each of those.

Configure as a ``rdk:service:world_state_store`` service with model
``viam:example-visualizations-python:simple-scene-example``. No
attributes are required — the scene is hardcoded.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from viam.proto.app.robot import ComponentConfig
from viam.proto.common import Geometry, ResourceName
from viam.resource.base import ResourceBase
from viam.resource.registry import Registry, ResourceCreatorRegistration
from viam.resource.types import Model, ModelFamily
from viam.services.worldstatestore import WorldStateStore

import viam_visuals as viz


# Model identifier. The triplet is (org, module-id, model-name).
MODEL = Model(
    ModelFamily("viam", "example-visualizations-python"),
    "simple-scene-example",
)


class SimpleSceneExample(viz.SceneServiceBase):
    """Minimal WSS service — three fixed geometries, no animation."""

    MODEL = MODEL

    def __init__(self, name: str) -> None:
        # SceneServiceBase initializes the state map, subscriber
        # list, tick task handle, and the WorldStateStore base.
        super().__init__(name)

    # ---- Framework entry points ---------------------------------------
    #
    # The Viam SDK Registry (see the call at the bottom of this file)
    # routes resource lifecycle through these three classmethod /
    # instance method hooks:

    @classmethod
    def new(
        cls,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ) -> "SimpleSceneExample":
        """Constructor: build the instance, then run reconfigure
        immediately. The Viam framework does NOT call ``reconfigure``
        automatically after construction — services start up with
        no state unless we wire it explicitly here."""
        instance = cls(config.name)
        instance.reconfigure(config, dependencies)
        return instance

    @classmethod
    def validate_config(
        cls, config: ComponentConfig,
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """Gate the machine config. Return ``(required_deps,
        optional_deps)``. This service has no dependencies and
        accepts no attributes — return empty lists."""
        return [], []

    def reconfigure(
        self,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ) -> None:
        """Called once on construction (via ``new`` above) and again
        every time the machine config changes. Build the scene from
        typed shape values and hand it to the library."""
        items = viz.to_dicts(
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
        # The library handles the rest: install items in the state
        # map, broadcast ADDED to any open subscribers, and start
        # the animation tick task if any items animate (none here).
        self.reconfigure_with(items)

    # ---- Library hooks ------------------------------------------------
    #
    # SceneServiceBase calls these during reconfigure / on every
    # tick. We only need to implement build_geometry — the others
    # (compute_tick, is_animated, load_preset, base_geom_for_item)
    # have suitable defaults on the base class for a static scene
    # with the standard primitive types.

    def build_geometry(
        self,
        item: Mapping[str, Any],
        override_geom: Mapping[str, Any],
    ) -> Geometry:
        """Build the ``commonpb.Geometry`` proto for an item.
        ``viam_visuals.build_basic_geometry`` dispatches on
        ``item['type']`` for box / sphere / capsule / point / arrow."""
        return viz.build_basic_geometry(item, override_geom)


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
