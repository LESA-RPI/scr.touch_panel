"""Switching room interfaces must preserve drive settings and uncertain results."""

from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from test_scr_touch_panel import Room, adapter, panel


def gradient_room():
    room = Room()
    room.state = {
        xy: tuple(65535 if channel == index % 8 else 0 for channel in range(8))
        for index, xy in enumerate(sorted(adapter.COORDINATES))
    }
    return room


def test_gradient_can_be_acquired_and_released_repeatedly_without_any_setter():
    room = gradient_room()
    original = dict(room.state)
    lights = adapter.Lights(room.call, keep_settings=True)
    for unused in range(5):
        acquired = lights.acquire()
        assert acquired["state"] == "ready" and acquired["baseline"] is None
        assert acquired["power"] == "on"
        released = lights.release()
        assert released["preserved"] and not released["restored"]
        assert room.state == original and room.writes == []


def test_explicit_selection_survives_release_and_next_interface_acquisition():
    room = gradient_room()
    lights = adapter.Lights(room.call, keep_settings=True)
    lights.acquire()
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    selected = dict(room.state)
    writes = list(room.writes)
    assert lights.release()["preserved"]
    assert room.state == selected and room.writes == writes
    assert lights.acquire()["baseline"] == "Sat"
    assert lights.release()["preserved"]
    assert room.state == selected and room.writes == writes


def test_release_does_not_overwrite_new_external_settings():
    room = Room()
    lights = adapter.Lights(room.call, keep_settings=True)
    lights.acquire()
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    room.state = gradient_room().state
    external = dict(room.state)
    writes = list(room.writes)
    assert lights.release()["preserved"]
    assert room.state == external and room.writes == writes


def test_changing_baseline_cannot_be_acquired_or_written():
    room = gradient_room()
    reads = []

    def changing_call(name, *args):
        if name == "get_lights":
            reads.append(name)
            if len(reads) == 2:
                xy = min(room.state)
                room.state[xy] = (0,) * 8
        return room.call(name, *args)

    lights = adapter.Lights(changing_call, keep_settings=True)
    result = lights.acquire()
    assert result["state"] == "ready" and result["manual_blocked"]
    assert lights.baseline is None
    with pytest.raises(ValueError, match="unavailable"):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert room.writes == []


@pytest.mark.parametrize("lost_response", [False, True])
def test_unknown_write_cannot_be_released_or_retried_even_if_readback_later_matches(
    lost_response,
):
    room = Room()
    room.lose_response = lost_response

    def call(name, *args):
        result = room.call(name, *args)
        if name == "sources_all" and not lost_response:
            # The response claims Sat; one fixture reports a different drive.
            room.state[min(room.state)] = (0,) * 8
        return result

    lights = adapter.Lights(call, keep_settings=True)
    lights.acquire()
    with pytest.raises((TimeoutError, ValueError)):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    room.state = dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS["Sat"]))
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    with pytest.raises(ValueError, match="unavailable"):
        lights.apply("channels", {"values": list(adapter.PRESETS["Off"])})
    assert len(room.writes) == 1


def test_external_change_before_explicit_selection_blocks_write_and_release():
    room = Room()
    lights = adapter.Lights(room.call, keep_settings=True)
    lights.acquire()
    room.state = gradient_room().state
    with pytest.raises(ValueError, match="ownership lost"):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert room.writes == []


def test_bounded_trials_still_reject_gradient_and_restore_qualified_presets():
    gradient = gradient_room()
    with pytest.raises(ValueError, match="restorable"):
        adapter.Lights(gradient.call).acquire()
    assert gradient.writes == []
    room = Room()
    initial = dict(room.state)
    trial = adapter.Lights(room.call)
    trial.acquire()
    trial.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert trial.release()["restored"]
    assert room.state == initial and len(room.writes) == 2


