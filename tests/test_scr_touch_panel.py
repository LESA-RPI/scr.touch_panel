"""Light writes require a restorable baseline and matching fixture feedback."""
from types import SimpleNamespace
from io import BytesIO, StringIO
import json
import datetime
import threading

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import scr_touch_panel as panel
import scr_touch_panel_lights as adapter
import event_journal
import preferences
import weather


class Room:
    def __init__(self):
        self.state = dict.fromkeys(adapter.COORDINATES, adapter.setter_words(adapter.PRESETS['Fid']))
        self.writes = []
        self.lose_response = False

    def call(self, name, *args):
        if name == 'get_lights':
            return SimpleNamespace(lights=[v for xy in sorted(self.state) for v in xy])
        if name == 'get_sources':
            # Installed service uses float32 percentages. Represent its precision.
            import struct
            return SimpleNamespace(sources=[struct.unpack('f', struct.pack('f', v * 100 / 65535))[0]
                                            for v in self.state[tuple(args)]])
        assert name == 'sources_all'
        self.writes.append(tuple(args))
        self.state = dict.fromkeys(self.state, adapter.setter_words(args))
        if self.lose_response:
            raise TimeoutError('Lost response after a write')
        return SimpleNamespace(cmdstr=str([float(v) / 100 for v in args]))


def test_exact_restore_after_confirmed_write_and_float32_readback():
    room = Room()
    lights = adapter.Lights(room.call)
    baseline = dict(room.state)
    assert lights.acquire()['state'] == 'ready'
    assert lights.apply('channels', {'values': list(adapter.PRESETS['Sat'])})['state'] == 'completed'
    assert lights.release()['restored']
    assert room.state == baseline


def test_unknown_baseline_and_invalid_requests_do_not_write():
    room = Room()
    xy = next(iter(room.state))
    room.state[xy] = (1,) * 8
    with pytest.raises(ValueError, match='restorable'):
        adapter.Lights(room.call).acquire()
    room.state[xy] = adapter.setter_words(adapter.PRESETS['Fid'])
    lights = adapter.Lights(room.call)
    lights.acquire()
    for action, arguments in [('channels', {'values': [101] * 8}),
                              ('cct', {'cct': 3500, 'intensity': -1}), ('script', {})]:
        with pytest.raises(ValueError):
            lights.apply(action, arguments)
    assert not room.writes


def test_lost_response_and_external_changes_block_retries_and_restore():
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    room.lose_response = True
    with pytest.raises(TimeoutError):
        lights.apply('channels', {'values': list(adapter.PRESETS['Sat'])})
    with pytest.raises(ValueError):
        lights.apply('channels', {'values': list(adapter.PRESETS['Fid'])})
    with pytest.raises(ValueError, match='unknown'):
        lights.release()
    assert len(room.writes) == 1


def test_restore_read_timeout_latches_failure_and_expired_lease_prevents_write():
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    lights.apply('channels', {'values': list(adapter.PRESETS['Sat'])})
    def timed_out():
        raise TimeoutError('Pre-restore read did not complete')
    lights.read = timed_out
    with pytest.raises(TimeoutError):
        lights.release()
    with pytest.raises(ValueError, match='unknown'):
        lights.release()
    assert len(room.writes) == 1
    room = Room()
    lights = adapter.Lights(room.call, can_write=timed_out)
    lights.acquire()
    with pytest.raises(TimeoutError):
        lights.apply('channels', {'values': list(adapter.PRESETS['Sat'])})
    assert not room.writes
    room = Room()
    lights = adapter.Lights(room.call)
    lights.acquire()
    lights.apply('channels', {'values': list(adapter.PRESETS['Sat'])})
    room.state = dict.fromkeys(room.state, (0,) * 8)
    with pytest.raises(ValueError, match='External'):
        lights.release()
    assert len(room.writes) == 1


