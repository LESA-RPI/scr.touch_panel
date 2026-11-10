"""Exercise visitor recovery and trusted handoff without processes or hardware."""

from io import BytesIO
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from test_panel_navigation import panel, REAL_POLL_WORKER
import panel_recovery
from lighting_recovery import LightingRecovery
import lighting_recovery
import panel_remote




@pytest.fixture
def recoverable(tmp_path, monkeypatch):
    """Real owner logic with a fake event loop; no Tk/native windows or processes."""
    view = panel.Panel.__new__(panel.Panel)
    view.args = SimpleNamespace(live_lights=True, timezone="America/New_York", light_at=420, dark_at=1140, duration=0)
    view.recovery = LightingRecovery(tmp_path / "lighting.json")
    view.closed, view.closing, view.keep_switcher = False, None, True
    view.mode, view.light_state = "room", "disconnected"
    view.worker, view.worker_ready, view.worker_buffer = None, False, ""
    view.light_changes_requested = view.release_confirmed = False
    view.light_capabilities, view.programme = {}, None
    view.blinds_connected = view.blinds_enabled = False
    view.blind_controller = None
    view.legacy_process = view.legacy_previous_pid = view.legacy_stopping_at = None
    view.legacy_killed = view.legacy_start_requested = False
    view.legacy_returning = False
    view.release_target = view.pending = view.queued_intent = view.intent_timer = None
    view.press_active = view.idle_active = False
    view.run_id, view.request_seq, view.sequence, view.view_generation = "test-owner", 0, 0, 0
    view.control_sequence = 0
    view.advanced_page = None
    view.confirmed_at = view.confirmed_power = view.confirmed_scene = None
    view.confirmed_light, view.light_message = "Not checked", "Lighting unavailable"
    view.cct = SimpleNamespace(get=lambda: 3500)
    view.intensity = SimpleNamespace(get=lambda: 1000)
    view.channel_values = [SimpleNamespace(get=lambda: 0) for unused in range(8)]
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
    view.args.classic_dir = str(tmp_path)
    view.args.classic_python = "classic-python"
    view.legacy_paths = lambda: (tmp_path / "original.pid", tmp_path / "original.log")
    view.start_legacy = lambda: True
    view.render = view.cancel_hold = view.update_navigation_buttons = lambda: None
    return view


def live_helper(view):
    view.worker_ready = True
    view.light_state = "ready"
    view.worker = SimpleNamespace(stdin=BytesIO(), stdout=SimpleNamespace(fileno=lambda: 99),
                                  poll=lambda: None, returncode=None)
    view.last_heartbeat = panel.monotonic()
    return view.worker


def test_public_connection_check_starts_read_only_acquire_with_no_setter(recoverable, monkeypatch):
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    recoverable.check_connection()
    assert starts == [{}]
    assert recoverable.pending is None
    assert recoverable.recovery.state["status"] == "normal"


def test_uncertain_connection_check_returns_control_on_stable_success(recoverable, monkeypatch):
    view = recoverable
    view.recovery.mark_uncertain("An earlier command was not confirmed.")
    starts = []
    monkeypatch.setattr(view, "start_worker", lambda **kw: starts.append(kw))
    view.check_connection()
    assert starts == [{"legacy_return": True}]
    live_helper(view)  # Fake the fresh helper's initialization.
    assert view.request("return_legacy")
    assert view.ownership_blocked()
    view.recovery_result(view.pending, {"state": "ready", "fixtures": 10})
    assert view.recovery.state["status"] == "normal"
    assert not view.ownership_blocked()


def test_uncertain_check_retires_acquired_helper_before_fresh_return(recoverable, monkeypatch):
    view = recoverable
    view.recovery.mark_uncertain("An earlier command was not confirmed.")
    worker = live_helper(view)
    starts = []
    monkeypatch.setattr(view, "start_worker", lambda **kw: starts.append(kw))
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    view.check_connection()
    assert view.pending["action"] == "release" and not starts
    view.worker_buffer = json.dumps({"version": 1, "request_id": view.pending["request_id"],
                                    "state": "released", "preserved": True}) + "\n"
    REAL_POLL_WORKER(view)
    assert not starts and view.worker is worker
    worker.poll = lambda: 0
    worker.returncode = 0
    REAL_POLL_WORKER(view)
    assert view.worker is None and starts == [{"legacy_return": True}]


