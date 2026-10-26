"""Exercise visitor recovery and trusted handoff without processes or hardware."""

from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from test_panel_navigation import panel, REAL_POLL_WORKER
from lighting_recovery import LightingRecovery
import lighting_recovery
import panel_remote


TOKEN = "experiment-owner-12345678"
LABEL = "Lighting study"


@pytest.fixture
def recoverable(tmp_path, monkeypatch):
    """Real owner logic with a fake event loop; no Tk/native windows or processes."""
    view = panel.Panel.__new__(panel.Panel)
    view.args = SimpleNamespace(live_lights=True, timezone="America/New_York", light_at=420, dark_at=1140)
    view.recovery = LightingRecovery(tmp_path / "lighting.json")
    view.closed, view.closing, view.keep_switcher = False, None, True
    view.mode, view.light_state = "room", "disconnected"
    view.worker, view.worker_ready, view.worker_buffer = None, False, ""
    view.light_changes_requested = view.release_confirmed = False
    view.light_capabilities, view.programme = {}, None
    view.blinds_connected = view.blinds_enabled = False
    view.blind_controller = None
    view.observing, view.recovery_check_at = False, None
    view.legacy_probe = view.legacy_target = None
    view.reservation_token = view.reservation_label = None
    view.release_target = view.pending = view.queued_intent = view.intent_timer = None
    view.press_active = view.running = view.idle_active = False
    view.run_id, view.request_seq, view.sequence, view.view_generation = "test-owner", 0, 0, 0
    view.elapsed, view.stage, view.profile = 0, 0, {}
    view.advanced_page = None
    view.confirmed_at = view.confirmed_power = view.confirmed_scene = None
    view.confirmed_light, view.light_message = "Not checked", "Lighting unavailable"
    view.cct = SimpleNamespace(get=lambda: 3500)
    view.intensity = SimpleNamespace(get=lambda: 1000)
    view.channel_values = [SimpleNamespace(get=lambda: 0) for unused in range(8)]
    view.annotation_text = SimpleNamespace(get=lambda: "")
    view.theme_choice, view.theme, view.clock_24 = "light", "light", True
    view.temperature_unit, view.idle_timeout, view.help_on = "f", 300, True
    view.blinds_display, view.health_cache, view.room_status = "disabled", {}, "Not checked"
    view.weather_reading = view.weather_good = None
    for key in ("bg", "surface", "ink", "muted", "control", "border", "accent", "selected_ink",
                "icon_colour", "accent_pressed", "pressed", "good", "warning", "weather_warm", "weather_cool"):
        setattr(view, key, "#ffffff")
    view.events, view.messages, view.scheduled = [], [], []
    view.root = SimpleNamespace(after=lambda *args: view.scheduled.append(args))
    view.status_text = SimpleNamespace(set=view.messages.append)
    view.lighting_feedback = view.messages.append
    view.emit = lambda event, **values: view.events.append((event, values))
    view.cancel_intent = lambda: setattr(view, "queued_intent", None)
    view.update_light_buttons = view.update_recovery_view = view.activity = lambda *unused: None
    view.poll_journal = view.poll_power = view.poll_status = view.poll_weather = lambda: None
    view.power_busy = lambda: False
    view.power_snapshot = lambda: None
    monkeypatch.setattr(panel.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("No external process is allowed"))
    return view


def live_helper(view):
    view.worker_ready = True
    view.light_state = "ready"
    view.worker = SimpleNamespace(stdin=BytesIO(), stdout=SimpleNamespace(fileno=lambda: 99),
                                  poll=lambda: None, returncode=None)
    view.last_heartbeat = panel.monotonic()
    return view.worker


def held_experiment(view):
    view.recovery.begin_reservation(TOKEN, LABEL)
    view.recovery.reserve(TOKEN, LABEL, released=True, helper_exited=True)


def test_public_connection_check_starts_read_only_acquire_with_no_setter(recoverable, monkeypatch):
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    recoverable.check_connection()
    assert starts == [{}]
    assert recoverable.pending is None
    assert recoverable.recovery.state["status"] == "normal"


