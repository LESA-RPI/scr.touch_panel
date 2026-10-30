"""Private ownership completion must match this experiment, never a public label."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lighting_handoff as client
from panel_control import command, handoff_command


TOKEN = "private-experiment-token-123"


@pytest.fixture
def transport(monkeypatch):
    class Socket:
        def __init__(self):
            self.parts = []
            self.now = 0
            self.advance = 1
            self.timeouts = []
            self.sent = []

        def __enter__(self):
            return self

        def __exit__(self, *unused):
            pass

        def settimeout(self, value):
            self.timeouts.append(value)

        def connect(self, path):
            self.path = path

        def sendall(self, value):
            self.sent.append(value)

        def recv(self, size):
            self.now += self.advance
            value = self.parts.pop(0) if self.parts else b""
            assert len(value) <= size
            return value

    connection = Socket()
    monkeypatch.setattr(client.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(client.socket, "socket", lambda *args: connection)
    monkeypatch.setattr(client.time, "monotonic", lambda: connection.now)
    return connection


def test_trickled_private_reply_has_one_deadline_and_one_request(transport):
    transport.parts = [b'{', b'"', b'o', b'k', b'":true}\n']
    with pytest.raises(TimeoutError, match="deadline"):
        client.exchange("owner.sock", {"op": "read"})
    assert transport.parts == [b'":true}\n']
    assert transport.timeouts[-4:] == pytest.approx([4, 3, 2, 1])
    assert transport.sent == [b'{"op": "read"}\n']


def test_private_reply_stops_at_first_complete_line(transport):
    transport.parts = [b'{"available":', b'true}\nunused']
    assert client.exchange("owner.sock", {"op": "read"}) == {"available": True}


@pytest.mark.parametrize("raw", [b'null\n', b'[]\n', b'{"x":NaN}\n', b'{"x":Infinity}\n', b'{}'])
def test_invalid_private_reply_does_not_grant_ownership(transport, raw):
    transport.parts = [raw]
    with pytest.raises((ValueError, RuntimeError), match="Invalid panel"):
        client.exchange("owner.sock", {"op": "read"})
    assert len(transport.sent) == 1


def test_private_reply_size_is_bounded(transport):
    transport.advance = 0
    transport.parts = [b' ' * 4096] * 16 + [b' ']
    with pytest.raises(RuntimeError, match="Invalid panel reply"):
        client.exchange("owner.sock", {"op": "read"})
    assert transport.parts == [] and len(transport.sent) == 1


def test_oversized_private_request_is_rejected_before_sending(transport):
    with pytest.raises(ValueError, match="too large"):
        client.exchange("owner.sock", {"label": "x" * 4096})
    assert not transport.sent


def test_private_handoff_is_not_an_ordinary_browser_command():
    value = dict(op="lighting_handoff", id="private-request-001", revision="current", action="reserve", arguments={"token": TOKEN, "label": "Experiment"})
    assert handoff_command(value)["action"] == "handoff_reserve"
    with pytest.raises(ValueError):
        command(value)
    with pytest.raises(ValueError):
        command({k: v for k, v in value.items() if k != "op"})


@pytest.mark.parametrize("arguments", [{"owner_closed": True}, {"owner_closed": True, "pending_clear": 1}, {"owner_closed": False, "pending_clear": True}])
def test_private_recovery_requires_both_explicit_true_assertions(arguments):
    with pytest.raises(ValueError):
        handoff_command(dict(op="lighting_handoff", id="private-request-002", revision="current", action="recover", arguments=arguments))


def test_reserved_snapshot_alone_cannot_grant_another_experiments_ownership(monkeypatch):
    calls = []
    def exchange(path, value):
        calls.append(value)
        if value.get("op") == "read":
            return dict(available=True, revision="current", lighting_recovery={"status": "reserved"})
        return {"ok": value["action"] == "reserve", "code": 202}
    monkeypatch.setattr(client, "exchange", exchange)
    with pytest.raises(RuntimeError, match="this experiment"):
        client.main(["--socket", "/private/socket", "reserve", "--token", TOKEN])
    actions = [v["action"] for v in calls if "action" in v]
    assert actions == ["reserve", "heartbeat"]


def test_lost_reserve_reply_is_never_replayed(monkeypatch):
    calls = []
    def exchange(path, value):
        calls.append(value)
        if value.get("op") == "read":
            return dict(available=True, revision="current")
        raise OSError("Lost acceptance")
    monkeypatch.setattr(client, "exchange", exchange)
    with pytest.raises(OSError):
        client.main(["--socket", "/private/socket", "reserve", "--token", TOKEN])
    assert len([v for v in calls if v.get("action") == "reserve"]) == 1


def test_success_confirms_token_without_printing_it(monkeypatch, capsys):
    calls = []
    def exchange(path, value):
        calls.append(value)
        return dict(available=True, revision="current", lighting_recovery={"status": "reserved"}) if value.get("op") == "read" else dict(ok=True, code=202)
    monkeypatch.setattr(client, "exchange", exchange)
    assert client.main(["--socket", "/private/socket", "reserve", "--token", TOKEN]) == 0
    assert TOKEN not in capsys.readouterr().out
    assert calls[-1]["action"] == "heartbeat" and calls[-1]["arguments"]["token"] == TOKEN
