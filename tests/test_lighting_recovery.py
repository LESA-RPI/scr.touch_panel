"""Everyday control returns only after confirmed ownership and fresh acquisition."""

import json
from pathlib import Path
import sys

import pytest
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lighting_recovery
from lighting_recovery import LightingRecovery


def test_background_checkpoints_remain_ordered_and_block_until_durable(tmp_path, monkeypatch):
    guard = LightingRecovery(tmp_path / "background.json", background=True)
    entered, release = threading.Event(), threading.Event()
    written = []
    persist = guard._persist

    def stalled(value):
        entered.set()
        assert release.wait(3)
        persist(value)
        written.append(value["status"])

    monkeypatch.setattr(guard, "_persist", stalled)
    try:
        guard.enter_legacy()
        assert entered.wait(1)
        guard.mark_uncertain("Legacy handoff did not confirm a preserved release.")
        assert guard.state["status"] == "uncertain"
        assert guard.pending and guard.public()["write_blocked"]
        assert not guard.public()["can_check"]
    finally:
        release.set()
    assert guard.settled.wait(2)
    assert written == ["legacy", "uncertain"]
    assert LightingRecovery(guard.path).state["status"] == "uncertain"


def test_everyday_commands_stay_in_memory_and_never_wait_for_storage(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path, background=True)
    guard.begin_write("one-command")
    assert not guard.pending and guard.public()["status"] == "writing"
    guard.finish_write("one-command")
    assert guard.state["status"] == "normal" and not guard.public()["write_blocked"]
    assert not path.exists()


def test_older_record_left_mid_command_reopens_ready_for_a_fresh_read(tmp_path):
    path = tmp_path / "lighting.json"
    state = dict(LightingRecovery().state, status="writing", request_id="before-crash")
    path.write_text(json.dumps(state))
    restarted = LightingRecovery(path)
    assert restarted.public()["status"] == "normal" and not restarted.error
    restarted.ready(stable=True)


@pytest.mark.parametrize("status", ["releasing", "reserved"])
def test_retired_experiment_handoff_loads_as_uncertain_not_a_storage_error(tmp_path, status):
    path = tmp_path / "lighting.json"
    old = dict(LightingRecovery().state, status=status, token_hash="a" * 64,
               label="Study", heartbeat_at=1.0)
    path.write_text(json.dumps(old))
    restarted = LightingRecovery(path)
    assert not restarted.error
    assert restarted.state["status"] == "uncertain" and restarted.public()["write_blocked"]


@pytest.mark.parametrize("status", ["uncertain", "recovering", "legacy", "releasing", "reserved"])
def test_persisted_handoff_can_retry_bounded_return(tmp_path, status):
    path = tmp_path / "lighting.json"
    old = dict(LightingRecovery().state, status=status, legacy_log=None,
               acknowledged_at=1, recovered_at=None, request_id="", token_hash="", label="", heartbeat_at=None)
    path.write_text(json.dumps(old))
    guard = LightingRecovery(path)
    assert not guard.error and guard.public()["can_check"]
    assert guard.public()["write_blocked"]
    guard.begin_write("check-connection", returning=True)
    assert json.loads(path.read_text())["status"] == "uncertain"
    restarted = LightingRecovery(path)
    assert restarted.public()["can_check"] and restarted.public()["write_blocked"]
    restarted.begin_write("retry", returning=True)
    restarted.finish_write("retry")
    assert LightingRecovery(path).state["status"] == "normal"


def test_mismatched_response_never_resolves_pending_write(tmp_path):
    guard = LightingRecovery(tmp_path / "lighting.json")
    guard.begin_write("command-one")
    with pytest.raises(ValueError):
        guard.finish_write("command-two")
    assert guard.public()["write_blocked"]
    guard.finish_write("command-one")
    assert not guard.public()["write_blocked"]
    with pytest.raises(ValueError):
        guard.finish_write("command-one")


@pytest.mark.parametrize("raw", ("{", "[]", "null", "{}", "x" * 8193))
def test_malformed_storage_fails_closed_and_is_preserved(tmp_path, raw):
    path = tmp_path / "lighting.json"
    path.write_text(raw)
    guard = LightingRecovery(path)
    assert guard.error and guard.public()["needs_staff"]
    assert guard.public()["write_blocked"] and not guard.public()["can_check"]
    with pytest.raises(RuntimeError):
        guard.begin_write("blocked", returning=True)
    assert path.read_text() == raw


@pytest.mark.parametrize("key,value", (("version", True), ("status", "unknown"),
                                      ("updated_at", float("nan")), ("updated_at", 10 ** 300),
                                      ("revision", -1)))
def test_semantically_invalid_state_also_fails_closed(tmp_path, key, value):
    path = tmp_path / "lighting.json"
    state = dict(LightingRecovery().state, **{key: value})
    path.write_text(json.dumps(state))
    guard = LightingRecovery(path)
    assert guard.error and guard.public()["write_blocked"]


def test_failed_durable_write_never_authorizes_hardware_operation(tmp_path, monkeypatch):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)

    def fail_replace(*unused):
        raise OSError("storage unavailable")

    monkeypatch.setattr(lighting_recovery.os, "replace", fail_replace)
    with pytest.raises(RuntimeError):
        guard.enter_legacy()
    assert guard.error and guard.public()["write_blocked"]
    with pytest.raises(RuntimeError):
        guard.begin_write("not-authorized-to-send")
    assert not path.exists()
    assert not list(tmp_path.glob(".lighting-*"))
