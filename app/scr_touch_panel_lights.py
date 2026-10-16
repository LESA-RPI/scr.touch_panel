#!/usr/bin/env python
"""Optional SCR light adapter. Author: Diyanko Bhowmik, with Codex assistance.

Uses the existing ROS owner. No discovery, scene control, blinds or raw sockets.
The temporary trial admits only uniform, known integer-percent baselines because
the installed ROS setter cannot restore arbitrary 16-bit drive words exactly.
"""
from __future__ import print_function
import argparse
import ast
import json
import math
import os
import select
import signal
import socket
import sys
import time

PRESETS = {'Fid': (39, 6, 25, 56, 57, 100, 3, 6),
           'Sat': (21, 14, 4, 73, 22, 100, 22, 4),
           'Dul': (41, 2, 25, 53, 38, 100, 2, 0), 'Off': (0,) * 8}
COORDINATES = {(0, 0), (0, 2), (1, 1), (2, 0), (2, 2),
               (3, 0), (3, 2), (4, 1), (5, 0), (5, 2)}


def words(percent):
    if len(percent) != 8 or any(not 0 <= v <= 100 or math.isnan(v) or math.isinf(v)
                               for v in percent):
        raise ValueError('Eight finite channel percentages in 0..100 required')
    return tuple(int(round(v * 65535 / 100.0)) for v in percent)


def setter_words(percent):
    return tuple(int((float(v) / 100) * 65535) for v in percent)


def clock():
    if hasattr(time, 'monotonic'):
        return time.monotonic()
    with open('/proc/uptime') as stream:
        return float(stream.read().split()[0])


def restore_preset(snapshot):
    for name, values in PRESETS.items():
        if all(state == setter_words(values) for state in snapshot.values()):
            return name
    raise ValueError('Baseline is not an exactly restorable preset; live controls stay off')


