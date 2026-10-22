"""Legacy functions share one bounded owner, with no work during navigation."""

from types import SimpleNamespace
import json

import pytest

from test_scr_touch_panel import Room, adapter


class Devices(Room):
    def __init__(self):
        super().__init__()
        self.actions = []
        self.fail_at = None

    def call(self, name, *args):
        if name == "sources":
            self.actions.append((name, args))
            values, xy = args[:8], tuple(args[8:])
            self.state[xy] = adapter.setter_words(values)
            if len(self.actions) == self.fail_at:
                raise TimeoutError("fixture reply lost after dispatch")
            return SimpleNamespace(cmdstr=str([v / 100 for v in values]))
        if name in ("lift_all", "tilt_all"):
            self.actions.append((name, args))
            return SimpleNamespace(**{"lift" if name == "lift_all" else "tilt": args[0]})
        return super().call(name, *args)


class Programmes:
    def __init__(self):
        self.requests = []

    def stop(self):
        self.requests.append("stop both")

    def start(self, name):
        self.requests.append(name)


def owner(room, **kwargs):
    return adapter.Lights(room.call, keep_settings=True, sleep=lambda seconds: None, **kwargs)


def test_gradient_reproduces_original_ten_fixture_pattern_and_release_does_nothing():
    room = Devices()
    lights = owner(room)
    lights.acquire()
    result = lights.apply_gradient()
    expected = dict((xy, adapter.setter_words(values)) for xy, values in adapter.GRADIENT.items())
    assert room.state == expected and len(room.actions) == 10
    assert not room.writes  # Never replace the spatial pattern with sources_all.
    assert result["scene"] == "Gradient" and result["power"] == "on"
    assert "words" not in result and len(result["fixture_words"]) == 10
    assert result["manual_blocked"] is False
    assert lights.release()["preserved"]
    assert room.state == expected and len(room.actions) == 10


def test_partial_gradient_failure_blocks_retry_and_release():
    room = Devices()
    room.fail_at = 3
    lights = owner(room)
    lights.acquire()
    with pytest.raises(TimeoutError):
        lights.apply_gradient()
    with pytest.raises(ValueError, match="unavailable"):
        lights.apply_gradient()
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert len(room.actions) == 3


def test_gradient_still_restores_starting_scene_in_bounded_trial():
    room = Devices()
    initial = dict(room.state)
    lights = adapter.Lights(room.call)
    lights.acquire()
    lights.apply_gradient()
    assert lights.release()["restored"] and room.state == initial


@pytest.mark.parametrize("name", ["Sun", "Circ"])
def test_programme_uses_existing_owner_and_survives_interface_release(name):
    room, programmes = Devices(), Programmes()
    lights = owner(room, programmes=programmes)
    lights.acquire()
    result = lights.run_programme(name)
    assert programmes.requests == ["stop both", name]
    assert result["programme"] == name and result["programme_confirmed"] is False
    assert result["manual_blocked"] and "accepted" in result["detail"]
    assert room.actions == room.writes == []
    lights.release()
    assert programmes.requests == ["stop both", name]


def test_stop_is_available_without_baseline_and_qualifies_static_controls():
    room, programmes = Devices(), Programmes()
    lights = owner(room, programmes=programmes)
    result = lights.run_programme("Stop")
    assert result["programme"] is None and not result["manual_blocked"]
    assert not result["programme_confirmed"] and lights.baseline == room.state
    lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert programmes.requests == ["stop both", "stop both"]
    assert len(room.writes) == 1


def test_manual_command_stops_original_programme_and_rebases_after_quiescence():
    room, programmes = Devices(), Programmes()
    lights = owner(room, programmes=programmes)
    lights.acquire()
    lights.run_programme("Sun")
    room.state = dict.fromkeys(room.state, adapter.setter_words(adapter.PRESETS["Dul"]))
    result = lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert programmes.requests == ["stop both", "Sun", "stop both"]
    assert result["programme"] is None and not result["manual_blocked"]
    assert len(room.writes) == 1


def test_moving_readback_after_stop_blocks_manual_write_and_automatic_retry():
    room, programmes = Devices(), Programmes()
    count = []

    def changing(name, *args):
        if name == "get_lights":
            count.append(True)
            room.state[min(room.state)] = (len(count),) * 8
        return room.call(name, *args)

    lights = adapter.Lights(changing, keep_settings=True, programmes=programmes,
                            sleep=lambda seconds: None)
    with pytest.raises(ValueError, match="still changing"):
        lights.run_programme("Stop")
    with pytest.raises(ValueError, match="unavailable"):
        lights.apply("channels", {"values": list(adapter.PRESETS["Sat"])})
    assert programmes.requests == ["stop both"] and not room.writes


