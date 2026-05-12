"""End-to-end tests covering the WorldStateStore service surface:
list_uuids, get_transform, stream_transform_changes, the animation
tick (for both UUID strategies), and reconfigure semantics. Bypasses
``new()`` and exercises the service directly with bare instances and
SimpleNamespace mocks for any framework-supplied inputs.
"""
import asyncio
from types import SimpleNamespace

import pytest
from viam.proto.app.robot import ComponentConfig
from viam.proto.service.worldstatestore import (
    StreamTransformChangesResponse,
    TransformChangeType,
)
from viam.utils import dict_to_struct

from src.service import (
    DEFAULT_PARENT_FRAME,
    DEFAULT_TICK_HZ,
    DEFAULT_UUID_STRATEGY,
    SceneSprites,
)


def _bare_service(strategy="stable", parent_frame=DEFAULT_PARENT_FRAME):
    s = SceneSprites.__new__(SceneSprites)
    SceneSprites.__init__(s, "test")
    s.tick_hz = DEFAULT_TICK_HZ
    s.uuid_strategy = strategy
    s.parent_frame = parent_frame
    s._animation_t0 = 0.0
    return s


def _sphere_item(label, animated_mode="none", **anim_extra):
    """A sphere item factory — easier to animate than a box because
    pose-based modes work on any shape."""
    return {
        "type": "sphere",
        "label": label,
        "pose": {"x": 0, "y": 0, "z": 0, "ox": 0, "oy": 0, "oz": 1, "theta": 0},
        "radius_mm": 50,
        "color": {"r": 100, "g": 100, "b": 100},
        "opacity": 1.0,
        "animation": dict(mode=animated_mode, **anim_extra),
    }


def _cfg(attrs):
    return ComponentConfig(attributes=dict_to_struct(attrs))


# ---------- list_uuids / get_transform ----------

async def test_list_uuids_empty_when_no_items():
    s = _bare_service()
    assert await s.list_uuids() == []


async def test_list_uuids_returns_one_per_item():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _sphere_item("a")})
    await s.do_command({"command": "add", "item": _sphere_item("b")})
    uuids = await s.list_uuids()
    assert sorted(u.decode() for u in uuids) == ["a", "b"]


async def test_get_transform_returns_cached_transform():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _sphere_item("a")})
    tf = await s.get_transform(b"a")
    assert tf.uuid == b"a"
    assert tf.physical_object.label == "a"


async def test_get_transform_unknown_uuid_raises():
    s = _bare_service()
    with pytest.raises(Exception, match="unknown uuid"):
        await s.get_transform(b"ghost")


# ---------- stream_transform_changes ----------

async def test_subscriber_receives_initial_burst_of_added_for_existing_items():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _sphere_item("a")})
    await s.do_command({"command": "add", "item": _sphere_item("b")})

    gen = s.stream_transform_changes()
    msg1 = await gen.__anext__()
    msg2 = await gen.__anext__()
    assert msg1.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    assert msg2.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    labels = {msg1.transform.physical_object.label, msg2.transform.physical_object.label}
    assert labels == {"a", "b"}
    await gen.aclose()


async def test_subscriber_unsubscribes_on_aclose():
    s = _bare_service()
    gen = s.stream_transform_changes()
    # Pump the burst to register the subscriber.
    async with asyncio.timeout(0.5):
        # No items, so the burst is empty — but the subscriber should be
        # registered before the generator yields. Drive one add to
        # confirm: the subscriber should see the ADDED.
        async def add_then_close():
            await asyncio.sleep(0.01)
            await s.do_command({"command": "add", "item": _sphere_item("c")})
        task = asyncio.create_task(add_then_close())
        msg = await gen.__anext__()
        assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
        await task
    await gen.aclose()
    # Subscriber list should be empty after aclose.
    assert s._subscribers == []


async def test_subscriber_receives_added_when_add_happens_while_subscribed():
    s = _bare_service()
    gen = s.stream_transform_changes()
    # Burst is empty because no items yet. Sub is now registered.
    add_task = asyncio.create_task(
        s.do_command({"command": "add", "item": _sphere_item("late")})
    )
    msg = await gen.__anext__()
    await add_task
    assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    assert msg.transform.physical_object.label == "late"
    await gen.aclose()


