"""Light writes require a restorable baseline and matching fixture feedback."""
from types import SimpleNamespace
from io import BytesIO
import json

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import scr_touch_panel as panel
import scr_touch_panel_lights as adapter


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
