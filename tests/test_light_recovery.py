"""Connection checks observe the room without claiming or restoring control."""

import builtins
import json
import os
import sys
from types import SimpleNamespace

import pytest

from test_scr_touch_panel import Room, adapter


class Programmes:
    def stop(self):
        pytest.fail("A connection check must not stop a programme")

    def start(self, name):
        pytest.fail("A connection check must not start a programme")


class LegacyProgrammes:
    def __init__(self, stop=None):
        self.requests, self.on_stop = [], stop

    def stop(self):
        self.requests.append("stop")
        if self.on_stop:
            self.on_stop()

    def start(self, name):
        pytest.fail("Returning from Legacy must not start a programme")


def observer(room, **kwargs):
    return adapter.Lights(room.call, observe_only=True, programmes=Programmes(),
                          sleep=lambda seconds: None, **kwargs)


@pytest.mark.parametrize("preset", ["Off", "Fid", "Sat", "Dul", None])
def test_check_reads_each_fixture_twice_and_preserves_any_scene(preset):
    room = Room()
    room.state = (dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS[preset]))
                  if preset else
                  {xy: tuple(index * 1000 + channel for channel in range(8))
                   for index, xy in enumerate(sorted(room.state))})
    original, reads = dict(room.state), []
    original_call = room.call

    def call(name, *args):
        reads.append((name, args))
        return original_call(name, *args)

    room.call = call
    lights = observer(room)
    result = lights.check()
    assert result["state"] == "checked" and result["stable"]
    assert result["fixtures"] == 10 and result["baseline"] == preset
    assert result["fixture_words"] == [[list(xy), list(values)]
                                        for xy, values in sorted(original.items())]
    assert result["power"] == ("off" if preset == "Off" else "on")
    assert result["manual_blocked"] and result["observation_only"]
    assert result["ownership_verified"] is False
    assert not result["capabilities"]["programmes"]
    assert reads.count(("get_lights", ())) == 2
    assert all(reads.count(("get_sources", xy)) == 2 for xy in adapter.COORDINATES)
    assert len(reads) == 22
    assert lights.baseline is lights.current is None
    assert lights.release()["preserved"]
    assert room.state == original and not room.writes


@pytest.mark.parametrize("persistent", [False, True])
def test_observer_rejects_all_actuators_and_acquisition_even_with_keep_settings(persistent):
    room = Room()
    lights = observer(room, keep_settings=persistent, blinds_connected=True)
    actions = [lights.acquire, lights.apply_gradient, lights.prepare_manual,
               lights.stop_programmes, lambda: lights.run_programme("Sun"),
               lambda: lights.run_programme("Stop"), lambda: lights.move_blinds("close"),
               lambda: lights.apply("channels", {"values": [0] * 8}),
               lambda: lights.apply("cct", {"cct": 3500, "intensity": 200})]
    for action in actions:
        with pytest.raises(ValueError):
            action()
    assert not room.writes
    assert lights.release()["preserved"]


def test_unstable_check_is_unconfirmed_and_never_stops_programmes_or_restores():
    room, scans = Room(), []
    original_call = room.call

    def call(name, *args):
        if name == "get_lights":
            scans.append(True)
            if len(scans) == 2:
                room.state[min(room.state)] = (1,) * 8
        return original_call(name, *args)

    room.call = call
    lights = observer(room)
    result = lights.check()
    assert result["state"] == "failed" and result["stable"] is False
    assert result["manual_blocked"] and result["ownership_verified"] is False
    assert lights.release()["preserved"] and not room.writes


@pytest.mark.parametrize("identities", [list(adapter.COORDINATES)[:-1],
                                       [(0, 0)] * 10,
                                       list(adapter.COORDINATES)[:-1] + [(9, 9)]])
