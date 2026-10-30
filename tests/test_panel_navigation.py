"""Exercise real Tk navigation with every external process and device call blocked."""

import argparse
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel

REAL_POLL_WORKER = panel.Panel.poll_worker


@pytest.fixture
def view(monkeypatch):
    original = panel.tk.Tk

    def invisible_root():
        try:
            root = original()
        except panel.tk.TclError:
            pytest.skip("Tk display unavailable; run with a display or xvfb-run")
        root.withdraw()
        root.attributes("-alpha", 0)
        root.tk.call("tk", "scaling", 96 / 72)
        return root

    def blocked(*args, **kwargs):
        raise AssertionError("Navigation must never launch a device or subprocess")

    monkeypatch.setattr(panel.tk, "Tk", invisible_root)
    monkeypatch.setattr(panel.subprocess, "Popen", blocked)
    monkeypatch.setattr(panel.Panel, "start_weather", lambda self: None)
    monkeypatch.setattr(panel.Panel, "refresh_resources", lambda self: None)
    monkeypatch.setattr(panel.Panel, "poll_worker", lambda self: None)
    monkeypatch.setattr(sys, "stdout", StringIO())
    args = argparse.Namespace(
        profile=None,
        preferences=None,
        journal=None,
        duration=0,
        keep_switcher=True,
        start_mode="room",
        theme="light",
        light_at=420,
        dark_at=1140,
        windowed=True,
        logo=None,
        live_lights=False,
        tips="on",
        clock_format="24",
        weather_latitude=None,
        weather_longitude=None,
        temperature_unit="f",
        idle_timeout=300,
    )
    instance = panel.Panel(args)
    # Legacy's strip is a separate window, also kept invisible during these checks.
    instance.dock.attributes("-alpha", 0)
    instance.root.update()
    errors = []
    instance.root.report_callback_exception = lambda kind, value, tb: errors.append(value)
    yield instance
    instance.journal.close()
    instance.root.destroy()
    assert instance.journal.done.wait(2)
    assert not errors


def test_blind_permissions_appear_when_helper_connects_on_open_settings(view):
    view.open_advanced("screen")
    view.root.update()
    def choices():
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        return [widget for widget in walk(view.body)
                if isinstance(widget, panel.tk.Button) and widget.winfo_ismapped()
                and widget.cget("text") in ("Locked", "Unlocked")]
    assert not choices()
    view.worker_ready = True
    view.worker = SimpleNamespace(poll=lambda: None)
    view.adapter_metadata({"blinds_connected": True, "capabilities": {"gradient": True}})
    view.root.update()
    assert len(choices()) == 2 and not view.blinds_enabled
    view.adapter_metadata({"blinds_connected": False})
    view.root.update()
    assert not choices()
    view.worker = None


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_home_and_tools_survive_legacy_idle_and_blank_display(view, theme):
    view.choose_theme(theme)
    view.root.update()
    home = view.body
    header = view.banner
    for unused in range(5):
        view.show("original")
        view.root.update()
        assert view.root.state() == "withdrawn"
        assert view.dock.winfo_height() == 144
        view.open_home()
        view.root.update()
        assert view.body is home  # Returning from Legacy must not reload Home.
        assert view.body.winfo_ismapped()
        assert view.banner is header and view.banner.winfo_y() == 8
        assert view.banner.winfo_y() + view.banner.winfo_height() < view.body.winfo_y()
        view.open_advanced("lighting")
        view.root.update()
        tools, detail = view.body, view.advanced_detail
        view.show("black")
        view.root.update()
        assert not tools.winfo_ismapped()
        view.return_from_blank()
        view.root.update()
        assert view.body is tools and tools.winfo_ismapped()
        assert view.advanced_detail is detail and detail.winfo_ismapped()
        view.show("visitor")
        view.root.update()
        view.return_from_idle()
        view.root.update()
        assert view.body is home and home.winfo_ismapped()
        assert view.tools_footer_button.winfo_ismapped()


