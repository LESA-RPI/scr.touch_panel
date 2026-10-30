"""Room diagnostics reuse one metadata worker and preserve the last observation."""

from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scr_touch_panel as panel
import panel_remote
from panel_control import command
from test_browser_status import status


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(panel.sys, "platform", "linux")
    monkeypatch.setattr(panel, "monotonic", lambda: 100.0)
    state = panel.Panel.__new__(panel.Panel)
    state.args = SimpleNamespace(expected_master="http://approved-room-master")
    state.closed, state.closing, state.status_worker = False, None, None
    state.status_started, state.room_status_at = None, 20
    state.room_status_state = "available"
    state.room_status_good_at, state.room_status_observed = 20, "2026-10-30T12:00:00+00:00"
    state.room_services = [{"name": "Lighting", "state": "listed"}]
    state.request = lambda *args: pytest.fail("Metadata checks must not dispatch device calls")
    return state


def completed_worker(state, value, code=0):
    worker = SimpleNamespace(
        poll=lambda: code,
        stdout=BytesIO(json.dumps(value).encode() if not isinstance(value, bytes) else value),
        stderr=BytesIO(),
    )
    state.status_worker, state.status_started = worker, 99
    return worker


def test_success_caches_dated_structured_service_rows(owner):
    worker = completed_worker(owner, {"version": 1, "services": [["Lighting", True], ["TOF", False]]})
    owner.poll_status()
    value = owner.room_diagnostics()
    assert value["state"] == "available" and value["age_s"] == 0
    assert value["observed_at"].endswith("+00:00")
    assert value["services"] == [{"name": "Lighting", "state": "listed"}, {"name": "TOF", "state": "missing"}]
    value["services"][0]["state"] = "missing"
    assert owner.room_services[0]["state"] == "listed"
    assert not value["checking"] and value["can_check"]
    assert worker.stdout.closed and worker.stderr.closed


@pytest.mark.parametrize("reply,code", [
    (b"not json", 0), ({"version": 1, "services": [["Lighting", 1]]}, 0),
    ({"version": True, "services": []}, 0),
    ({"version": 1, "services": [["Lighting", True], ["Lighting", False]]}, 0),
    ({"version": 1, "services": [["Lighting", True]]}, 1),
])
def test_failed_or_invalid_probe_preserves_last_good_rows_and_age(owner, reply, code):
    completed_worker(owner, reply, code)
    owner.poll_status()
    value = owner.room_diagnostics()
    assert value["state"] == "unavailable" and value["age_s"] == 80
    assert value["services"] == [{"name": "Lighting", "state": "listed"}]
    assert value["observed_at"] == "2026-10-30T12:00:00+00:00"
    assert "Previous results" in value["detail"]


def test_explicit_refresh_reuses_one_worker_and_keeps_cached_observation(owner, monkeypatch):
    calls = []
    worker = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(panel.subprocess, "Popen", lambda args, **kwargs: calls.append(args) or worker)
    assert owner.refresh_status()
    assert not owner.refresh_status() and not owner.start_status()
    assert len(calls) == 1 and "--status-only" in calls[0]
    assert owner.room_status_at == 100
    value = owner.room_diagnostics()
    assert value["checking"] and not value["can_check"] and value["age_s"] == 80


def test_failed_launch_preserves_previous_observation(owner, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("Cannot launch helper")

    monkeypatch.setattr(panel.subprocess, "Popen", unavailable)
    assert not owner.refresh_status()
    assert owner.room_diagnostics()["state"] == "unavailable"
    assert owner.room_diagnostics()["age_s"] == 80


def test_unconfigured_checks_have_no_refresh_path(owner):
    owner.args.expected_master = None
    assert owner.room_diagnostics()["state"] == "unconfigured"
    assert not owner.refresh_status()


def test_refresh_metadata_command_has_empty_arguments_and_ignores_actuator_busy(monkeypatch):
    value = dict(id="diagnostic-check-0001", revision="current", action="refresh_status", arguments={})
    assert command(value) == value
    with pytest.raises(ValueError):
        command(dict(value, arguments={"service": "arbitrary"}))
    calls = []
    state = SimpleNamespace(refresh_status=lambda: calls.append("metadata") or True,
                            activity=lambda *args: None)
    monkeypatch.setattr(panel_remote, "snapshot", lambda panel: {"busy": True})
    assert panel_remote.execute(state, value)["ok"]
    assert calls == ["metadata"]


def test_metadata_refresh_preserves_a_held_touch_and_blocks_following_lighting(owner, monkeypatch):
    owner.press_active = True
    owner.refresh_status = lambda: True
    owner.lights_on = lambda: pytest.fail("A held panel touch must still block lighting")
    monkeypatch.setattr(panel_remote, "snapshot", lambda state: {"busy": state.press_active})
    value = dict(id="diagnostic-check-0002", revision="current", action="refresh_status", arguments={})
    assert panel_remote.execute(owner, value)["ok"]
    assert owner.press_active is True
    with pytest.raises(RuntimeError, match="busy"):
        panel_remote.execute(owner, dict(value, action="on"))


def test_secondary_diagnostics_tick_does_not_touch_destroyed_overview_widgets(owner):
    calls = []
    owner.mode, owner.system_diagnostics_visible = "health", True
    owner.refresh_resources = lambda: calls.append("resources")
    owner.update_room_diagnostics = lambda: calls.append("details")
    owner.update_health()
    assert calls == ["resources", "details"]


def test_gateway_status_uses_owner_cache_without_another_ros_query(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(status.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(status, "host_status", lambda: {"temperature_c": 50})
    monkeypatch.setattr(status, "bounded_graph", lambda master: pytest.fail("Gateway must use the owner's existing observation"))
    value = {"available": True, "room_diagnostics": {
        "state": "available", "services": [{"name": "TOF", "state": "listed"}],
        "age_s": 40.0, "observed_at": "2026-10-30T12:00:00+00:00"}}
    source = SimpleNamespace(read=lambda: value)
    snapshot = status.Snapshot("Website host", master="http://approved-room-master", controller=source)
    snapshot.collect()
    room = snapshot.read()["room"]
    assert room["state"] == "available" and room["observation_age_s"] == 40
    assert room["services"] == [{"name": "Time-of-flight", "state": "advertised"}]
    now[0] = 150
    value["available"] = False
    snapshot.collect()
    result = snapshot.read()
    assert result["room"]["state"] == "unavailable"
    assert result["room"]["services"] == room["services"]
    assert result["room"]["observed_at"] == room["observed_at"]
    assert result["room"]["observation_age_s"] == 90
    assert result["host"]["temperature_c"] == 50


@pytest.mark.parametrize("reply", [
    {"available": False},
    {"available": True},
    {"available": True, "room_diagnostics": {"state": "available", "services": [], "age_s": None}},
    {"available": True, "room_diagnostics": {"state": "available", "services": [], "age_s": float("nan"), "observed_at": "date"}},
])
def test_unavailable_or_invalid_owner_never_falls_back_to_ros(monkeypatch, reply):
    monkeypatch.setattr(status, "host_status", lambda: {})
    monkeypatch.setattr(status, "bounded_graph", lambda master: pytest.fail("No fallback room query is permitted"))
    source = SimpleNamespace(read=lambda: reply)
    snapshot = status.Snapshot("Website host", master="http://approved-room-master", controller=source)
    snapshot.collect()
    room = snapshot.read()["room"]
    assert room["state"] == "unavailable" and room["observation_age_s"] is None