def test_existing_helper_check_sends_only_read_request(recoverable):
    worker = live_helper(recoverable)
    recoverable.check_connection()
    requests = [json.loads(line) for line in worker.stdin.getvalue().splitlines()]
    assert [item["action"] for item in requests] == ["check"]
    assert recoverable.recovery.state["status"] == "normal"
    assert not recoverable.light_changes_requested


def test_failed_return_keeps_check_available_and_can_retry(recoverable, monkeypatch):
    recoverable.recovery.enter_legacy()
    monkeypatch.setattr(recoverable, "start_worker", lambda **kw: None)
    recoverable.check_connection()
    live_helper(recoverable)
    assert recoverable.request("return_legacy")
    request = recoverable.pending
    recoverable.pending = None
    recoverable.recovery_result(request, {"state": "failed"})
    recoverable.worker = None  # The failed helper has exited.
    state = recoverable.recovery_snapshot()
    assert state["status"] == "uncertain" and state["can_check"]
    assert state["write_blocked"] and not state["needs_staff"]
    assert LightingRecovery(recoverable.recovery.path).public()["can_check"]
    recoverable.check_connection()
    live_helper(recoverable)
    assert recoverable.request("return_legacy")
    recoverable.recovery_result(recoverable.pending, {"state": "ready", "fixtures": 10})
    assert not recoverable.ownership_blocked()


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


def test_legacy_can_reopen_after_failed_return(recoverable):
    recoverable.recovery.mark_uncertain("Previous lighting ownership is unresolved.")
    recoverable.show("original")
    assert recoverable.mode == "original"
    assert recoverable.recovery_snapshot()["write_blocked"]


@pytest.mark.parametrize("programme", ["Sun", "Circ"])
def test_programme_check_keeps_its_explanation_and_ownership(recoverable, monkeypatch, programme):
    messages = []
    monkeypatch.setattr(recoverable, "lighting_feedback", messages.append)
    before = dict(recoverable.recovery.state)
    detail = "Programme requested; readings may change. Stop for a stable check. Running status is unverified."
    recoverable.recovery_result(
        {"action": "check"},
        {"state": "checked", "programme": programme, "detail": detail},
    )
    assert messages[0].startswith(detail)
    assert recoverable.recovery.state == before


def test_public_legacy_action_opens_original_fallback(recoverable, monkeypatch):
    destinations = []
    monkeypatch.setattr(recoverable, "show", destinations.append)
    panel_remote.execute(recoverable, {"id": "browser-legacy-12345", "action": "legacy", "arguments": {}})
    assert destinations == ["original"]


def test_everyday_command_never_waits_for_or_depends_on_storage(recoverable, monkeypatch):
    worker = live_helper(recoverable)
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))

    def fail_replace(*unused):
        raise OSError("storage unavailable")

    monkeypatch.setattr(lighting_recovery.os, "replace", fail_replace)
    assert recoverable.request("channels", {"values": [0] * 8})
    assert [json.loads(line)["action"] for line in worker.stdin.getvalue().splitlines()] == ["channels"]
    recoverable.worker_buffer = json.dumps({"version": 1, "request_id": recoverable.pending["request_id"],
        "state": "completed", "fixtures": 10, "words": [0] * 8}) + "\n"
    REAL_POLL_WORKER(recoverable)
    assert not recoverable.recovery.error and not recoverable.ownership_blocked()
    assert not recoverable.recovery_snapshot()["needs_staff"]


@pytest.mark.parametrize("failure_at", ("write", "flush"))
def test_lost_helper_pipe_reconnects_without_staff(recoverable, failure_at):
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
    assert recoverable.recovery.state["status"] == "normal"
    assert not recoverable.recovery_snapshot()["needs_staff"]
    assert recoverable.reconnect_after_exit
    assert recoverable.worker is worker  # Do not launch a replacement while it might still run.


