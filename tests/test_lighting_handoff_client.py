"""Private ownership completion must match this experiment, never a public label."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lighting_handoff as client
from panel_control import command, handoff_command


TOKEN = "private-experiment-token-123"


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
