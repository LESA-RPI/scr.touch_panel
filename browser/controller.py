"""Trusted-network gateway to the panel's private socket, never a second driver."""

import json
import socket
import time


class Controller:
    def __init__(self, path):
        self.path = path

    def exchange(self, value):
        try:
            raw = json.dumps(value, allow_nan=False).encode() + b"\n"
        except (ValueError, TypeError):
            return self.not_sent("Invalid command. Command not sent.")
        if len(raw) > 32768:
            return self.not_sent("Command too large. Command not sent.")
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except OSError:
            return self.not_sent()
        with client:
            deadline = time.monotonic() + 2.8
            try:
                client.settimeout(2.8)
                client.connect(self.path)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Panel connect deadline exceeded")
                client.settimeout(remaining)
            except OSError:
                return self.not_sent()
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

    @staticmethod
    def not_sent(detail="Panel connection unavailable. Command not sent."):
        return {"available": False, "ok": False, "code": 409,
                "detail": detail}

    def read(self):
        try:
            return self.exchange({"op": "read"})
        except (OSError, ValueError):
            return {
                "available": False,
                "detail": "Panel controller unavailable. Controls are disabled.",
            }
