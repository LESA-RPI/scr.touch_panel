"""Optional status failures must not interrupt the shared UI polling loop."""

from io import BytesIO, StringIO
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel
from test_scr_touch_panel import journal_panel


def instruction_state():
    def control(text=""):
        values, changes = {"text": text, "state": "normal"}, []
        def configure(**updated):
            values.update(updated)
            changes.append(updated)
        return SimpleNamespace(cget=values.__getitem__, config=configure, changes=changes)
    state = panel.Panel.__new__(panel.Panel)
    state.mode, state.running, state.elapsed, state.run_started = "experiment", False, 0.0, None
    state.profile, state.stage = {"stages": ["First", "Middle", "Last"]}, 0
    state.pending = state.release_target = state.closing = state.power = None
    state.stage_label, state.timer_label, state.run_label = control(), control(), control()
    state.session_buttons = [control(text) for text in (
        "Start instructions", "Pause", "Previous instruction", "Next instruction"
    )]
    state.annotation_text = SimpleNamespace(set=lambda value: None)
    state.emit = lambda *args, **kwargs: None
    return state


@pytest.mark.parametrize("running,elapsed,stage,start,pause,previous,next_text", [
    (False, 0, 0, "Start instructions", "disabled", "disabled", "Next instruction"),
    (True, 0, 1, "Start instructions", "normal", "normal", "Next instruction"),
    (False, 12, 1, "Resume instructions", "disabled", "normal", "Next instruction"),
    (False, 12, 2, "Resume instructions", "disabled", "normal", "Finish instructions"),
])
def test_instruction_controls_describe_the_current_actions(monkeypatch, running, elapsed, stage, start, pause, previous, next_text):
    state = instruction_state()
    state.running, state.elapsed, state.stage = running, elapsed, stage
    state.run_started = 90 if running or elapsed > 0 else None
    monkeypatch.setattr(panel, "monotonic", lambda: 100)
    state.update_session()
    assert state.session_buttons[0].cget("text") == start
    assert state.session_buttons[0].cget("state") == ("disabled" if running else "normal")
    assert state.session_buttons[1].cget("state") == pause
    assert state.session_buttons[2].cget("state") == previous
    assert state.session_buttons[3].cget("text") == next_text


def test_unchanged_instruction_refresh_preserves_a_held_action():
    state = instruction_state()
    state.update_session()
    controls = [state.stage_label, state.timer_label, state.run_label, *state.session_buttons]
    for control in controls:
        control.changes.clear()
    state.press_active = True
    state.can_load_profile = lambda: pytest.fail("A held instruction button is not profile admission")
    state.update_session()
    assert all(not control.changes for control in controls)
    assert state.session_buttons[0].cget("state") == "normal"


@pytest.mark.parametrize("busy", ["pending", "release_target", "closing", "power"])
def test_instruction_controls_respect_existing_pending_and_power_work(busy):
    state = instruction_state()
    setattr(state, busy, SimpleNamespace(busy=True) if busy == "power" else True)
    state.update_session()
    assert all(button.cget("state") == "disabled" for button in state.session_buttons)


def test_finishing_the_final_instruction_pauses_without_a_new_completion_state(monkeypatch):
    state = instruction_state()
    state.running, state.stage, state.run_started = True, 2, 90
    monkeypatch.setattr(panel, "monotonic", lambda: 100)
    state.next_stage()
    assert not state.running and state.stage == 2 and state.elapsed == 10
    assert state.session_buttons[0].cget("text") == "Resume instructions"
    assert state.session_buttons[3].cget("text") == "Finish instructions"


