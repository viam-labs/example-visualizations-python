"""``playground-driver`` — Generic component that mutates a Scene and
pushes the resulting events to a visualizer.

Companion to :class:`src.visualizer.PlaygroundVisualizer`. The
driver owns the *domain logic* (which visuals to draw, how they
change over time); the visualizer owns the *renderer contract* (WSS
service, subscriber fanout). The pair demonstrates the library's
:class:`viam_visuals.Scene` + :class:`viam_visuals.SceneServiceBase`
architecture working as separable concerns.

Config:

    {
      "visualizer": "scene_python_vis",     // resource name of the visualizer
      "recipe": "marching_boxes",           // entry in src.recipes.RECIPES
      "tick_hz": 5,                         // optional, default 5
      "namespace": "drv1"                   // optional label prefix
    }

The driver looks up its visualizer via :mod:`viam_visuals.registry`
— a direct Python reference, no gRPC. This is correct because both
models ship from the same module binary, so both instances live in
the same process and the framework's dependency-injection stub
would just add latency. If the visualizer isn't found in the
registry at reconfigure time, the driver fails fast.
"""
from __future__ import annotations

import asyncio
import time
from typing import Mapping, Optional, Sequence, Tuple

from viam.components.generic import Generic
from viam.proto.app.robot import ComponentConfig
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import ValueTypes, struct_to_dict

from viam_visuals import Scene, events_to_wire, registry

from .recipes import RECIPES, Recipe


DEFAULT_TICK_HZ = 5.0
MAX_TICK_HZ = 30.0
DEFAULT_RECIPE = "marching_boxes"


class PlaygroundDriver(Generic, EasyResource):
    """Generic component that drives a visualizer with Scene mutations."""

    MODEL = Model(
        ModelFamily("viam", "example-visualizations-python"),
        "playground-driver",
    )

    # ---- validation ---------------------------------------------------

    @classmethod
    def validate_config(
        cls, config: ComponentConfig,
    ) -> Tuple[Sequence[str], Sequence[str]]:
        attrs = struct_to_dict(config.attributes) if config.attributes else {}

        vis_name = attrs.get("visualizer")
        if not vis_name or not isinstance(vis_name, str):
            raise Exception("'visualizer' is required (name of the visualizer service)")

        recipe = attrs.get("recipe", DEFAULT_RECIPE)
        if recipe not in RECIPES:
            raise Exception(
                f"unknown recipe {recipe!r}; valid: {sorted(RECIPES.keys())}"
            )

        tick_hz = attrs.get("tick_hz")
        if tick_hz is not None:
            v = float(tick_hz)
            if not (0 < v <= MAX_TICK_HZ):
                raise Exception(f"tick_hz must be in (0, {MAX_TICK_HZ}]")

        return [], []  # No declared deps — registry handles the lookup.

    # ---- lifecycle ----------------------------------------------------

    async def reconfigure(self, config, dependencies):
        attrs = struct_to_dict(config.attributes) if config.attributes else {}
        self._vis_name: str = attrs["visualizer"]
        self._recipe_name: str = attrs.get("recipe", DEFAULT_RECIPE)
        self._tick_hz: float = float(attrs.get("tick_hz", DEFAULT_TICK_HZ))
        self._namespace: str = str(attrs.get("namespace", "") or "")
        self._recipe: Recipe = RECIPES[self._recipe_name]

        # Look up the visualizer in the in-process registry. We do
        # NOT fall back to the gRPC stub today — both models ship
        # from the same binary, so the visualizer must be in this
        # process. If it isn't, that's a config error (probably
        # missing `depends_on` for ordering, or the visualizer
        # crashed during its own reconfigure).
        vis = registry.lookup(self._vis_name)
        if vis is None:
            raise Exception(
                f"visualizer {self._vis_name!r} not found in the in-process "
                "registry; ensure it's configured and listed before this "
                "driver in 'depends_on'. (Cross-process driver→visualizer "
                "via gRPC isn't supported yet.)"
            )
        self._visualizer = vis

        # Cancel any prior tick task.
        prev_task = getattr(self, "_tick_task", None)
        if prev_task is not None and not prev_task.done():
            prev_task.cancel()
            try:
                await prev_task
            except (asyncio.CancelledError, Exception):
                pass

        # Build fresh Scene from the recipe.
        self._scene = Scene()
        initial_events = self._recipe.initial(self._scene)

        # Clear any prior visualizer state for our namespace (best-
        # effort — drop our own labels in case a prior driver left
        # them behind). We do this by REMOVING every label in the
        # scene first.
        # NOTE: this only clears labels we'd be re-adding; other
        # namespaces or labels remain untouched.
        if initial_events:
            wipe = [
                {"kind": "removed", "label": e.label}
                for e in initial_events
            ]
            await self._send_command({
                "command": "apply_events",
                "namespace": self._namespace,
                "events": wipe,
            })

        # Push the initial scene.
        await self._send_events(initial_events)

        # Start the tick task.
        self._t0 = time.monotonic()
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def close(self):
        task = getattr(self, "_tick_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        # Best-effort: clear our entities from the visualizer.
        scene = getattr(self, "_scene", None)
        if scene is not None and getattr(self, "_visualizer", None) is not None:
            remove_events = list(scene.clear())
            try:
                await self._send_events(remove_events)
            except Exception:
                pass

    # ---- tick loop ----------------------------------------------------

    async def _tick_loop(self):
        period = 1.0 / max(0.01, self._tick_hz)
        while True:
            await asyncio.sleep(period)
            t = time.monotonic() - self._t0
            try:
                events = self._recipe.tick(self._scene, t)
                await self._send_events(events)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Don't kill the loop on a transient error — log
                # and keep ticking.
                logger = getattr(self, "logger", None)
                if logger is not None:
                    logger.warn(f"driver tick error: {e}")

    # ---- visualizer comms --------------------------------------------

    async def _send_events(self, events) -> None:
        if not events:
            return
        await self._send_command({
            "command": "apply_events",
            "namespace": self._namespace,
            "events": events_to_wire(events),
        })

    async def _send_command(self, command: Mapping[str, ValueTypes]) -> None:
        # Direct method call — same process as the visualizer.
        await self._visualizer.do_command(command)

    # ---- DoCommand surface -------------------------------------------

    async def do_command(
        self,
        command: Mapping[str, ValueTypes],
        *,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Mapping[str, ValueTypes]:
        cmd = command.get("command") if command else None
        if cmd == "info":
            return {
                "visualizer": self._vis_name,
                "recipe": self._recipe_name,
                "tick_hz": self._tick_hz,
                "namespace": self._namespace,
                "scene_size": len(self._scene),
                "visualizer_type": type(self._visualizer).__name__,
                "tick_running": (
                    self._tick_task is not None and not self._tick_task.done()
                ),
            }
        if cmd == "recipes":
            return {"recipes": sorted(RECIPES.keys())}
        return {"unknown_command": str(cmd)}
