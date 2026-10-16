#!/usr/bin/env python3
"""SCR browser interface with read-only diagnostics and an optional panel gateway.

Python 3.11+, no installed dependencies.

Author: Diyanko Bhowmik, with Codex assistance. No control adapter is imported.
"""
import argparse
import datetime as dt
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import secrets
import hmac
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
          '/design.js': ('design.js','text/javascript'), '/theme.js': ('theme.js','text/javascript'),
          '/room.js': ('room.js','text/javascript'), '/room.css': ('room.css','text/css'),
          # Home, Room tools and Guide are one page; room.js picks the view from the path.
          '/tools': ('index.html','text/html'), '/room-content.json': ('room-content.json','application/json'),
          '/diagnostics': ('diagnostics.html', 'text/html'), '/guide': ('index.html', 'text/html'),
          '/logo.jpg': ('lesa-logo.jpeg', 'image/jpeg')}

# Explicit static artwork allowlist; never resolve request paths from the filesystem.
ASSETS.update({
    '/fonts.css': ('fonts.css','text/css'),
    '/fonts/Cantarell-Regular.otf': ('fonts/Cantarell-Regular.otf','font/otf'),
    '/fonts/Cantarell-Bold.otf': ('fonts/Cantarell-Bold.otf','font/otf'),
    '/icons/book-open.svg': ('icons/book-open.svg', 'image/svg+xml'),
    '/icons/circle-question-mark-light.png': ('icons/circle-question-mark-light.png', 'image/png'),
    '/icons/cloud-fog-light.png': ('icons/cloud-fog-light.png', 'image/png'),
    '/icons/cloud-light.png': ('icons/cloud-light.png', 'image/png'),
    '/icons/cloud-lightning-light.png': ('icons/cloud-lightning-light.png', 'image/png'),
    '/icons/cloud-moon-light.png': ('icons/cloud-moon-light.png', 'image/png'),
    '/icons/cloud-rain-light.png': ('icons/cloud-rain-light.png', 'image/png'),
    '/icons/cloud-snow-light.png': ('icons/cloud-snow-light.png', 'image/png'),
    '/icons/cloud-sun-light.png': ('icons/cloud-sun-light.png', 'image/png'),
    '/icons/lightbulb-off.svg': ('icons/lightbulb-off.svg', 'image/svg+xml'),
    '/icons/lightbulb.svg': ('icons/lightbulb.svg', 'image/svg+xml'),
    '/icons/moon-light.png': ('icons/moon-light.png', 'image/png'),
    '/icons/sliders-horizontal.svg': ('icons/sliders-horizontal.svg', 'image/svg+xml'),
    '/icons/sun-light.png': ('icons/sun-light.png', 'image/png'),
})


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


def client_network(value):
    network = ipaddress.IPv4Network(value, strict=True)
    private_address(str(network.network_address))
    private_address(str(network.broadcast_address))
    return network