@pytest.fixture
def controller(monkeypatch):
    """Run the real owner poller without Tk, processes, sockets or device access."""
    state = panel.Panel.__new__(panel.Panel)
    state.closed, state.closing, state.keep_switcher = False, None, True
    state.mode, state.light_state = "room", "connecting"
    state.worker_ready = True
    state.light_capabilities = {}
    state.light_programme, state.light_manual_blocked = None, False
    state.blinds_connected = False
    state.release_confirmed = state.light_changes_requested = False
    state.release_target = state.queued_intent = state.intent_timer = None
    state.pending = {"request_id": "test:1", "action": "acquire", "arguments": {}}
    state.worker_buffer = ""
    state.last_heartbeat = panel.monotonic()
    state.root = SimpleNamespace(after=lambda *args: state.scheduled.append(args))
    state.scheduled, state.messages, state.events, state.shown = [], [], [], []
    state.status_text = SimpleNamespace(set=state.messages.append)
    state.lighting_feedback = state.messages.append
    state.emit = lambda *args, **kwargs: state.events.append((args, kwargs))
    state.cancel_intent = lambda: setattr(state, "queued_intent", None)
    state.update_light_buttons = lambda: None
    state.poll_journal = state.poll_power = state.poll_status = state.poll_weather = (
        lambda: None
    )
    state.show = state.shown.append
    state.worker = SimpleNamespace(
        stdin=BytesIO(), stdout=SimpleNamespace(fileno=lambda: 99), poll=lambda: None
    )
    monkeypatch.setattr(panel.select, "select", lambda *args: ([], [], []))
    return state


def test_real_gradient_acquisition_response_keeps_poller_running(controller):
    room = gradient_room()
    response = adapter.Lights(room.call, keep_settings=True).acquire()
    controller.worker_buffer = json.dumps(
        dict(response, version=1, request_id="test:1")
    ) + "\n"
    controller.poll_worker()
    assert controller.light_state == "ready" and controller.pending is None
    assert controller.confirmed_light == "Current room settings"
    assert controller.confirmed_scene is None and controller.confirmed_power == "on"
    assert controller.scheduled and room.writes == []


def test_stalled_helper_startup_is_cancelled_before_any_light_command(
    controller, monkeypatch
):
    controller.pending = None
    controller.worker_ready = False
    controller.worker_started = 0
    terminated = []
    controller.worker.terminate = lambda: terminated.append(True)
    monkeypatch.setattr(panel, "monotonic", lambda: 31)
    controller.poll_worker()
    assert terminated == [True] and controller.light_state == "failed"
    assert not controller.light_changes_requested
    assert controller.worker.stdin.closed and controller.scheduled


@pytest.mark.parametrize("reply", ["null", "[]", "42", '"ready"', "{broken"])
def test_invalid_adapter_json_latches_failure_and_keeps_poller_running(controller, reply):
    controller.worker_buffer = reply + "\n"
    controller.poll_worker()
    assert controller.light_state == "failed"
    assert controller.worker.stdin.closed
    assert controller.scheduled and controller.shown == []


def test_invalid_adapter_utf8_latches_failure_and_keeps_poller_running(
    controller, monkeypatch
):
    readable = [[controller.worker.stdout], [], []]
    monkeypatch.setattr(panel.select, "select", lambda *args: readable)
    monkeypatch.setattr(panel.os, "read", lambda *args: b"\xff\n")
    controller.poll_worker()
    assert controller.light_state == "failed"
    assert controller.worker.stdin.closed
    assert controller.scheduled and controller.shown == []


@pytest.mark.parametrize("baseline", [[], {}, 42, True])
def test_invalid_baseline_type_latches_failure(controller, baseline):
    controller.worker_buffer = json.dumps(
        dict(version=1, request_id="test:1", state="ready", baseline=baseline)
    ) + "\n"
    controller.poll_worker()
    assert controller.light_state == "failed" and controller.worker.stdin.closed
    assert controller.scheduled and controller.shown == []


@pytest.mark.parametrize(
    "action, reply",
    [
        ("acquire", "completed"),
        ("acquire", "released"),
        ("release", "ready"),
        ("release", "completed"),
        ("channels", "ready"),
        ("channels", "released"),
        ("cct", "ready"),
    ],
)
def test_reply_must_match_the_pending_action(controller, action, reply):
    controller.pending["action"] = action
    controller.worker_buffer = json.dumps(
        dict(version=1, request_id="test:1", state=reply)
    ) + "\n"
    controller.poll_worker()
    assert controller.light_state == "failed" and controller.worker.stdin.closed
    assert not controller.release_confirmed
    assert controller.scheduled and controller.shown == []


def test_response_deadline_disables_controls_without_retry(controller, monkeypatch):
    monkeypatch.setattr(panel, "monotonic", lambda: 100.0)
    controller.pending["sent_monotonic_s"] = 64.0
    controller.light_changes_requested = True
    worker = controller.worker
    controller.poll_worker()
    assert controller.light_state == "failed" and worker.stdin.closed
    assert controller.pending is None and not controller.worker_ready
    assert controller.worker is worker  # Retain ownership until the child exits.
    assert controller.scheduled and controller.shown == []
    controller.release_target = "original"
    worker.poll = lambda: 1
    controller.poll_worker()
    assert controller.worker is None and controller.shown == []