def test_profile_is_data_only_and_scheduled_theme_handles_midnight(tmp_path):
    item = tmp_path / 'profile.json'
    item.write_text('{"script":"anything"}')
    with pytest.raises(ValueError, match='permits'):
        panel.profile(str(item))
    assert panel.scheduled_theme(8 * 60, 7 * 60, 19 * 60) == 'light'
    assert panel.scheduled_theme(20 * 60, 7 * 60, 19 * 60) == 'dark'
    assert panel.scheduled_theme(23 * 60, 19 * 60, 7 * 60) == 'light'
    assert panel.scheduled_theme(12 * 60, 19 * 60, 7 * 60) == 'dark'


def test_preferences_restore_appearance_only_and_survive_invalid_input(tmp_path, monkeypatch):
    path = tmp_path / 'appearance.json'
    assert preferences.load(str(path)) == ({}, None)
    writer = preferences.Preferences(str(path))
    value = {'theme': 'dark', 'clock_format': '12', 'tips': 'off', 'light_at': 420,
             'dark_at': 1140, 'temperature_unit': 'c'}
    entered, unblock = threading.Event(), threading.Event()
    original = preferences.os.fsync
    def slow_sync(fd):
        entered.set()
        assert unblock.wait(2)
        original(fd)
    monkeypatch.setattr(preferences.os, 'fsync', slow_sync)
    writer.save(value)
    assert entered.wait(2)
    # New UI selections do not wait for storage; the latest snapshot wins.
    for theme in ('light', 'auto', 'dark'):
        writer.save(dict(value, theme=theme))
    unblock.set()
    writer.close()
    assert writer.done.wait(2)
    assert preferences.load(str(path)) == (value, None)
    path.write_text('{"theme":"light","lights":"on","recording":true}')
    assert preferences.load(str(path))[0] == {'theme': 'light'}
    path.write_text('{"theme":"invalid"}')
    assert preferences.load(str(path))[0] == {}
    assert preferences.load(str(path))[1]
    path.write_text('{"temperature_unit":"kelvin"}')
    assert preferences.load(str(path))[1]
    path.write_text('{"light_at":480}')
    assert preferences.load(str(path), {'light_at': 420, 'dark_at': 480})[1]
    path.write_text('x' * 5000)
    assert preferences.load(str(path))[1]


