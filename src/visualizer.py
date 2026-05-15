"""``playground-visualizer`` — passive WSS that accepts pushed Scene events.

Thin subclass of :class:`src.service.SceneSprites` (the
``standalone-playground`` model) that:

  * Drops ``items`` / ``preset`` config — the visualizer is passive.
    Items arrive at runtime via the ``apply_events`` DoCommand from
    a driver component (typically :class:`src.driver.PlaygroundDriver`,
    but anything that speaks the wire format works).
  * Registers itself in :mod:`viam_visuals.registry` on construction
    so an in-process driver can hold a direct Python reference and
    skip the gRPC round-trip.
  * Otherwise reuses every geometry builder, asset reader, animation
    tick, custom DoCommand verb, and metadata convention from
    ``SceneSprites``. Mesh / PCD loading, vertex-color transcoding,
    and chunked-delivery setup all work identically.

The pairing with :class:`src.driver.PlaygroundDriver` is the canonical
demonstration of the split. The architecture follows two principles:

  * **Visualizer owns the WSS contract.** It serves
    ``ListUUIDs`` / ``GetTransform`` / ``StreamTransformChanges`` to
    the renderer, manages subscriber fanout, holds the UUID strategy.
  * **Driver owns the domain logic.** It mutates a
    :class:`viam_visuals.Scene` at tick rate and pushes the resulting
    events. The renderer never knows the driver exists.

See README.md's "Driver + visualizer quickstart" section for the
user-facing how-to, and CLAUDE.md's "Three-model split" for the
architectural rationale.
"""
from __future__ import annotations

from typing import List, Mapping, Sequence, Tuple

from viam.proto.app.robot import ComponentConfig
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import struct_to_dict

from viam_visuals import VALID_STRATEGIES, registry

from .service import SceneSprites


class PlaygroundVisualizer(SceneSprites, EasyResource):
    """Passive WSS — accepts ``apply_events`` from a driver component."""

    MODEL = Model(
        ModelFamily("viam", "example-visualizations-python"),
        "playground-visualizer",
    )
    # No auto-loaded preset; the driver populates the scene at runtime.
    DEFAULT_PRESET = None

    @classmethod
    def validate_config(
        cls, config: ComponentConfig,
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """Visualizer rejects ``items`` and ``preset`` — those belong
        on the driver side. Accepts the same ``tick_hz``,
        ``uuid_strategy``, ``parent_frame`` knobs as the monolith
        (tick is only relevant if the driver pushes animated items;
        normally driver ticks client-side and pushes UPDATED events)."""
        attrs = struct_to_dict(config.attributes) if config.attributes else {}

        if "items" in attrs:
            raise Exception(
                "playground-visualizer doesn't accept 'items' — those "
                "should come from a driver via apply_events"
            )
        if "preset" in attrs:
            raise Exception(
                "playground-visualizer doesn't accept 'preset' — those "
                "belong on the driver side"
            )

        tick_hz = attrs.get("tick_hz")
        if tick_hz is not None:
            v = float(tick_hz)
            if not (0 < v <= 30):
                raise Exception("tick_hz must be in (0, 30]")
        strategy = attrs.get("uuid_strategy")
        if strategy is not None and strategy not in VALID_STRATEGIES:
            raise Exception(
                f"uuid_strategy must be one of {VALID_STRATEGIES}, got {strategy!r}"
            )
        return [], []

    def reconfigure(self, config, dependencies):
        # Defer to SceneServiceBase (no items/preset to load).
        super().reconfigure(config, dependencies)
        # Register the live instance so an in-process driver can find
        # us without going through the framework's gRPC stub.
        registry.register(self.name, self)

    async def close(self):
        registry.unregister(self.name)
        # SceneServiceBase exposes an async close; defer to it.
        base_close = getattr(super(), "close", None)
        if base_close is not None:
            res = base_close()
            if hasattr(res, "__await__"):
                await res
