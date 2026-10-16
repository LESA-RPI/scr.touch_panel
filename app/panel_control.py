"""Local-only bridge into the existing Tk command owner. No hardware imports."""
import collections
import json
import os
from pathlib import Path
import queue
import re
import socket
import socketserver
import stat
import threading
import time


def command(value):
    """Strict shared command vocabulary; no paths or shell text. Owner guards readiness."""
    if not isinstance(value, dict) or set(value) != {'id','revision','action','arguments'}:
        raise ValueError('Invalid command envelope')
    if not isinstance(value['id'], str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', value['id']):
        raise ValueError('Invalid command ID')
    if not isinstance(value['revision'], str) or not 1 <= len(value['revision']) <= 100:
        raise ValueError('A current panel revision is required')
    action, args = value['action'], value['arguments']
    if not isinstance(args, dict):
        raise ValueError('Invalid command arguments')
    shapes = {'on':(), 'off':(), 'home':(), 'legacy':(), 'blank':(), 'clock_view':(),
              'start':(), 'pause':(), 'previous':(), 'next':(), 'mark':('label',),
              'cct':('cct','intensity'), 'preset':('name',), 'channels':('values',),
              'theme':('value',), 'clock':('value',), 'temperature':('value',),
              'idle':('value',), 'blinds_display':('value',), 'blinds_enabled':('value',), 'blind':('name',), 'tips':('value',),
              'schedule':('which','delta'), 'power':('operation','confirmed')}
    if not isinstance(action, str) or action not in shapes or set(args) != set(shapes[action]):
        raise ValueError('Unsupported command or arguments')
    def integer(key, low, high):
        return type(args[key]) is int and low <= args[key] <= high
    valid = True
    if action == 'cct': valid = integer('cct',1600,10000) and integer('intensity',0,1900)
    if action == 'channels':
        valid = isinstance(args['values'], list) and len(args['values']) == 8 and all(type(v) is int and 0 <= v <= 100 for v in args['values'])
    choices = {'preset':('Fid','Sat','Dul','Off'), 'theme':('light','dark','auto'),
               'clock':('12','24'), 'temperature':('c','f'), 'idle':(0,60,300,900),
               'blinds_display':('hidden','disabled'), 'blinds_enabled':(True,False),
               'blind':('lift','open','close'), 'tips':(True,False)}
    if action in choices:
        key = 'name' if action in ('preset','blind') else 'value'
        valid = type(args[key]) is type(choices[action][0]) and args[key] in choices[action]
    if action == 'mark': valid = isinstance(args['label'], str) and 1 <= len(args['label']) <= 100
    if action == 'power': valid = args['operation'] in ('reboot','shutdown') and args['confirmed'] is True
    if action == 'schedule': valid = args['which'] in ('light_at','dark_at') and type(args['delta']) is int and args['delta'] in (-30,30)
    if not valid:
        raise ValueError('Command values are out of range')
    return value


class Bridge:
    """Socket threads only read cached JSON or enqueue. Tk drains and owns actions."""
    def __init__(self, path):
        import fcntl
        self.path = Path(path)
        if not self.path.is_absolute(): raise ValueError('Control socket must be absolute')
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lease = open(str(self.path)+'.lock','a')
        os.fchmod(self.lease.fileno(),0o600)
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if self.path.exists():
            info=self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('Control socket path is not an owned socket')
            with socket.socket(socket.AF_UNIX) as probe:
                try: probe.connect(str(self.path))
                except ConnectionRefusedError: self.path.unlink()
                else: raise ValueError('A panel controller is already serving')
        self.lock=threading.Lock();self.snapshot=None;self.at=0
        self.requests=queue.Queue(maxsize=8)
        self.receipts=collections.OrderedDict();self.fingerprints={}
        bridge=self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(3)
                try:
                    raw=self.rfile.readline(4097)
                    if len(raw)>4096 or not raw.endswith(b'\n'):return
                    request=json.loads(raw)
                    if request == {'op':'read'}:
                        with bridge.lock:
                            reply=dict(bridge.snapshot or {})
                            reply['available']=bool(reply) and time.monotonic()-bridge.at<2
                    else:
                        item={'value':command(request), 'deadline':time.monotonic()+2,
                              'done':threading.Event(), 'cancelled':False}
                        bridge.requests.put_nowait(item)
                        if not item['done'].wait(2):
                            item['cancelled']=True
                            reply={'ok':False,'code':503,'detail':'Command receipt unknown. Check the panel; do not retry.'}
                        else: reply=item['reply']
                    self.wfile.write(json.dumps(reply,allow_nan=False).encode()+b'\n')
                except (OSError,ValueError,queue.Full):
                    self.wfile.write(b'{"ok":false,"code":400,"detail":"Invalid or busy command"}\n')
        self.server=socketserver.ThreadingUnixStreamServer(str(self.path),Handler)
        self.server.daemon_threads=True
        self.path.chmod(0o600)
        self.thread=threading.Thread(target=self.server.serve_forever,name='panel-control-socket',daemon=True)
        self.thread.start()

    def drain(self, snapshot, execute):
        for unused in range(8):
            try: item=self.requests.get_nowait()
            except queue.Empty:break
            value=item['value'];key=value['id'];fingerprint=json.dumps(value,sort_keys=True)
            if item['cancelled'] or time.monotonic()>item['deadline']:
                reply={'ok':False,'code':408,'detail':'Command expired before acceptance. No action was sent.'}
            elif key in self.receipts:
                reply=self.receipts[key] if self.fingerprints[key]==fingerprint else {'ok':False,'code':409,'detail':'Command ID already used'}
            elif value['revision'] != snapshot()['revision']:
                reply={'ok':False,'code':409,'detail':'Room state changed. Review the current settings.'}
            else:
                try: reply=execute(value)
                except (ValueError,RuntimeError) as error:
                    reply={'ok':False,'code':409,'detail':str(error)}
                reply=dict(reply,id=key)
                self.receipts[key]=reply;self.fingerprints[key]=fingerprint
                while len(self.receipts)>64:
                    old,_=self.receipts.popitem(last=False);self.fingerprints.pop(old,None)
            item['reply']=reply;item['done'].set()
        value=snapshot();value['receipts']=list(self.receipts.values())[-16:]
        with self.lock:self.snapshot=value;self.at=time.monotonic()

    def close(self):
        # Called before the Tk owner begins releasing hardware; no new requests.
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        if self.path.exists():self.path.unlink()
        self.lease.close()