def test_startup_cancellation_waits_for_child_exit_before_showing_legacy(controller):
    terminated = []
    controller.worker.terminate = lambda: terminated.append(True)
    controller.pending = None
    panel.Panel.show(controller, "original")
    assert terminated == [True] and controller.shown == []
    assert controller.release_target == "original"
    controller.poll_worker()
    assert controller.shown == [] and controller.worker is not None
    controller.worker.poll = lambda: -15
    controller.poll_worker()
    assert controller.worker is None and controller.shown == ["original"]


def test_failed_relaunch_after_confirmed_old_session_keeps_legacy_available(
    controller, monkeypatch
):
    controller.args = SimpleNamespace(journal="unused", expected_master="http://unused")
    controller.worker = None
    controller.release_confirmed = controller.light_changes_requested = True
    controller.cancel_hold = lambda: None
    controller.render = lambda: controller.shown.append(controller.mode)
    controller.update_navigation_buttons = lambda: None

    def unavailable(*args, **kwargs):
        raise OSError("helper interpreter unavailable")

    monkeypatch.setattr(panel.subprocess, "Popen", unavailable)
    controller.start_worker()
    assert controller.worker is None and controller.light_state == "failed"
    assert not controller.light_changes_requested and not controller.release_confirmed
    panel.Panel.show(controller, "original")
    assert controller.mode == "original" and controller.shown == ["original"]


@pytest.mark.parametrize("persistent", [False, True])
def test_helper_mode_argument_matches_persistent_or_bounded_trial(
    controller, monkeypatch, persistent
):
    controller.keep_switcher = persistent
    controller.args = SimpleNamespace(journal="unused", expected_master="http://unused")
    commands = []
    worker = controller.worker

    def launch(command, **kwargs):
        commands.append(command)
        return worker

    monkeypatch.setattr(panel.subprocess, "Popen", launch)
    controller.start_worker()
    assert ("--keep-settings" in commands[0]) is persistent
    assert controller.light_state == "connecting"
    assert not controller.light_changes_requested and not controller.release_confirmed


@pytest.mark.parametrize(
    "persistent, acknowledgement, accepted",
    [
        (True, "preserved", True),
        (True, "restored", False),
        (False, "restored", True),
        (False, "preserved", False),
    ],
)
def test_power_requires_release_acknowledgement_for_the_current_mode(
    controller, persistent, acknowledgement, accepted
):
    failures = []
    controller.keep_switcher = persistent
    controller.power = SimpleNamespace(phase="restoring", fail=failures.append)
    controller.power_cleanup_confirmed = False
    controller.pending["action"] = "release"
    controller.release_target = "power"
    controller.worker_buffer = json.dumps(
        dict(version=1, request_id="test:1", state="released", **{acknowledgement: True})
    ) + "\n"
    controller.poll_worker()
    assert controller.release_confirmed is accepted
    assert controller.power_cleanup_confirmed is accepted
    assert bool(failures) == (not accepted)
    assert controller.worker is not None and controller.shown == []


@pytest.mark.parametrize("changes_requested", [False, True])
def test_helper_exit_without_release_never_hands_off_unconfirmed_writes(
    controller, changes_requested
):
    controller.release_target = "original"
    controller.light_changes_requested = changes_requested
    controller.worker.poll = lambda: 1
    controller.poll_worker()
    assert controller.worker is None
    assert controller.shown == ([] if changes_requested else ["original"])
    assert controller.light_state == "failed" and controller.scheduled


def test_confirmed_release_still_waits_for_exact_helper_to_exit(controller):
    controller.pending["action"] = "release"
    controller.light_changes_requested = True
    controller.release_target = "original"
    controller.worker_buffer = json.dumps(
        {
            "version": 1,
            "request_id": "test:1",
            "state": "released",
            "preserved": True,
            "restored": False,
        }
    ) + "\n"
    controller.poll_worker()
    assert controller.release_confirmed and controller.shown == []
    assert controller.worker is not None
    controller.worker.poll = lambda: 0
    controller.poll_worker()
    assert controller.worker is None and controller.shown == ["original"]
