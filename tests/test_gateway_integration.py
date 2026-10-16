"""Real HTTP and private socket transport, with a mocked room controller only."""

import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "browser"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from controller import Controller
from test_browser_status import status, request, server
from panel_control import Bridge
from panel_remote import execute
import panel_remote


@pytest.fixture
def owner_socket(tmp_path, monkeypatch):
    pytest.importorskip("fcntl")
    bridge = Bridge(str(tmp_path / "owner.sock"))
    calls = []
    current = {"revision": "current", "busy": False, "can_control": True}

    def preset(name):
        calls.append(name)
        current["revision"] = "after-write"
        # Model a lost controller response: future writes stay blocked.
        current["can_control"] = False

    owner = SimpleNamespace(
        idle_active=False,
        preset=preset,
        pending=None,
        emit=lambda *a, **kw: None,
        activity=lambda *a: None,
    )
    monkeypatch.setattr(panel_remote, "snapshot", lambda panel: dict(current))
    stopped = threading.Event()
    paused = threading.Event()

    def drain():
        while not stopped.wait(0.01):
            if not paused.is_set():
                bridge.drain(lambda: dict(current), lambda value: execute(owner, value))

    worker = threading.Thread(target=drain, daemon=True)
    worker.start()
    try:
        yield bridge, calls, current, paused
    finally:
        stopped.set()
        worker.join(3)
        bridge.close()


def test_http_socket_duplicate_stale_and_uncertain_results(server, owner_socket):
    bridge, calls, current, paused = owner_socket
    server.controller = Controller(str(bridge.path))
    headers = {
        "Origin": "http://" + server.expected_host,
        "X-SCR-Token": server.control_nonce,
        "Content-Type": "application/json",
    }
    value = {
        "id": "socket-command-00001",
        "revision": "current",
        "action": "preset",
        "arguments": {"name": "Sat"},
    }

    def send(value):
        code, raw, _ = request(
            server, "POST", "/api/command", headers, json.dumps(value)
        )
        return code, json.loads(raw)

    first = send(value)
    assert first[0] == 202 and calls == ["Sat"]
    assert send(value) == first and calls == ["Sat"]
    assert send(dict(value, arguments={"name": "Dul"}))[0] == 409
    assert send(dict(value, id="socket-command-00002"))[0] == 409
    assert (
        send(dict(value, id="socket-command-00003", revision="after-write"))[0] == 409
    )
    assert calls == ["Sat"]
    code, raw, _ = request(server, "GET", "/api/controller")
    snapshot = json.loads(raw)
    assert code == 200 and not snapshot["can_control"]
    assert any(
        r["id"] == value["id"] and r["code"] == 202 for r in snapshot["receipts"]
    )


def test_socket_timeout_expires_without_late_write_or_automatic_retry(
    server, owner_socket
):
    bridge, calls, current, paused = owner_socket
    paused.set()
    server.controller = Controller(str(bridge.path))
    headers = {
        "Origin": "http://" + server.expected_host,
        "X-SCR-Token": server.control_nonce,
        "Content-Type": "application/json",
    }
    value = {
        "id": "expired-socket-command-01",
        "revision": "current",
        "action": "preset",
        "arguments": {"name": "Sat"},
    }
    code, raw, _ = request(server, "POST", "/api/command", headers, json.dumps(value))
    assert code == 503 and "do not retry" in json.loads(raw)["detail"]
    paused.clear()
    limit = time.monotonic() + 2
    while not bridge.requests.empty() and time.monotonic() < limit:
        time.sleep(0.01)
    assert bridge.requests.empty() and not calls


def test_power_replay_keeps_original_receipt_after_owner_state_changes():
    import collections
    import queue

    bridge = Bridge.__new__(Bridge)
    bridge.lock = threading.Lock()
    bridge.requests = queue.Queue()
    bridge.receipts = collections.OrderedDict()
    bridge.fingerprints = {}
    calls = []
    revision = ["current"]
    value = {
        "id": "confirmed-power-replay-01",
        "revision": "current",
        "action": "power",
        "arguments": {"operation": "reboot", "confirmed": True},
    }

    def execute_power(value):
        calls.append(value)
        revision[0] = "saving-and-releasing"
        return {"ok": True, "code": 202}

    for unused in range(2):
        item = {
            "value": value,
            "deadline": time.monotonic() + 2,
            "cancelled": False,
            "done": threading.Event(),
        }
        bridge.requests.put(item)
        bridge.drain(lambda: {"revision": revision[0]}, execute_power)
        assert item["reply"]["code"] == 202
    assert calls == [value]
