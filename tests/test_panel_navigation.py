"""Exercise real Tk navigation with every external process and device call blocked."""

import argparse
from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel


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
    assert view.mode == "original" and view.dock.winfo_ismapped()
    dock_home = next(
        button
        for button in view.navigation_buttons
        if button.cget("text") == "Home" and button is not view.home_button
    )
    dock_home.invoke()
    view.root.update()
    assert view.mode == "room" and view.body.winfo_ismapped()


def test_home_explains_why_running_instructions_disable_lighting(view):
    view.open_advanced("experiment")
    view.start_preview()
    view.open_home()
    view.root.update()
    assert "Pause Experiment mode" in view.status_text.get()
    assert all(button.cget("state") == "disabled" for button in view.light_buttons)


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