async def test_subscriber_receives_removed_on_remove():
    s = _bare_service()
    await s.do_command({"command": "add", "item": _sphere_item("doomed")})
    gen = s.stream_transform_changes()
    # Drain initial ADDED.
    await gen.__anext__()
    rm_task = asyncio.create_task(
        s.do_command({"command": "remove", "label": "doomed"})
    )
    msg = await gen.__anext__()
    await rm_task
    assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED
    await gen.aclose()


# ---------- animation tick — stable strategy ----------

async def test_tick_once_with_stable_uuid_emits_updated_event_with_fieldmask():
    """The core contract: an animated item, when ticked, emits an
    UPDATED event with the right field-mask paths. This is the path
    the renderer reads to apply the delta."""
    s = _bare_service(strategy="stable")
    s.tick_hz = 100  # short period
    await s.do_command({
        "command": "add",
        "item": _sphere_item("spin_me", animated_mode="oscillate",
                             amplitude_mm=200, period_s=4),
    })

    gen = s.stream_transform_changes()
    # Initial ADDED.
    msg_added = await gen.__anext__()
    assert msg_added.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED

    # Drive one tick at t=1.0 (T/4 -> max excursion). Set _animation_t0
    # so the elapsed time is exactly 1.0.
    import time
    s._animation_t0 = time.monotonic() - 1.0

    tick_task = asyncio.create_task(s._tick_once())
    msg = await gen.__anext__()
    await tick_task

    assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_UPDATED
    # Same UUID — stable strategy.
    assert msg.transform.uuid == b"spin_me"
    # Field-mask carries the y path.
    assert list(msg.updated_fields.paths) == ["poseInObserverFrame.pose.y"]
    # Y is at the max excursion (~200 mm).
    assert msg.transform.pose_in_observer_frame.pose.y == pytest.approx(200.0, abs=1e-6)
    await gen.aclose()


async def test_static_items_do_not_emit_on_tick():
    """A scene with no animated items should produce zero events from
    a tick — the tick_loop simply doesn't get scheduled, and a manual
    _tick_once is a no-op."""
    s = _bare_service(strategy="stable")
    await s.do_command({"command": "add", "item": _sphere_item("static")})

    gen = s.stream_transform_changes()
    # Drain the initial burst (1 ADDED).
    await gen.__anext__()

    # Drive a manual tick — should add nothing to the queue.
    await s._tick_once()
    # Now check no message is pending.
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.05):
            await gen.__anext__()
    await gen.aclose()


# ---------- animation tick — versioned strategy ----------

async def test_tick_with_versioned_strategy_emits_removed_plus_added():
    """The other half of the toggle: when uuid_strategy is versioned,
    a tick emits REMOVED (old uuid) + ADDED (new uuid) instead of
    UPDATED. This is the apriltag-tracker pattern, available as a
    fallback if the renderer ever stops honoring UPDATED."""
    s = _bare_service(strategy="versioned")
    s.tick_hz = 100
    await s.do_command({
        "command": "add",
        "item": _sphere_item("v_item", animated_mode="oscillate",
                             amplitude_mm=100, period_s=4),
    })

    # Capture the initial versioned UUID so we can verify it gets
    # replaced.
    initial_uuid = s._state["v_item"]["uuid"]
    assert initial_uuid != b"v_item"  # has a timestamp suffix

    gen = s.stream_transform_changes()
    msg_added = await gen.__anext__()
    assert msg_added.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    assert msg_added.transform.uuid == initial_uuid

    # Tick — expect REMOVED of initial_uuid then ADDED of a fresh UUID.
    import time
    s._animation_t0 = time.monotonic() - 1.0
    tick_task = asyncio.create_task(s._tick_once())
    msg_rm = await gen.__anext__()
    msg_add = await gen.__anext__()
    await tick_task

    assert msg_rm.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED
    assert msg_rm.transform.uuid == initial_uuid
    assert msg_add.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    assert msg_add.transform.uuid != initial_uuid
    await gen.aclose()


# ---------- reconfigure ----------

