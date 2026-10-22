"""Trusted-network gateway to the panel's private socket, never a second driver."""

import json
import socket
import time


class Controller:
    def __init__(self, path):
        self.path = path

    def exchange(self, value):
        raw = json.dumps(value, allow_nan=False).encode() + b"\n"
        if len(raw) > 4096:
            raise ValueError("Command too large")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            deadline = time.monotonic() + 2.8
            client.settimeout(2.8)
            client.connect(self.path)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Panel reply deadline exceeded")
            client.settimeout(remaining)
            client.sendall(raw)
            reply = bytearray()
            while len(reply) <= 65536:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Panel reply deadline exceeded")
                client.settimeout(remaining)
                part = client.recv(min(4096, 65537 - len(reply)))
                if not part:
                    break
                reply.extend(part)
                newline = reply.find(b"\n")
                if newline >= 0:
                    reply = reply[:newline + 1]
                    break
        if len(reply) > 65536 or not reply.endswith(b"\n"):
            raise ValueError("Invalid panel reply")

        def invalid_constant(value):
            raise ValueError("Invalid panel number")

        value = json.loads(reply, parse_constant=invalid_constant)
        if not isinstance(value, dict):
            raise ValueError("Invalid panel reply")
        return value

    def read(self):
        try:
            return self.exchange({"op": "read"})
        except (OSError, ValueError):
            return {
                "available": False,
                "detail": "Panel controller unavailable. Controls are disabled.",
            }
