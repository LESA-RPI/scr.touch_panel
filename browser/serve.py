#!/usr/bin/env python3
"""Read-only SCR status page. Python 3.11+, no installed dependencies.

Author: Diyanko Bhowmik, with Codex assistance. No control adapter is imported.
"""
import argparse
import datetime as dt
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import xmlrpc.client

ROOT = Path(__file__).resolve().parent
GROUPS = {
    'Lighting': {'/get_lights', '/get_sources', '/cct_all'},
    'Blinds': {'/get_blinds', '/lift_all', '/tilt_all'},
    'Environment': {'/get_temp', '/get_rh'},
    'Time-of-flight': {'/get_distances', '/get_distances_all'},
}
ASSETS = {'/': ('index.html', 'text/html'), '/styles.css': ('styles.css', 'text/css'),
          '/status.js': ('status.js', 'text/javascript'),
          '/logo.png': ('../lesa_banner.png', 'image/png')}


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def private_address(value):
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_multicast or not (address.is_private or address.is_loopback):
        raise ValueError('Use one explicit private or loopback IPv4 address')
    return str(address)


def master_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('Use an approved http://PRIVATE_IP:PORT room master')
    private_address(parsed.hostname)
    if parsed.port is None or not 1 <= parsed.port <= 65535:
        raise ValueError('The room master needs an explicit port')
    return value