async def test_reconfigure_loads_default_preset_when_no_items_or_preset():
    s = _bare_service()
    s.reconfigure(_cfg({}), {})
    # Default preset is `all` — bundles every other preset. Should
    # contain at least every primitive (12) plus the lifecycle row,
    # so > 12. Don't pin an exact count — adding a new preset to
    # `all_preset` shouldn't break this test.
    assert len(s._state) > 12
    # Then close it cleanly so the test runner doesn't warn about
    # unawaited tasks.
    await s.close()


async def test_reconfigure_with_explicit_items_overrides_preset():
    s = _bare_service()
    s.reconfigure(_cfg({
        "preset": "orientation_vectors",
        "items": [_sphere_item("only_me")],
    }), {})
    assert list(s._state.keys()) == ["only_me"]
    await s.close()


async def test_reconfigure_pushes_removed_for_prior_added_for_new_to_subscribers():
    """Subscribers connected at reconfigure time see REMOVED for the
    prior world and ADDED for the new — matches the WorldStateStore
    contract that the diff is observable through the stream."""
    s = _bare_service()
    s.reconfigure(_cfg({"items": [_sphere_item("first")]}), {})
    gen = s.stream_transform_changes()
    # Drain initial burst (1 ADDED for "first").
    await gen.__anext__()

    reconfig_task = asyncio.create_task(
        asyncio.to_thread(
            s.reconfigure, _cfg({"items": [_sphere_item("second")]}), {},
        )
    )
    # Should see: REMOVED first, ADDED second.
    msg1 = await gen.__anext__()
    msg2 = await gen.__anext__()
    await reconfig_task
    types = {msg1.change_type, msg2.change_type}
    assert TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED in types
    assert TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED in types
    await gen.aclose()
    await s.close()


async def test_reconfigure_starts_tick_task_only_when_items_are_animated():
    """A static-only config shouldn't spawn the tick — pure CPU savings
    + cleaner debug snapshots."""
    s = _bare_service()
    s.reconfigure(_cfg({"items": [_sphere_item("static")]}), {})
    assert s._tick_task is None
    s.reconfigure(_cfg({
        "items": [_sphere_item("moving", animated_mode="oscillate")],
    }), {})
    assert s._tick_task is not None
    await s.close()


# ---------- close cleans up the tick task ----------

# ---------- flicker REMOVED/ADDED scene-graph operations ----------

async def test_flicker_emits_removed_then_added_on_phase_transitions():
    """Flicker truly removes and re-adds the entity to the scene
    instead of just toggling opacity. Subscribers see REMOVED on the
    falling edge of the duty cycle and ADDED on the rising edge."""
    import time
    s = _bare_service(strategy="stable")
    s.tick_hz = 100
    await s.do_command({
        "command": "add",
        "item": _sphere_item("blink", animated_mode="flicker",
                             period_s=4.0, duty_cycle=0.5),
    })
    # Initial state: visible.
    assert s._state["blink"]["visible_to_viewer"] is True

    gen = s.stream_transform_changes()
    # Drain initial ADDED burst.
    await gen.__anext__()

    # Drive a tick at t=3s (3/4 of the period → out of scene).
    s._animation_t0 = time.monotonic() - 3.0
    tick_task = asyncio.create_task(s._tick_once())
    msg = await gen.__anext__()
    await tick_task
    assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_REMOVED
    assert s._state["blink"]["visible_to_viewer"] is False

    # Drive a tick at t=4s (full period wrap → back in scene).
    s._animation_t0 = time.monotonic() - 4.0
    tick_task = asyncio.create_task(s._tick_once())
    msg = await gen.__anext__()
    await tick_task
    assert msg.change_type == TransformChangeType.TRANSFORM_CHANGE_TYPE_ADDED
    assert s._state["blink"]["visible_to_viewer"] is True
    await gen.aclose()


