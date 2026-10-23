"""Light writes require a restorable baseline and matching fixture feedback."""

from types import SimpleNamespace
from io import BytesIO, StringIO
import json
import datetime
import threading

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel
import scr_touch_panel_lights as adapter
import event_journal
import preferences
import weather


class Room:
    def __init__(self):
        self.state = dict.fromkeys(
            adapter.COORDINATES, adapter.setter_words(adapter.PRESETS["Fid"])
        )
        self.writes = []
        self.lose_response = False

    def call(self, name, *args):
        if name == "get_lights":
            return SimpleNamespace(lights=[v for xy in sorted(self.state) for v in xy])
        if name == "get_sources":
            # Installed service uses float32 percentages. Represent its precision.
            import struct

            return SimpleNamespace(
                sources=[
                    struct.unpack("f", struct.pack("f", v * 100 / 65535))[0]
                    for v in self.state[tuple(args)]
                ]
            )
        assert name == "sources_all"
        self.writes.append(tuple(args))
        self.state = dict.fromkeys(self.state, adapter.setter_words(args))
        if self.lose_response:
            raise TimeoutError("Lost response after a write")
        return SimpleNamespace(cmdstr=str([float(v) / 100 for v in args]))


def test_exact_restore_after_confirmed_write_and_float32_readback():
    room = Room()
    lights = adapter.Lights(room.call)
    baseline = dict(room.state)
    assert lights.acquire()["state"] == "ready"
    assert (
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})["state"]
        == "completed"
    )
    assert lights.release()["restored"]
    assert room.state == baseline


def test_unknown_baseline_and_invalid_requests_do_not_write():
    room = Room()
    xy = next(iter(room.state))
    room.state[xy] = (1,) * 8
    with pytest.raises(ValueError, match="restorable"):
        adapter.Lights(room.call).acquire()
    room.state[xy] = adapter.setter_words(adapter.PRESETS["Fid"])
    lights = adapter.Lights(room.call)
    lights.acquire()
    for action, arguments in [
        ("channels", {"values": [101] * 8}),
        ("cct", {"cct": 3500, "intensity": -1}),
        ("script", {}),
    ]:
        with pytest.raises(ValueError):
            lights.apply(action, arguments)
    assert not room.writes


def test_lost_response_and_external_changes_block_retries_and_restore():
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    room.lose_response = True
    with pytest.raises(TimeoutError):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    with pytest.raises(ValueError):
        lights.apply("channels", {"values": list(adapter.PRESETS["Fid"])})
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert len(room.writes) == 1


def test_external_change_before_first_write_never_reports_successful_release():
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    room.state = dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS["Dul"]))
    with pytest.raises(ValueError, match="ownership lost"):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    for unused in range(2):
        with pytest.raises(ValueError, match="unknown"):
            lights.release()
        with pytest.raises(ValueError, match="unavailable"):
            lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert not room.writes and lights.failed and lights.baseline is not None


def test_restore_read_timeout_latches_failure_and_expired_lease_prevents_write():
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})

    def timed_out():
        raise TimeoutError("Pre-restore read did not complete")

    lights.read = timed_out
    with pytest.raises(TimeoutError):
        lights.release()
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert len(room.writes) == 1
    room = Room()
    lights = adapter.Lights(room.call, can_write=timed_out)
    lights.acquire()
    with pytest.raises(TimeoutError):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert not room.writes
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    room.state = dict.fromkeys(room.state, (0,) * 8)
    with pytest.raises(ValueError, match="External"):
        lights.release()
    assert len(room.writes) == 1


def test_profile_is_data_only_and_scheduled_theme_handles_midnight(tmp_path):
    item = tmp_path / "profile.json"
    item.write_text('{"script":"anything"}')
    with pytest.raises(ValueError, match="permits"):
        panel.profile(str(item))
    assert panel.scheduled_theme(8 * 60, 7 * 60, 19 * 60) == "light"
    assert panel.scheduled_theme(20 * 60, 7 * 60, 19 * 60) == "dark"
    assert panel.scheduled_theme(23 * 60, 19 * 60, 7 * 60) == "light"
    assert panel.scheduled_theme(12 * 60, 19 * 60, 7 * 60) == "dark"