def host_status():
    """Resources belong to this server host, not every room computer."""
    result = {'memory_available_mib': None, 'memory_total_mib': None,
              'uptime_s': None, 'temperature_c': None, 'power': 'unavailable'}
    try:
        memory = {line.split(':')[0]: int(line.split()[1])
                  for line in Path('/proc/meminfo').read_text().splitlines()}
        result.update(memory_available_mib=memory['MemAvailable'] // 1024,
                      memory_total_mib=memory['MemTotal'] // 1024)
        result['uptime_s'] = float(Path('/proc/uptime').read_text().split()[0])
    except (OSError, ValueError, KeyError):
        pass
    try:
        result['temperature_c'] = float(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage(Path.cwd().anchor or '/')
    result.update(disk_available_gib=round(disk.free / 2**30, 1),
                  disk_used_percent=round(100 * disk.used / disk.total, 1))
    utility = shutil.which('vcgencmd')
    if utility:
        try:
            reply = subprocess.run([utility, 'get_throttled'], capture_output=True,
                                   text=True, timeout=2, check=True)
            flags = int(reply.stdout.strip().split('=')[1], 16)
            result['power'] = 'warning_now' if flags & 1 else 'warning_earlier' if flags & 0x10000 else 'no_warning'
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    return result


def service_graph(master):
    """Only getSystemState; no ROS node, service call, registration or publisher."""
    parsed = urlsplit(master)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    request = xmlrpc.client.dumps(('scr_browser_status',), methodname='getSystemState').encode()
    try:
        connection.request('POST', '/', body=request, headers={'Content-Type': 'text/xml'})
        response = connection.getresponse()
        body = response.read(262145)
        if response.status != 200 or len(body) > 262144 or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
            raise ValueError('Unusable service graph')
        values, _ = xmlrpc.client.loads(body)
        result = values[0]
        if result[0] != 1:
            raise ValueError('Service graph refused')
        services = result[2][2]
        names = {name for name, providers in services if providers}
        return [{'name': name, 'state': 'advertised' if required <= names else
                 'partial' if required & names else 'not_advertised'}
                for name, required in GROUPS.items()]
    finally:
        connection.close()


def bounded_graph(master):
    # A socket timeout alone does not bound a peer that continually trickles data.
    result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--probe-master', master], capture_output=True,
                            text=True, timeout=4, check=True)
    return json.loads(result.stdout)


class Snapshot:
    def __init__(self, label, master=None):
        self.label, self.master = label, master
        self.lock = threading.Lock()
        self.data = None
        self.sample_time = self.graph_time = None
        self.last_graph = None
        self.last_graph_utc = None

    def collect(self):
        host = host_status()
        graph = {'state': 'unconfigured', 'observed_at': None, 'services': []}
        graph_time = self.graph_time
        if self.master:
            try:
                self.last_graph = bounded_graph(self.master)
                graph_time, self.last_graph_utc = time.monotonic(), utc()
                graph['state'] = 'available'
            except (OSError, ValueError, subprocess.SubprocessError):
                graph['state'] = 'unavailable'
            graph.update(services=self.last_graph or [], observed_at=self.last_graph_utc)
        data = {'version': 1, 'read_only': True, 'host_label': self.label,
                'sampled_at': utc(), 'host': host, 'room': graph}
        with self.lock:
            self.data, self.sample_time, self.graph_time = data, time.monotonic(), graph_time

    def read(self):
        with self.lock:
            result = dict(self.data)
            result['sample_age_s'] = max(0, round(time.monotonic() - self.sample_time, 1))
            result['room'] = dict(result['room'])
            result['room']['observation_age_s'] = None if self.graph_time is None else max(0, round(time.monotonic() - self.graph_time, 1))
            return result

    def run(self, stopped):
        while not stopped.wait(30):
            try:
                self.collect()
            except OSError:
                # Keep the dated previous sample; clients mark it stale.
                continue


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 closes each connection. No unbounded worker threads or file serving.
    def setup(self):
        super().setup()
        self.connection.settimeout(2)
        self.deadline = threading.Timer(4, self.expire)
        self.deadline.daemon = True
        self.deadline.start()

    def expire(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self):
        try:
            super().finish()
        finally:
            self.deadline.cancel()

    def log_message(self, *_):
        pass

    def respond(self, status, data=b'', content_type='text/plain'):
        self.send_response(status)
        self.send_header('Content-Type', content_type + ('; charset=utf-8' if content_type != 'image/png' else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_GET(self):
        # A foreign origin cannot use this as a cross-origin status API. Exact Host
        # also prevents DNS rebinding; links use the configured literal IP address.
        if self.headers.get('Host') != self.server.expected_host:
            self.respond(403)
            return
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.server.expected_host:
            self.respond(403)
            return
        path = self.path
        if path == '/api/status':
            self.respond(200, json.dumps(self.server.snapshot.read(), allow_nan=False).encode(), 'application/json')
        elif path in ASSETS:
            filename, content_type = ASSETS[path]
            self.respond(200, (ROOT / filename).read_bytes(), content_type)
        else:
            self.respond(404)

    do_HEAD = do_GET

    def do_POST(self):
        self.respond(405, b'Read-only endpoint')

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1', help='Explicit private IPv4 address; default is local-only')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--label', default='Dashboard host', help='Public host label; no private experiment metadata')
    parser.add_argument('--master', help='Approved private ROS master URL; omit for host-only status')
    parser.add_argument('--probe-master', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        args.bind = private_address(args.bind)
        if not 1 <= args.port <= 65535 or not 1 <= len(args.label) <= 60:
            raise ValueError('Use port 1..65535 and a host label of 1..60 characters')
        if args.master:
            args.master = master_url(args.master)
        if args.probe_master:
            print(json.dumps(service_graph(master_url(args.probe_master))))
            return
    except ValueError as error:
        parser.error(str(error))
    snapshot = Snapshot(args.label, args.master)
    snapshot.collect()
    server = HTTPServer((args.bind, args.port), Handler)
    server.expected_host = '%s:%d' % server.server_address
    server.snapshot = snapshot
    stopped = threading.Event()
    worker = threading.Thread(target=snapshot.run, args=(stopped,), daemon=True)
    worker.start()
    print('Read-only room status: http://' + server.expected_host, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stopped.set()
        worker.join(timeout=5)


if __name__ == '__main__':
    main()