class RoomServer(HTTPServer):
    def verify_request(self, request, client_address):
        # Use the socket peer, never a caller-supplied forwarding header.
        return ipaddress.IPv4Address(client_address[0]) in self.allowed_clients


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
    def __init__(self, label, master=None, weather_location=None):
        self.label, self.master = label, master
        self.lock = threading.Lock()
        self.data = None
        self.sample_time = self.graph_time = None
        self.last_graph = None
        self.last_graph_utc = None
        self.weather_location = weather_location
        self.weather_time = self.weather_attempt = None
        self.weather_data = None
        self.weather_utc = None
        self.weather_state = 'unconfigured' if weather_location is None else 'unavailable'

    def collect_weather(self):
        if self.weather_location is None or (self.weather_attempt is not None and time.monotonic() - self.weather_attempt < 900):
            return
        self.weather_attempt = time.monotonic()
        try:
            result = subprocess.run([sys.executable, '-B', str(ROOT.parent / 'app/weather.py'),
                                     *map(str, self.weather_location), 'America/New_York'],
                                    capture_output=True, text=True, timeout=8, check=True)
            value = json.loads(result.stdout)
            if 'error' in value or 'temperature_f' not in value:
                raise ValueError('Weather unavailable')
            self.weather_data = value
            self.weather_time, self.weather_utc = time.monotonic(), utc()
            self.weather_state = 'available'
        except (OSError, ValueError, subprocess.SubprocessError):
            self.weather_state = 'unavailable'

    def collect(self):
        self.collect_weather()
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
                'sampled_at': utc(), 'host': host, 'room': graph,
                'weather': {'state': self.weather_state, 'data': self.weather_data,
                            'observed_at': self.weather_utc,
                            'observation_age_s': None if self.weather_time is None else round(time.monotonic() - self.weather_time, 1)}}
        with self.lock:
            self.data, self.sample_time, self.graph_time = data, time.monotonic(), graph_time

    def read(self):
        with self.lock:
            result = dict(self.data)
            result['sample_age_s'] = max(0, round(time.monotonic() - self.sample_time, 1))
            result['room'] = dict(result['room'])
            result['room']['observation_age_s'] = None if self.graph_time is None else max(0, round(time.monotonic() - self.graph_time, 1))
            result['weather'] = dict(result['weather'])
            if result['weather']['observation_age_s'] is not None:
                result['weather']['observation_age_s'] += result['sample_age_s']
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

    def log_problem(self, status):
        # One line per refused or failed request so the room host can see why.
        print('%s %s %s %s -> %d' % (utc(), self.client_address[0], self.command,
                                     self.path[:200], status), file=sys.stderr, flush=True)

    def respond(self, status, data=b'', content_type='text/plain'):
        # Closing with an unread body can reset the connection before the client
        # receives its rejection. Discard only a bounded, explicitly sized body.
        if self.command not in ('GET','HEAD') and not getattr(self,'body_consumed',False):
            self.body_consumed=True
            try:
                length=int(self.headers.get('Content-Length','0'))
                if 0<length<=4096 and not self.headers.get('Transfer-Encoding'):
                    self.rfile.read(length)
            except (ValueError,OSError):
                pass
        if status >= 400:
            self.log_problem(status)
        self.send_response(status)
        self.send_header('Content-Type', content_type + ('' if content_type.startswith('image/') else '; charset=utf-8'))
        self.send_header('Content-Length', str(len(data)))
        # Fonts and artwork rarely change; everything else reflects the live room.
        cacheable = status == 200 and self.path.startswith(('/fonts/', '/icons/', '/logo.jpg'))
        self.send_header('Cache-Control', 'max-age=86400' if cacheable else 'no-store')
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
        if path == '/api/controller':
            gateway = getattr(self.server, 'controller', None)
            value = gateway.read() if gateway else {'available':False,'detail':'Browser control is not configured.'}
            value['csrf'] = getattr(self.server, 'control_nonce', '')
            self.respond(200, json.dumps(value, allow_nan=False).encode(), 'application/json')
        elif path == '/api/status':
            self.respond(200, json.dumps(self.server.snapshot.read(), allow_nan=False).encode(), 'application/json')
        elif path in ASSETS:
            filename, content_type = ASSETS[path]
            try:
                data = (ROOT / filename).read_bytes()
            except OSError:
                self.respond(500, b'Website file missing. Ask the room host to reinstall the website.')
                return
            self.respond(200, data, content_type)
        else:
            self.respond(404)

    do_HEAD = do_GET

    def do_POST(self):
        gateway=getattr(self.server,'controller',None)
        if self.path!='/api/command' or gateway is None:
            self.respond(405,b'Control is not configured');return
        if (self.headers.get('Host')!=self.server.expected_host or
            self.headers.get('Origin')!='http://'+self.server.expected_host or
            not hmac.compare_digest(self.headers.get('X-SCR-Token',''),self.server.control_nonce)):
            self.respond(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if (not 1<=length<=4096 or self.headers.get('Transfer-Encoding') or
                self.headers.get('Content-Type')!='application/json'):
                raise ValueError('Invalid command body')
            self.body_consumed=True
            value=json.loads(self.rfile.read(length))
            if not isinstance(value,dict):raise ValueError('Invalid command')
        except ValueError:
            self.respond(400,b'Invalid command');return
        except OSError:
            self.respond(503,b'Command receipt unknown. Check the panel; do not retry.');return
        # Once the command may have reached the panel, any failure leaves its result unknown.
        try:
            reply=gateway.exchange(value)
            status=int(reply.get('code',503))
        except (OSError,ValueError,TypeError,AttributeError):
            self.respond(503,b'Command receipt unknown. Check the panel; do not retry.');return
        if status not in (202,400,408,409,503):status=503
        self.respond(status,json.dumps(reply,allow_nan=False).encode(),'application/json')

    def unsupported(self):self.respond(405)
    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = unsupported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel-control-socket', help='Opt in to trusted-network controls through the existing panel owner')
    parser.add_argument('--bind', default='127.0.0.1', help='Explicit private IPv4 address; default is local-only')
    parser.add_argument('--allow-clients', help='Trusted IPv4 subnet in CIDR form; required for room-network hosting')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--label', default='Dashboard host', help='Public host label; no private experiment metadata')
    parser.add_argument('--master', help='Approved private ROS master URL; omit for host-only status')
    parser.add_argument('--weather-latitude', type=float, help='Optional public outdoor-weather location')
    parser.add_argument('--weather-longitude', type=float)
    parser.add_argument('--probe-master', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        args.bind = private_address(args.bind)
        allowed = client_network(args.allow_clients or '127.0.0.0/8')
        if ipaddress.IPv4Address(args.bind) not in allowed:
            raise ValueError('The bind address must belong to the explicit allowed client subnet')
        if not 1 <= args.port <= 65535 or not 1 <= len(args.label) <= 60:
            raise ValueError('Use port 1..65535 and a host label of 1..60 characters')
        if args.master:
            args.master = master_url(args.master)
        if args.probe_master:
            print(json.dumps(service_graph(master_url(args.probe_master))))
            return
        if (args.weather_latitude is None) != (args.weather_longitude is None):
            raise ValueError('Weather needs both latitude and longitude')
        if args.weather_latitude is not None and not (-90 <= args.weather_latitude <= 90 and -180 <= args.weather_longitude <= 180):
            raise ValueError('Weather coordinates are out of range')
    except ValueError as error:
        parser.error(str(error))
    location = None if args.weather_latitude is None else (args.weather_latitude, args.weather_longitude)
    snapshot = Snapshot(args.label, args.master, location)
    snapshot.collect()
    server = RoomServer((args.bind, args.port), Handler)
    server.allowed_clients = allowed
    server.expected_host = '%s:%d' % server.server_address
    server.snapshot = snapshot
    server.controller = None
    server.control_nonce = secrets.token_urlsafe(32)
    if args.panel_control_socket:
        from controller import Controller
        if not Path(args.panel_control_socket).is_absolute():parser.error('Panel socket path must be absolute')
        server.controller = Controller(args.panel_control_socket)
    stopped = threading.Event()
    worker = threading.Thread(target=snapshot.run, args=(stopped,), daemon=True)
    worker.start()
    print('Room interface: http://' + server.expected_host, flush=True)
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
