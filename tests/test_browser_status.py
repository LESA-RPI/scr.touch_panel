"""Read-only boundary and freshness checks; no room hardware is used."""
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import threading
import time
from unittest.mock import patch
from xmlrpc.server import SimpleXMLRPCServer

import pytest

spec = importlib.util.spec_from_file_location('room_status', Path(__file__).parents[1] / 'browser/serve.py')
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


def test_graph_calls_only_master_state_and_preserves_unknown_results():
    methods = []
    master = SimpleXMLRPCServer(('127.0.0.1', 0), logRequests=False)
    def graph(caller):
        methods.append(('getSystemState', caller))
        return [1, '', [[], [], [[name, ['existing-server']] for name in status.GROUPS['Lighting']]]]
    master.register_function(graph, 'getSystemState')
    thread = threading.Thread(target=master.serve_forever, daemon=True)
    thread.start()
    try:
        result = status.service_graph('http://127.0.0.1:%d' % master.server_address[1])
        assert methods == [('getSystemState', 'scr_browser_status')]
        assert result[0] == {'name': 'Lighting', 'state': 'advertised'}
        assert result[1]['state'] == 'not_advertised'
    finally:
        master.shutdown()
        master.server_close()
        thread.join(timeout=2)


def test_failure_retains_original_observation_age():
    snapshot = status.Snapshot('Cabinet Pi', 'http://127.0.0.1:11311')
    with patch.object(status, 'host_status', return_value={}), patch.object(status, 'bounded_graph', return_value=[{'name': 'Lighting', 'state': 'advertised'}]):
        snapshot.collect()
    snapshot.graph_time -= 100
    with patch.object(status, 'host_status', return_value={}), patch.object(status, 'bounded_graph', side_effect=OSError):
        snapshot.collect()
    value = snapshot.read()
    assert value['room']['state'] == 'unavailable'
    assert value['room']['services'][0]['state'] == 'advertised'
    assert value['room']['observation_age_s'] >= 100
    assert value['sample_age_s'] < 1


@pytest.fixture
def server():
    snapshot = status.Snapshot('Test host')
    with patch.object(status, 'host_status', return_value={}):
        snapshot.collect()
    instance = status.RoomServer(('127.0.0.1', 0), status.Handler)
    instance.allowed_clients = status.client_network('127.0.0.0/8')
    instance.expected_host = '%s:%d' % instance.server_address
    instance.snapshot = snapshot
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=2)


def request(server, method, path, headers=None, body=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=7)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.headers)
    finally:
        connection.close()


def test_http_boundary_and_cache(server):
    with patch.object(server.snapshot, 'collect', side_effect=AssertionError('HTTP must not poll room')):
        code, body, headers = request(server, 'GET', '/api/status')
        assert code == 200 and json.loads(body)['read_only'] is True
        assert headers['Cache-Control'] == 'no-store'
        assert 'Access-Control-Allow-Origin' not in headers
        assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
        code, image, headers = request(server, 'GET', '/logo.jpg')
        assert code == 200 and image.startswith(b'\xff\xd8')
        assert headers['Content-Type'] == 'image/jpeg'
        code, image, headers = request(server, 'GET', '/icons/cloud-moon-light.png')
        assert code == 200 and image.startswith(b'\x89PNG\r\n\x1a\n')
        assert headers['Content-Type'] == 'image/png'
        code, icon, headers = request(server, 'GET', '/icons/lightbulb.svg')
        assert code == 200 and b'<svg' in icon
        assert headers['Content-Type'] == 'image/svg+xml'
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            assert request(server, method, '/api/status')[0] == 405
        for path in ('/../README.md', '/api/status?master=http://other', '/deployment.env',
                     '/icons/../serve.py', '/icons/not-listed.svg', '/icons/LICENSE'):
            assert request(server, 'GET', path)[0] == 404
        assert request(server, 'GET', '/api/status', {'Host': 'foreign.test'})[0] == 403
        assert request(server, 'GET', '/api/status', {'Origin': 'http://foreign.test'})[0] == 403


