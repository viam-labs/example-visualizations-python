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
    # Default preset is all_primitives -> 7 items.
    assert len(s._state) == 7
    # Then close it cleanly so the test runner doesn't warn about
    # unawaited tasks (only animated configs spawn a tick task; this
    # one is static).
    await s.close()


async def test_reconfigure_with_explicit_items_overrides_preset():
    s = _bare_service()
    s.reconfigure(_cfg({
        "preset": "color_wheel",
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
