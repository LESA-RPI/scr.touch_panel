"""Preference completion includes the filename and the newest queued selection."""
import json
from pathlib import Path
import sys
import threading
import pytest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import preferences


@pytest.mark.parametrize('text', [None, '{', '[]', '{"blinds_enabled": 1}',
                                '{"blinds_enabled": true, "theme": "broken"}',
                                '{"theme": "dark"}'])
def test_missing_corrupt_and_old_preferences_default_to_locked(tmp_path, text):
    path = tmp_path / 'appearance.json'
    if text is not None:
        path.write_text(text)
    saved, warning = preferences.load(str(path))
    assert saved.get('blinds_enabled', False) is False
    if text == '{"theme": "dark"}':
        assert saved == {'theme': 'dark'} and warning is None


def finish(writer):
    writer.close()
    assert writer.done.wait(3)


def test_directory_sync_closes_descriptor_and_uses_directory_flag(monkeypatch):
    calls=[]
    fake=SimpleNamespace(name='posix',O_RDONLY=1,O_DIRECTORY=2,
                         open=lambda path,flags:calls.append(('open',path,flags)) or 17,
                         fsync=lambda fd:calls.append(('sync',fd)),
                         close=lambda fd:calls.append(('close',fd)))
    monkeypatch.setattr(preferences,'os',fake)
    preferences.sync_directory('/settings')
    assert calls==[('open','/settings',3),('sync',17),('close',17)]
    fake.name='nt';calls.clear()
    preferences.sync_directory('/settings')
    assert calls==[]


def test_settled_waits_for_directory_sync_and_newest_pending_snapshot(tmp_path,monkeypatch):
    entered=[threading.Event(),threading.Event()]
    release=[threading.Event(),threading.Event()]
    count=[]
    def sync(directory):
        index=len(count);count.append(directory)
        entered[index].set()
        assert release[index].wait(3)
    monkeypatch.setattr(preferences,'sync_directory',sync)
    path=tmp_path/'appearance.json'
    writer=preferences.Preferences(str(path))
    try:
        assert writer.settled.is_set()
        writer.save({'theme':'light'})
        assert entered[0].wait(3)
        assert path.exists() and writer.writing and writer.pending is None
        assert not writer.settled.is_set()
        writer.save({'theme':'dark'})
        assert not writer.settled.is_set()
        release[0].set()
        assert entered[1].wait(3)
        assert writer.writing and not writer.settled.is_set()
        release[1].set()
        assert writer.settled.wait(3)
        assert not writer.writing and writer.pending is None and writer.error is None
        assert json.loads(path.read_text())=={'theme':'dark'}
    finally:
        for event in release:event.set()
        finish(writer)


def test_atomic_replace_precedes_directory_sync_and_failure_remains_visible(tmp_path,monkeypatch):
    order=[]
    replace=preferences.os.replace
    def renamed(source,target):
        replace(source,target);order.append('replace')
    def failed_sync(directory):
        order.append('directory_sync')
        raise OSError('directory persistence unavailable')
    monkeypatch.setattr(preferences.os,'replace',renamed)
    monkeypatch.setattr(preferences,'sync_directory',failed_sync)
    writer=preferences.Preferences(str(tmp_path/'appearance.json'))
    try:
        writer.save({'theme':'light'})
        assert writer.settled.wait(3)
        assert order==['replace','directory_sync']
        assert writer.error=='directory persistence unavailable'
        assert not writer.writing and writer.pending is None
    finally:finish(writer)


def test_later_success_clears_persistence_failure(tmp_path,monkeypatch):
    attempts=[]
    def sync(directory):
        attempts.append(directory)
        if len(attempts)==1:raise OSError('temporary storage error')
    monkeypatch.setattr(preferences,'sync_directory',sync)
    path=tmp_path/'appearance.json'
    writer=preferences.Preferences(str(path))
    try:
        writer.save({'theme':'light'})
        assert writer.settled.wait(3) and writer.error
        writer.save({'theme':'dark'})
        assert writer.settled.wait(3) and writer.error is None
        assert json.loads(path.read_text())=={'theme':'dark'}
    finally:finish(writer)