def test_uncertain_connection_check_only_observes_and_does_not_authorize_writes(recoverable, monkeypatch):
    recoverable.recovery.mark_uncertain("An earlier command was not confirmed.")
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    recoverable.check_connection()
    assert starts == [{"observe_only": True}]
    recoverable.recovery_result({"action": "check"}, {"state": "checked", "stable": True, "fixtures": 10})
    assert recoverable.recovery_snapshot()["needs_staff"]
    assert recoverable.recovery.state["status"] == "uncertain"
    assert recoverable.ownership_blocked()


def test_existing_helper_check_sends_only_read_request(recoverable):
    worker = live_helper(recoverable)
    recoverable.check_connection()
    requests = [json.loads(line) for line in worker.stdin.getvalue().splitlines()]
    assert [item["action"] for item in requests] == ["check"]
    assert recoverable.recovery.state["status"] == "normal"
    assert not recoverable.light_changes_requested


def test_reservation_is_not_granted_until_preserved_release_and_helper_exit(recoverable, monkeypatch):
    worker = live_helper(recoverable)
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    recoverable.handoff("reserve", {"token": TOKEN, "label": LABEL})
    request_id = recoverable.pending["request_id"]
    assert recoverable.recovery.state["status"] == "releasing"
    recoverable.worker_buffer = json.dumps({"version": 1, "request_id": request_id,
        "state": "released", "preserved": True}) + "\n"
    REAL_POLL_WORKER(recoverable)
    assert recoverable.release_confirmed
    assert recoverable.worker is worker
    assert recoverable.recovery.state["status"] == "releasing"
    worker.returncode = 0
    worker.poll = lambda: 0
    REAL_POLL_WORKER(recoverable)
    assert recoverable.worker is None
    assert recoverable.recovery.state["status"] == "reserved"
    assert not recoverable.recovery_snapshot()["can_check"]


def test_abnormal_exit_after_release_does_not_grant_experiment(recoverable, monkeypatch):
    worker = live_helper(recoverable)
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    recoverable.handoff("reserve", {"token": TOKEN, "label": LABEL})
    recoverable.worker_buffer = json.dumps({"version": 1, "request_id": recoverable.pending["request_id"],
        "state": "released", "preserved": True}) + "\n"
    REAL_POLL_WORKER(recoverable)
    worker.returncode = 1
    worker.poll = lambda: 1
    REAL_POLL_WORKER(recoverable)
    assert recoverable.recovery.state["status"] == "uncertain"
    assert recoverable.recovery_snapshot()["write_blocked"]


@pytest.mark.parametrize("arguments", ({"token": "wrong-experiment-owner"},
                                      {"token": TOKEN, "owner_closed": True},
                                      {"token": TOKEN, "owner_closed": True, "pending_clear": False}))
def test_experiment_finish_needs_matching_token_and_both_closure_assertions(recoverable, monkeypatch, arguments):
    held_experiment(recoverable)
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    with pytest.raises((ValueError, RuntimeError)):
        recoverable.handoff("finish", arguments)
    assert starts == []
    assert recoverable.recovery.state["status"] == "reserved"


def test_verified_finish_waits_for_stable_all_fixture_acquire(recoverable, monkeypatch):
    held_experiment(recoverable)
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    recoverable.handoff("finish", {"token": TOKEN, "owner_closed": True, "pending_clear": True})
    assert starts == [{}]
    assert recoverable.recovery.state["status"] == "recovering"
    assert recoverable.ownership_blocked()
    recoverable.recovery_result({"action": "acquire"}, {"state": "ready", "fixtures": 10, "manual_blocked": False})
    assert recoverable.recovery.state["status"] == "normal"


def test_failed_reconnect_keeps_ownership_block_durable(recoverable):
    held_experiment(recoverable)
    recoverable.recovery.finish(TOKEN, owner_closed=True, pending_clear=True)
    recoverable.recovery_result({"action": "acquire"}, {"state": "failed"})
    assert recoverable.recovery.state["status"] == "uncertain"
    restarted = LightingRecovery(recoverable.recovery.path)
    assert restarted.public()["needs_staff"]


def test_read_only_initial_acquire_failure_keeps_original_fallback_available(recoverable, monkeypatch):
    recoverable.recovery_result({"action": "acquire"}, {"state": "failed", "outcome_unknown": False})
    assert recoverable.recovery.state["status"] == "normal"
    recoverable.light_state = "failed"
    destinations = []
    monkeypatch.setattr(recoverable, "render", lambda: destinations.append(recoverable.mode))
    monkeypatch.setattr(recoverable, "cancel_hold", lambda: None)
    monkeypatch.setattr(recoverable, "update_navigation_buttons", lambda: None)
    recoverable.show("original")
    assert destinations == ["original"]
    assert recoverable.recovery.state["status"] == "legacy"