def test_pending_legacy_handoff_is_visible_and_cannot_dispatch_more_commands(view):
    view.light_state = "ready"
    requests = []
    view.worker = SimpleNamespace(stdin=StringIO())
    view.request = lambda action: requests.append(action)
    view.show("original")
    view.root.update()
    assert view.mode == "room" and view.release_target == "original"
    assert requests == ["release"]
    assert view.legacy_button.cget("text") == "Opening"
    assert all(button.cget("state") == "disabled" for button in view.navigation_buttons)
    feedback = view.status_text.get()
    for button in view.navigation_buttons:
        button.invoke()
        button.event_generate("<ButtonPress-1>")
        button.event_generate("<ButtonRelease-1>")
    view.root.update()
    assert requests == ["release"] and view.mode == "room"
    assert view.status_text.get() == feedback
    # Simulate confirmed cleanup and child exit; no actual helper exists.
    view.worker = view.release_target = None
    view.show("original")
    view.open_home()
    view.root.update()
    assert view.body.winfo_ismapped()
    assert view.legacy_button.cget("text") == "Legacy"
    assert all(button.cget("state") == "normal" for button in view.navigation_buttons)


def test_header_and_footer_commands_open_their_labeled_pages(view):
    view.connection_badges[0][0].invoke()
    view.root.update()
    assert view.advanced_page == "system" and view.body.winfo_ismapped()
    view.home_button.invoke()
    view.root.update()
    assert view.mode == "room" and view.advanced_page is None
    view.guide_footer_button.invoke()
    view.root.update()
    assert view.mode == "guide" and view.guide_page == -1
    view.tools_footer_button.invoke()
    view.root.update()
    assert view.advanced_page == "system" and view.body.winfo_ismapped()
    view.legacy_button.invoke()
    view.root.update()
    assert view.mode == "original" and not view.body.winfo_ismapped()
    assert view.dock.winfo_ismapped()
    view.home_button.invoke()
    view.root.update()
    assert view.mode == "room" and view.body.winfo_ismapped()


def test_home_explains_why_running_instructions_disable_lighting(view):
    view.open_advanced("experiment")
    view.start_preview()
    view.open_home()
    view.root.update()
    assert "Pause Experiment mode" in view.status_text.get()
    assert all(button.cget("state") == "disabled" for button in view.light_buttons)


def test_unchanged_controls_and_recovery_do_not_schedule_geometry_work(view, monkeypatch):
    view.open_advanced("system")
    view.root.update()
    view.update_light_buttons()
    changes = []
    widgets = [view.recovery_label, view.recovery_button, *view.light_buttons]
    for widget in widgets:
        original = widget.config

        def configure(*args, _original=original, **kwargs):
            changes.append(kwargs)
            return _original(*args, **kwargs)

        monkeypatch.setattr(widget, "config", configure)
    for unused in range(3):
        view.update_light_buttons()
        view.root.update()
    assert not changes


@pytest.mark.parametrize("mode", ["original", "black", "visitor"])
def test_native_display_switches_require_paused_instructions(mode):
    view = panel.Panel.__new__(panel.Panel)
    view.release_target = view.closing = None
    view.running, view.mode = True, "experiment"
    messages = []
    view.status_text = SimpleNamespace(set=messages.append)
    view.show(mode)
    assert view.mode == "experiment"
    assert messages == ["Pause the instructions before switching the panel."]


def shared_worker(view):
    """An already acquired owner; navigation cannot start or dispatch any process."""
    worker = SimpleNamespace(pid=7301, stdin=BytesIO(), stdout=SimpleNamespace(fileno=lambda: 99), poll=lambda: None)
    view.worker = worker
    view.worker_ready = True
    view.worker_started = view.last_heartbeat = panel.monotonic()
    view.args.live_lights = True
    view.light_state = "ready"
    view.light_capabilities = {"gradient": True, "programmes": True}
    view.confirmed_power, view.confirmed_scene = "on", "Fid"
    view.confirmed_light, view.confirmed_at = "Fid scene", panel.monotonic()
    view.light_changes_requested = True
    view.request_seq = 23
    return worker


def test_classic_and_home_keep_one_acquired_owner_without_hardware_work(view):
    worker = shared_worker(view)
    confirmed = (view.confirmed_light, view.confirmed_at, view.confirmed_power, view.confirmed_scene)
    requests = []
    view.request = lambda action, arguments=None: requests.append((action, arguments))
    home = view.body
    classic = None
    for unused in range(8):
        view.show("classic")
        view.root.update()
        assert view.mode == "classic" and view.body.winfo_ismapped()
        classic = classic or view.body
        assert view.body is classic
        assert not view.dock.winfo_ismapped()
        assert view.worker is worker and view.worker.pid == 7301
        assert view.worker_ready and view.light_state == "ready"
        assert view.request_seq == 23 and not view.worker.stdin.getvalue()
        assert (view.confirmed_light, view.confirmed_at, view.confirmed_power, view.confirmed_scene) == confirmed
        view.home_button.invoke()
        view.root.update()
        assert view.mode == "room" and view.body is home
        assert view.worker is worker and view.release_target is None
    assert requests == []  # No acquire, release, setter or programme action.