def test_fast_pause_resumes_and_loading_a_profile_resets_instruction_labels(monkeypatch):
    state = instruction_state()
    clock = [100.0]
    monkeypatch.setattr(panel, "monotonic", lambda: clock[0])
    state.cancel_intent = lambda: None
    state.start_preview()
    clock[0] += 0.2
    state.stop_preview()
    assert 0 < state.elapsed < 1
    assert state.session_buttons[0].cget("text") == "Resume instructions"
    state.check_profile_fit = lambda value: None
    state.can_load_profile = lambda: True
    state.status_text = SimpleNamespace(set=lambda value: None)
    state.render = lambda: None
    state.load_profile({"title": "New instructions"})
    state.update_session()
    assert state.run_started is None and state.elapsed == 0 and state.stage == 0
    assert state.session_buttons[0].cget("text") == "Start instructions"


@pytest.mark.parametrize("resources", [{}, {"error": "Resource query unavailable"}])
def test_room_service_status_refreshes_independently_of_panel_resource_errors(resources):
    state = panel.Panel.__new__(panel.Panel)
    state.mode, state.theme, state.health_rendered = "health", "light", None
    state.health_cache, state.room_status = resources, "Checking advertised services"
    state.refresh_resources = lambda: None
    services = []
    state.services_label = SimpleNamespace(config=lambda **value: services.append(value["text"]))
    state.health_details = SimpleNamespace(config=lambda **value: None)
    state.power_label, state.muted = SimpleNamespace(config=lambda **value: None), "muted"
    state.update_health()
    state.room_status = "Lighting service: missing"
    state.update_health()
    state.update_health()
    assert services == ["Checking advertised services", "Lighting service: missing"]


def test_resource_failure_removes_current_power_claim_until_a_new_reading():
    state = panel.Panel.__new__(panel.Panel)
    state.mode, state.theme, state.health_rendered, state.muted = "health", "light", None, "muted"
    state.room_status, state.refresh_resources = "Services checked", lambda: None
    state.services_label = state.health_details = SimpleNamespace(config=lambda **value: None)
    power = {}
    state.power_label = SimpleNamespace(config=lambda **value: power.update(value))
    healthy = {"ram_available": 100, "ram_total": 1000, "disk_available": 2,
               "temperature": 45, "power": "Current power warning"}
    state.health_cache = healthy
    state.update_health()
    assert power["text"] == "Power: Current power warning"
    state.health_cache = {"error": "Reading failed"}
    state.update_health()
    assert power == {"text": "Power reading unavailable.", "fg": "muted"}
    state.health_cache = dict(healthy, power="No current power warning")
    state.update_health()
    assert power == {"text": "Power: No current power warning", "fg": "muted"}


@pytest.mark.parametrize("same_page", [False, True])
def test_contextual_lighting_help_resets_only_its_view_state(same_page):
    state = panel.Panel.__new__(panel.Panel)
    state.release_target = state.closing = state.legacy_probe = None
    state.power_busy = lambda: False
    state.mode, state.advanced_page = ("health", "system") if same_page else ("room", None)
    state.system_diagnostics_visible = state.support_commands_visible = True
    state.support_page, state.support_step = 3, 2
    calls = []
    state.open_advanced = lambda page: calls.append(("open", page))
    state.rebuild_advanced_detail = lambda: calls.append(("refresh", "system"))
    state.open_lighting_help()
    assert (state.support_page, state.support_step) == (0, 0)
    assert not state.system_diagnostics_visible and not state.support_commands_visible
    assert calls == [("refresh" if same_page else "open", "system")]


@pytest.mark.parametrize("field", ["release_target", "closing", "legacy_probe", "power_busy"])
def test_contextual_lighting_help_preserves_busy_navigation_guards(field):
    state = panel.Panel.__new__(panel.Panel)
    state.release_target = state.closing = state.legacy_probe = None
    state.power_busy = lambda: False
    state.support_page, state.support_step = 3, 2
    state.system_diagnostics_visible = state.support_commands_visible = True
    setattr(state, field, (lambda: True) if field == "power_busy" else True)
    state.open_lighting_help()
    assert (state.support_page, state.support_step) == (3, 2)
    assert state.system_diagnostics_visible and state.support_commands_visible