def test_weather_timeout_preserves_last_success_without_touching_lights(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.weather_worker = SimpleNamespace(poll=lambda: None, kill=lambda: stopped.append(True))
    state.weather_started = 0
    stopped = []
    monkeypatch.setattr(panel, 'monotonic', lambda: 9)
    state.poll_weather()
    assert stopped == [True]
    state.weather_worker = SimpleNamespace(poll=lambda: 1, stdout=BytesIO(b'{"error":"timeout"}'), stderr=None)
    state.weather_last_text = 'Last successful weather'
    shown = []
    state.weather_text = SimpleNamespace(set=shown.append)
    state.poll_weather()
    assert state.weather_worker is None
    assert 'refresh failed' in shown[-1] and state.weather_last_text in shown[-1]
    data = weather.summary({'current': {'temperature_2m': 50, 'weather_code': 2,
        'time': '2026-10-13T12:00'}, 'daily': {'sunrise': ['2026-10-13T06:30'], 'sunset': ['2026-10-13T18:00']}})
    assert data['temperature_c'] == 10 and data['sunrise'].endswith('06:30')
    state.weather_worker = SimpleNamespace(poll=lambda: 0, stdout=BytesIO(json.dumps(data).encode()), stderr=None)
    state.update_weather = lambda **kwargs: None
    state.poll_weather()
    assert state.weather_reading == weather.validate(data)
    assert state.weather_good == 9 and 'model 2026-10-13 12:00' in shown[-1]
    day = weather.daylight(data, datetime.datetime(2026, 10, 13, 12, 0))
    assert 0 < day['fraction'] < 1 and day['label'] == 'Sun sets in 6 h 00 min'
    assert weather.daylight(data, datetime.datetime(2026, 10, 13, 5, 0))['fraction'] == 0
    assert 'rises' in weather.daylight(data, datetime.datetime(2026, 10, 13, 5, 0))['label']
    assert weather.daylight(data, datetime.datetime(2026, 10, 13, 19, 0))['fraction'] == 1
    assert weather.daylight(data, datetime.datetime(2026, 10, 14, 12, 0)) is None
    with pytest.raises(ValueError):
        weather.validate(dict(data, temperature_f=float('nan')))


def test_latest_touch_intent_is_copied_serialized_and_cancelled_before_release(monkeypatch):
    class Scheduler:
        def __init__(self):
            self.calls = {}
            self.seq = 0
        def after(self, delay, callback):
            self.seq += 1
            self.calls[self.seq] = callback
            return self.seq
        def after_cancel(self, item):
            self.calls.pop(item, None)
        def fire(self):
            callbacks, self.calls = list(self.calls.values()), {}
            for callback in callbacks:
                callback()
    state = panel.Panel.__new__(panel.Panel)
    state.root = Scheduler()
    state.mode, state.light_state = 'room', 'ready'
    state.pending = state.release_target = state.closing = None
    state.queued_intent = state.intent_timer = state.slider_drag = None
    state.view_generation = 0
    state.status_text = state.light_text = SimpleNamespace(set=lambda value: None)
    sent = []
    def request(action, args):
        sent.append((action, args))
        return True
    state.request = request
    state.update_light_buttons = lambda: None
    values = [10] * 8
    state.apply('channels', values=values)
    values[0] = 99
    state.root.fire()
    assert sent == [('channels', {'values': [10] * 8})]
    state.pending = {'request_id': 'first'}
    state.apply('cct', cct=4000, intensity=1000)
    state.apply('cct', cct=5000, intensity=1050)
    state.root.fire()
    assert len(sent) == 1  # One in flight; only the latest remains unsent.
    state.pending, state.light_state = None, 'ready'
    state.dispatch_intent()
    assert sent[-1] == ('cct', {'cct': 5000, 'intensity': 1050})
    state.confirmed_light = 'Fid scene'
    feedback = []
    state.light_text = SimpleNamespace(set=feedback.append)
    state.apply('cct', cct=4500, intensity=1000)
    assert 'Selected: 4500 K input / level 1000' in feedback[-1]
    assert 'Last confirmed drive: Fid scene' in feedback[-1]
    # A new selection does not overwrite the previous successful readback.
    assert state.confirmed_light == 'Fid scene'
    assert panel.light_selection('channels', {'values': list(adapter.PRESETS['Sat'])}) == 'Sat scene'
    state.apply('channels', values=[30] * 8)
    state.cancel_intent()
    state.root.fire()
    assert len(sent) == 2
    state.release_target = 'original'
    state.apply('channels', values=[40] * 8)
    assert state.queued_intent is None
    state.release_target, state.light_state = None, 'ready'
    state.request = lambda action, args: False
    state.apply('channels', values=[50] * 8)
    state.root.fire()
    assert state.light_state == 'failed'
    state.light_state, state.closed = 'ready', False
    state.status_worker = None
    state.worker = SimpleNamespace(stdout=object(), poll=lambda: 0)
    state.worker_buffer = ''
    monkeypatch.setattr(panel.select, 'select', lambda *args: ([], [], []))
    state.poll_worker()
    assert state.worker is None and state.light_state == 'failed'
    # A failed helper can still be doing EOF cleanup. Never uncover legacy
    # actuator controls until that exact child has exited.
    state.keep_switcher, state.closed, state.closing = True, False, None
    state.mode, state.release_target = 'room', None
    state.trial_deadline = 1
    pipe = SimpleNamespace(closed=False)
    pipe.close = lambda: setattr(pipe, 'closed', True)
    state.worker = SimpleNamespace(stdin=pipe, poll=lambda: None)
    state.show('original')
    assert state.mode == 'room' and state.release_target == 'original' and pipe.closed
    assert state.trial_deadline is None


def test_slow_adapter_initialization_sends_fresh_request_once_and_honors_exit(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(panel, 'monotonic', lambda: now[0])
    monkeypatch.setattr(panel.select, 'select', lambda *args: ([], [], []))
    for leave in (None, 'original', 'close'):
        now[0] = 100.0
        worker = SimpleNamespace(stdin=BytesIO(), stdout=object(), poll=lambda: None)
        monkeypatch.setattr(panel.subprocess, 'Popen', lambda *args, **kwargs: worker)
        state = panel.Panel.__new__(panel.Panel)
        state.args = SimpleNamespace(journal='unused', expected_master='http://room-master',
                                     adapter_python='unused', live_lights=True)
        state.root = SimpleNamespace(after=lambda *args: None)
        state.run_id, state.request_seq, state.last_heartbeat = 'trial', 0, 100.0
        state.pending = state.release_target = state.closing = None
        state.closed, state.keep_switcher, state.mode = False, False, 'room'
        state.status_worker, state.trial_deadline = None, 1.0
        state.status_text = state.light_text = SimpleNamespace(set=lambda value: None)
        state.emit = lambda *args, **kwargs: None
        state.cancel_intent = state.poll_status = state.update_light_buttons = lambda: None
        state.start_worker()
        assert state.pending is None and not worker.stdin.getvalue()
        assert not state.request('acquire')
        if leave == 'original':
            state.show('original')
            assert state.mode == 'room' and state.release_target == 'original'
        elif leave == 'close':
            state.close('signal')
            assert state.closing == 'signal' and state.release_target == 'close'

        # Cold imports exceed the ten-second command lease. Heartbeats may flow,
        # but no acquire/release command can age in the helper's unread pipe.
        now[0] = 125.0
        state.worker_buffer = json.dumps({'version': 2, 'state': 'initialized'}) + '\n'
        state.poll_worker()
        commands = lambda: [json.loads(line) for line in worker.stdin.getvalue().splitlines()
                            if json.loads(line)['action'] != 'heartbeat']
        assert commands() == [] and not state.worker_ready
        state.worker_buffer = json.dumps({'version': 1, 'state': 'initialized'}) + '\n'
        state.poll_worker()
        sent = commands()
        assert len(sent) == 1
        assert sent[0]['action'] == ('release' if leave else 'acquire')
        assert sent[0]['sent_monotonic_s'] == 125.0
        assert state.pending['request_id'] == sent[0]['request_id']
        state.worker_buffer = json.dumps({'version': 1, 'state': 'initialized'}) + '\n'
        state.poll_worker()
        assert commands() == sent


def test_confirmed_display_uses_matching_request_not_newer_selection(monkeypatch):
    state = panel.Panel.__new__(panel.Panel)
    state.closed, state.closing, state.worker_ready = False, None, True
    state.worker = SimpleNamespace(stdin=BytesIO(), stdout=object(), poll=lambda: None)
    state.last_heartbeat = panel.monotonic()
    state.light_state, state.confirmed_light = 'applying', 'Fid scene'
    state.pending = {'request_id': 'one', 'action': 'cct', 'arguments': {'cct': 3500, 'intensity': 1000}}
    state.release_target = state.queued_intent = state.intent_timer = None
    state.poll_journal = state.poll_status = state.poll_weather = state.update_light_buttons = lambda: None
    state.emit = lambda *args, **kwargs: None
    state.root = SimpleNamespace(after=lambda *args: None)
    shown = []
    state.light_text = SimpleNamespace(set=shown.append)
    state.status_text = SimpleNamespace(set=lambda value: None)
    monkeypatch.setattr(panel.select, 'select', lambda *args: ([], [], []))
    reply = {'version': 1, 'request_id': 'other', 'state': 'completed',
             'detail': 'Drive settings confirmed on 10 lights'}
    state.worker_buffer = json.dumps(reply) + '\n'
    state.poll_worker()
    assert state.confirmed_light == 'Fid scene' and state.pending
    state.worker_buffer = json.dumps(dict(reply, request_id='one')) + '\n'
    state.poll_worker()
    assert state.confirmed_light == '3500 K input / level 1000'
    assert state.pending is None and 'Last confirmed drive: 3500 K input / level 1000' in shown[-1]


def journal_panel(journal, path):
    state = panel.Panel.__new__(panel.Panel)
    state.journal, state.args = journal, SimpleNamespace(journal=path)
    state.sequence, state.stage, state.started = 0, 0, panel.monotonic()
    state.mode, state.run_id, state.boot_id = 'experiment', 'trial', None
    state.profile, state.pending_annotation = panel.DEFAULT_PROFILE, None
    state.annotation_text = SimpleNamespace(value='', set=lambda value: setattr(state.annotation_text, 'value', value))
    state.status_text = SimpleNamespace(value='', set=lambda value: setattr(state.status_text, 'value', value))
    return state


def test_journal_fsync_does_not_block_emit_and_saved_waits_for_durable_ack(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def blocked_fsync(unused):
        entered.set()
        if not release.wait(3):
            raise OSError('Test fsync gate timed out')
    monkeypatch.setattr(event_journal.os, 'fsync', blocked_fsync)
    path = tmp_path / 'events.jsonl'
    journal = event_journal.EventJournal(str(path), StringIO())
    state = journal_panel(journal, str(path))
    try:
        state.emit('practice_started')
        state.mark('Activity started')
        assert entered.wait(2)
        state.emit('instruction_selected')  # Returns while fsync remains blocked.
        state.poll_journal()
        assert state.annotation_text.value == 'Saving annotation: Activity started'
        journal.close()  # Close requests drainage without joining the writer.
        assert not journal.done.is_set()
    finally:
        release.set()
        journal.close()
        assert journal.done.wait(3)
        journal.thread.join(1)
    state.poll_journal()
    assert state.annotation_text.value.startswith('Saved on panel: Activity started')
    assert journal.error is None and not journal.thread.is_alive()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [item['sequence'] for item in records] == [1, 2, 3]
    assert [item['event'] for item in records] == ['practice_started', 'annotation', 'instruction_selected']


def test_journal_backlog_is_bounded_and_accepted_records_drain_in_order():
    entered, release = threading.Event(), threading.Event()
    class BlockedOutput(StringIO):
        def write(self, value):
            entered.set()
            if not release.wait(3):
                raise OSError('Test output gate timed out')
            return super().write(value)
    output = BlockedOutput()
    journal = event_journal.EventJournal(None, output, capacity=2)
    try:
        journal.append('first\n', 1)
        assert entered.wait(2)
        journal.append('second\n', 2)
        journal.append('third\n', 3)
        with pytest.raises(IOError, match='queue is full'):
            journal.append('rejected\n', 4)
        assert journal.pending.qsize() == 2
        with pytest.raises(IOError):
            journal.append('also rejected\n', 5)
    finally:
        journal.close()
        release.set()
        assert journal.done.wait(3)
        journal.thread.join(1)
    assert output.getvalue() == 'first\nsecond\nthird\n'
    assert not journal.thread.is_alive()


def test_journal_failures_never_claim_unsaved_annotations_are_saved(tmp_path, monkeypatch, capsys):
    class FailedOutput:
        def write(self, unused):
            raise OSError('Injected output failure')
        def flush(self):
            raise AssertionError('Failed write must not be flushed')
    for kind in ('persist', 'output-only', 'mirror'):
        path = None if kind == 'output-only' else str(tmp_path / (kind + '.jsonl'))
        def fsync(unused):
            if kind == 'persist':
                raise OSError('Injected persistence failure')
        monkeypatch.setattr(event_journal.os, 'fsync', fsync)
        output = StringIO() if kind == 'persist' else FailedOutput()
        journal = event_journal.EventJournal(path, output)
        state = journal_panel(journal, path)
        try:
            state.mark('Activity finished')
        finally:
            journal.close()
            assert journal.done.wait(3)
            journal.thread.join(1)
        state.closed, state.worker, state.closing = False, None, 'test'
        destroyed = []
        state.root = SimpleNamespace(destroy=lambda: destroyed.append(state.annotation_text.value))
        state.finish_close()  # Final results must be processed before Tk disappears.
        stderr = capsys.readouterr().err
        assert state.closed and destroyed == [state.annotation_text.value]
        assert not journal.thread.is_alive()
        if kind == 'mirror':
            assert state.annotation_text.value.startswith('Saved on panel: Activity finished')
            assert journal.output_error == 'Injected output failure'
            assert not stderr
        else:
            assert state.annotation_text.value.startswith('Annotation not saved:')
            assert 'Saved on panel' not in state.annotation_text.value
            assert 'Written to panel output' not in state.annotation_text.value
            assert 'Panel journal shutdown failed:' in stderr
