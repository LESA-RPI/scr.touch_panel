"""The browser may submit only bounded commands to the existing UI owner."""

import queue
import threading
import time
from types import SimpleNamespace
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from panel_control import command, Bridge
from panel_remote import execute
from panel_remote import snapshot
from design_tokens import THEMES


def envelope(action="off", arguments=None, revision="current", id="test-command-00001"):
    return {
        "id": id,
        "revision": revision,
        "action": action,
        "arguments": arguments or {},
    }


def test_commands_reject_blinds_shell_paths_extra_fields_and_invalid_numbers():
    for value in [
        envelope("blinds"),
        envelope("shell", {"command": "echo hi"}),
        dict(envelope(), path="/tmp/x"),
        envelope("cct", {"cct": True, "intensity": 1000}),
        envelope("channels", {"values": [100] * 7}),
        envelope("channels", {"values": [101] * 8}),
        envelope("idle", {"value": True}),
        envelope("blinds_display", {"value": "enabled"}),
        envelope([], {}),
        envelope("cct", {"cct": 3500, "intensity": 1901}),
    ]:
        with pytest.raises(ValueError):
            command(value)
    assert command(envelope("cct", {"cct": 3500, "intensity": 1000}))["action"] == "cct"


def test_stale_expired_and_duplicate_commands_never_dispatch_twice():
    bridge = Bridge.__new__(Bridge)
    import collections

    bridge.requests = queue.Queue()
    bridge.receipts = collections.OrderedDict()
    bridge.fingerprints = {}
    bridge.lock = threading.Lock()
    calls = []

    def put(value, expired=False):
        item = {
            "value": value,
            "deadline": time.monotonic() + (-1 if expired else 2),
            "cancelled": False,
            "done": threading.Event(),
        }
        bridge.requests.put(item)
        bridge.drain(
            lambda: {"revision": "current"},
            lambda value: calls.append(value) or {"ok": True, "code": 202},
        )
        return item["reply"]

    assert put(envelope(revision="old"))["code"] == 409 and not calls
    assert put(envelope(), True)["code"] == 408 and not calls
    first = put(envelope())
    assert first["ok"] and len(calls) == 1
    assert put(envelope()) == first and len(calls) == 1
    assert put(envelope("on"))["code"] == 409 and len(calls) == 1


def test_remote_light_action_is_blocked_when_owner_busy_uncertain_legacy_or_studying(
    monkeypatch,
):
    import panel_remote

    owner = SimpleNamespace(lights_on=lambda: pytest.fail("Must not call the owner"))
    for state in (
        {"busy": True, "can_control": True},
        {"busy": False, "can_control": False},
    ):
        monkeypatch.setattr(panel_remote, "snapshot", lambda panel: state)
        with pytest.raises(RuntimeError):
            execute(owner, envelope("on"))
    sent = []
    monkeypatch.setattr(
        panel_remote, "snapshot", lambda panel: {"busy": False, "can_control": True}
    )
    owner = SimpleNamespace(
        idle_active=False,
        lights_on=lambda: sent.append("existing owner"),
        emit=lambda *a, **kw: None,
        activity=lambda *a: None,
        pending=None,
    )
    assert execute(owner, envelope("on"))["ok"] and sent == ["existing owner"]


