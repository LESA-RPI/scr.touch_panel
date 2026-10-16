"""Trusted-network gateway to the panel's private socket, never a second driver."""
import json
import socket


class Controller:
    def __init__(self,path): self.path=path

    def exchange(self,value):
        raw=json.dumps(value,allow_nan=False).encode()+b'\n'
        if len(raw)>4096:raise ValueError('Command too large')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2.8)
            client.connect(self.path);client.sendall(raw)
            with client.makefile('rb') as stream:reply=stream.readline(65537)
        if len(reply)>65536 or not reply.endswith(b'\n'):raise ValueError('Invalid panel reply')
        return json.loads(reply)

    def read(self):
        try:return self.exchange({'op':'read'})
        except (OSError,ValueError):return {'available':False,'detail':'Panel controller unavailable. Controls are disabled.'}