@pytest.mark.parametrize(
    "name, expected", [("lift", [("lift_all", (100,))]),
                       ("open", [("tilt_all", (50,))]),
                       ("close", [("tilt_all", (100,)), ("lift_all", (0,))])],
)
def test_blinds_match_original_actions_without_changing_lights_or_programmes(name, expected):
    room, programmes = Devices(), Programmes()
    sleeps = []
    lights = adapter.Lights(room.call, keep_settings=True, programmes=programmes,
                            sleep=sleeps.append, blinds_connected=True)
    result = lights.move_blinds(name)
    assert room.actions == expected and room.writes == programmes.requests == []
    assert sleeps == ([2] if name == "close" else [])
    assert "physical position is not measured" in result["detail"]


def test_partial_blind_movement_blocks_second_action_and_release():
    room = Devices()

    def lost_lease():
        if room.actions:
            raise ValueError("lease ended")

    lights = adapter.Lights(room.call, can_write=lost_lease, keep_settings=True,
                            sleep=lambda seconds: None, blinds_connected=True)
    with pytest.raises(ValueError, match="lease ended"):
        lights.move_blinds("close")
    with pytest.raises(ValueError, match="unavailable"):
        lights.move_blinds("close")
    with pytest.raises(ValueError, match="unknown"):
        lights.release()
    assert room.actions == [("tilt_all", (100,))] and not lights.failed


def test_invalid_programme_and_blind_actions_have_no_side_effects():
    room, programmes = Devices(), Programmes()
    lights = owner(room, programmes=programmes, blinds_connected=True)
    for name in ("sun;anything", "auto", ""):
        with pytest.raises(ValueError, match="Unknown"):
            lights.run_programme(name)
        with pytest.raises(ValueError, match="Unknown"):
            lights.move_blinds(name)
    assert not lights.failed and not lights.blinds_failed
    assert room.actions == room.writes == programmes.requests == []


def test_status_requests_are_bounded_allowlisted_and_validate_acceptance(monkeypatch):
    import urllib.request

    requests = []
    closed = []

    def accepted(request, timeout):
        name = json.loads(request.data)["name"]
        requests.append((request.full_url, name, timeout))
        return SimpleNamespace(getcode=lambda: 202, read=lambda size: json.dumps({"name": name}).encode(),
                               close=lambda: closed.append(True))

    monkeypatch.setattr(urllib.request, "urlopen", accepted)
    client = adapter.StatusProgrammes("http://status.invalid:5000/")
    client.stop()
    client.start("Sun")
    assert [request[1] for request in requests] == ["sun", "circ", "sun"]
    assert all(request[2] == 3 for request in requests) and len(closed) == 3
    with pytest.raises(ValueError, match="Only original"):
        client.request("Run", "sun;anything")
    assert len(requests) == 3


def test_programme_stop_rechecks_lease_before_each_http_request(monkeypatch):
    import urllib.request
    requests = []
    def accepted(request, timeout):
        name = json.loads(request.data)["name"]
        requests.append(name)
        return SimpleNamespace(getcode=lambda: 202, read=lambda size: json.dumps({"name": name}).encode(), close=lambda: None)
    def lease():
        if requests:
            raise ValueError("lease ended")
    monkeypatch.setattr(urllib.request, "urlopen", accepted)
    with pytest.raises(ValueError, match="lease ended"):
        adapter.StatusProgrammes("http://status.invalid", can_write=lease).stop()
    assert requests == ["sun"]


@pytest.mark.skipif(not hasattr(__import__("signal"), "SIGALRM"), reason="Pi uses POSIX operation deadlines")
def test_trickled_http_reply_cannot_outlive_whole_programme_budget():
    import http.server
    import signal
    import threading
    import time
    class Trickle(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(202)
            self.send_header("Content-Length", "100")
            self.end_headers()
            try:
                for unused in range(10):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(.4)
            except OSError:
                pass
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Trickle)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def expired(*args):
        raise TimeoutError("operation budget expired")
    previous = signal.signal(signal.SIGALRM, expired)
    started = adapter.clock()
    try:
        client = adapter.StatusProgrammes("http://127.0.0.1:%d" % server.server_port,
                                         deadline=lambda: started + .2)
        with pytest.raises(TimeoutError, match="operation budget"):
            client.start("Sun")
        assert adapter.clock() - started < 2
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        server.shutdown()
        server.server_close()
