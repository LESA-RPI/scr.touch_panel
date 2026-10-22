"""Storage failures remain visible without silently losing later panel events."""

from io import StringIO
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import event_journal
import preferences


def finish(writer):
    writer.close()
    assert writer.done.wait(3)
    writer.thread.join(1)
    assert not writer.thread.is_alive()


@pytest.mark.parametrize("output_kind", ["closed", "absent"])
def test_optional_console_failure_does_not_stop_private_journal(tmp_path, output_kind):
    output = StringIO() if output_kind == "closed" else None
    if output is not None:
        output.close()
    path = tmp_path / "events.jsonl"
    journal = event_journal.EventJournal(str(path), output)
    try:
        journal.append("first\n", 1, durable=True)
        journal.append("second\n", 2, durable=True)
    finally:
        finish(journal)
    assert journal.error is None and journal.output_error
    assert journal.poll() == [1, 2]
    assert path.read_text() == "first\nsecond\n"


@pytest.mark.parametrize("output_kind", ["closed", "absent"])
def test_output_only_logging_reports_unavailable_output(output_kind):
    output = StringIO() if output_kind == "closed" else None
    if output is not None:
        output.close()
    journal = event_journal.EventJournal(None, output)
    try:
        if output is not None:
            journal.append("annotation\n", 1, durable=True)
        else:
            assert journal.done.wait(3)
    finally:
        finish(journal)
    assert journal.error and journal.output_error
    assert journal.poll() == []
    with pytest.raises(IOError):
        journal.append("later\n", 2)


@pytest.mark.parametrize("private_file", [False, True])
def test_console_error_without_message_never_claims_output_was_written(
    tmp_path, private_file
):
    class FailedOutput:
        def write(self, value):
            raise OSError()

    path = str(tmp_path / "events.jsonl") if private_file else None
    journal = event_journal.EventJournal(path, FailedOutput())
    journal.append("annotation\n", 1, durable=True)
    finish(journal)
    assert journal.output_error
    assert journal.poll() == ([1] if private_file else [])
    assert bool(journal.error) is not private_file


def test_new_journal_name_is_synced_before_annotation_acknowledgement(
    tmp_path, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    directories = []

    def sync(directory):
        directories.append(directory)
        entered.set()
        if not release.wait(3):
            raise OSError("Test directory sync timed out")

    monkeypatch.setattr(event_journal, "sync_directory", sync)
    path = tmp_path / "events.jsonl"
    journal = event_journal.EventJournal(str(path), StringIO())
    try:
        journal.append("annotation\n", 1, durable=True)
        assert entered.wait(3)
        assert directories == [str(tmp_path)] and not journal.poll()
        assert path.read_text() == ""
    finally:
        release.set()
        finish(journal)
    assert journal.error is None and journal.poll() == [1]
    assert path.read_text() == "annotation\n"


def test_failed_journal_directory_sync_never_acknowledges_annotation(
    tmp_path, monkeypatch
):
    def failed_sync(directory):
        raise OSError("Journal filename persistence failed")

    monkeypatch.setattr(event_journal, "sync_directory", failed_sync)
    journal = event_journal.EventJournal(str(tmp_path / "events.jsonl"), StringIO())
    assert journal.done.wait(3)
    finish(journal)
    assert journal.error == "Journal filename persistence failed"
    assert journal.poll() == []
    with pytest.raises(IOError, match="filename persistence"):
        journal.append("annotation\n", 1, durable=True)


def test_unexpected_journal_failure_is_latched_and_rejects_later_events(monkeypatch):
    errors = []

    class BrokenOutput:
        def write(self, value):
            raise RuntimeError("Unexpected output failure")

    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    journal = event_journal.EventJournal(None, BrokenOutput())
    journal.append("first\n", 1)
    assert journal.done.wait(3)
    journal.thread.join(1)
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
    assert "stopped" in journal.error
    with pytest.raises(IOError, match="stopped"):
        journal.append("later\n", 2)
    assert journal.pending.empty()
    finish(journal)


def test_deeply_nested_corrupt_preferences_report_error(tmp_path):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme":' + "[" * 1500 + "0" + "]" * 1500 + "}")
    saved, error = preferences.load(str(path))
    assert saved == {} and error


def test_unexpected_preference_failure_is_latched_and_rejects_later_saves(
    tmp_path, monkeypatch
):
    errors = []

    def broken_dump(*args, **kwargs):
        raise RuntimeError("Unexpected serializer failure")

    monkeypatch.setattr(preferences.json, "dump", broken_dump)
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    writer = preferences.Preferences(str(tmp_path / "appearance.json"))
    writer.save({"theme": "light"})
    assert writer.done.wait(3)
    writer.thread.join(1)
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
    assert "stopped" in writer.error and writer.settled.is_set()
    writer.save({"theme": "dark"})
    assert writer.pending is None and "stopped" in writer.error
    assert not list(tmp_path.glob(".appearance-*"))
    finish(writer)


def test_preference_error_without_message_remains_visible(tmp_path, monkeypatch):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme":"light"}')

    def failed_replace(*args):
        raise OSError()

    monkeypatch.setattr(preferences.os, "replace", failed_replace)
    writer = preferences.Preferences(str(path))
    try:
        writer.save({"theme": "dark"})
        assert writer.settled.wait(3) and writer.error
        assert path.read_text() == '{"theme":"light"}'
        assert not list(tmp_path.glob(".appearance-*"))
    finally:
        finish(writer)
