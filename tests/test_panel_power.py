"""Exercise power commands with injected runners only; never contact the OS."""

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from panel_power import PowerActions, SYSTEMCTL
from panel_control import command
from scr_touch_panel import Panel


def result(code=0, text=""):
    return SimpleNamespace(returncode=code, stdout=text)


def test_capability_probe_never_runs_power_or_prompts_and_keeps_fixed_argv():
    calls = []

    def runner(argv):
        calls.append(argv)
        if argv == [SYSTEMCTL, "--help"]:
            return result(text="--check-inhibitors=MODE")
        if argv[0].endswith("busctl"):
            return result(text='s "challenge"')
        assert argv[:5] == ["/usr/bin/sudo", "-n", "-l", "--", SYSTEMCTL]
        assert argv[5:] in (
            ["--check-inhibitors=yes", "--no-ask-password", "reboot"],
            ["--check-inhibitors=yes", "--no-ask-password", "poweroff"],
        )
        return result()

    power = PowerActions(True, runner)
    power.worker.join(2)
    assert power.phase == "ready" and set(power.commands) == {"reboot", "shutdown"}
    assert all(argv[0] != SYSTEMCTL or argv == [SYSTEMCTL, "--help"] for argv in calls)
    with pytest.raises(RuntimeError):
        power.prepare("arbitrary-command")
    power.prepare("reboot")
    with pytest.raises(RuntimeError):
        power.execute()
    power.phase = "saving"
    # Swap only the runner after the read-only probe to record the single OS call.
    actual = []
    power.runner = lambda argv: (actual.append(argv) or result())
    power.execute()
    power.worker.join(2)
    with pytest.raises(RuntimeError):
        power.execute()
    assert actual == [
        [
            "/usr/bin/sudo",
            "-n",
            "--",
            SYSTEMCTL,
            "--check-inhibitors=yes",
            "--no-ask-password",
            "reboot",
        ]
    ]


@pytest.mark.parametrize("mode", ["unsupported", "denied", "timeout"])
def test_unavailable_permissions_never_offer_an_execution_path(mode):
    def runner(argv):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(argv, 8)
        if argv == [SYSTEMCTL, "--help"]:
            return result(text="" if mode == "unsupported" else "--check-inhibitors")
        return result(1)

    power = PowerActions(True, runner)
    power.worker.join(2)
    assert power.phase == "unavailable" and not power.commands
    with pytest.raises(RuntimeError):
        power.prepare("shutdown")


def test_uncertain_os_response_is_not_retried():
    calls = []

    def timeout(argv):
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, 8)

    power = PowerActions(runner=timeout)
    power.commands = {"shutdown": ["fake-poweroff"]}
    power.phase = "ready"
    power.prepare("shutdown")
    power.phase = "saving"
    power.execute()
    power.worker.join(2)
    assert power.phase == "failed" and len(calls) == 1
    with pytest.raises(RuntimeError):
        power.prepare("shutdown")


class Value:
    def __init__(self):
        self.value = ""

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.fixture
def owner():
    panel = Panel.__new__(Panel)
    panel.mode, panel.running, panel.light_state = "health", False, "ready"
    panel.idle_active = False
    panel.worker = object()
    panel.pending = panel.queued_intent = panel.intent_timer = panel.slider_drag = None
    panel.release_target = panel.closing = None
    panel.power = PowerActions()
    panel.power.commands = {"reboot": ["fake-reboot"], "shutdown": ["fake-poweroff"]}
    panel.power.phase = "ready"
    panel.power_text, panel.status_text = Value(), Value()
    panel.power_buttons = []
    panel.requests, panel.events, panel.os_calls = [], [], []
    panel.request = lambda action: (panel.requests.append(action) or True)
    panel.emit = lambda event, **args: (
        panel.events.append((event, args)) or len(panel.events)
    )
    panel.journal = SimpleNamespace(error=None)
    settled = threading.Event()
    panel.preferences = SimpleNamespace(error=None, settled=settled)
    panel.power.runner = lambda argv: (panel.os_calls.append(argv) or result())
    return panel


@pytest.mark.parametrize(
    "field,value",
    [
        ("running", True),
        ("pending", {}),
        ("queued_intent", ("cct",)),
        ("light_state", "failed"),
        ("mode", "original"),
        ("worker", None),
        ("closing", "signal"),
    ],
)
def test_busy_uncertain_and_legacy_states_refuse_power(owner, field, value):
    # A pending envelope is nonempty in the real controller.
    if field == "pending":
        value = {"id": "pending"}
    setattr(owner, field, value)
    with pytest.raises(RuntimeError):
        owner.request_power("reboot", confirmed=True)
    assert not owner.requests and not owner.os_calls


def test_power_waits_for_confirmed_release_helper_exit_and_durable_saves(owner):
    owner.request_power("reboot", confirmed=True)
    assert owner.requests == ["release"] and not owner.os_calls
    owner.power_cleanup_confirmed = True
    owner.worker = None
    owner.release_target = None
    owner.power_after_release(0)
    assert owner.events[-1][0] == "power_requested" and owner.power.phase == "saving"
    owner.poll_power()
    assert not owner.os_calls
    owner.power_checkpoint_saved = True
    owner.poll_power()
    assert not owner.os_calls
    owner.preferences.settled.set()
    owner.poll_power()
    owner.power.worker.join(2)
    owner.poll_power()
    assert owner.os_calls == [["fake-reboot"]] and owner.power.phase == "executing"


@pytest.mark.parametrize("confirmed,code", [(False, 0), (True, 1)])
def test_missing_cleanup_confirmation_cancels_power(owner, confirmed, code):
    owner.request_power("shutdown", confirmed=True)
    owner.power_cleanup_confirmed = confirmed
    owner.power_after_release(code)
    assert owner.power.phase == "failed" and not owner.os_calls


@pytest.mark.parametrize("store", ["journal", "preferences"])
def test_failed_persistence_cancels_power(owner, store):
    owner.request_power("shutdown", confirmed=True)
    owner.power_cleanup_confirmed = True
    owner.power_after_release(0)
    getattr(owner, store).error = "disk failure"
    owner.poll_power()
    assert owner.power.phase == "failed" and not owner.os_calls


def test_power_wire_contract_requires_exact_confirmation_and_operation():
    envelope = {
        "id": "power-confirmation-123",
        "revision": "revision",
        "action": "power",
        "arguments": {"operation": "reboot", "confirmed": True},
    }
    assert command(envelope) == envelope
    for operation, confirmed in [
        ("reboot", False),
        ("shutdown", 1),
        ("arbitrary", True),
    ]:
        with pytest.raises(ValueError):
            command(
                dict(
                    envelope, arguments={"operation": operation, "confirmed": confirmed}
                )
            )
