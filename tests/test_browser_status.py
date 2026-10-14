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
    instance = status.HTTPServer(('127.0.0.1', 0), status.Handler)
    instance.expected_host = '%s:%d' % instance.server_address
    instance.snapshot = snapshot
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=2)


def request(server, method, path, headers=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=7)
    try:
        connection.request(method, path, headers=headers or {})
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
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            assert request(server, method, '/api/status')[0] == 405
        for path in ('/../README.md', '/api/status?master=http://other', '/deployment.env'):
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