async def test_flicker_uses_fresh_uuid_on_each_rising_edge():
    """The viewer caches UUIDs across REMOVED and silently drops a
    subsequent ADDED for the same UUID — apriltag-tracker's prior
    finding. So flicker must rotate the UUID on every re-add, or
    second-cycle items never come back without a viewer refresh.

    Pins the workaround: after one REMOVED+ADDED cycle, the entity's
    UUID is different from what it was on install."""
    import time
    s = _bare_service(strategy="stable")
    s.tick_hz = 100
    await s.do_command({
        "command": "add",
        "item": _sphere_item("blink", animated_mode="flicker",
                             period_s=4.0, duty_cycle=0.5),
    })
    initial_uuid = s._state["blink"]["uuid"]
    # Stable strategy → UUID matches the label.
    assert initial_uuid == b"blink"

    # Tick at t=3s → out of scene.
    s._animation_t0 = time.monotonic() - 3.0
    await s._tick_once()
    assert s._state["blink"]["visible_to_viewer"] is False

    # Tick at t=4s → back in scene. UUID must rotate so the viewer
    # doesn't drop this ADDED as a duplicate of the prior REMOVED.
    s._animation_t0 = time.monotonic() - 4.0
    await s._tick_once()
    assert s._state["blink"]["visible_to_viewer"] is True
    new_uuid = s._state["blink"]["uuid"]
    assert new_uuid != initial_uuid, (
        "flicker re-add must use a fresh UUID; the viewer caches "
        "removed UUIDs and silently drops repeats"
    )
    # The new UUID still encodes the label so it's debuggable.
    assert new_uuid.startswith(b"blink_")


async def test_flicker_with_rotate_uuid_on_readd_false_keeps_uuid_stable():
    """Opt-out: when an item's animation sets
    ``rotate_uuid_on_readd: false``, the UUID stays the same across
    every REMOVED+ADDED cycle. This intentionally trips the
    viewer's UUID cache (the side-by-side broken-grid demo in
    geometry_morph) — the entity never re-appears in the viewer
    after the first cycle, even though our service correctly emits
    REMOVED/ADDED on the wire. Pinned so the teaching demo
    behavior doesn't accidentally regress to working."""
    import time
    s = _bare_service(strategy="stable")
    s.tick_hz = 100
    item = _sphere_item("stuck", animated_mode="flicker",
                        period_s=4.0, duty_cycle=0.5)
    item["animation"]["rotate_uuid_on_readd"] = False
    await s.do_command({"command": "add", "item": item})
    initial_uuid = s._state["stuck"]["uuid"]
    # Falling edge.
    s._animation_t0 = time.monotonic() - 3.0
    await s._tick_once()
    # Rising edge — without the opt-in rotation, UUID stays the same.
    s._animation_t0 = time.monotonic() - 4.0
    await s._tick_once()
    assert s._state["stuck"]["uuid"] == initial_uuid, (
        "rotate_uuid_on_readd=False must keep the UUID stable; the "
        "viewer caches the original UUID and will silently drop the "
        "subsequent ADDED — that's the bug this opt-out demonstrates"
    )


async def test_flicker_removed_item_is_filtered_from_list_uuids_and_get_transform():
    """While an entity is in the flicker 'off' phase, it must be
    invisible to subscribers: list_uuids omits its UUID, and
    get_transform raises rather than returning the stale transform
    (which would otherwise leak the 'removed' entity back into the
    viewer through a subsequent burst)."""
    import time
    s = _bare_service(strategy="stable")
    s.tick_hz = 100
    await s.do_command({
        "command": "add",
        "item": _sphere_item("blink", animated_mode="flicker",
                             period_s=4.0, duty_cycle=0.5),
    })
    # Drive a tick that flips it out of the scene.
    s._animation_t0 = time.monotonic() - 3.0
    await s._tick_once()
    assert s._state["blink"]["visible_to_viewer"] is False

    # The UUID should be absent from list_uuids while removed.
    uuids = await s.list_uuids()
    assert b"blink" not in uuids
    # And get_transform raises rather than returning the stale tf.
    with pytest.raises(Exception, match="not in the scene"):
        await s.get_transform(b"blink")


async def test_close_cancels_tick_task():
    s = _bare_service()
    s.reconfigure(_cfg({
        "items": [_sphere_item("moving", animated_mode="oscillate")],
    }), {})
    assert s._tick_task is not None
    # Give the loop a chance to schedule.
    await asyncio.sleep(0)
    await s.close()
    assert s._tick_task.cancelled() or s._tick_task.done()