class Lights(object):
    def __init__(self, call, can_write=lambda: None):
        self.call, self.can_write = call, can_write
        self.baseline = self.current = None
        self.baseline_name = None
        self.changed = self.failed = False

    def read(self):
        flat = list(self.call('get_lights').lights)
        coords = [tuple(flat[i:i + 2]) for i in range(0, len(flat), 2)]
        if len(flat) != 20 or len(set(coords)) != 10 or set(coords) != COORDINATES:
            raise ValueError('Installed fixture identities differ from the qualified ten')
        return dict((xy, words(list(self.call('get_sources', *xy).sources)))
                    for xy in sorted(coords))

    def acquire(self):
        if self.baseline is not None:
            raise ValueError('Lighting trial already acquired')
        state = self.read()
        name = restore_preset(state)
        if self.read() != state:
            raise ValueError('Light settings are changing; live controls stay off')
        self.baseline, self.current, self.baseline_name = state, state, name
        return {'state': 'ready', 'baseline': name, 'fixtures': 10}

    def apply(self, action, arguments):
        if self.failed or self.baseline is None:
            raise ValueError('Lighting trial is unavailable')
        if action == 'channels':
            values = arguments['values']
            if (len(values) != 8 or any(isinstance(v, bool) or not isinstance(v, int)
                                      or not 0 <= v <= 100 for v in values)):
                raise ValueError('Channels must be eight integers in 0..100')
            name, args = 'sources_all', values
        elif action == 'cct':
            cct, intensity = arguments['cct'], arguments['intensity']
            if (any(isinstance(v, bool) or not isinstance(v, int) for v in (cct, intensity))
                    or not 1600 <= cct <= 10000 or not 0 <= intensity <= 1900):
                raise ValueError('CCT 1600..10000 K and intensity 0..1900 required')
            name, args = 'cct_all', [cct, intensity]
        else:
            raise ValueError('Unknown lighting action')
        try:
            if self.read() != self.current:
                raise ValueError('Another controller changed the lights; trial ownership lost')
            self.can_write()
            self.changed = True
            # Until a matching readback arrives, the result is uncertain.
            self.current = None
            reply = self.call(name, *args)
            calculated = ast.literal_eval(reply.cmdstr)
            if len(calculated) != 8 or any(not 0 <= v <= 1 for v in calculated):
                raise ValueError('Malformed service response')
            expected = tuple(int(float(v) * 65535) for v in calculated)
            actual = self.read()
            if any(value != expected for value in actual.values()):
                raise ValueError('Fixture drive readback differs from the command')
            self.current = actual
            return {'state': 'completed', 'fixtures': 10,
                    'detail': 'Drive settings confirmed on 10 lights', 'words': list(expected)}
        except Exception:
            self.failed = True
            raise

    def release(self):
        if self.failed:
            raise ValueError('Outcome unknown; no automatic restore or retry. Inspect the retained receipt')
        if self.baseline is None or not self.changed:
            self.baseline = self.current = None
            return {'state': 'released', 'restored': True, 'detail': 'No light settings changed'}
        if self.failed or self.current is None:
            raise ValueError('Outcome unknown; no automatic restore or retry. Inspect the retained receipt')
        try:
            if self.read() != self.current:
                raise ValueError('External light change detected; refuse to overwrite it')
            self.current = None
            self.call('sources_all', *PRESETS[self.baseline_name])
            if self.read() != self.baseline:
                raise ValueError('Starting drive settings were not restored exactly')
            self.baseline = self.current = None
            self.changed = False
            return {'state': 'released', 'restored': True, 'detail': 'Starting light settings restored'}
        except Exception:
            self.failed = True
            raise


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', help='New private JSONL recovery journal')
    parser.add_argument('--parent-pid', type=int, help='Direct panel parent; no foreign process control')
    parser.add_argument('--expected-master', required=True, help='Approved deployment ROS_MASTER_URI')
    parser.add_argument('--status-only', action='store_true', help='Read advertised services only; no ROS node or fixture queries')
    args = parser.parse_args()
    if not args.status_only and os.environ.get('ROS_MASTER_URI') != args.expected_master:
        parser.error('ROS_MASTER_URI does not match the approved master')
    try:
        from urlparse import urlparse
    except ImportError:
        from urllib.parse import urlparse
    master = urlparse(args.expected_master)
    if master.scheme != 'http' or not master.hostname or master.hostname in ('localhost', '127.0.0.1', '::1'):
        parser.error('A configured remote room master is required')
    if args.status_only:
        socket.setdefaulttimeout(3)
        try:
            from xmlrpclib import ServerProxy
        except ImportError:
            from xmlrpc.client import ServerProxy
        result = ServerProxy(args.expected_master).getSystemState('scr_panel_status')
        if result[0] != 1:
            raise ValueError('Room master did not return its service graph')
        names = {name for name, nodes in result[2][2]}
        required = [('Lighting', {'/get_lights', '/get_sources', '/cct_all'}),
                    ('Blinds', {'/get_blinds', '/lift_all', '/tilt_all'}),
                    ('Environment', {'/get_temp', '/get_rh'}),
                    ('TOF', {'/get_distances', '/get_distances_all'})]
        print(json.dumps({'version': 1, 'services': [(name, services <= names) for name, services in required]}))
        return 0
    if not args.receipt or not args.parent_pid:
        parser.error('Connected control requires --receipt and --parent-pid')
    lock = open('/tmp/scr-panel-light-owner.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = os.fdopen(os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w')
    socket.setdefaulttimeout(10)
    import rospy
    from scr_control.srv import GetLights, GetSources, OctaLight_sourcesAll, OctaLight_CCTAll
    rospy.init_node('scr_panel_lights', anonymous=True, disable_signals=True)
    types = dict(get_lights=GetLights, get_sources=GetSources,
                 sources_all=OctaLight_sourcesAll, cct_all=OctaLight_CCTAll)
    def expired(signum, frame):
        raise RuntimeError('Lighting service deadline expired; outcome may be unknown')
    signal.signal(signal.SIGALRM, expired)
    deadline = [clock() + 30]
    def call(name, *values):
        remaining = deadline[0] - clock()
        if remaining <= 0:
            raise RuntimeError('Whole lighting operation exceeded 30 seconds')
        signal.alarm(min(12, max(1, int(math.ceil(remaining)))))
        try:
            return rospy.ServiceProxy(name, types[name])(*values)
        finally:
            signal.alarm(0)
    inbox = {'buffer': '', 'last_seen': clock(), 'eof': False, 'requests': []}
    def consume():
        while select.select([sys.stdin], [], [], 0)[0] and not inbox['eof']:
            chunk = os.read(sys.stdin.fileno(), 4096).decode('utf-8')
            if not chunk:
                inbox['eof'] = True
                break
            inbox['buffer'] += chunk
            if len(inbox['buffer']) > 8192:
                raise ValueError('Oversized adapter input')
            while '\n' in inbox['buffer']:
                line, inbox['buffer'] = inbox['buffer'].split('\n', 1)
                if len(line) > 4096:
                    raise ValueError('Oversized adapter request')
                item = json.loads(line)
                if item.get('version') != 1:
                    raise ValueError('Unsupported adapter protocol version')
                sent = float(item['sent_monotonic_s'])
                if not 0 <= clock() - sent <= 10:
                    if item['action'] == 'heartbeat':
                        continue
                    raise ValueError('Stale adapter request')
                inbox['last_seen'] = max(sent, inbox['last_seen'])
                if item['action'] != 'heartbeat':
                    inbox['requests'].append(item)
                    if len(inbox['requests']) > 1:
                        raise ValueError('Only one pending light request is permitted')
    def can_write():
        consume()
        if stopping[0] or inbox['eof'] or os.getppid() != args.parent_pid or clock() - inbox['last_seen'] > 10:
            raise ValueError('Panel lease ended before dispatch; no command sent')
    lights = Lights(call, can_write)
    def record(event, **values):
        values.update(event=event, epoch_s=time.time(), pid=os.getpid())
        if lights.baseline is not None:
            values['baseline'] = [[list(xy), list(state)] for xy, state in sorted(lights.baseline.items())]
        journal.write(json.dumps(values, sort_keys=True) + '\n')
        journal.flush()
        os.fsync(journal.fileno())
    def respond(request_id, result):
        record('result', request_id=request_id, result=result)
        print(json.dumps(dict(result, version=1, request_id=request_id)))
        sys.stdout.flush()
    stopping = [False]
    signal.signal(signal.SIGTERM, lambda signum, frame: stopping.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda signum, frame: stopping.__setitem__(0, True))
    print(json.dumps({'version': 1, 'state': 'initialized'}))
    sys.stdout.flush()
    try:
        while not stopping[0]:
            if not inbox['requests']:
                select.select([sys.stdin], [], [], 1)
            consume()
            if inbox['eof'] or clock() - inbox['last_seen'] > 10 or os.getppid() != args.parent_pid:
                break
            if not inbox['requests']:
                continue
            item = inbox['requests'].pop(0)
            deadline[0] = clock() + 30
            action, request_id = item['action'], item.get('request_id')
            if action == 'heartbeat':
                continue
            record('request', request=item)
            try:
                if action == 'acquire':
                    result = lights.acquire()
                elif action == 'release':
                    result = lights.release()
                else:
                    result = lights.apply(action, item.get('arguments', {}))
                respond(request_id, result)
                if action == 'release':
                    break
            except Exception as error:
                respond(request_id, {'state': 'failed', 'detail': str(error),
                                     'outcome_unknown': lights.failed})
                break
    finally:
        deadline[0] = clock() + 30
        try:
            result = lights.release()
            record('closed', result=result)
        except Exception as error:
            record('restore_failed', detail=str(error))
        journal.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