def test_theme_text_contrast_neutral_dark_surfaces_and_semantic_accents():
    def rgb(value):
        return [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]

    def light(value):
        return sum(
            c * w
            for c, w in zip(
                [
                    c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in rgb(value)
                ],
                (0.2126, 0.7152, 0.0722),
            )
        )

    def ratio(a, b):
        high, low = sorted((light(a), light(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for theme in THEMES.values():
        for fg, bg in [
            ("ink", "bg"),
            ("muted", "bg"),
            ("ink", "control"),
            ("muted", "control"),
            ("selected_ink", "accent"),
            ("selected_ink", "accent_pressed"),
            ("ink", "pressed"),
            ("good", "control"),
            ("warning", "control"),
            ("warning", "bg"),
        ]:
            assert ratio(theme[fg], theme[bg]) >= 4.5, (fg, bg, theme)
    assert all(
        len(set(rgb(THEMES["dark"][key]))) == 1
        for key in ("bg", "surface", "control", "border", "pressed")
    )
    assert len(set(rgb(THEMES["dark"]["accent"]))) > 1


def test_blind_permission_is_strict_and_independent_of_visibility_and_connection():
    import preferences
    from scr_touch_panel import Panel

    assert preferences.validated({}) == {}  # old files retain the disabled default
    assert preferences.validated({"blinds_enabled": False}) == {"blinds_enabled": False}
    for invalid in (1, 0, "true", None):
        with pytest.raises(ValueError):
            preferences.validated({"blinds_enabled": invalid})
        with pytest.raises(ValueError):
            command(envelope("blinds_enabled", {"value": invalid}))
    state = Panel.__new__(Panel)
    state.pending = state.queued_intent = state.release_target = state.closing = None
    state.running = False
    state.mode = "room"
    state.blinds_display = "hidden"
    state.blinds_enabled = False
    state.blind_controller = None
    messages = []
    calls = []
    state.status_text = SimpleNamespace(set=messages.append)
    for name in ("lift", "open", "close"):
        assert command(envelope("blind", {"name": name}))
        assert not state.blind_command(name)
    assert state.blind_state()["detail"] == "Disabled"
    assert state.blind_state()["reason"] == "Controls locked in settings"
    state.blinds_enabled = True
    assert not state.blind_command("open")
    assert state.blind_state()["detail"] == "Disabled"
    assert state.blind_state()["reason"] == "Controller not connected"
    state.blind_controller = SimpleNamespace(connected=True, submit=calls.append)
    for field, value in [
        ("pending", {}),
        ("queued_intent", True),
        ("release_target", "original"),
        ("closing", True),
        ("running", True),
        ("mode", "original"),
    ]:
        previous = getattr(state, field)
        setattr(state, field, value or True)
        assert not state.blind_command("lift")
        setattr(state, field, previous)
    assert calls == []
    for name in ("lift", "open", "close"):
        assert state.blind_command(name)
    assert calls == ["lift", "open", "close"]
    with pytest.raises(ValueError):
        state.blind_command("shell")
    state.blinds_enabled = False
    assert not state.blind_command("open") and len(calls) == 3


def test_remote_blind_action_uses_owner_readiness_and_never_bypasses_setting(
    monkeypatch,
):
    import panel_remote

    calls = []
    owner = SimpleNamespace(
        blind_command=lambda name: calls.append(name) or True,
        emit=lambda *a, **kw: None,
        activity=lambda *a: None,
        pending=None,
    )
    for available in (False, True):
        monkeypatch.setattr(
            panel_remote,
            "snapshot",
            lambda panel: {
                "busy": False,
                "blinds": {"available": available, "detail": "Disabled in settings"},
            },
        )
        if not available:
            with pytest.raises(RuntimeError):
                execute(owner, envelope("blind", {"name": "lift"}))
            assert not calls
        else:
            assert execute(owner, envelope("blind", {"name": "lift"}))["ok"]
    assert calls == ["lift"]


@pytest.fixture
def remote_owner():
    """Complete cached presentation state; every action stays inside this fake owner."""
    def variable(value):
        return SimpleNamespace(get=lambda: value)

    owner = SimpleNamespace(
        args=SimpleNamespace(live_lights=True, timezone="America/New_York", light_at=420, dark_at=1140),
        pending=None, queued_intent=None, release_target=None, closing=None,
        press_active=False, running=False, idle_active=False,
        light_state="ready", mode="room", elapsed=0, run_started=time.monotonic(),
        run_id="owner", sequence=1, view_generation=1,
        confirmed_power="on", confirmed_scene="Fid", confirmed_light="Fid scene",
        confirmed_at=None, light_message="Light settings confirmed.",
        cct=variable(3500), intensity=variable(1000),
        channel_values=[variable(25) for _ in range(8)],
        theme_choice="light", theme="light", clock_24=False, temperature_unit="f",
        idle_timeout=300, help_on=True, blinds_display="disabled", blinds_enabled=False,
        profile={"title":"Practice", "stages":["Pause"], "annotations":[]}, stage=0,
        annotation_text=variable(""), weather_reading=None, weather_good=None,
        health_cache={}, room_status="Not checked",
        blind_state=lambda: {"available":False},
        emit=lambda *args, **kwargs: None, activity=lambda *args: None,
    )
    for name, value in THEMES["light"].items():
        setattr(owner, name, value)
    owner.calls = []
    owner.lights_on = lambda: owner.calls.append(owner.mode)
    return owner


@pytest.mark.parametrize("mode", ["room", "classic", "guide", "settings", "health", "about", "advanced", "experiment", "visitor"])
def test_remote_lighting_uses_current_owner_without_changing_beta_page(remote_owner, mode):
    remote_owner.mode = mode
    assert snapshot(remote_owner)["can_control"] is True
    assert execute(remote_owner, envelope("on"))["ok"]
    assert remote_owner.calls == [mode]
    assert remote_owner.mode == mode


@pytest.mark.parametrize("field,value", [
    ("mode", "original"), ("mode", "black"), ("running", True),
    ("pending", {"request_id":"pending"}), ("queued_intent", {"action":"on"}),
    ("release_target", "original"), ("closing", "exit"), ("press_active", True),
    ("light_state", "failed"), ("light_state", "connecting"),
    ("power_busy", lambda: True),
])
def test_remote_lighting_keeps_safety_locks_on_every_beta_page(remote_owner, field, value):
    remote_owner.mode = "guide"
    setattr(remote_owner, field, value)
    assert snapshot(remote_owner)["can_control"] is False
    with pytest.raises(RuntimeError):
        execute(remote_owner, envelope("on"))
    assert not remote_owner.calls


@pytest.mark.parametrize("field,value", [
    ("running", True), ("pending", {"request_id": "pending"}),
    ("queued_intent", {"action": "on"}), ("release_target", "original"),
    ("closing", "exit"), ("press_active", True), ("light_state", "failed"),
    ("light_state", "connecting"), ("power_busy", lambda: True),
])
def test_remote_classic_keeps_every_owner_safety_lock(remote_owner, field, value):
    remote_owner.mode = "classic"
    setattr(remote_owner, field, value)
    assert snapshot(remote_owner)["can_control"] is False
    with pytest.raises(RuntimeError):
        execute(remote_owner, envelope("on"))
    assert not remote_owner.calls and remote_owner.mode == "classic"


@pytest.mark.parametrize("running", [False, True])
def test_remote_legacy_opens_original_only_when_instructions_are_paused(remote_owner, running):
    remote_owner.running = running
    remote_owner.show = lambda mode: (remote_owner.calls.append(mode), setattr(remote_owner, "mode", mode))
    if running:
        with pytest.raises(RuntimeError, match="Pause"):
            execute(remote_owner, envelope("legacy"))
        assert not remote_owner.calls
    else:
        assert execute(remote_owner, envelope("legacy"))["ok"]
        assert remote_owner.calls == ["original"] and remote_owner.mode == "original"
    assert remote_owner.running is running


def test_extended_lighting_commands_keep_bounded_public_shapes():
    assert command(envelope("gradient"))["action"] == "gradient"
    for name in ("Sun", "Circ", "Stop"):
        assert command(envelope("programme", {"name": name}))["arguments"] == {"name": name}
    for value in (
        envelope("gradient", {"target": "all"}),
        envelope("programme", {"name": "arbitrary script"}),
        envelope("programme", {"name": True}),
        envelope("programme", {"name": "Sun", "path": "/tmp/programme"}),
    ):
        with pytest.raises(ValueError):
            command(value)


def test_remote_gradient_and_programme_call_existing_owner_without_navigation(remote_owner):
    remote_owner.mode = "guide"
    remote_owner.light_capabilities = {"gradient": True, "programmes": True}
    remote_owner.apply = lambda action, **values: remote_owner.calls.append((action, values))
    remote_owner.programme_command = lambda name: remote_owner.calls.append(("programme", name)) or True
    assert execute(remote_owner, envelope("gradient"))["ok"]
    assert execute(remote_owner, envelope("programme", {"name": "Stop"}))["ok"]
    assert remote_owner.calls == [("gradient", {"immediate": True}), ("programme", "Stop")]
    assert remote_owner.mode == "guide"