def test_lost_reservation_release_does_not_leave_a_ready_restart(recoverable, monkeypatch):
    live_helper(recoverable)
    monkeypatch.setattr(recoverable, "request", lambda *unused, **kwargs: False)
    with pytest.raises(RuntimeError):
        recoverable.handoff("reserve", {"token": TOKEN, "label": LABEL})
    restarted = LightingRecovery(recoverable.recovery.path)
    assert restarted.public()["status"] == "uncertain"
    assert restarted.public()["write_blocked"]


def test_expired_experiment_heartbeat_never_reclaims_ownership(recoverable, monkeypatch):
    held_experiment(recoverable)
    monkeypatch.setattr(recoverable.recovery, "clock", lambda: recoverable.recovery.state["heartbeat_at"] + 86400)
    state = recoverable.recovery_snapshot()
    assert state["status"] == "reserved" and state["needs_staff"]
    assert not state["can_check"]
    with pytest.raises(RuntimeError):
        recoverable.check_connection()


@pytest.mark.parametrize("status", ("reserved", "uncertain"))
def test_legacy_cannot_bypass_unresolved_ownership(recoverable, status):
    if status == "reserved":
        held_experiment(recoverable)
    else:
        recoverable.recovery.mark_uncertain("Previous lighting ownership is unresolved.")
    recoverable.show("original")
    assert recoverable.mode != "original"
    assert recoverable.recovery_snapshot()["write_blocked"]


def test_reservation_token_is_absent_from_public_snapshot_and_events(recoverable, monkeypatch):
    live_helper(recoverable)
    events = []
    original_emit = recoverable.emit

    def emit(event, **values):
        events.append((event, values))
        return original_emit(event, **values)

    monkeypatch.setattr(recoverable, "emit", emit)
    recoverable.handoff("reserve", {"token": TOKEN, "label": LABEL})
    visible = json.dumps(panel_remote.snapshot(recoverable))
    assert TOKEN not in visible and recoverable.recovery.state["token_hash"] not in visible
    assert TOKEN not in json.dumps(events)


def test_public_legacy_action_opens_original_fallback(recoverable, monkeypatch):
    destinations = []
    monkeypatch.setattr(recoverable, "show", destinations.append)
    panel_remote.execute(recoverable, {"id": "browser-legacy-12345", "action": "legacy", "arguments": {}})
    assert destinations == ["original"]


def test_storage_failure_after_command_confirmation_keeps_ui_loop_and_safety_block(recoverable, monkeypatch):
    live_helper(recoverable)
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    assert recoverable.request("channels", {"values": [0] * 8})
    recoverable.worker_buffer = json.dumps({"version": 1, "request_id": recoverable.pending["request_id"],
        "state": "completed", "fixtures": 10, "words": [0] * 8}) + "\n"
    scheduled = []
    monkeypatch.setattr(recoverable.root, "after", lambda *args: scheduled.append(args))

    def fail_replace(*unused):
        raise OSError("storage unavailable")

    monkeypatch.setattr(lighting_recovery.os, "replace", fail_replace)
    REAL_POLL_WORKER(recoverable)
    assert recoverable.recovery_snapshot()["needs_staff"]
    assert recoverable.ownership_blocked()
    assert any(args[0] == 100 for args in scheduled)


@pytest.mark.parametrize("failure_at", ("write", "flush"))
def test_lost_helper_pipe_blocks_immediately_and_remains_blocked_after_restart(recoverable, failure_at):
    worker = live_helper(recoverable)

    class LostPipe(BytesIO):
        def write(self, data):
            if failure_at == "write":
                raise BrokenPipeError("helper disconnected")
            return super().write(data)

        def flush(self):
            if failure_at == "flush":
                raise BrokenPipeError("helper disconnected")
            return super().flush()

    worker.stdin = LostPipe()
    assert not recoverable.request("channels", {"values": [0] * 8})
    assert recoverable.recovery.state["status"] == "uncertain"
    assert recoverable.recovery_snapshot()["needs_staff"]
    assert recoverable.worker is worker  # Do not launch a replacement while it might still run.
    assert LightingRecovery(recoverable.recovery.path).public()["write_blocked"]