def test_trickled_request_has_absolute_deadline(server):
    connection = socket.create_connection(server.server_address)
    stopped = threading.Event()
    def trickle():
        while not stopped.wait(0.25):
            try:
                connection.sendall(b'x')
            except OSError:
                return
    started = time.monotonic()
    connection.sendall(b'GET / HTTP/1.1\r\nX-Test: ')
    worker = threading.Thread(target=trickle, daemon=True)
    worker.start()
    try:
        # The healthy request must finish while the slow socket remains open.
        assert request(server, 'GET', '/api/status')[0] == 200
        assert time.monotonic() - started < 6
    finally:
        stopped.set()
        connection.close()
        worker.join(timeout=1)


def test_explicit_network_configuration():
    assert status.private_address('192.168.1.5') == '192.168.1.5'
    for value in ('0.0.0.0', '8.8.8.8', '224.0.0.1'):
        with pytest.raises(ValueError):
            status.private_address(value)
    for value in ('https://192.168.1.5:11311', 'http://192.168.1.5:11311/path',
                  'http://user:secret@192.168.1.5:11311', 'http://192.168.1.5:11311?redirect=x'):
        with pytest.raises(ValueError):
            status.master_url(value)


def test_client_subnet_rejects_other_peers_and_forwarded_headers(server):
    assert request(server, 'GET', '/api/status')[0] == 200
    server.allowed_clients = status.client_network('192.168.0.0/24')
    with pytest.raises((http.client.RemoteDisconnected, ConnectionResetError, ConnectionAbortedError)):
        request(server, 'GET', '/api/status', {'X-Forwarded-For': '192.168.0.20'})
    assert not server.verify_request(None, ('192.168.1.20', 1234))
    assert server.verify_request(None, ('192.168.0.20', 1234))
    for value in ('0.0.0.0/0', '8.8.8.0/24', '192.168.0.28/24'):
        with pytest.raises(ValueError):
            status.client_network(value)


def test_weather_cache_preserves_provenance_on_failure():
    value = {'temperature_f': 60, 'temperature_c': 15.6, 'condition': 'Cloudy',
             'code': 3, 'sunrise': '2026-10-14T07:00', 'sunset': '2026-10-14T18:00',
             'model_time': '2026-10-14T12:00'}
    snapshot = status.Snapshot('Test host', weather_location=(42.7, -73.7))
    reply = type('Reply', (), {'stdout': json.dumps(value)})()
    with patch.object(status, 'host_status', return_value={}), patch.object(status.subprocess, 'run', return_value=reply) as fetch:
        snapshot.collect()
        original = snapshot.read()['weather']['observed_at']
        snapshot.collect()
        assert fetch.call_count == 1  # Multiple samplings do not multiply weather requests.
        snapshot.weather_attempt -= 901
        snapshot.weather_time -= 1900
        fetch.side_effect = OSError('Offline')
        snapshot.collect()
    result = snapshot.read()['weather']
    assert result['state'] == 'unavailable'
    assert result['observed_at'] == original
    assert result['data'] == value
    assert result['observation_age_s'] >= 1900

def test_gateway_requires_exact_origin_nonce_and_bounded_json_without_polling_devices(server):
    class Gateway:
        def __init__(self):self.calls=[]
        def read(self):return {'available':True,'revision':'one'}
        def exchange(self,value):self.calls.append(value);return {'ok':True,'code':202,'id':value['id']}
    gateway=Gateway();server.controller=gateway;server.control_nonce='test-nonce'
    code,body,_=request(server,'GET','/api/controller')
    assert code==200 and json.loads(body)['csrf']=='test-nonce' and not gateway.calls
    payload=json.dumps({'id':'known-command-0001','revision':'one','action':'off','arguments':{}})
    headers={'Origin':'http://'+server.expected_host,'X-SCR-Token':'test-nonce','Content-Type':'application/json'}
    for override in ({'Origin':'http://foreign.test'},{'X-SCR-Token':'wrong'},{'Host':'foreign.test'}):
        assert request(server,'POST','/api/command',dict(headers,**override),payload)[0]==403
    assert not gateway.calls
    assert request(server,'POST','/api/command',dict(headers,**{'Content-Type':'text/plain'}),payload)[0]==400
    assert not gateway.calls
    assert request(server,'POST','/api/command',headers,payload)[0]==202
    assert len(gateway.calls)==1 and gateway.calls[0]['action']=='off'
    for method in ('PUT','DELETE','PATCH','OPTIONS'):
        assert request(server,method,'/api/command',headers,payload)[0]==405
    assert len(gateway.calls)==1
