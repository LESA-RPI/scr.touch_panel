"""Real Tk press/release paths never contact room equipment."""

import pytest

from test_panel_navigation import panel, shared_worker, view
from panel_guides import DEMO


def widgets(parent):
    yield parent
    for child in parent.winfo_children():
        yield from widgets(child)


def button_named(view, text):
    button, = [widget for widget in widgets(view.root)
               if isinstance(widget, panel.tk.Button) and widget.winfo_ismapped()
               and widget.cget("text") == text]
    return button


def touch(view, button):
    button.event_generate("<Enter>", x=10, y=10)
    button.event_generate("<ButtonPress-1>", x=10, y=10)
    view.root.update()
    assert view.press_active
    button.event_generate("<ButtonRelease-1>", x=10, y=10)
    view.root.update()
    assert not view.press_active


@pytest.mark.parametrize("destination", [
    "topic", "next", "previous", "back", "preference", "header-home",
    "footer-tools", "footer-guide", "legacy", "dock-home",
])
def test_rebuilt_buttons_finish_the_real_touch_release(view, destination):
    if destination == "preference":
        view.open_advanced("clock")
        text = "12-hour"
    elif destination == "topic":
        view.choose_guide(-1)
        text = DEMO[0]["title"] + "  ›\n" + DEMO[0]["caption"]
    elif destination == "dock-home":
        view.show("original")
        text = "Home"
    else:
        view.choose_guide(1 if destination == "previous" else 0)
        text = {"next": "Next", "previous": "Previous", "back": "Back to topics",
                "header-home": "Home", "footer-tools": "Room tools",
                "footer-guide": "Demo & guide", "legacy": "Legacy"}[destination]
    view.root.update()
    touch(view, button_named(view, text))
    assert view.dock.winfo_ismapped() if destination == "legacy" else view.body.winfo_ismapped()


def test_screensaver_remains_wakeable_when_a_handoff_blocks_home(view):
    view.show("visitor")
    view.root.update()
    view.release_target = "original"
    touch(view, button_named(view, "Touch anywhere to open controls"))
    assert view.idle_active and view.mode == "visitor"
    view.release_target = None
    touch(view, button_named(view, "Touch anywhere to open controls"))
    assert not view.idle_active and view.mode == "room"


@pytest.mark.parametrize("outcome", ["ready", "failed"])
def test_delayed_connection_check_stays_visible_and_navigation_responds(view, outcome):
    shared_worker(view)
    view.open_advanced("system")
    view.root.update()
    requests = []

    def delayed(action):
        requests.append(action)
        view.pending = {"action": action, "request_id": "test-check"}
        return True

    view.request = delayed
    button = view.recovery_button
    position = (button.winfo_rootx(), button.winfo_rooty(), button.winfo_height())
    touch(view, button)
    assert requests == ["check"]
    assert button.winfo_ismapped() and button.cget("state") == "disabled"
    assert "Checking" in button.cget("text")
    assert position == (button.winfo_rootx(), button.winfo_rooty(), button.winfo_height())
    assert "Checking" in view.recovery_label.cget("text")
    assert view.connection_text.get() == "Checking"
    touch(view, view.home_button)
    assert view.mode == "room" and view.body.winfo_ismapped()
    if outcome == "failed":
        view.fail_worker("The helper disconnected during the read")
    else:
        view.pending = None
        view.lighting_feedback("Current light settings checked. No lighting command was sent.")
        view.update_recovery_view()
    view.root.update()
    touch(view, view.guide_footer_button)
    assert view.mode == "guide" and requests == ["check"]
    view.worker = None


def test_real_check_then_sun_request_keeps_navigation_responsive(view):
    shared_worker(view)
    view.open_advanced("system")
    view.root.update()
    requests = []

    def delayed(action, arguments=None):
        requests.append((action, arguments))
        view.pending = {"action": action, "arguments": arguments or {}, "request_id": "test"}
        return True

    view.request = delayed
    touch(view, view.recovery_button)
    assert requests == [("check", None)]
    view.pending = None  # The delayed fake helper has completed its read.
    view.lighting_feedback("Current light settings checked. No lighting command was sent.")
    view.update_light_buttons()
    touch(view, button_named(view, "Lighting"))
    touch(view, button_named(view, "Programmes"))
    touch(view, button_named(view, "Start Sun"))
    assert requests == [("check", None), ("programme", {"name": "Sun"})]
    assert view.pending["action"] == "programme"
    touch(view, view.home_button)
    touch(view, view.guide_footer_button)
    assert view.mode == "guide" and len(requests) == 2
    view.worker = None


def test_pending_check_clears_uncertain_handoff_only_after_bounded_success(view):
    shared_worker(view)
    view.worker = None
    view.recovery.mark_uncertain("Legacy handoff did not confirm a preserved release.")
    view.light_state = "failed"
    view.open_advanced("system")
    view.root.update()
    requests = []

    def delayed(action):
        requests.append(action)
        view.pending = {"action": action, "request_id": "test-check"}
        return True

    def start(**kwargs):
        assert kwargs == {"legacy_return": True}
        view.legacy_returning = True
        view.recovery.begin_write("test-check", returning=True)
        delayed("return_legacy")

    view.start_worker = start
    touch(view, view.recovery_button)
    assert view.recovery_snapshot()["status"] == "returning"
    assert view.recovery_snapshot()["write_blocked"]
    assert view.recovery.state["status"] == "uncertain" and view.ownership_blocked()
    view.pending = None
    view.recovery_result({"action": "return_legacy", "request_id": "test-check"},
                         {"state": "ready", "fixtures": 10})
    view.light_state = "ready"
    view.update_light_buttons()
    view.root.update()
    assert view.connection_text.get() == "Ready"
    assert view.recovery.state["status"] == "normal" and not view.ownership_blocked()
    assert requests == ["return_legacy"]
    view.worker = None


def test_real_check_reports_helper_start_failure_without_sticking_checking(view, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("Isolated helper launch failure")

    view.args.live_lights = True
    view.args.journal, view.args.expected_master = "unused-test-receipt", "unused-test-master"
    view.light_state = "disconnected"
    view.open_advanced("system")
    view.root.update()
    monkeypatch.setattr(panel.subprocess, "Popen", unavailable)
    touch(view, view.recovery_button)
    assert view.worker is None and view.light_state == "failed"
    assert "unavailable" in view.light_message.lower()
    assert view.recovery_button.cget("text") == "Check connection"
    touch(view, view.home_button)
    assert view.mode == "room" and view.body.winfo_ismapped()


def test_real_check_shows_checking_during_slow_helper_startup(view):
    worker = shared_worker(view)
    view.worker, view.worker_ready, view.light_state = None, False, "disconnected"

    def slow_launcher():
        view.worker = worker
        view.light_state = "connecting"

    view.start_worker = slow_launcher
    view.open_advanced("system")
    view.root.update()
    button = view.recovery_button
    touch(view, button)
    assert view.pending is None and not view.worker_ready
    assert button.winfo_ismapped() and button.cget("state") == "disabled"
    assert button.cget("text") == "Checking…"
    assert "Checking" in view.recovery_label.cget("text")
    assert view.connection_text.get() == "Checking"
    touch(view, view.home_button)
    assert view.mode == "room" and view.body.winfo_ismapped()
    assert not worker.stdin.getvalue()
    view.worker = None
