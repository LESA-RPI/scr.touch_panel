"""Bounded reads from the existing owner; no hardware or Unix socket is needed."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "browser"))
import controller


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
    monkeypatch.setattr(controller.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(controller.socket, "socket", lambda *args: connection)
    monkeypatch.setattr(controller.time, "monotonic", lambda: connection.now)
    return connection


def test_trickled_owner_reply_has_one_absolute_deadline(transport):
    transport.parts = [b'{', b'"', b'a', b'"', b':1}\n']
    with pytest.raises(TimeoutError, match="deadline"):
        controller.Controller("owner.sock").exchange({"op": "read"})
    assert len(transport.parts) == 2
    assert transport.timeouts[-3:] == pytest.approx([2.8, 1.8, 0.8])
    assert transport.sent == [b'{"op": "read"}\n']


def test_complete_owner_reply_stops_at_first_line(transport):
    transport.parts = [b'{"available":', b'true}\nunused']
    assert controller.Controller("owner.sock").read() == {"available": True}


@pytest.mark.parametrize("raw", [b'null\n', b'[]\n', b'{"x":NaN}\n', b'{"x":Infinity}\n', b'{}'])
def test_unusable_owner_snapshot_disables_controls(transport, raw):
    transport.parts = [raw]
    value = controller.Controller("owner.sock").read()
    assert value["available"] is False
    assert "unavailable" in value["detail"]


def test_owner_reply_size_limit_remains_bounded(transport):
    transport.advance = 0
    transport.parts = [b' ' * 4096] * 16 + [b' ']
    assert controller.Controller("owner.sock").read()["available"] is False
    assert len(transport.sent) == 1
    assert transport.parts == []
