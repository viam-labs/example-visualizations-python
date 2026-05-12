"""``scene-primitives`` — a WorldStateStore service that publishes a
configurable set of primitives to the Viam 3D scene viewer.

This is the playground entrypoint. It owns:

  - the item list (config-driven or DoCommand-managed at runtime)
  - per-item base pose + base geometry (kept separate from the
    animated tick state so animations can compose)
  - the cached `Transform` proto for each item (what subscribers see)
  - the subscriber list + per-subscriber asyncio.Queue
  - the per-cycle animation task

Two UUID strategies are supported, selectable at runtime:

  - ``stable``: every item keeps its UUID for life. Animation pushes
    ``UPDATED`` events with field-mask paths matching the conventions
    in rdk/services/worldstatestore/fake/moving_geos_world.go.
  - ``versioned``: every animation tick re-emits the item with a
    fresh timestamp-suffixed UUID. Pushes ``REMOVED`` for the prior
    version then ``ADDED`` for the new version, matching the
    apriltag-tracker pattern. Use this if the viewer is dropping
    UPDATED events for stable UUIDs.

The strategy can be flipped at runtime via the
``set_uuid_strategy`` DoCommand, which makes the renderer's behavior
itself a teaching surface."""
import asyncio
import time
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    ClassVar,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from google.protobuf.field_mask_pb2 import FieldMask
from typing_extensions import Self
from viam.logging import getLogger
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import (
    Geometry,
    Pose,
    PoseInFrame,
    ResourceName,
    Transform,
)
from viam.proto.service.worldstatestore import (
    StreamTransformChangesResponse,
    TransformChangeType,
)
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.services.worldstatestore import WorldStateStore
from viam.utils import ValueTypes, dict_to_struct, struct_to_dict

from . import animation as anim_mod
from . import geometries
from . import presets as presets_mod


LOGGER = getLogger(__name__)


# ---------- config defaults / attribute names ----------

ATTR_TICK_HZ = "tick_hz"
ATTR_UUID_STRATEGY = "uuid_strategy"
ATTR_PARENT_FRAME = "parent_frame"
ATTR_PRESET = "preset"
ATTR_ITEMS = "items"

DEFAULT_TICK_HZ = 30.0
DEFAULT_UUID_STRATEGY = "stable"
DEFAULT_PARENT_FRAME = "world"
DEFAULT_PRESET = "primitives"
UUID_STRATEGIES = ("stable", "versioned")


# ---------- module directory (for asset path resolution) ----------

MODULE_DIR = Path(__file__).resolve().parent.parent


# ---------- pure helpers ----------