@pytest.mark.parametrize("state", ("helper_died", "failed_result"))
def test_unconfirmed_command_restarts_helper_for_a_fresh_read(recoverable, monkeypatch, state):
    worker = live_helper(recoverable)
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    assert recoverable.request("channels", {"values": [0] * 8})
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    if state == "failed_result":
        recoverable.worker_buffer = json.dumps({"version": 1, "request_id": recoverable.pending["request_id"],
            "state": "failed", "detail": "Lighting service deadline expired; outcome may be unknown",
            "outcome_unknown": True, "stable": False}) + "\n"
        REAL_POLL_WORKER(recoverable)
        assert starts == [] and recoverable.reconnect_after_exit
    worker.returncode = 1
    worker.poll = lambda: 1
    REAL_POLL_WORKER(recoverable)
    assert recoverable.worker is None and recoverable.pending is None
    assert recoverable.recovery.state["status"] == "normal"
    assert not recoverable.recovery_snapshot()["needs_staff"]
    assert starts == [{}] and not recoverable.reconnect_after_exit
    assert [json.loads(line)["action"] for line in worker.stdin.getvalue().splitlines()] == ["channels"]
    assert any(args[0] == 100 for args in recoverable.scheduled)


def test_helper_exit_without_a_lost_command_does_not_restart_in_a_loop(recoverable, monkeypatch):
    worker = live_helper(recoverable)
    starts = []
    monkeypatch.setattr(recoverable, "start_worker", lambda **kwargs: starts.append(kwargs))
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    worker.returncode = 1
    worker.poll = lambda: 1
    REAL_POLL_WORKER(recoverable)
    assert starts == [] and recoverable.worker is None


class LegacyChild:
    pid = 43210

    def __init__(self):
        self.returncode = None
        self.reaped = False

    def poll(self):
        return self.returncode

    def wait(self):
        assert self.returncode is not None
        self.reaped = True
        return self.returncode


@pytest.mark.parametrize("preserved,exit_code", [(True, 0), (False, 0), (True, 1)])
def test_legacy_waits_for_preserving_release_and_successful_helper_exit(recoverable, monkeypatch, preserved, exit_code):
    view = recoverable
    worker, starts = live_helper(view), []
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    monkeypatch.setattr(view, "start_legacy", lambda: starts.append("child") or True)
    view.show("original")
    assert view.pending["action"] == "release" and not starts
    view.worker_buffer = json.dumps({"version": 1, "request_id": view.pending["request_id"],
                                    "state": "released", "preserved": preserved}) + "\n"
    REAL_POLL_WORKER(view)
    assert not starts and view.worker is worker
    worker.poll = lambda: exit_code
    worker.returncode = exit_code
    REAL_POLL_WORKER(view)
    assert starts == (["child"] if preserved and exit_code == 0 else [])


def test_open_starts_exactly_one_child_after_checkpoint(recoverable, monkeypatch):
    view = recoverable
    child, calls = LegacyChild(), []
    view.start_legacy = panel.Panel.start_legacy.__get__(view)

    def popen(argv, **kwargs):
        assert json.loads(Path(view.recovery.path).read_text())["status"] == "legacy"
        assert view.worker is None
        calls.append((argv, kwargs))
        kwargs["stdout"].write(b"new log output\n")
        return child

    monkeypatch.setattr(panel.subprocess, "Popen", popen)
    view.legacy_paths()[1].write_bytes(b"old log\n")
    view.show("original")
    view.show("original")
    assert view.mode == "original" and len(calls) == 1
    argv, options = calls[0]
    assert argv == ["classic-python", "-u", "-B", str(Path(panel.__file__).with_name("run_original.py")),
                    "--classic-dir", view.args.classic_dir]
    assert options["cwd"] == view.args.classic_dir
    assert options["start_new_session"] and options["stderr"] == panel.subprocess.STDOUT
    assert view.legacy_paths()[1].read_bytes() == b"old log\nnew log output\n"
    assert view.legacy_paths()[0].read_text().strip() == str(child.pid)