def test_sent_command_completes_once_after_switching_classic_and_home(view, monkeypatch):
    worker = shared_worker(view)
    arguments = {"cct": 3500, "intensity": 1000}
    pending = {"request_id": "shared:23", "action": "cct", "arguments": arguments,
               "sent_monotonic_s": panel.monotonic()}
    view.pending, view.light_state = pending, "applying"
    view.recovery.begin_write(pending["request_id"])
    view.queued_intent = ("channels", {"values": [0] * 8}, view.view_generation)
    view.intent_timer = view.root.after(10000, lambda: pytest.fail("Stale selection was dispatched"))
    requests = []
    view.request = lambda action, arguments=None: requests.append((action, arguments))
    events = []
    original_emit = view.emit

    def emit(event, **values):
        events.append(event)
        return original_emit(event, **values)

    view.emit = emit
    view.show("classic")
    view.root.update()
    assert view.mode == "classic" and view.body.winfo_ismapped()
    assert view.pending is pending and view.worker is worker
    assert view.queued_intent is None and view.intent_timer is None
    view.open_home()
    view.root.update()
    assert view.pending is pending and view.worker is worker and view.mode == "room"
    monkeypatch.setattr(panel.select, "select", lambda *args: ([], [], []))
    reply = json.dumps({"version": 1, "request_id": "shared:23", "state": "completed",
                        "fixtures": 10, "words": [1000] * 8}) + "\n"
    view.worker_buffer = reply
    REAL_POLL_WORKER(view)
    assert view.pending is None and view.light_state == "ready"
    assert view.confirmed_at is not None and view.worker is worker
    assert events.count("light_result") == 1
    view.worker_buffer = reply
    REAL_POLL_WORKER(view)
    assert events.count("light_result") == 1 and requests == []
    assert view.request_seq == 23 and not worker.stdin.getvalue()


def test_classic_retains_uncertainty_and_disables_actuators_without_reconnecting(view):
    worker = shared_worker(view)
    view.light_state = "failed"
    view.show("classic")
    view.root.update()
    assert view.mode == "classic" and view.worker is worker
    assert view.light_state == "failed" and view.light_changes_requested
    assert view.classic_buttons and view.light_buttons
    assert all(button.cget("state") == "disabled" for button in view.light_buttons)
    assert all(button.cget("state") == "disabled" for button in view.programme_buttons)
    assert all(button.cget("state") == "disabled" for button in view.blind_buttons)
    view.open_home()
    view.root.update()
    assert view.worker is worker and view.light_state == "failed"
    assert view.request_seq == 23 and not worker.stdin.getvalue()


def test_cached_classic_vertical_sliders_rebind_to_cct_after_navigation(view):
    shared_worker(view)
    view.show("classic")
    view.root.update()
    classic = view.body
    sliders = [control for control in view.light_buttons if isinstance(control, panel.TouchSlider)]
    assert len(sliders) == 2 and all(slider.vertical for slider in sliders)
    calls = []
    view.cct_apply = lambda: calls.append("cct")
    view.channels_apply = lambda: calls.append("channels")
    traces = [len(variable.trace_info()) for variable in (view.cct, view.intensity)]
    for unused in range(4):
        view.open_home()
        view.show("classic")
        view.root.update()
        assert view.body is classic
        for slider in sliders:
            assert slider.cget("state") == "normal"
            slider.on_start()
            slider.command(str(slider.variable.get()))
            slider.on_end()
        assert view.slider_drag is None
    assert calls and set(calls) == {"cct"}
    assert traces == [len(variable.trace_info()) for variable in (view.cct, view.intensity)]


def test_running_instructions_block_original_legacy_without_unlocking_controls(view):
    worker = shared_worker(view)
    view.open_advanced("experiment")
    view.start_preview()
    view.legacy_button.invoke()
    view.root.update()
    assert view.mode == "experiment" and view.running and view.worker is worker
    assert "Pause" in view.status_text.get()
    assert all(button.cget("state") == "disabled" for button in view.light_buttons)
    assert all(button.cget("state") == "disabled" for button in view.programme_buttons)
    view.open_home()
    view.root.update()
    assert view.running and view.worker is worker and view.request_seq == 23