def _base_geom_for_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract the shape-specific dim/radius/length fields the animator
    needs. The returned dict is what compute_tick treats as immutable
    base_geom — never mutated, always copied before modification."""
    t = item["type"]
    if t == "box":
        return {"dims_mm": dict(item["dims_mm"])}
    if t == "sphere":
        return {"radius_mm": float(item["radius_mm"])}
    if t == "capsule":
        return {
            "radius_mm": float(item["radius_mm"]),
            "length_mm": float(item["length_mm"]),
        }
    if t == "arrow":
        return {
            "radius_mm": float(item["radius_mm"]),
            "length_mm": float(item["length_mm"]),
        }
    # point / mesh / pointcloud have no scalable base.
    return {}


def _build_geometry(item: Mapping[str, Any], override_geom: Mapping[str, Any]) -> Geometry:
    """Build a Geometry proto for an item, honoring per-tick geometry
    overrides (only meaningful for `pulse` mode). Mesh / pointcloud
    bytes are read from disk at this point — repeated reads are cheap
    because the static items only build once."""
    t = item["type"]
    label = item["label"]
    if t == "box":
        return geometries.build_box(override_geom.get("dims_mm", item["dims_mm"]), label)
    if t == "sphere":
        return geometries.build_sphere(
            override_geom.get("radius_mm", item["radius_mm"]), label
        )
    if t == "capsule":
        return geometries.build_capsule(
            override_geom.get("radius_mm", item["radius_mm"]),
            override_geom.get("length_mm", item["length_mm"]),
            label,
        )
    if t == "point":
        return geometries.build_point(label)
    if t == "arrow":
        return geometries.build_arrow(
            override_geom.get("length_mm", item["length_mm"]),
            override_geom.get("radius_mm", item["radius_mm"]),
            label,
        )
    if t == "mesh":
        path = item["mesh_path"]
        raw = geometries.read_asset(path, MODULE_DIR)
        ply_bytes = geometries.load_mesh_bytes_as_ply(raw, path)
        # build_mesh requires content_type="ply"; STL got converted above.
        return geometries.build_mesh(ply_bytes, "ply", label)
    if t == "pointcloud":
        return geometries.build_pointcloud(
            geometries.read_asset(item["pointcloud_path"], MODULE_DIR), label
        )
    raise ValueError(f"unknown type {t!r}")


def _build_transform(
    item: Mapping[str, Any],
    pose: Mapping[str, float],
    geom: Geometry,
    uuid: bytes,
    parent_frame: str,
) -> Transform:
    # If the user didn't set a uniform `color` AND the mesh has
    # per-vertex colors embedded in the PLY, transcode those into
    # metadata.colors so the viewer renders them. The viewer ignores
    # PLY's own embedded vertex colors; metadata.colors is its only
    # per-vertex color channel.
    vertex_colors = None
    user_color = item.get("color")
    if user_color is None and geom.HasField("mesh"):
        vertex_colors = geometries.extract_ply_vertex_colors(geom.mesh.mesh)
    metadata = geometries.build_metadata(
        user_color,
        item.get("opacity"),
        show_axes_helper=bool(item.get("show_axes_helper", False)),
        invisible=bool(item.get("invisible", False)),
        vertex_colors=vertex_colors,
    )
    return Transform(
        uuid=uuid,
        reference_frame=item["label"],
        pose_in_observer_frame=PoseInFrame(
            reference_frame=item.get("parent_frame", parent_frame),
            pose=geometries.build_pose(pose),
        ),
        physical_object=geom,
        metadata=metadata,
    )


# ---------- the service ----------

class SceneSprites(WorldStateStore, EasyResource):
    """Playground WorldStateStore — publishes every supported geometry
    primitive to the Viam 3D scene viewer.

    Items can be supplied via config (top-level ``items`` list or
    ``preset`` name) or managed at runtime via DoCommand. Animations
    are computed in a background asyncio task at the configured
    ``tick_hz`` and pushed to subscribers either as UPDATED events
    (stable UUID mode) or REMOVED+ADDED (versioned mode).
    """

    MODEL: ClassVar[Model] = Model(
        ModelFamily("viam", "example-visualizations"), "scene-primitives",
    )

    def __init__(self, name: str):
        super().__init__(name)
        # Lock guards _state, _subscribers, _items.
        self._lock = asyncio.Lock()
        # label -> {item dict, base_pose, base_geom, uuid (bytes),
        # transform (Transform), start_t (float monotonic seconds)}
        self._state: Dict[str, Dict[str, Any]] = {}
        # Active subscribers.
        self._subscribers: List[asyncio.Queue] = []
        # Animation tick task.
        self._tick_task: Optional[asyncio.Task] = None
        # Config-driven state.
        self.tick_hz: float = DEFAULT_TICK_HZ
        self.uuid_strategy: str = DEFAULT_UUID_STRATEGY
        self.parent_frame: str = DEFAULT_PARENT_FRAME
        # Monotonic clock origin for animation t=0.
        self._animation_t0: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        # EasyResource.new doesn't call reconfigure() for service models,
        # so we do it explicitly. Without this the service starts with
        # no items and the tick task never launches.
        instance = super().new(config, dependencies)
        instance.reconfigure(config, dependencies)
        return instance

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        attrs = struct_to_dict(config.attributes)
        # tick_hz: optional, 1..30.
        if ATTR_TICK_HZ in attrs:
            hz = float(attrs[ATTR_TICK_HZ])
            if hz <= 0 or hz > 30:
                raise Exception(f"{ATTR_TICK_HZ} must be in (0, 30]")
        # uuid_strategy: optional, must be in UUID_STRATEGIES.
        if ATTR_UUID_STRATEGY in attrs:
            s = str(attrs[ATTR_UUID_STRATEGY])
            if s not in UUID_STRATEGIES:
                raise Exception(
                    f"{ATTR_UUID_STRATEGY} must be one of {UUID_STRATEGIES}, got {s!r}"
                )
        # preset: optional, must be a known name.
        preset = attrs.get(ATTR_PRESET)
        if preset is not None and str(preset) not in presets_mod.PRESET_NAMES:
            raise Exception(
                f"{ATTR_PRESET} must be one of {presets_mod.PRESET_NAMES}, got {preset!r}"
            )
        # items: optional; if present, each item must validate.
        items = attrs.get(ATTR_ITEMS)
        if items is not None:
            if not isinstance(items, list):
                raise Exception(f"{ATTR_ITEMS} must be a list")
            seen_labels = set()
            for i, it in enumerate(items):
                if not isinstance(it, Mapping):
                    raise Exception(f"items[{i}] must be a dict")
                _validate_item(it, i)
                label = it["label"]
                if label in seen_labels:
                    raise Exception(f"items[{i}] duplicate label {label!r}")
                seen_labels.add(label)
        # No required deps; no optional deps.
        return [], []

    def reconfigure(
        self,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ):
        attrs = struct_to_dict(config.attributes)
        self.tick_hz = float(attrs.get(ATTR_TICK_HZ, DEFAULT_TICK_HZ))
        self.uuid_strategy = str(attrs.get(ATTR_UUID_STRATEGY, DEFAULT_UUID_STRATEGY))
        self.parent_frame = str(attrs.get(ATTR_PARENT_FRAME, DEFAULT_PARENT_FRAME))

        # Pick the source of items: explicit items > preset > default preset.
        raw_items = attrs.get(ATTR_ITEMS)
        if raw_items:
            items = [dict(it) for it in raw_items]
        else:
            preset_name = str(attrs.get(ATTR_PRESET, DEFAULT_PRESET))
            items = [dict(it) for it in presets_mod.load(preset_name)]

        # Cancel any prior tick task.
        if self._tick_task is not None:
            self._tick_task.cancel()
            self._tick_task = None

        # Rebuild state from scratch, pushing REMOVED/ADDED to current
        # subscribers so they see the new world. We don't try to diff
        # against the previous state — a reconfigure is a coarse signal
        # and a hard reset is easier to reason about.
        prior_transforms = [s["transform"] for s in self._state.values()]
        self._state = {}
        for it in items:
            self._install_item(it)

        for t in prior_transforms:
            self._broadcast(StreamTransformChangesResponse(
                change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED,
                transform=t,
            ))
        for s in self._state.values():
            self._broadcast(StreamTransformChangesResponse(
                change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED,
                transform=s["transform"],
            ))

        # Reset animation clock and (re)start the tick task if any
        # items are animated. Static-only configs save the tick cycle.
        self._animation_t0 = time.monotonic()
        if any(anim_mod.is_animated(s["item"]) for s in self._state.values()):
            self._tick_task = asyncio.create_task(self._tick_loop())
        LOGGER.info(
            f"reconfigure: tick_hz={self.tick_hz} uuid_strategy={self.uuid_strategy} "
            f"parent_frame={self.parent_frame} items={len(self._state)}"
        )

    async def close(self):
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Item lifecycle helpers (sync — caller holds lock or is in
    # reconfigure where the loop isn't yet running).
    # ------------------------------------------------------------------

    def _install_item(self, item: Mapping[str, Any]) -> None:
        """Bring an item into _state and build its initial Transform."""
        label = item["label"]
        if label in self._state:
            raise Exception(f"duplicate item label {label!r}")
        base_pose = dict(item.get("pose") or {})
        # Ensure all pose fields are filled in for downstream animation
        # math, which reads keys directly.
        for k, default in (("x", 0.0), ("y", 0.0), ("z", 0.0),
                           ("ox", 0.0), ("oy", 0.0), ("oz", 1.0),
                           ("theta", 0.0)):
            base_pose.setdefault(k, default)
        base_geom = _base_geom_for_item(item)
        uuid = _initial_uuid(label, self.uuid_strategy)
        geom_proto = _build_geometry(item, base_geom)
        tf = _build_transform(item, base_pose, geom_proto, uuid, self.parent_frame)
        self._state[label] = {
            "item": dict(item),
            "base_pose": base_pose,
            "base_geom": base_geom,
            "uuid": uuid,
            "transform": tf,
        }

    def _remove_item(self, label: str) -> Optional[Transform]:
        s = self._state.pop(label, None)
        if s is None:
            return None
        return s["transform"]

    # ------------------------------------------------------------------
    # Animation tick
    # ------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        period = 1.0 / max(0.01, self.tick_hz)
        try:
            while True:
                try:
                    await self._tick_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.warning(f"tick failed: {type(e).__name__}: {e}")
                await asyncio.sleep(period)
        except asyncio.CancelledError:
            return

    async def _tick_once(self) -> None:
        t = time.monotonic() - self._animation_t0
        async with self._lock:
            for label, s in list(self._state.items()):
                item = s["item"]
                if not anim_mod.is_animated(item):
                    continue
                pose, geom, paths = anim_mod.compute_tick(
                    item, s["base_pose"], s["base_geom"], t,
                )
                if not paths:
                    # Animation mode had no effect for this type
                    # (e.g. pulse on a point) — skip.
                    continue
                geom_proto = _build_geometry(item, geom)
                if self.uuid_strategy == "stable":
                    new_tf = _build_transform(
                        item, pose, geom_proto, s["uuid"], self.parent_frame,
                    )
                    s["transform"] = new_tf
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_UPDATED,
                        transform=new_tf,
                        updated_fields=FieldMask(paths=list(paths)),
                    ))
                else:  # versioned
                    old_tf = s["transform"]
                    new_uuid = _versioned_uuid(label)
                    new_tf = _build_transform(
                        item, pose, geom_proto, new_uuid, self.parent_frame,
                    )
                    s["uuid"] = new_uuid
                    s["transform"] = new_tf
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED,
                        transform=old_tf,
                    ))
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED,
                        transform=new_tf,
                    ))

    # ------------------------------------------------------------------
    # Subscriber fanout
    # ------------------------------------------------------------------

    def _broadcast(self, msg: StreamTransformChangesResponse) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                LOGGER.warning("subscriber queue full; dropping event")

    # ------------------------------------------------------------------
    # WorldStateStore service API
    # ------------------------------------------------------------------

    async def list_uuids(
        self,
        *,
        extra: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> List[bytes]:
        async with self._lock:
            return [s["uuid"] for s in self._state.values()]

    async def get_transform(
        self,
        uuid: bytes,
        *,
        extra: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Transform:
        async with self._lock:
            for s in self._state.values():
                if s["uuid"] == uuid:
                    return s["transform"]
        raise Exception(f"unknown uuid {uuid!r}")

    async def stream_transform_changes(
        self,
        *,
        extra: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[StreamTransformChangesResponse, None]:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.append(q)
            # Burst the current world to the new subscriber so it
            # doesn't need to wait for the next tick.
            for s in self._state.values():
                q.put_nowait(StreamTransformChangesResponse(
                    change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED,
                    transform=s["transform"],
                ))
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    # ------------------------------------------------------------------
    # DoCommand — the playground surface
    # ------------------------------------------------------------------

    async def do_command(
        self,
        command: Mapping[str, ValueTypes],
        *,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Mapping[str, ValueTypes]:
        cmd = command.get("command") if command else None

        if cmd == "list":
            async with self._lock:
                return {"items": [self._item_summary(label) for label in self._state]}

        if cmd == "add":
            new_item = command.get("item")
            if not isinstance(new_item, Mapping):
                raise Exception("add requires an 'item' dict")
            _validate_item(new_item, 0)
            async with self._lock:
                if new_item["label"] in self._state:
                    raise Exception(f"item {new_item['label']!r} already exists")
                self._install_item(new_item)
                tf = self._state[new_item["label"]]["transform"]
                self._broadcast(StreamTransformChangesResponse(
                    change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED,
                    transform=tf,
                ))
                # Restart the tick task if this is the first animated
                # item — otherwise its animation would never fire.
                self._maybe_restart_tick()
                return {"label": new_item["label"], "uuid": tf.uuid.decode()}

        if cmd == "remove":
            label = command.get("label")
            if not label:
                raise Exception("remove requires a 'label'")
            async with self._lock:
                tf = self._remove_item(str(label))
                if tf is None:
                    return {"removed": False}
                self._broadcast(StreamTransformChangesResponse(
                    change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED,
                    transform=tf,
                ))
                return {"removed": True}

        if cmd == "update":
            label = command.get("label")
            patch = command.get("patch")
            if not label or not isinstance(patch, Mapping):
                raise Exception("update requires 'label' and 'patch'")
            async with self._lock:
                s = self._state.get(str(label))
                if s is None:
                    raise Exception(f"unknown label {label!r}")
                updated_fields = self._apply_patch(s, patch)
                # Rebuild transform (mesh_path may have changed,
                # geometry may have changed, etc.). For simplicity we
                # always rebuild on update — the playground rate is
                # human-interactive, not animation-frequent.
                geom_proto = _build_geometry(s["item"], s["base_geom"])
                new_tf = _build_transform(
                    s["item"], s["base_pose"], geom_proto, s["uuid"], self.parent_frame,
                )
                s["transform"] = new_tf
                self._broadcast(StreamTransformChangesResponse(
                    change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_UPDATED,
                    transform=new_tf,
                    updated_fields=FieldMask(paths=updated_fields),
                ))
                # If we just turned animation on, the tick task may
                # need to start.
                self._maybe_restart_tick()
                return {"updated_fields": updated_fields}

        if cmd == "clear":
            async with self._lock:
                count = len(self._state)
                for tf in [s["transform"] for s in self._state.values()]:
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED,
                        transform=tf,
                    ))
                self._state = {}
                return {"removed_count": count}

        if cmd == "preset":
            name = command.get("name")
            if not name:
                raise Exception("preset requires a 'name'")
            items = presets_mod.load(str(name))
            async with self._lock:
                prior = [s["transform"] for s in self._state.values()]
                self._state = {}
                for it in items:
                    self._install_item(dict(it))
                for tf in prior:
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED,
                        transform=tf,
                    ))
                for s in self._state.values():
                    self._broadcast(StreamTransformChangesResponse(
                        change_type=TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED,
                        transform=s["transform"],
                    ))
                self._maybe_restart_tick()
                return {"loaded": str(name), "count": len(self._state)}

        if cmd == "snapshot":
            async with self._lock:
                return {"config": {
                    "tick_hz": self.tick_hz,
                    "uuid_strategy": self.uuid_strategy,
                    "parent_frame": self.parent_frame,
                    "items": [
                        dict(s["item"]) for s in self._state.values()
                    ],
                }}

        if cmd == "set_uuid_strategy":
            strategy = command.get("strategy")
            if strategy not in UUID_STRATEGIES:
                raise Exception(
                    f"strategy must be one of {UUID_STRATEGIES}, got {strategy!r}"
                )
            async with self._lock:
                self.uuid_strategy = str(strategy)
                return {"strategy": self.uuid_strategy}

        # Default: return a debug snapshot for unrecognized / missing
        # commands. Mirrors apriltag-tracker.
        return self._debug_snapshot()

    # ------------------------------------------------------------------
    # do_command helpers
    # ------------------------------------------------------------------

    def _item_summary(self, label: str) -> Mapping[str, Any]:
        s = self._state[label]
        return {
            "label": label,
            "type": s["item"]["type"],
            "uuid": s["uuid"].decode(),
            "pose": dict(s["base_pose"]),
            "animation_mode": (s["item"].get("animation") or {}).get("mode", "none"),
            "color": s["item"].get("color"),
            "opacity": s["item"].get("opacity"),
        }

    def _apply_patch(self, s: Dict[str, Any], patch: Mapping[str, Any]) -> List[str]:
        """Apply an item patch, mutating ``s`` (the state row) in place.
        Returns the field-mask paths describing what changed, so the
        UPDATED event carries them."""
        updated_fields: List[str] = []
        item = s["item"]
        if "color" in patch:
            item["color"] = dict(patch["color"]) if patch["color"] is not None else None
            updated_fields.append("metadata.color")
        if "opacity" in patch:
            item["opacity"] = (
                float(patch["opacity"]) if patch["opacity"] is not None else None
            )
            updated_fields.append("metadata.opacity")
        if "pose" in patch:
            new_pose = dict(s["base_pose"])
            new_pose.update(patch["pose"])
            s["base_pose"] = new_pose
            for k in patch["pose"]:
                fm = _POSE_KEY_TO_PATH.get(k)
                if fm is not None:
                    updated_fields.append(fm)
        if "dims_mm" in patch and item["type"] == "box":
            item["dims_mm"] = dict(patch["dims_mm"])
            s["base_geom"] = _base_geom_for_item(item)
            updated_fields.extend([
                anim_mod.PATH_BOX_DIMS_X,
                anim_mod.PATH_BOX_DIMS_Y,
                anim_mod.PATH_BOX_DIMS_Z,
            ])
        if "radius_mm" in patch and item["type"] in ("sphere", "capsule"):
            item["radius_mm"] = float(patch["radius_mm"])
            s["base_geom"] = _base_geom_for_item(item)
            updated_fields.append(anim_mod.PATH_SPHERE_RADIUS)
        if "length_mm" in patch and item["type"] == "capsule":
            item["length_mm"] = float(patch["length_mm"])
            s["base_geom"] = _base_geom_for_item(item)
            updated_fields.append(anim_mod.PATH_CAPSULE_LENGTH)
        if "mesh_path" in patch and item["type"] == "mesh":
            item["mesh_path"] = str(patch["mesh_path"])
            # Whole-geometry replacement — the renderer rebuilds the mesh.
            updated_fields.append("physicalObject.mesh")
        if "pointcloud_path" in patch and item["type"] == "pointcloud":
            item["pointcloud_path"] = str(patch["pointcloud_path"])
            updated_fields.append("physicalObject.pointcloud")
        if "animation" in patch:
            item["animation"] = dict(patch["animation"])
            # Animation changes don't directly modify the transform; the
            # next tick will. No field-mask path needed.
        return updated_fields

    def _maybe_restart_tick(self) -> None:
        """Start the tick task if any animated items exist and no task
        is currently running. Idempotent — safe to call after any
        add/update/preset."""
        has_animated = any(
            anim_mod.is_animated(s["item"]) for s in self._state.values()
        )
        if has_animated and (self._tick_task is None or self._tick_task.done()):
            self._animation_t0 = time.monotonic()
            try:
                self._tick_task = asyncio.create_task(self._tick_loop())
            except RuntimeError:
                # No running event loop (e.g. in unit tests calling
                # do_command synchronously). The tick is best-effort
                # in that environment; the test exercises tick_once
                # directly.
                self._tick_task = None

    def _debug_snapshot(self) -> Mapping[str, ValueTypes]:
        return {
            "tick_hz": self.tick_hz,
            "uuid_strategy": self.uuid_strategy,
            "parent_frame": self.parent_frame,
            "item_count": len(self._state),
            "subscriber_count": len(self._subscribers),
            "tick_running": (
                self._tick_task is not None and not self._tick_task.done()
            ),
            "animation_t0": self._animation_t0,
        }


# ---------- field-mask map for pose patches ----------

_POSE_KEY_TO_PATH = {
    "x": anim_mod.PATH_X,
    "y": anim_mod.PATH_Y,
    "z": anim_mod.PATH_Z,
    "theta": anim_mod.PATH_THETA,
    # ox/oy/oz aren't covered by the RDK fake's path conventions; we
    # could synthesize "poseInObserverFrame.pose.oX" but it isn't
    # confirmed to work. Whole-pose updates are safe via reconfigure.
}


# ---------- per-item validation ----------

def _validate_item(item: Mapping[str, Any], index: int) -> None:
    """Validate one item dict. Raises with index-prefixed messages so
    config errors point at the offending entry."""
    where = f"items[{index}]"
    if "type" not in item:
        raise Exception(f"{where} missing 'type'")
    t = item["type"]
    if t not in geometries.SUPPORTED_TYPES:
        raise Exception(
            f"{where} unknown type {t!r}; expected one of {geometries.SUPPORTED_TYPES}"
        )
    if "label" not in item or not str(item["label"]).strip():
        raise Exception(f"{where} missing or empty 'label'")
    animation = item.get("animation") or {"mode": "none"}
    mode = animation.get("mode", "none")
    if mode not in anim_mod.SUPPORTED_MODES:
        raise Exception(
            f"{where} unknown animation.mode {mode!r}; expected one of "
            f"{anim_mod.SUPPORTED_MODES}"
        )
    if mode == "trajectory":
        wps = animation.get("waypoints")
        if not isinstance(wps, list) or len(wps) < 2:
            raise Exception(
                f"{where} animation.mode 'trajectory' requires "
                f"animation.waypoints to be a list of 2+ pose dicts"
            )
        for j, wp in enumerate(wps):
            if not isinstance(wp, Mapping):
                raise Exception(
                    f"{where} animation.waypoints[{j}] must be a dict"
                )
    color = item.get("color")
    if color is not None:
        for ch in ("r", "g", "b"):
            v = color.get(ch, 0)
            if not 0 <= float(v) <= 255:
                raise Exception(f"{where} color.{ch} must be in [0, 255]")
    if "opacity" in item and item["opacity"] is not None:
        op = float(item["opacity"])
        if not 0.0 <= op <= 1.0:
            raise Exception(f"{where} opacity must be in [0, 1]")
    # Shape-specific.
    if t == "box":
        dims = item.get("dims_mm")
        if not dims:
            raise Exception(f"{where} box requires 'dims_mm'")
        for axis in ("x", "y", "z"):
            if axis not in dims:
                raise Exception(f"{where} box dims_mm missing '{axis}'")
            if float(dims[axis]) <= 0:
                raise Exception(f"{where} box dims_mm.{axis} must be > 0")
    elif t == "sphere":
        if "radius_mm" not in item:
            raise Exception(f"{where} sphere requires 'radius_mm'")
        if float(item["radius_mm"]) <= 0:
            raise Exception(f"{where} sphere radius_mm must be > 0")
    elif t == "capsule":
        for k in ("radius_mm", "length_mm"):
            if k not in item:
                raise Exception(f"{where} capsule requires {k!r}")
            if float(item[k]) <= 0:
                raise Exception(f"{where} capsule {k} must be > 0")
    elif t == "arrow":
        for k in ("radius_mm", "length_mm"):
            if k not in item:
                raise Exception(f"{where} arrow requires {k!r}")
            if float(item[k]) <= 0:
                raise Exception(f"{where} arrow {k} must be > 0")
    elif t == "point":
        pass  # No shape config.
    elif t == "mesh":
        path = item.get("mesh_path")
        if not path:
            raise Exception(f"{where} mesh requires 'mesh_path'")
        # Reject uppercase content type — the renderer is case-sensitive.
        geometries.infer_mesh_content_type(str(path))
        resolved = _resolve_asset_path(str(path))
        if not resolved.exists():
            raise Exception(f"{where} mesh asset not found: {resolved}")
    elif t == "pointcloud":
        path = item.get("pointcloud_path")
        if not path:
            raise Exception(f"{where} pointcloud requires 'pointcloud_path'")
        resolved = _resolve_asset_path(str(path))
        if not resolved.exists():
            raise Exception(f"{where} pointcloud asset not found: {resolved}")


def _resolve_asset_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = MODULE_DIR / path
    return path


# ---------- UUID strategies ----------

# Monotonic counter ensures versioned UUIDs are strictly unique even
# when allocated within the same millisecond. The label prefix +
# timestamp is still the readable identifier; the counter is the
# tiebreaker.
_VERSIONED_COUNTER = 0


def _initial_uuid(label: str, strategy: str) -> bytes:
    if strategy == "versioned":
        return _versioned_uuid(label)
    return label.encode()


def _versioned_uuid(label: str) -> bytes:
    global _VERSIONED_COUNTER
    _VERSIONED_COUNTER += 1
    return f"{label}_{int(time.time() * 1000)}_{_VERSIONED_COUNTER}".encode()
