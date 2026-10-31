"""Timing diagnostics do not invalidate a reviewed command; state events do."""

import collections
import json
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from test_panel_control import remote_owner, envelope
from panel_control import Bridge
from panel_remote import execute, snapshot
from scr_touch_panel import Panel


@pytest.fixture
def journalled_owner(remote_owner):
    remote_owner.started, remote_owner.boot_id = time.monotonic(), None
    remote_owner.records = []
    remote_owner.journal = SimpleNamespace(append=lambda line, sequence, durable:
        remote_owner.records.append((json.loads(line), sequence, durable)))
    remote_owner.emit = Panel.emit.__get__(remote_owner)
    return remote_owner


@pytest.fixture
def bridge():
    value = Bridge.__new__(Bridge)
    value.requests = queue.Queue()
    value.receipts = collections.OrderedDict()
    value.fingerprints = {}
    value.lock = threading.Lock()
    return value


def dispatch(bridge, owner, value):
    item = {"value": value, "deadline": time.monotonic() + 2,
            "cancelled": False, "done": threading.Event()}
    bridge.requests.put(item)
    bridge.drain(lambda: snapshot(owner), lambda command: execute(owner, command))
    assert item["done"].is_set()
    return item["reply"]


def test_timing_event_keeps_revision_and_command_dispatches_only_once(journalled_owner, bridge):
    owner = journalled_owner
    revision = snapshot(owner)["revision"]
    raw_sequence, control_sequence = owner.sequence, owner.control_sequence
    owner.emit("slow_ui_callback", callback="tick", duration_ms=201, delay_ms=0)
    assert owner.sequence == raw_sequence + 1
    assert owner.control_sequence == control_sequence
    assert snapshot(owner)["revision"] == revision
    event, saved_sequence, durable = owner.records[0]
    assert event["event"] == "slow_ui_callback"
    assert event["sequence"] == saved_sequence == raw_sequence + 1
    assert durable is False
    command = envelope("on", revision=revision)
    receipt = dispatch(bridge, owner, command)
    assert receipt["ok"] and owner.calls == ["room"]
    assert snapshot(owner)["revision"] != revision
    assert dispatch(bridge, owner, command) == receipt
    assert owner.calls == ["room"]
    assert [event["sequence"] for event, _, _ in owner.records] == [
        raw_sequence + 1, raw_sequence + 2
    ]


@pytest.mark.parametrize("event", [
    "light_requested", "light_result", "browser_command", "mode_changed",
    "profile_loaded", "lighting_ownership", "temperature_unit_selected",
    "practice_started", "annotation", "power_requested", "new_state_event",
])
def test_state_events_still_reject_the_old_revision_before_dispatch(journalled_owner, bridge, event):
    owner = journalled_owner
    revision = snapshot(owner)["revision"]
    raw_sequence, control_sequence = owner.sequence, owner.control_sequence
    owner.emit(event)
    assert owner.sequence == raw_sequence + 1
    assert owner.control_sequence == control_sequence + 1
    assert snapshot(owner)["revision"] != revision
    assert dispatch(bridge, owner, envelope("on", revision=revision))["code"] == 409
    assert not owner.calls
    assert owner.records[0][2] is (event in ("annotation", "power_requested"))


@pytest.mark.parametrize("field,value", [("view_generation", 2), ("run_id", "new-owner")])
def test_new_view_or_owner_still_rejects_stale_commands(journalled_owner, bridge, field, value):
    owner = journalled_owner
    revision = snapshot(owner)["revision"]
    setattr(owner, field, value)
    assert snapshot(owner)["revision"] != revision
    assert dispatch(bridge, owner, envelope("on", revision=revision))["code"] == 409
    assert not owner.calls and not owner.records