def test_helper_death_with_pending_write_blocks_without_restarting_panel(recoverable, monkeypatch):
    worker = live_helper(recoverable)
    assert recoverable.request("channels", {"values": [0] * 8})
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    worker.returncode = 1
    worker.poll = lambda: 1
    REAL_POLL_WORKER(recoverable)
    assert recoverable.worker is None
    assert recoverable.pending is None
    assert recoverable.recovery.state["status"] == "uncertain"
    assert recoverable.recovery_snapshot()["needs_staff"]
    assert LightingRecovery(recoverable.recovery.path).public()["write_blocked"]
    assert any(args[0] == 100 for args in recoverable.scheduled)


def test_original_idle_probe_never_grants_beta_ownership_and_same_legacy_can_reopen(recoverable, monkeypatch):
    recoverable.recovery.enter_legacy()
    recoverable.mode = "original"
    recoverable.legacy_probe = SimpleNamespace(poll=lambda: 0, returncode=0,
        stdout=BytesIO(b'{"idle":true}'), stderr=BytesIO())
    recoverable.legacy_target = ("room", None)
    rendered = []
    monkeypatch.setattr(recoverable, "render", lambda: rendered.append(recoverable.mode))
    monkeypatch.setattr(recoverable, "cancel_hold", lambda: None)
    monkeypatch.setattr(recoverable, "update_navigation_buttons", lambda: None)
    monkeypatch.setattr(recoverable, "start_worker", lambda **unused: pytest.fail("An idle callback cannot grant ownership"))
    recoverable.poll_legacy_return()
    assert recoverable.mode == "room"
    assert recoverable.recovery.state["status"] == "legacy"
    assert recoverable.recovery_snapshot()["write_blocked"]
    assert recoverable.recovery_snapshot()["needs_staff"]
    recoverable.show("original")
    assert recoverable.mode == "original" and rendered == ["room", "original"]
    assert recoverable.recovery.state["status"] == "legacy"


def test_only_covered_original_and_explicit_staff_assertions_can_return_beta(recoverable, monkeypatch):
    recoverable.recovery.enter_legacy()
    recoverable.mode = "original"
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    assertions = {"owner_closed": True, "pending_clear": True}
    with pytest.raises(RuntimeError):
        recoverable.handoff("recover", assertions)
    recoverable.mode = "room"  # Original input is covered before local reconciliation.
    with pytest.raises(RuntimeError):
        recoverable.handoff("recover", {"owner_closed": True})
    assert recoverable.recovery.state["status"] == "legacy" and starts == []
    recoverable.handoff("recover", assertions)
    assert recoverable.recovery.state["status"] == "recovering"
    assert starts == [{}]
    recoverable.recovery_result({"action": "acquire"}, {"state": "ready", "fixtures": 10, "manual_blocked": False})
    assert not recoverable.ownership_blocked()


def test_failed_read_only_legacy_probe_keeps_same_original_available(recoverable, monkeypatch):
    recoverable.recovery.enter_legacy()
    recoverable.mode = "original"
    recoverable.legacy_probe = SimpleNamespace(poll=lambda: 1, returncode=1,
        stdout=BytesIO(b'{"idle":false}'), stderr=BytesIO())
    recoverable.legacy_target = ("room", None)
    monkeypatch.setattr(recoverable, "render", lambda: None)
    monkeypatch.setattr(recoverable, "cancel_hold", lambda: None)
    monkeypatch.setattr(recoverable, "update_navigation_buttons", lambda: None)
    recoverable.poll_legacy_return()
    assert recoverable.recovery.state["status"] == "legacy"
    assert recoverable.ownership_blocked()
    recoverable.show("original")
    assert recoverable.mode == "original"


def test_navigation_and_staff_recovery_are_rejected_during_original_probe(recoverable):
    recoverable.recovery.enter_legacy()
    recoverable.mode = "original"
    recoverable.legacy_probe = SimpleNamespace(poll=lambda: None)
    recoverable.legacy_target = ("room", None)
    for mode in ("room", "original", "black", "health"):
        recoverable.show(mode)
        assert recoverable.mode == "original"
        assert recoverable.legacy_target == ("room", None)
    with pytest.raises(RuntimeError):
        recoverable.handoff("recover", {"owner_closed": True, "pending_clear": True})
    assert recoverable.recovery.state["status"] == "legacy"
