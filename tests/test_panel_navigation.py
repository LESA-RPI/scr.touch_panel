"""Exercise real Tk navigation with every external process and device call blocked."""

import argparse
import gc
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
    gc.collect()
    original = panel.tk.Tk

    def invisible_root():
        try:
            root = original()
        except panel.tk.TclError as error:
            pytest.skip("Tk display unavailable: " + str(error))
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