@pytest.mark.parametrize("self_exit,force", [(False, False), (False, True), (True, False)])
def test_home_and_self_exit_stop_group_and_reap_before_helper(recoverable, monkeypatch, self_exit, force):
    view = recoverable
    child, events = LegacyChild(), []
    view.legacy_process = child
    view.mode = "original"
    view.recovery.enter_legacy()
    # Windows also exercises the POSIX contract using fakes.
    monkeypatch.setattr(panel_recovery.os, "killpg", lambda pid, sig: events.append((pid, sig)), raising=False)
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(view, "start_worker", lambda **kw: events.append(("helper", child.reaped, kw)))
    if self_exit:
        child.returncode = 1
    else:
        view.show("room")
    view.poll_legacy()
    assert events[0] == (child.pid, signal.SIGTERM)
    if not self_exit:
        assert not any(event[0] == "helper" for event in events)
        if force:
            view.legacy_stopping_at -= 4
            view.poll_legacy()
            assert events[-1] == (child.pid, signal.SIGKILL)
            assert not child.reaped
        child.returncode = -9 if force else 0
        view.poll_legacy()
    assert events[-1] == ("helper", True, {"legacy_return": True})
    assert view.mode == "room" and view.legacy_process is None
    assert not view.legacy_paths()[0].exists()


@pytest.mark.parametrize("alive,status", [(True, "legacy"), (False, "legacy"),
                                         (True, "uncertain"), (True, "normal")])
def test_startup_stops_previous_process_before_return(recoverable, monkeypatch, alive, status):
    view = recoverable
    view.recovery.enter_legacy()
    view.recovery.state["status"] = status
    events = []
    pid = 43210 if alive else None
    monkeypatch.setattr(view, "previous_legacy_pid", lambda: pid)
    monkeypatch.setattr(panel_recovery.os, "killpg", lambda pid, sig: events.append((pid, sig)), raising=False)
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(view, "start_worker", lambda **kw: events.append(("helper", kw)))
    view.startup_lighting()
    view.poll_legacy()
    if alive:
        assert events == [(43210, signal.SIGTERM)]
        pid = None
        view.poll_legacy()
    assert events[-1] == ("helper", {"legacy_return": True})
    assert view.mode == "room"


def test_upgrade_can_stop_validated_old_boot_process_without_own_group(recoverable, monkeypatch):
    view = recoverable
    view.legacy_previous_pid = 43210
    events = []
    monkeypatch.setattr(view, "previous_legacy_pid", lambda: 43210)

    def no_group(*args):
        raise ProcessLookupError()

    monkeypatch.setattr(panel_recovery.os, "killpg", no_group, raising=False)
    monkeypatch.setattr(panel_recovery.os, "kill", lambda pid, sig: events.append((pid, sig)))
    view.stop_legacy()
    assert events == [(43210, signal.SIGTERM)]


def test_previous_pid_requires_wrapper_and_exact_classic_directory(recoverable, monkeypatch):
    view = recoverable
    view.legacy_paths()[0].write_text("43210")
    original = Path.read_bytes
    args = ["python2.7", "/panel/app/run_original.py", "--classic-dir", view.args.classic_dir]
    monkeypatch.setattr(Path, "read_bytes", lambda path: b"\0".join(os.fsencode(arg) for arg in args)
                        if str(path).replace("\\", "/") == "/proc/43210/cmdline" else original(path))
    assert view.previous_legacy_pid() == 43210
    args[-1] += "-other"
    assert view.previous_legacy_pid() is None
    args[-1] = view.args.classic_dir
    args[1] = "/other/main.py"
    assert view.previous_legacy_pid() is None


def test_helper_never_acquires_while_legacy_alive(recoverable):
    recoverable.legacy_process = LegacyChild()
    recoverable.start_worker()
    recoverable.start_worker(legacy_return=True)
    assert recoverable.worker is None