def test_check_rejects_missing_duplicate_or_foreign_fixture_identities(identities):
    calls = []

    def call(name, *args):
        calls.append(name)
        return SimpleNamespace(lights=[v for xy in identities for v in xy])

    lights = adapter.Lights(call, observe_only=True)
    with pytest.raises(ValueError, match="identities"):
        lights.check()
    assert calls == ["get_lights"]
    assert lights.release()["preserved"]


@pytest.mark.parametrize("persistent", [False, True])
def test_failed_read_does_not_restore_or_grant_control(persistent):
    room = Room()
    lights = observer(room, keep_settings=persistent)

    def timeout(name, *args):
        raise RuntimeError("Whole lighting operation exceeded 30 seconds")

    lights.call = timeout
    with pytest.raises(RuntimeError, match="30 seconds"):
        lights.check()
    assert lights.release()["preserved"] and not room.writes
    assert lights.capabilities()["manual_blocked"]


def test_later_matching_check_cannot_clear_an_uncertain_write():
    room = Room()
    lights = adapter.Lights(room.call, keep_settings=True, sleep=lambda seconds: None)
    lights.acquire()
    room.lose_response = True
    with pytest.raises(TimeoutError):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    result = lights.check()
    assert result["stable"] and result["state"] == "failed"
    assert result["baseline"] == "Sat" and result["outcome_unknown"]
    assert lights.failed and result["manual_blocked"]
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert len(room.writes) == 1


def test_check_after_external_change_blocks_owner_without_adopting_new_baseline():
    room = Room()
    lights = adapter.Lights(room.call, keep_settings=True, sleep=lambda seconds: None)
    lights.acquire()
    expected = dict(lights.current)
    room.state = dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS["Dul"]))
    result = lights.check()
    assert result["stable"] and result["state"] == "failed"
    assert result["baseline"] == "Dul" and result["manual_blocked"]
    assert lights.current == lights.baseline == expected
    with pytest.raises(ValueError, match="unavailable"):
        lights.apply("channels", {"values": [0] * 8})
    assert not room.writes


def test_check_timeout_blocks_bounded_trial_from_automatic_restore():
    room = Room()
    lights = adapter.Lights(room.call, sleep=lambda seconds: None)
    lights.acquire()
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})

    def timeout():
        raise TimeoutError("No fixture response")

    lights.read = timeout
    with pytest.raises(TimeoutError):
        lights.check()
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert len(room.writes) == 1


@pytest.mark.parametrize("preset", ["Off", "Fid", None])
def test_legacy_return_stops_programmes_and_reads_exactly_twice_without_changing_scene(preset):
    room = Room()
    room.state = (dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS[preset]))
                  if preset else
                  {xy: tuple(index * 1000 + channel for channel in range(8))
                   for index, xy in enumerate(sorted(room.state))})
    original, calls = dict(room.state), []
    programmes = LegacyProgrammes()

    def call(name, *args):
        calls.append((name, args))
        assert programmes.requests == ["stop"]
        return room.call(name, *args)

    lights = adapter.Lights(call, keep_settings=True, programmes=programmes,
                            sleep=lambda seconds: None)
    result = lights.return_legacy()
    assert result["state"] == "ready" and result["manual_blocked"] is False
    assert result["baseline"] == preset and result["fixtures"] == 10
    assert result["power"] == ("off" if preset == "Off" else "on")
    assert result["fixture_words"] == [[list(xy), list(values)]
                                        for xy, values in sorted(original.items())]
    assert calls.count(("get_lights", ())) == 2
    assert all(calls.count(("get_sources", xy)) == 2 for xy in adapter.COORDINATES)
    assert len(calls) == 22 and not room.writes
    assert lights.release()["preserved"] and room.state == original


@pytest.mark.parametrize("persistent, observing, configured", [
    (False, False, True), (True, True, True), (True, False, False),
])
def test_legacy_return_requires_persistent_writable_configured_status(
    persistent, observing, configured,
):
    room, programmes = Room(), LegacyProgrammes()
    lights = adapter.Lights(room.call, keep_settings=persistent, observe_only=observing,
                            programmes=programmes if configured else None)
    with pytest.raises(ValueError, match="requires"):
        lights.return_legacy()
    assert lights.failed and not room.writes and not programmes.requests
    if observing:
        assert lights.release()["preserved"]
    else:
        with pytest.raises(ValueError, match="unknown"):
            lights.release()


