"""Everyday control returns only after confirmed ownership and fresh acquisition."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import lighting_recovery
from lighting_recovery import LightingRecovery


TOKEN = "experiment-token-12345678"
OTHER_TOKEN = "experiment-token-87654321"
LABEL = "Lighting study"
LOG_POSITION = {"device": 5, "inode": 17, "size": 100}


def reserve(guard, token=TOKEN):
    guard.begin_reservation(token, LABEL)
    guard.reserve(token, released=True, helper_exited=True)


def test_full_handoff_requires_preserved_release_exit_owner_closure_and_acquire(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    guard.begin_reservation(TOKEN, LABEL)
    assert json.loads(path.read_text())["status"] == "releasing"
    assert guard.public()["write_blocked"]
    for release, exited in ((False, True), (True, False), (1, True)):
        with pytest.raises(RuntimeError):
            guard.reserve(TOKEN, released=release, helper_exited=exited)
    guard.reserve(TOKEN, released=True, helper_exited=True)
    with pytest.raises(RuntimeError):
        guard.finish(TOKEN, owner_closed=True)
    guard.finish(TOKEN, owner_closed=True, pending_clear=True)
    assert guard.public()["status"] == "recovering"
    with pytest.raises(RuntimeError):
        guard.ready(stable=False)
    guard.ready(stable=True)
    assert guard.public()["status"] == "normal"
    assert not guard.public()["write_blocked"]
    assert guard.state["acknowledged_at"] is not None
    assert guard.state["recovered_at"] is not None
    assert guard.state["revision"] == 4


def test_stale_and_wrong_tokens_cannot_release_a_new_experiment(tmp_path):
    guard = LightingRecovery(tmp_path / "lighting.json")
    reserve(guard)
    for operation in (guard.heartbeat, guard.finish):
        with pytest.raises(ValueError):
            operation(OTHER_TOKEN)
    guard.finish(TOKEN, owner_closed=True, pending_clear=True)
    guard.ready(stable=True)
    with pytest.raises(ValueError):
        reserve(guard)
    reserve(guard, OTHER_TOKEN)
    with pytest.raises(ValueError):
        guard.finish(TOKEN, owner_closed=True, pending_clear=True)
    assert guard.public()["status"] == "reserved"


def test_public_status_never_contains_token_or_token_hash(tmp_path):
    guard = LightingRecovery(tmp_path / "lighting.json")
    reserve(guard)
    visible = json.dumps(guard.public())
    assert TOKEN not in visible and guard.state["token_hash"] not in visible
    assert TOKEN not in (tmp_path / "lighting.json").read_text()
    assert guard.public()["label"] == LABEL


def test_no_heartbeat_or_clock_jump_ever_reclaims_experiment(tmp_path):
    now = [1000.0]
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path, clock=lambda: now[0])
    reserve(guard)
    for at in (10000000.0, 0.0):
        now[0] = at
        restarted = LightingRecovery(path, clock=lambda: now[0])
        assert restarted.public()["status"] == "reserved"
        assert restarted.public()["heartbeat_stale"]
        assert restarted.public()["needs_staff"]
        with pytest.raises(RuntimeError):
            restarted.ready(stable=True)
        with pytest.raises(RuntimeError):
            restarted.begin_write("next-command")


@pytest.mark.parametrize("operation", ("write", "release"))
def test_crash_during_write_or_handoff_is_durable_and_stays_blocked(tmp_path, operation):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    if operation == "write":
        guard.begin_write("request-before-crash")
    else:
        guard.begin_reservation(TOKEN, LABEL)
    restarted = LightingRecovery(path)
    assert restarted.public()["status"] == "uncertain"
    assert restarted.public()["can_check"]
    for unused in range(2):
        with pytest.raises(RuntimeError):
            restarted.ready(stable=True)
    again = LightingRecovery(path)
    assert again.public()["write_blocked"]
    with pytest.raises(RuntimeError):
        again.acknowledge(owner_closed=True, pending_clear=False)
    again.acknowledge(owner_closed=True, pending_clear=True)
    recovered = LightingRecovery(path)
    assert recovered.public()["status"] == "uncertain"
    with pytest.raises(RuntimeError):
        recovered.ready(stable=True)
    recovered.acknowledge(owner_closed=True, pending_clear=True)
    recovered.ready(stable=True)
    assert recovered.public()["status"] == "normal"
    assert recovered.state["reason"]
    assert recovered.state["request_id"] == ("request-before-crash" if operation == "write" else "")


def test_mismatched_response_never_resolves_pending_write(tmp_path):
    guard = LightingRecovery(tmp_path / "lighting.json")
    guard.begin_write("command-one")
    with pytest.raises(ValueError):
        guard.confirm_write("command-two")
    assert guard.public()["write_blocked"]
    guard.confirm_write("command-one")
    assert not guard.public()["write_blocked"]
    with pytest.raises(ValueError):
        guard.confirm_write("command-one")


def test_release_failure_after_panel_stops_preserves_reservation_proof(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    guard.begin_reservation(TOKEN, LABEL)
    guard.mark_uncertain("Lighting helper stopped without confirming preserved release.")
    restarted = LightingRecovery(path)
    assert restarted.state["label"] == LABEL
    assert restarted.state["token_hash"] == guard.state["token_hash"]
    with pytest.raises(RuntimeError):
        restarted.finish(TOKEN, owner_closed=True, pending_clear=True)
    with pytest.raises(RuntimeError):
        restarted.ready(stable=True)


@pytest.mark.parametrize("raw", ("{", "[]", "null", "{}", "x" * 8193))
def test_malformed_storage_fails_closed_and_is_preserved(tmp_path, raw):
    path = tmp_path / "lighting.json"
    path.write_text(raw)
    guard = LightingRecovery(path)
    assert guard.error and guard.public()["needs_staff"]
    assert guard.public()["write_blocked"] and not guard.public()["can_check"]
    with pytest.raises(RuntimeError):
        guard.acknowledge(owner_closed=True, pending_clear=True)
    assert path.read_text() == raw


@pytest.mark.parametrize("key,value", (("version", True), ("status", "unknown"),
                                      ("updated_at", float("nan")), ("updated_at", 10 ** 300),
                                      ("revision", -1), ("status", "reserved"),
                                      ("status", "recovering"), ("status", "writing")))
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
        guard.begin_write("not-authorized-to-send")
    assert guard.error and guard.public()["write_blocked"]
    assert not path.exists()
    assert not list(tmp_path.glob(".lighting-*"))


@pytest.mark.parametrize("token,label", (("short", LABEL), ("a" * 129, LABEL),
                                        (TOKEN, ""), (TOKEN, "a" * 81),
                                        (TOKEN, "line\nbreak")))
def test_invalid_reservation_inputs_never_block_the_room(token, label):
    guard = LightingRecovery()
    with pytest.raises(ValueError):
        guard.begin_reservation(token, label)
    assert guard.public()["status"] == "normal"


def test_local_staff_can_reconcile_crashed_owner_but_still_needs_fresh_acquire():
    guard = LightingRecovery()
    reserve(guard)
    guard.acknowledge(owner_closed=True, pending_clear=True)
    assert guard.public()["write_blocked"]
    guard.ready(stable=True)
    assert not guard.public()["write_blocked"]


def test_legacy_owner_survives_restart_and_requires_confirmed_idle_before_acquire(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    guard.enter_legacy(LOG_POSITION)
    restarted = LightingRecovery(path)
    assert restarted.public()["status"] == "legacy"
    assert restarted.public()["write_blocked"] and not restarted.public()["can_check"]
    for operation in (lambda: restarted.begin_write("blocked"),
                      lambda: restarted.begin_reservation(TOKEN, LABEL),
                      lambda: restarted.acknowledge(owner_closed=True),
                      lambda: restarted.leave_legacy(idle_confirmed=1, callback_clean=True),
                      lambda: restarted.leave_legacy(idle_confirmed=True)):
        with pytest.raises(RuntimeError):
            operation()
    restarted.leave_legacy(idle_confirmed=True, callback_clean=True)
    assert restarted.public()["status"] == "recovering"
    assert restarted.public()["write_blocked"]
    restarted.ready(stable=True)
    assert not restarted.public()["write_blocked"]


@pytest.mark.parametrize("status", ("uncertain", "reserved"))
def test_opening_legacy_cannot_bypass_experiment_or_unknown_write(status):
    guard = LightingRecovery()
    if status == "reserved":
        reserve(guard)
    else:
        guard.mark_uncertain("Earlier result not confirmed.")
    with pytest.raises(RuntimeError):
        guard.enter_legacy()
    assert guard.public()["write_blocked"]


@pytest.mark.parametrize("owner", ("experiment", "legacy"))
def test_interrupted_recovery_does_not_reuse_stale_owner_closure(tmp_path, owner):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    if owner == "experiment":
        reserve(guard)
        guard.finish(TOKEN, owner_closed=True, pending_clear=True)
    else:
        guard.enter_legacy(LOG_POSITION)
        guard.leave_legacy(idle_confirmed=True, callback_clean=True)
    assert guard.state["status"] == "recovering"
    proof = guard.state["acknowledged_at"]
    restarted = LightingRecovery(path)
    assert restarted.public()["status"] == "uncertain"
    assert restarted.state["acknowledged_at"] == proof  # Receipt retained; permission is not.
    with pytest.raises(RuntimeError):
        restarted.ready(stable=True)
    restarted.acknowledge(owner_closed=True, pending_clear=True)
    restarted.ready(stable=True)
    assert not restarted.public()["write_blocked"]


@pytest.mark.parametrize("marker", (b"Exception in Tkinter callback", b"Traceback", b"ROSException", b"ServiceException", b"Service call failed:"))
def test_legacy_new_callback_error_blocks_automatic_return(marker):
    guard = LightingRecovery()
    guard.enter_legacy(LOG_POSITION)
    log = b"normal output\n" + marker + b"\nfailure details\n"
    current = dict(LOG_POSITION, size=LOG_POSITION["size"] + len(log))
    assert not guard.legacy_log_unchanged(current, log)
    assert guard.state["status"] == "legacy"


def test_legacy_clean_appended_log_and_return_marker_restore_normal_without_fixture_replay(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    guard.enter_legacy(LOG_POSITION)
    log = b"successful room command\n"
    position = dict(LOG_POSITION, size=LOG_POSITION["size"] + len(log))
    assert guard.legacy_log_unchanged(position, log)
    guard.leave_legacy(idle_confirmed=True, callback_clean=True)
    with pytest.raises(RuntimeError):
        guard.begin_write("ordinary-command-is-blocked")
    guard.begin_write("return-from-original", returning=True)
    assert json.loads(path.read_text())["status"] == "writing"
    guard.confirm_write("return-from-original")
    assert guard.public()["status"] == "normal"
    assert not guard.public()["write_blocked"]


@pytest.mark.parametrize("position,delta", ((dict(LOG_POSITION, inode=99), b""),
                                          (dict(LOG_POSITION, device=99), b""),
                                          (dict(LOG_POSITION, size=99), b""),
                                          (dict(LOG_POSITION, size=101), b""),
                                          (dict(LOG_POSITION, size=100), b"unread growth"),
                                          ({"size": 100}, b"")))
def test_legacy_rotated_truncated_or_partially_read_log_cannot_authorize_return(position, delta):
    guard = LightingRecovery()
    guard.enter_legacy(LOG_POSITION)
    assert not guard.legacy_log_unchanged(position, delta)


def test_old_legacy_record_loads_but_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lighting.json"
    guard = LightingRecovery(path)
    guard.enter_legacy()
    old = json.loads(path.read_text())
    old.pop("legacy_log")
    path.write_text(json.dumps(old))
    restarted = LightingRecovery(path)
    assert not restarted.error and restarted.state["legacy_log"] is None
    assert not restarted.legacy_log_unchanged(LOG_POSITION, b"")
    with pytest.raises(RuntimeError):
        restarted.leave_legacy(idle_confirmed=True, callback_clean=True)
    restarted.acknowledge(owner_closed=True, pending_clear=True)
    assert restarted.state["status"] == "recovering"


@pytest.mark.parametrize("position", ({"device": True, "inode": 2, "size": 4},
                                     {"device": 1, "inode": 2, "size": -1},
                                     {"device": 1, "inode": 2},
                                     {"device": 1, "inode": 2, "size": 4, "extra": 5}))
def test_malformed_legacy_checkpoint_is_rejected_before_legacy_opens(position):
    guard = LightingRecovery()
    with pytest.raises(ValueError):
        guard.enter_legacy(position)
    assert guard.state["status"] == "normal"
