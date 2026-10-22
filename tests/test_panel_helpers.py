"""Optional status failures must not interrupt the shared UI polling loop."""

from io import BytesIO, StringIO
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel
from test_scr_touch_panel import journal_panel


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
def test_persistent_close_shortcuts_use_shared_view_without_releasing_owner(reason):
    from scr_touch_panel import Panel
    view = Panel.__new__(Panel)
    view.closed = False
    view.closing = None
    view.keep_switcher = True
    calls = []
    view.show = calls.append
    view.close(reason)
    assert calls == ["classic"] and view.closing is None