def test_legacy_return_lost_stop_response_latches_failure_without_fixture_reads_or_retry():
    room = Room()

    def timeout():
        raise TimeoutError("Status stop response lost")

    programmes = LegacyProgrammes(timeout)
    reads = []

    def call(name, *args):
        reads.append(name)
        return room.call(name, *args)

    lights = adapter.Lights(call, keep_settings=True, programmes=programmes)
    with pytest.raises(TimeoutError, match="response lost"):
        lights.return_legacy()
    with pytest.raises(ValueError, match="requires"):
        lights.return_legacy()
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert programmes.requests == ["stop"] and reads == [] and not room.writes


def test_legacy_return_unstable_readback_fails_without_retry_or_restore():
    room, scans = Room(), []

    def call(name, *args):
        if name == "get_lights":
            scans.append(True)
            if len(scans) == 2:
                room.state[min(room.state)] = (1,) * 8
        return room.call(name, *args)

    programmes = LegacyProgrammes()
    lights = adapter.Lights(call, keep_settings=True, programmes=programmes,
                            sleep=lambda seconds: None)
    with pytest.raises(ValueError, match="still changing"):
        lights.return_legacy()
    assert lights.failed and lights.baseline is None
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert programmes.requests == ["stop"] and len(scans) == 2 and not room.writes


def test_legacy_return_read_timeout_never_retries_stop_or_changes_fixtures():
    room, reads = Room(), []

    def call(name, *args):
        reads.append(name)
        raise TimeoutError("Fixture readback expired")

    programmes = LegacyProgrammes()
    lights = adapter.Lights(call, keep_settings=True, programmes=programmes,
                            sleep=lambda seconds: None)
    with pytest.raises(TimeoutError):
        lights.return_legacy()
    assert lights.failed and programmes.requests == ["stop"]
    assert reads == ["get_lights"] and not room.writes


@pytest.mark.parametrize("code, name", [(500, "sun"), (202, "other")])
def test_legacy_return_rejects_unmatched_or_failed_http_stop(monkeypatch, code, name):
    import urllib.request

    requests = []

    def open_request(request, timeout):
        requests.append(request.full_url)
        return SimpleNamespace(getcode=lambda: code,
                               read=lambda size: json.dumps({"name": name}).encode(),
                               close=lambda: None)

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    room = Room()
    programmes = adapter.StatusProgrammes("http://status.invalid")
    lights = adapter.Lights(room.call, keep_settings=True, programmes=programmes)
    with pytest.raises(ValueError, match="accept|match"):
        lights.return_legacy()
    assert lights.failed and len(requests) == 1 and not room.writes


