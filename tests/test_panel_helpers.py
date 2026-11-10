"""Optional status failures must not interrupt the shared UI polling loop."""

from io import BytesIO, StringIO
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel
from test_scr_touch_panel import journal_panel


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
    assert power["text"] == "Power supply: Current power warning"
    state.health_cache = {"error": "Reading failed"}
    state.update_health()
    assert power == {"text": "Power reading unavailable.", "fg": "muted"}
    state.health_cache = dict(healthy, power="No current power warning")
    state.update_health()
    assert power == {"text": "Power supply: No current power warning", "fg": "muted"}


@pytest.mark.parametrize("same_page", [False, True])
def test_contextual_lighting_help_resets_only_its_view_state(same_page):
    state = panel.Panel.__new__(panel.Panel)
    state.release_target = state.closing = state.legacy_stopping_at = None
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


@pytest.mark.parametrize("field", ["release_target", "closing", "legacy_stopping_at", "power_busy"])
def test_contextual_lighting_help_preserves_busy_navigation_guards(field):
    state = panel.Panel.__new__(panel.Panel)
    state.release_target = state.closing = state.legacy_stopping_at = None
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