def test_preferences_restore_appearance_only_and_survive_invalid_input(
    tmp_path, monkeypatch
):
    path = tmp_path / "appearance.json"
    assert preferences.load(str(path)) == ({}, None)
    writer = preferences.Preferences(str(path))
    value = {
        "theme": "dark",
        "clock_format": "12",
        "tips": "off",
        "light_at": 420,
        "dark_at": 1140,
        "temperature_unit": "c",
        "idle_timeout": 900,
    }
    entered, unblock = threading.Event(), threading.Event()
    original = preferences.os.fsync

    def slow_sync(fd):
        entered.set()
        assert unblock.wait(2)
        original(fd)

    monkeypatch.setattr(preferences.os, "fsync", slow_sync)
    writer.save(value)
    assert entered.wait(2)
    # New UI selections do not wait for storage; the latest snapshot wins.
    for theme in ("light", "auto", "dark"):
        writer.save(dict(value, theme=theme))
    unblock.set()
    writer.close()
    assert writer.done.wait(2)
    assert preferences.load(str(path)) == (value, None)
    path.write_text('{"theme":"light","lights":"on","recording":true}')
    assert preferences.load(str(path))[0] == {"theme": "light"}
    path.write_text('{"theme":"invalid"}')
    assert preferences.load(str(path))[0] == {}
    assert preferences.load(str(path))[1]
    for display in ("disabled", "hidden"):
        assert preferences.validated({"blinds_display": display}) == {
            "blinds_display": display
        }
    with pytest.raises(ValueError):
        preferences.validated({"blinds_display": "enabled"})
    path.write_text('{"temperature_unit":"kelvin"}')
    assert preferences.load(str(path))[1]
    for invalid in (True, 61, -1, "300"):
        path.write_text(json.dumps({"idle_timeout": invalid}))
        assert preferences.load(str(path))[1]
    path.write_text('{"light_at":480}')
    assert preferences.load(str(path), {"light_at": 420, "dark_at": 480})[1]
    path.write_text("x" * 5000)
    assert preferences.load(str(path))[1]