@pytest.mark.parametrize("mode", ["stable", "changing", "timeout", "budget"])
def test_observation_main_loop_never_dispatches_a_write_or_restores(
    tmp_path, monkeypatch, capsys, mode,
):
    """Exercise the actual CLI, protocol and finally path with fake ROS only."""
    import xmlrpc.client

    room, calls, reads, now = Room(), [], [], [100.0]
    original_call = room.call

    def service(name, unused_type):
        assert name in ("get_lights", "get_sources")

        def invoke(*args):
            calls.append((name, args))
            if mode == "timeout":
                raise TimeoutError("No fixture response")
            if name == "get_lights":
                reads.append(True)
                if mode == "changing" and len(reads) == 2:
                    room.state[min(room.state)] = (1,) * 8
                if mode == "budget":
                    now[0] += 31
            return original_call(name, *args)

        return invoke

    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(
        LOCK_EX=1, LOCK_NB=2, flock=lambda *args: None))
    monkeypatch.setitem(sys.modules, "rospy", SimpleNamespace(
        init_node=lambda *args, **kwargs: None, ServiceProxy=service))
    service_types = SimpleNamespace(**{name: object for name in (
        "GetLights", "GetSources", "OctaLight_sourcesAll", "OctaLight_CCTAll",
        "OctaLight_sources", "BlindLiftAll", "BlindTiltAll")})
    monkeypatch.setitem(sys.modules, "scr_control", SimpleNamespace(srv=service_types))
    monkeypatch.setitem(sys.modules, "scr_control.srv", service_types)
    monkeypatch.setattr(xmlrpc.client, "ServerProxy", lambda *args: SimpleNamespace(
        getSystemState=lambda *args: [1, "ok", [[], [], []]]))
    monkeypatch.setattr(adapter, "StatusProgrammes", lambda *args: pytest.fail(
        "An observation process must not connect a programme actuator"))
    monkeypatch.setattr(adapter, "clock", lambda: now[0])
    monkeypatch.setattr(adapter.signal, "SIGALRM", 14, raising=False)
    monkeypatch.setattr(adapter.signal, "alarm", lambda *args: None, raising=False)
    monkeypatch.setattr(adapter.signal, "signal", lambda *args: None)
    monkeypatch.setattr(adapter.os, "getppid", lambda: 123)
    monkeypatch.setattr(adapter.socket, "setdefaulttimeout", lambda *args: None)
    monkeypatch.setenv("ROS_MASTER_URI", "http://room.invalid:11311")
    monkeypatch.setattr(sys, "argv", ["helper", "--observe-only", "--receipt",
        str(tmp_path / "receipt.jsonl"), "--parent-pid", "123", "--expected-master",
        "http://room.invalid:11311", "--status-url", "http://status.invalid"])

    # Keep lock and directory durability operations local and portable to Windows.
    real_open, real_os_open = builtins.open, os.open
    directory_file = tmp_path / "directory"
    directory_file.write_text("")
    monkeypatch.setattr(builtins, "open", lambda path, *args, **kwargs: real_open(
        str(tmp_path / "owner.lock") if path == "/tmp/scr-panel-light-owner.lock" else path,
        *args, **kwargs))
    monkeypatch.setattr(adapter.os, "O_DIRECTORY", 0, raising=False)
    monkeypatch.setattr(adapter.os, "open", lambda path, flags, *args: real_os_open(
        str(directory_file) if os.path.isdir(path) else path, flags, *args))
    monkeypatch.setattr(adapter.os, "fsync", lambda descriptor: None)

    ready, supplied = [False], [False]
    stdin = SimpleNamespace(fileno=lambda: 99)
    monkeypatch.setattr(sys, "stdin", stdin)

    def select(streams, writes, errors, timeout):
        if timeout:
            ready[0] = True
        return ([stdin] if ready[0] else [], [], [])

    def read(descriptor, size):
        assert descriptor == 99
        ready[0] = False
        if supplied[0]:
            return b""
        supplied[0] = True
        return (json.dumps({"version": 1, "action": "check", "request_id": "check:1",
                            "sent_monotonic_s": now[0]}) + "\n").encode("utf-8")

    monkeypatch.setattr(adapter.select, "select", select)
    monkeypatch.setattr(adapter.os, "read", read)
    assert adapter.main() == 0
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0]["observation_only"] and output[0]["manual_blocked"]
    result = output[1]
    assert result["state"] == ("checked" if mode == "stable" else "failed")
    assert result["stable"] is (mode == "stable")
    assert result["manual_blocked"] and not room.writes
    journal = [json.loads(line) for line in (tmp_path / "receipt.jsonl").read_text().splitlines()]
    assert journal[-1]["event"] == "closed"
    assert journal[-1]["result"]["preserved"]
    assert journal[-1]["result"]["restored"] is False
    assert calls and all(name in ("get_lights", "get_sources") for name, args in calls)