def test_return_mode_survives_actual_helper_initialization_until_matching_response(recoverable, monkeypatch, tmp_path):
    recoverable.recovery.enter_legacy()
    recoverable.args.journal = str(tmp_path / "events.jsonl")
    recoverable.args.expected_master = "http://example.invalid:11311"
    worker = SimpleNamespace(stdin=BytesIO(), stdout=SimpleNamespace(fileno=lambda: 99),
                             poll=lambda: None, returncode=None)
    monkeypatch.setattr(panel.subprocess, "Popen", lambda *args, **kwargs: worker)
    monkeypatch.setattr(panel.select, "select", lambda *unused: ([], [], []))
    recoverable.last_heartbeat = panel.monotonic()
    recoverable.start_worker(legacy_return=True)
    assert recoverable.legacy_returning
    recoverable.worker_buffer = '{"version":1,"state":"initialized"}\n'
    REAL_POLL_WORKER(recoverable)
    assert recoverable.legacy_returning
    assert recoverable.pending["action"] == "return_legacy"
    assert recoverable.recovery.state["status"] == "uncertain"
    recoverable.worker_buffer = json.dumps({"version": 1, "request_id": recoverable.pending["request_id"],
        "state": "ready", "fixtures": 10, "manual_blocked": False}) + "\n"
    REAL_POLL_WORKER(recoverable)
    assert not recoverable.legacy_returning
    assert recoverable.pending is None
    assert recoverable.recovery.state["status"] == "normal"
    assert [json.loads(line)["action"] for line in worker.stdin.getvalue().splitlines()] == ["return_legacy"]


def test_storage_error_still_blocks_new_commands(recoverable):
    worker = live_helper(recoverable)
    recoverable.recovery.error = "Lighting recovery state could not be read"
    assert not recoverable.request("channels", {"values": [0] * 8})
    assert worker.stdin.getvalue() == b"" and recoverable.ownership_blocked()


@pytest.mark.parametrize("timed_out", (False, True))
def test_legacy_input_waits_for_background_handoff_save(recoverable, monkeypatch, tmp_path, timed_out):
    guard = recoverable.recovery = LightingRecovery(tmp_path / "background.json", background=True)
    entered, release = threading.Event(), threading.Event()
    persist = guard._persist

    def stalled(value):
        entered.set()
        assert release.wait(3)
        persist(value)

    monkeypatch.setattr(guard, "_persist", stalled)
    rendered = []
    monkeypatch.setattr(recoverable, "render", lambda: rendered.append(recoverable.mode))
    monkeypatch.setattr(recoverable, "cancel_hold", lambda: None)
    monkeypatch.setattr(recoverable, "update_navigation_buttons", lambda: None)
    try:
        recoverable.show("original")
        assert entered.wait(1)
        assert recoverable.mode == "room" and not rendered
        assert recoverable.release_target == "legacy_save"
        if timed_out:
            recoverable.legacy_save_started -= 11
            REAL_POLL_WORKER(recoverable)
            assert recoverable.release_target is None and not rendered
    finally:
        release.set()
    assert guard.settled.wait(2)
    REAL_POLL_WORKER(recoverable)
    if timed_out:
        recoverable.show("original")
        assert guard.settled.wait(2)
        REAL_POLL_WORKER(recoverable)
        assert rendered == ["original"] and recoverable.mode == "original"
    else:
        assert rendered == ["original"] and recoverable.mode == "original"


@pytest.mark.skipif(os.name != "posix", reason="Linux helper pipe")
def test_full_helper_pipe_fails_closed_without_blocking(recoverable):
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    with os.fdopen(write_fd, "wb", buffering=0) as pipe:
        try:
            while True:
                os.write(write_fd, b"x" * 4096)
        except BlockingIOError:
            pass
        try:
            worker = live_helper(recoverable)
            worker.stdin = pipe
            assert not recoverable.request("channels", {"values": [0] * 8})
            assert recoverable.pending is None
            assert recoverable.recovery_snapshot()["needs_staff"]
            assert LightingRecovery(recoverable.recovery.path).public()["write_blocked"]
        finally:
            os.close(read_fd)