def test_weather_timeout_preserves_last_success_without_touching_lights(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.weather_worker = SimpleNamespace(
        poll=lambda: None, kill=lambda: stopped.append(True)
    )
    state.weather_started = 0
    stopped = []
    monkeypatch.setattr(panel, "monotonic", lambda: 9)
    state.poll_weather()
    assert stopped == [True]
    state.weather_worker = SimpleNamespace(
        poll=lambda: 1, stdout=BytesIO(b'{"error":"timeout"}'), stderr=None
    )
    state.weather_last_text = "Last successful weather"
    shown = []
    state.weather_text = SimpleNamespace(set=shown.append)
    state.poll_weather()
    assert state.weather_worker is None
    assert "refresh failed" in shown[-1] and state.weather_last_text in shown[-1]
    data = weather.summary(
        {
            "current": {
                "temperature_2m": 50,
                "weather_code": 2,
                "time": "2026-10-13T12:00",
            },
            "daily": {"sunrise": ["2026-10-13T06:30"], "sunset": ["2026-10-13T18:00"]},
        }
    )
    assert data["temperature_c"] == 10 and data["sunrise"].endswith("06:30")
    state.weather_worker = SimpleNamespace(
        poll=lambda: 0, stdout=BytesIO(json.dumps(data).encode()), stderr=None
    )
    state.update_weather = lambda **kwargs: None
    state.poll_weather()
    assert state.weather_reading == weather.validate(data)
    assert state.weather_good == 9 and "model 2026-10-13 12:00" in shown[-1]
    day = weather.daylight(data, datetime.datetime(2026, 10, 13, 12, 0))
    assert 0 < day["fraction"] < 1 and day["label"] == "Sun sets in 6 h 00 min"
    assert (
        weather.daylight(data, datetime.datetime(2026, 10, 13, 5, 0))["fraction"] == 0
    )
    assert (
        "rises"
        in weather.daylight(data, datetime.datetime(2026, 10, 13, 5, 0))["label"]
    )
    assert (
        weather.daylight(data, datetime.datetime(2026, 10, 13, 19, 0))["fraction"] == 1
    )
    assert weather.daylight(data, datetime.datetime(2026, 10, 14, 12, 0)) is None
    with pytest.raises(ValueError):
        weather.validate(dict(data, temperature_f=float("nan")))


def test_latest_touch_intent_is_copied_serialized_and_cancelled_before_release(
    monkeypatch,
):
    class Scheduler:
        def __init__(self):
            self.calls = {}
            self.seq = 0

        def after(self, delay, callback):
            self.seq += 1
            self.calls[self.seq] = callback
            return self.seq

        def after_cancel(self, item):
            self.calls.pop(item, None)

        def fire(self):
            callbacks, self.calls = list(self.calls.values()), {}
            for callback in callbacks:
                callback()

    state = panel.Panel.__new__(panel.Panel)
    state.root = Scheduler()
    state.mode, state.light_state = "room", "ready"
    state.pending = state.release_target = state.closing = None
    state.queued_intent = state.intent_timer = state.slider_drag = None
    state.view_generation = 0
    state.status_text = state.light_text = SimpleNamespace(set=lambda value: None)
    sent = []

    def request(action, args):
        sent.append((action, args))
        return True

    state.request = request
    state.update_light_buttons = lambda: None
    values = [10] * 8
    state.apply("channels", values=values)
    values[0] = 99
    state.root.fire()
    assert sent == [("channels", {"values": [10] * 8})]
    state.pending = {"request_id": "first"}
    state.apply("cct", cct=4000, intensity=1000)
    state.apply("cct", cct=5000, intensity=1050)
    state.root.fire()
    assert len(sent) == 1  # One in flight; only the latest remains unsent.
    state.pending, state.light_state = None, "ready"
    state.dispatch_intent()
    assert sent[-1] == ("cct", {"cct": 5000, "intensity": 1050})
    state.confirmed_light = "Fid scene"
    feedback = []
    state.light_text = SimpleNamespace(set=feedback.append)
    state.apply("cct", cct=4500, intensity=1000)
    assert "Selected: 4500 K input / level 1000" in feedback[-1]
    assert "Last confirmed drive: Fid scene" in feedback[-1]
    # A new selection does not overwrite the previous successful readback.
    assert state.confirmed_light == "Fid scene"
    assert (
        panel.light_selection("channels", {"values": list(adapter.PRESETS["Sat"])})
        == "Sat scene"
    )
    state.apply("channels", values=[30] * 8)
    state.cancel_intent()
    state.root.fire()
    assert len(sent) == 2
    state.release_target = "original"
    state.apply("channels", values=[40] * 8)
    assert state.queued_intent is None
    state.release_target, state.light_state = None, "ready"
    state.request = lambda action, args: False
    state.apply("channels", values=[50] * 8)
    state.root.fire()
    assert state.light_state == "failed"
    state.light_state, state.closed = "ready", False
    state.status_worker = None
    state.worker = SimpleNamespace(stdout=object(), poll=lambda: 0)
    state.worker_buffer = ""
    monkeypatch.setattr(panel.select, "select", lambda *args: ([], [], []))
    state.poll_worker()
    assert state.worker is None and state.light_state == "failed"
    # A failed helper can still be doing EOF cleanup. Never uncover legacy
    # actuator controls until that exact child has exited.
    state.keep_switcher, state.closed, state.closing = True, False, None
    state.mode, state.release_target = "room", None
    state.trial_deadline = 1
    pipe = SimpleNamespace(closed=False)
    pipe.close = lambda: setattr(pipe, "closed", True)
    state.worker = SimpleNamespace(stdin=pipe, poll=lambda: None)
    state.show("original")
    assert state.mode == "room" and state.release_target == "original" and pipe.closed
    assert state.trial_deadline is None


def test_button_intents_dispatch_without_slider_delay_but_stay_serialized():
    state = panel.Panel.__new__(panel.Panel)
    state.mode, state.light_state = "room", "ready"
    state.pending = state.release_target = state.closing = None
    state.queued_intent = state.intent_timer = state.slider_drag = None
    state.view_generation = 0
    cancelled, sent, feedback = [], [], []

    def delayed(*args):
        raise AssertionError("Discrete button must not wait for slider debounce")

    state.root = SimpleNamespace(after=delayed, after_cancel=cancelled.append)
    state.status_text = state.light_text = SimpleNamespace(set=feedback.append)
    state.update_light_buttons = lambda: None

    def request(action, arguments):
        sent.append((action, arguments))
        state.pending = {"request_id": str(len(sent))}
        return True

    state.request = request
    state.intent_timer = "old slider timer"
    state.apply("cct", immediate=True, cct=3500, intensity=1000)
    assert cancelled == ["old slider timer"]
    assert sent == [("cct", {"cct": 3500, "intensity": 1000})]
    assert state.intent_timer is None and state.queued_intent is None
    state.apply("channels", immediate=True, values=[0] * 8)
    assert len(sent) == 1 and state.queued_intent[0] == "channels"
    assert any("waiting for current request" in text for text in feedback)
    state.pending, state.light_state = None, "ready"
    state.dispatch_intent()
    assert sent[-1] == ("channels", {"values": [0] * 8})
    # Uncertainty blocks button dispatch just as it blocks slider changes.
    state.pending, state.light_state = None, "failed"
    state.apply("cct", immediate=True, cct=3500, intensity=1000)
    assert len(sent) == 2


def test_unchanged_display_variables_do_not_schedule_another_redraw():
    updates = []
    variable = SimpleNamespace(get=lambda: "12:34", set=updates.append)
    panel.set_changed(variable, "12:34")
    assert not updates
    panel.set_changed(variable, "12:35")
    assert updates == ["12:35"]


def test_slow_resource_read_never_holds_navigation_or_starts_a_second_query(
    monkeypatch,
):
    entered, release = threading.Event(), threading.Event()

    def slow_read():
        entered.set()
        assert release.wait(3)
        return {"error": "Controlled slow resource read"}

    monkeypatch.setattr(panel, "health", slow_read)
    state = panel.Panel.__new__(panel.Panel)
    state.mode, state.health_at, state.health_cache = "health", -10, {}
    state.theme, state.health_rendered = "light", None
    state.health_worker = state.health_pending = None
    state.status_worker, state.room_status_at, state.room_status = (
        None,
        panel.monotonic(),
        "Not queried",
    )
    shown = []
    state.health_details = state.services_label = SimpleNamespace(
        config=lambda **kw: shown.append(kw)
    )
    try:
        state.update_health()  # Returns while the resource read is held below.
        assert entered.wait(1) and state.health_worker.is_alive()
        worker = state.health_worker
        paints = len(shown)
        state.health_at = -10
        state.update_health()
        assert state.health_worker is worker and len(shown) == paints
        state.mode = "room"
        state.update_health()
        assert state.health_worker is worker
    finally:
        release.set()
        state.health_worker.join(3)
    state.mode, state.health_at = "health", panel.monotonic()
    state.update_health()
    assert state.health_cache == {"error": "Controlled slow resource read"}
    assert any("Controlled slow resource read" in item["text"] for item in shown)


def test_slow_adapter_initialization_sends_fresh_request_once_and_honors_exit(
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(panel, "monotonic", lambda: now[0])
    monkeypatch.setattr(panel.select, "select", lambda *args: ([], [], []))
    for leave in (None, "original", "close"):
        now[0] = 100.0
        worker = SimpleNamespace(
            stdin=BytesIO(), stdout=object(), poll=lambda: None, terminate=lambda: None
        )
        monkeypatch.setattr(panel.subprocess, "Popen", lambda *args, **kwargs: worker)
        state = panel.Panel.__new__(panel.Panel)
        state.args = SimpleNamespace(
            journal="unused",
            expected_master="http://room-master",
            adapter_python="unused",
            live_lights=True,
        )
        state.root = SimpleNamespace(after=lambda *args: None)
        state.run_id, state.request_seq, state.last_heartbeat = "trial", 0, 100.0
        state.pending = state.release_target = state.closing = None
        state.closed, state.keep_switcher, state.mode = False, False, "room"
        state.status_worker, state.trial_deadline = None, 1.0
        state.status_text = state.light_text = SimpleNamespace(set=lambda value: None)
        state.emit = lambda *args, **kwargs: None
        state.cancel_intent = state.poll_status = state.update_light_buttons = (
            lambda: None
        )
        state.start_worker()
        assert state.pending is None and not worker.stdin.getvalue()
        assert not state.request("acquire")
        if leave == "original":
            state.show("original")
            assert state.mode == "room" and state.release_target == "original"
        elif leave == "close":
            state.close("signal")
            assert state.closing == "signal" and state.release_target == "close"

        # Cold imports exceed the ten-second command lease. Heartbeats may flow,
        # but no acquire/release command can age in the helper's unread pipe.
        now[0] = 125.0
        state.worker_buffer = json.dumps({"version": 2, "state": "initialized"}) + "\n"
        state.poll_worker()
        commands = lambda: [
            json.loads(line)
            for line in worker.stdin.getvalue().splitlines()
            if json.loads(line)["action"] != "heartbeat"
        ]
        assert commands() == [] and not state.worker_ready
        state.worker_buffer = json.dumps({"version": 1, "state": "initialized"}) + "\n"
        state.poll_worker()
        sent = commands()
        assert len(sent) == 1
        assert sent[0]["action"] == ("release" if leave else "acquire")
        assert sent[0]["sent_monotonic_s"] == 125.0
        assert state.pending["request_id"] == sent[0]["request_id"]
        state.worker_buffer = json.dumps({"version": 1, "state": "initialized"}) + "\n"
        state.poll_worker()
        assert commands() == sent


def test_confirmed_display_uses_matching_request_not_newer_selection(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.closed, state.closing, state.worker_ready = False, None, True
    state.worker = SimpleNamespace(stdin=BytesIO(), stdout=object(), poll=lambda: None)
    state.last_heartbeat = panel.monotonic()
    state.light_state, state.confirmed_light = "applying", "Fid scene"
    state.pending = {
        "request_id": "one",
        "action": "cct",
        "arguments": {"cct": 3500, "intensity": 1000},
    }
    state.release_target = state.queued_intent = state.intent_timer = None
    state.poll_journal = state.poll_status = state.poll_weather = (
        state.update_light_buttons
    ) = lambda: None
    state.emit = lambda *args, **kwargs: None
    state.root = SimpleNamespace(after=lambda *args: None)
    shown = []
    state.light_text = SimpleNamespace(set=shown.append)
    status = []
    state.status_text = SimpleNamespace(set=status.append)
    monkeypatch.setattr(panel.select, "select", lambda *args: ([], [], []))
    reply = {
        "version": 1,
        "request_id": "other",
        "state": "completed",
        "detail": "Drive settings confirmed on 10 lights",
    }
    state.worker_buffer = json.dumps(reply) + "\n"
    state.poll_worker()
    assert state.confirmed_light == "Fid scene" and state.pending
    state.worker_buffer = json.dumps(dict(reply, request_id="one")) + "\n"
    state.poll_worker()
    assert state.confirmed_light == "3500 K input / level 1000"
    assert (
        state.pending is None
        and "Last confirmed drive: 3500 K input / level 1000" in shown[-1]
    )
    assert status[-1] == ""
    confirmed_at = state.confirmed_at
    monkeypatch.setattr(panel, "monotonic", lambda: confirmed_at + 61)
    raw = []
    state.emit = lambda event, **values: raw.append(values["result"])
    state.cancel_intent = lambda: None
    state.pending = {
        "request_id": "two",
        "action": "cct",
        "arguments": {"cct": 4500, "intensity": 1000},
    }
    failure = dict(
        reply, request_id="two", state="failed", detail="Long ROS error " * 100
    )
    state.worker_buffer = json.dumps(failure) + "\n"
    state.poll_worker()
    assert (
        state.light_state == "failed"
        and state.confirmed_light == "3500 K input / level 1000"
    )
    assert state.confirmed_at == confirmed_at and "1 min ago" in shown[-1]
    assert raw[-1]["detail"] == failure["detail"]
    assert len(shown[-1]) < 150 and "Controls disabled" in shown[-1]
    assert "ask staff" in status[-1]


def test_weather_details_are_optional_convert_units_and_reject_invalid_forecasts():
    raw = {
        "current": {
            "temperature_2m": 50,
            "apparent_temperature": 45,
            "weather_code": 2,
            "time": "2026-10-15T12:00",
        },
        "daily": {
            "sunrise": ["2026-10-15T07:00"],
            "sunset": ["2026-10-15T18:00"],
            "temperature_2m_max": [59],
            "temperature_2m_min": [32],
            "precipitation_probability_max": [80],
        },
    }
    value = weather.summary(raw)
    assert value["high_c"] == 15 and value["low_c"] == 0
    assert (
        weather.details(value, "f")
        == "Feels like 45° F\nHigh 59° · Low 32° · Rain today 80%"
    )
    assert "High 15° · Low 0°" in weather.details(value, "c")
    assert weather.details(value, earlier=True) == "Earlier weather: 2026-10-15 12:00"
    assert dict(weather.measurements(value, "c")) == {
        "Feels like": "7°",
        "Rain today": "80%",
        "High": "15°",
        "Low": "0°",
    }
    assert weather.measurements(value, earlier=True) == []
    assert dict(weather.measurements({"rain_chance": 0})) == {
        "Feels like": "—",
        "Rain today": "0%",
        "High": "—",
        "Low": "—",
    }
    for invalid in (
        {"rain_chance": -1},
        {"rain_chance": 101},
        {"high_f": float("nan")},
        {"feels_like_f": True},
        {"low_f": 60},
    ):
        with pytest.raises(ValueError):
            weather.validate(dict(value, **invalid))
    raw["current"].pop("apparent_temperature")
    for key in (
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
    ):
        raw["daily"].pop(key)
    assert weather.details(weather.summary(raw)) == ""


def test_idle_guards_and_wake_do_not_dispatch_a_touch(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.idle_timeout, state.mode, state.light_state = 300, "room", "ready"
    state.running = state.press_active = False
    for name in (
        "pending",
        "queued_intent",
        "intent_timer",
        "slider_drag",
        "release_target",
        "closing",
    ):
        setattr(state, name, None)
    assert state.idle_eligible()
    for mode in ("experiment", "original", "black", "visitor"):
        state.mode = mode
        assert not state.idle_eligible()
    state.mode = "room"
    for name in (
        "running",
        "press_active",
        "pending",
        "queued_intent",
        "intent_timer",
        "slider_drag",
        "release_target",
        "closing",
    ):
        setattr(state, name, True)
        assert not state.idle_eligible()
        setattr(state, name, False if name in ("running", "press_active") else None)
    for light_state in ("connecting", "applying", "failed"):
        state.light_state = light_state
        assert not state.idle_eligible()
    state.light_state, state.idle_timeout = "ready", 0
    assert not state.idle_eligible()
    state.idle_timeout, state.last_touch, state.section = 300, 0, "channels"
    state.idle_active = False
    shown, restored, deferred = [], [], []
    state.show = lambda mode: (shown.append(mode), setattr(state, "mode", mode))
    state.channel_view = lambda: restored.append("channels")
    state.status_text = SimpleNamespace(set=lambda value: None)
    state.root = SimpleNamespace(focus_set=lambda: None, after_idle=deferred.append)
    monkeypatch.setattr(panel, "monotonic", lambda: 299)
    state.update_idle()
    assert not shown
    monkeypatch.setattr(panel, "monotonic", lambda: 300)
    state.update_idle()
    assert shown == ["visitor"] and state.idle_active
    assert state.wake_idle(True) == "break" and not deferred
    assert state.wake_idle(False) == "break" and state.mode == "visitor"
    deferred.pop()()
    assert shown == ["visitor", "room"] and not restored
    assert not state.idle_active and state.last_touch == 300 and not state.press_active
    assert state.wake_idle(True) is None
    state.mode = "advanced"
    assert state.idle_eligible()
    state.idle_active, state.idle_return = True, ("room", "lighting")
    state.open_lighting = lambda: restored.append("lighting")
    state.return_from_idle()
    assert shown[-1] == "room" and not restored and not state.idle_active
    assert panel.confirmation_age(59, 0) == "just now"
    assert panel.confirmation_age(60, 0) == "1 min ago"
    assert panel.confirmation_age(3600, 0) == "1 h ago"
    assert panel.confirmation_age(86400, 0) == "1 d ago"
    assert panel.confirmation_age(500, None) == ""


def test_home_power_requires_confirmed_readback_and_clears_during_changes():
    assert panel.confirmed_power({"state": "ready", "baseline": "Off"}) == "off"
    assert panel.confirmed_power({"state": "ready", "baseline": "Fid"}) == "on"
    assert panel.confirmed_power({"state": "completed", "words": [0] * 8}) == "off"
    assert panel.confirmed_power({"state": "completed", "words": [0] * 7 + [1]}) == "on"
    for reply in (
        {"state": "ready", "baseline": "Unknown"},
        {"state": "failed", "words": [0] * 8},
        {"state": "completed", "words": [True] * 8},
        {"state": "completed", "words": [65536] * 8},
        {"state": "completed", "words": [0] * 7},
        {"state": "completed", "intensity": 0},
    ):
        assert panel.confirmed_power(reply) is None
    state = panel.Panel.__new__(panel.Panel)
    state.light_state, state.confirmed_power = "ready", "off"
    state.pending = state.queued_intent = state.release_target = state.closing = None
    state.accent, state.selected_ink, state.accent_pressed = (
        panel.ACCENT,
        "white",
        "#10575e",
    )
    state.control, state.ink, state.icon_colour, state.border = (
        "neutral",
        "ink",
        "icon",
        "border",
    )
    state.icon = lambda *args: None
    buttons = [
        SimpleNamespace(winfo_exists=lambda: True, config=lambda **kw: None)
        for _ in range(2)
    ]
    for button in buttons:
        button.config = lambda button=button, **kw: setattr(button, "options", kw)
    state.home_power_buttons = [
        (buttons[0], "on", "Lights on"),
        (buttons[1], "off", "Lights off"),
    ]
    state.update_power_highlights()
    assert (
        buttons[0].options["bg"] == "neutral"
        and buttons[1].options["bg"] == panel.ACCENT
    )
    assert buttons[1].options["activeforeground"] == buttons[1].options["fg"] == "white"
    for field in ("pending", "queued_intent", "release_target", "closing"):
        setattr(state, field, True)
        state.update_power_highlights()
        assert all(button.options["bg"] == "neutral" for button in buttons)
        setattr(state, field, None)
    state.light_state = "failed"
    state.update_power_highlights()
    assert all(button.options["bg"] == "neutral" for button in buttons)


def test_scene_highlight_uses_exact_confirmed_words_and_clears_for_custom_or_uncertain():
    state = panel.Panel.__new__(panel.Panel)
    state.light_state = "ready"
    state.pending = state.queued_intent = state.release_target = state.closing = None
    state.accent, state.selected_ink, state.accent_pressed = (
        panel.ACCENT,
        "white",
        "#10575e",
    )
    state.control, state.ink, state.border = "neutral", "ink", "border"
    buttons = []
    for name in ("Fid", "Sat", "Dul"):
        button = SimpleNamespace(winfo_exists=lambda: True)
        button.config = lambda button=button, **kw: setattr(button, "options", kw)
        buttons.append((button, name))
    state.scene_buttons = buttons
    for name, preset in adapter.PRESETS.items():
        assert panel.confirmed_scene({"state": "ready", "baseline": name}) == name
        reply = {"state": "completed", "words": list(adapter.setter_words(preset))}
        state.confirmed_scene = panel.confirmed_scene(reply)
        assert state.confirmed_scene == name
        state.update_power_highlights()
        assert [
            label for button, label in buttons if button.options["bg"] == panel.ACCENT
        ] == ([] if name == "Off" else [name])
    custom = list(adapter.setter_words(adapter.PRESETS["Fid"]))
    custom[0] += 1  # Even a one-word difference is not the known scene.
    for reply in (
        {"state": "completed", "words": custom},
        {"state": "completed", "values": list(adapter.PRESETS["Fid"])},
        {
            "state": "failed",
            "words": list(adapter.setter_words(adapter.PRESETS["Fid"])),
        },
    ):
        state.confirmed_scene = panel.confirmed_scene(reply)
        assert state.confirmed_scene is None
        state.update_power_highlights()
        assert all(button.options["bg"] == "neutral" for button, name in buttons)
    state.confirmed_scene = "Sat"
    for field in ("pending", "queued_intent", "release_target", "closing"):
        setattr(state, field, True)
        state.update_power_highlights()
        assert all(button.options["bg"] == "neutral" for button, name in buttons)
        setattr(state, field, None)
    state.light_state = "failed"
    state.update_power_highlights()
    assert all(button.options["bg"] == "neutral" for button, name in buttons)


def test_advanced_navigation_and_blank_return_preserve_tool_but_idle_opens_home():
    state = panel.Panel.__new__(panel.Panel)
    state.last_advanced_page, state.release_target, state.closing = "scenes", None, None
    shown = []
    state.show = lambda mode, **kw: shown.append((mode, kw))
    state.open_advanced()
    assert shown[-1] == ("room", {"advanced_page": "lighting"})
    assert state.lighting_tab == "channels"
    state.open_advanced("clock")
    assert shown[-1] == ("settings", {"advanced_page": "clock"})
    state.blank_advanced_return, state.blank_return = "screen", "settings"
    state.return_from_blank()
    assert shown[-1] == ("settings", {"advanced_page": "screen"})
    state.idle_active = True
    state.root = SimpleNamespace(focus_set=lambda: None)
    state.return_from_idle()
    assert shown[-1] == ("room", {})
    state.release_target = "original"
    state.open_advanced("white")
    assert shown[-1] == ("room", {})


def journal_panel(journal, path):
    state = panel.Panel.__new__(panel.Panel)
    state.journal, state.args = journal, SimpleNamespace(journal=path)
    state.sequence, state.stage, state.started = 0, 0, panel.monotonic()
    state.mode, state.run_id, state.boot_id = "experiment", "trial", None
    state.profile, state.pending_annotation = panel.DEFAULT_PROFILE, None
    state.annotation_text = SimpleNamespace(
        value="", set=lambda value: setattr(state.annotation_text, "value", value)
    )
    state.status_text = SimpleNamespace(
        value="", set=lambda value: setattr(state.status_text, "value", value)
    )
    return state


def test_journal_fsync_does_not_block_emit_and_saved_waits_for_durable_ack(
    tmp_path, monkeypatch
):
    entered, release = threading.Event(), threading.Event()

    def blocked_fsync(unused):
        entered.set()
        if not release.wait(3):
            raise OSError("Test fsync gate timed out")

    monkeypatch.setattr(event_journal.os, "fsync", blocked_fsync)
    path = tmp_path / "events.jsonl"
    journal = event_journal.EventJournal(str(path), StringIO())
    state = journal_panel(journal, str(path))
    try:
        state.emit("practice_started")
        state.mark("Activity started")
        assert entered.wait(2)
        state.emit("instruction_selected")  # Returns while fsync remains blocked.
        state.poll_journal()
        assert state.annotation_text.value == "Saving annotation: Activity started"
        journal.close()  # Close requests drainage without joining the writer.
        assert not journal.done.is_set()
    finally:
        release.set()
        journal.close()
        assert journal.done.wait(3)
        journal.thread.join(1)
    state.poll_journal()
    assert state.annotation_text.value.startswith("Saved on panel: Activity started")
    assert journal.error is None and not journal.thread.is_alive()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [item["sequence"] for item in records] == [1, 2, 3]
    assert [item["event"] for item in records] == [
        "practice_started",
        "annotation",
        "instruction_selected",
    ]


def test_journal_backlog_is_bounded_and_accepted_records_drain_in_order():
    entered, release = threading.Event(), threading.Event()

    class BlockedOutput(StringIO):
        def write(self, value):
            entered.set()
            if not release.wait(3):
                raise OSError("Test output gate timed out")
            return super().write(value)

    output = BlockedOutput()
    journal = event_journal.EventJournal(None, output, capacity=2)
    try:
        journal.append("first\n", 1)
        assert entered.wait(2)
        journal.append("second\n", 2)
        journal.append("third\n", 3)
        with pytest.raises(IOError, match="queue is full"):
            journal.append("rejected\n", 4)
        assert journal.pending.qsize() == 2
        with pytest.raises(IOError):
            journal.append("also rejected\n", 5)
    finally:
        journal.close()
        release.set()
        assert journal.done.wait(3)
        journal.thread.join(1)
    assert output.getvalue() == "first\nsecond\nthird\n"
    assert not journal.thread.is_alive()


def test_journal_failures_never_claim_unsaved_annotations_are_saved(
    tmp_path, monkeypatch, capsys
):
    class FailedOutput:
        def write(self, unused):
            raise OSError("Injected output failure")

        def flush(self):
            raise AssertionError("Failed write must not be flushed")

    for kind in ("persist", "output-only", "mirror"):
        path = None if kind == "output-only" else str(tmp_path / (kind + ".jsonl"))

        def fsync(unused):
            if kind == "persist":
                raise OSError("Injected persistence failure")

        monkeypatch.setattr(event_journal.os, "fsync", fsync)
        output = StringIO() if kind == "persist" else FailedOutput()
        journal = event_journal.EventJournal(path, output)
        state = journal_panel(journal, path)
        try:
            state.mark("Activity finished")
        finally:
            journal.close()
            assert journal.done.wait(3)
            journal.thread.join(1)
        state.closed, state.worker, state.closing = False, None, "test"
        destroyed = []
        state.root = SimpleNamespace(
            destroy=lambda: destroyed.append(state.annotation_text.value)
        )
        state.finish_close()  # Final results must be processed before Tk disappears.
        stderr = capsys.readouterr().err
        assert state.closed and destroyed == [state.annotation_text.value]
        assert not journal.thread.is_alive()
        if kind == "mirror":
            assert state.annotation_text.value.startswith(
                "Saved on panel: Activity finished"
            )
            assert journal.output_error == "Injected output failure"
            assert not stderr
        else:
            assert state.annotation_text.value.startswith("Annotation not saved:")
            assert "Saved on panel" not in state.annotation_text.value
            assert "Written to panel output" not in state.annotation_text.value
            assert "Panel journal shutdown failed:" in stderr


def test_panel_loops_keep_running_after_one_unexpected_error(capsys):
    scheduled = []
    state = panel.Panel.__new__(panel.Panel)
    state.closed = False
    state.root = SimpleNamespace(after=lambda delay, callback: scheduled.append(callback))
    calls = []

    def step():
        calls.append(1)
        if len(calls) < 3:
            raise KeyError("broken reading")
        return False if len(calls) == 4 else None

    state.repeat(step, 1000)
    scheduled.pop()()
    assert capsys.readouterr().err.count("KeyError:") == 1  # logged once
    scheduled.pop()()
    scheduled.pop()()  # returned False: the loop ends
    assert len(calls) == 4 and not scheduled
    state.closed = True
    state.repeat(lambda: None, 1000)
    assert not scheduled


def test_live_snapshot_leaves_guide_and_help_to_the_shared_export():
    import inspect
    import panel_remote

    source = inspect.getsource(panel_remote.snapshot)
    assert '"guide"' not in source and '"help"' not in source