def test_status_helper_launch_failure_is_reported_without_raising(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.args = SimpleNamespace(expected_master="http://approved-room-master")
    monkeypatch.setattr(panel.sys, "platform", "linux")

    def failed(*args, **kwargs):
        raise OSError("Cannot start process")

    monkeypatch.setattr(panel.subprocess, "Popen", failed)
    state.start_status()
    assert state.status_worker is None
    assert "could not be checked" in state.room_status


@pytest.mark.parametrize("reply", [
    b"[]", b"null", b'{"services":null}', b'{"services":[1]}',
    b'{"services":[["Lighting","yes"]]}', b"\xff", b"x" * 4097,
])
def test_bad_optional_status_reply_closes_pipes_without_crashing(reply):
    state = panel.Panel.__new__(panel.Panel)
    state.status_started = panel.monotonic()
    output, errors = BytesIO(reply), BytesIO()
    state.status_worker = SimpleNamespace(
        poll=lambda: 0, stdout=output, stderr=errors,
    )
    state.poll_status()
    assert state.status_worker is None and output.closed and errors.closed
    assert "could not be checked" in state.room_status


def test_power_checkpoint_cannot_claim_acceptance_after_journal_failure():
    def failed(*args, **kwargs):
        raise OSError("Journal is unavailable")

    state = journal_panel(SimpleNamespace(append=failed), "unused")
    with pytest.raises(OSError, match="unavailable"):
        state.emit("power_requested", operation="reboot")
    # Ordinary UI events can report the fault without crashing navigation.
    state.emit("mode_changed", target="room")
    assert "unavailable" in state.status_text.value


@pytest.mark.parametrize("diagnostic", ["closed", "missing", "failed"])
def test_broken_diagnostics_cannot_interrupt_completed_shutdown(monkeypatch, diagnostic):
    class FailedOutput:
        def write(self, text):
            raise OSError("Diagnostic output failed")

    output = StringIO()
    output.close()
    monkeypatch.setattr(sys, "stderr", {
        "closed": output, "missing": None, "failed": FailedOutput(),
    }[diagnostic])
    state = panel.Panel.__new__(panel.Panel)
    state.closed, state.worker = False, None
    state.preferences = SimpleNamespace(
        close=lambda: None, done=SimpleNamespace(is_set=lambda: True),
        error="Settings write failed",
    )
    state.journal = SimpleNamespace(
        closing=True, done=SimpleNamespace(is_set=lambda: True),
        error="Journal write failed",
    )
    destroyed = []
    state.root = SimpleNamespace(destroy=lambda: destroyed.append(True))
    state.poll_journal = lambda: None
    state.finish_close()
    assert state.closed and destroyed == [True]


def test_starting_instructions_waits_for_inflight_lighting():
    state = panel.Panel.__new__(panel.Panel)
    state.pending, state.running = {"request_id": "inflight"}, False
    messages = []
    state.status_text = SimpleNamespace(set=messages.append)
    state.start_preview()
    assert not state.running and "lighting confirmation" in messages[-1]


def test_queued_light_selection_cannot_dispatch_after_instructions_start():
    state = panel.Panel.__new__(panel.Panel)
    state.pending = state.release_target = state.closing = None
    state.mode, state.light_state, state.running = "settings", "ready", True
    state.view_generation = 1
    state.queued_intent = ("cct", {"cct": 3500, "intensity": 1000}, 1)
    state.request = lambda *args: pytest.fail("Instructions must block queued setters")
    state.dispatch_intent()
    assert state.queued_intent is None


@pytest.mark.parametrize("reason", ["exit", "timeout", "escape", "window_close"])
def test_persistent_close_shortcuts_use_the_guarded_original_legacy_path(reason):
    from scr_touch_panel import Panel
    view = Panel.__new__(Panel)
    view.closed = False
    view.closing = None
    view.keep_switcher = True
    calls = []
    view.show = calls.append
    view.close(reason)
    assert calls == ["original"] and view.closing is None
