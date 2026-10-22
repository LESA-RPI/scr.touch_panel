#!/usr/bin/env python
"""Optional SCR light adapter. Author: Diyanko Bhowmik, with Codex assistance.

Uses the existing ROS owner. Persistent room control keeps settings on release;
bounded trials restore only exactly reproducible, uniform starting presets.
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

PRESETS = {
    "Fid": (39, 6, 25, 56, 57, 100, 3, 6),
    "Sat": (21, 14, 4, 73, 22, 100, 22, 4),
    "Dul": (41, 2, 25, 53, 38, 100, 2, 0),
    "Off": (0,) * 8,
}
COORDINATES = {
    (0, 0),
    (0, 2),
    (1, 1),
    (2, 0),
    (2, 2),
    (3, 0),
    (3, 2),
    (4, 1),
    (5, 0),
    (5, 2),
}
GRADIENT = dict(
    (xy, tuple(100 if channel == colour else 0 for channel in range(8)))
    for xy, colour in zip(sorted(COORDINATES), (0, 0, 1, 2, 3, 4, 5, 6, 7, 7))
)


class StatusProgrammes(object):
    """Use the existing Status owner; an HTTP acknowledgement is only acceptance."""

    def __init__(self, base_url, can_write=lambda: None, deadline=None):
        try:
            from urlparse import urlparse
        except ImportError:
            from urllib.parse import urlparse
        url = urlparse(base_url)
        if (url.scheme not in ("http", "https") or not url.hostname
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("A configured Status HTTP address without credentials is required")
        self.base_url = base_url.rstrip("/")
        self.can_write, self.deadline = can_write, deadline

    def request(self, operation, name):
        if operation not in ("Run", "Kill") or name not in ("sun", "circ"):
            raise ValueError("Only original Sun/Circ programme requests are permitted")
        try:
            from urllib2 import Request, urlopen
        except ImportError:
            from urllib.request import Request, urlopen
        request = Request(
            self.base_url + "/Script_" + operation,
            json.dumps({"name": name}).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        self.can_write()
        if self.deadline is not None:
            remaining = self.deadline() - clock()
            if remaining <= 0:
                raise RuntimeError("Whole programme operation exceeded 30 seconds")
            signal.alarm(max(1, int(math.ceil(min(3, remaining)))))
        response = None
        try:
            response = urlopen(request, timeout=3)
            body = response.read(4097)
            if response.getcode() != 202 or len(body) > 4096:
                raise ValueError("Status did not accept the programme request")
            result = json.loads(body.decode("utf-8"))
            if not isinstance(result, dict) or result.get("name") != name:
                raise ValueError("Status programme acknowledgement did not match")
        finally:
            if self.deadline is not None:
                signal.alarm(0)
            if response is not None:
                response.close()

    def stop(self):
        self.request("Kill", "sun")
        self.request("Kill", "circ")

    def start(self, name):
        self.request("Run", {"Sun": "sun", "Circ": "circ"}[name])


def words(percent):
    if len(percent) != 8 or any(
        not 0 <= v <= 100 or math.isnan(v) or math.isinf(v) for v in percent
    ):
        raise ValueError("Eight finite channel percentages in 0..100 required")
    return tuple(int(round(v * 65535 / 100.0)) for v in percent)


def setter_words(percent):
    return tuple(int((float(v) / 100) * 65535) for v in percent)


def clock():
    if hasattr(time, "monotonic"):
        return time.monotonic()
    with open("/proc/uptime") as stream:
        return float(stream.read().split()[0])


def restore_preset(snapshot):
    for name, values in PRESETS.items():
        if all(state == setter_words(values) for state in snapshot.values()):
            return name
    raise ValueError(
        "Baseline is not an exactly restorable preset; live controls stay off"
    )


class Lights(object):
    def __init__(self, call, can_write=lambda: None, keep_settings=False,
                 programmes=None, sleep=time.sleep, blinds_connected=False,
                 gradient_connected=True):
        self.call, self.can_write = call, can_write
        self.keep_settings = keep_settings
        self.baseline = self.current = None
        self.baseline_name = None
        self.changed = self.failed = False
        self.programmes, self.sleep = programmes, sleep
        self.programme = None
        self.blinds_connected, self.blinds_failed = blinds_connected, False
        self.gradient_connected = gradient_connected

    def capabilities(self):
        return {
            "capabilities": {"gradient": self.gradient_connected,
                             "programmes": bool(self.programmes and self.keep_settings)},
            "programme": self.programme,
            "programme_confirmed": False,
            "blinds_connected": self.keep_settings and self.blinds_connected and not self.blinds_failed,
            "manual_blocked": self.programme is not None or self.baseline is None,
        }

    def read(self):
        flat = list(self.call("get_lights").lights)
        coords = [tuple(flat[i : i + 2]) for i in range(0, len(flat), 2)]
        if len(flat) != 20 or len(set(coords)) != 10 or set(coords) != COORDINATES:
            raise ValueError(
                "Installed fixture identities differ from the qualified ten"
            )
        return dict(
            (xy, words(list(self.call("get_sources", *xy).sources)))
            for xy in sorted(coords)
        )

    def acquire(self):
        if self.baseline is not None:
            raise ValueError("Lighting trial already acquired")
        state = self.read()
        try:
            name = restore_preset(state)
        except ValueError:
            if not self.keep_settings:
                raise
            name = None
        if self.read() != state:
            if self.keep_settings:
                result = {"state": "ready", "baseline": None, "fixtures": 10,
                          "detail": "Lights are changing. Stop the programme before manual control."}
                result.update(self.capabilities())
                return result
            raise ValueError("Light settings are changing; live controls stay off")
        self.baseline, self.current, self.baseline_name = state, state, name
        result = {
            "state": "ready",
            "baseline": name,
            "power": "on" if any(any(values) for values in state.values()) else "off",
            "fixtures": 10,
        }
        result.update(self.capabilities())
        return result

    def stop_programmes(self):
        """Qualify quiescent drive after stop acceptance, without claiming job health."""
        self.can_write()
        self.programmes.stop()
        self.sleep(0.25)
        state = self.read()
        self.sleep(0.25)
        if self.read() != state:
            raise ValueError("Programme stop accepted but lights are still changing")
        self.programme = None
        if self.baseline is None:
            self.baseline = state
            self.baseline_name = None
        self.current = state

    def run_programme(self, name):
        if name not in ("Sun", "Circ", "Stop"):
            raise ValueError("Unknown original programme")
        if not self.keep_settings or not self.programmes or self.failed:
            raise ValueError("Original programmes are unavailable")
        try:
            self.stop_programmes()
            if name != "Stop":
                self.can_write()
                self.changed = True
                self.current = None
                self.programmes.start(name)
                self.programme = name
            result = {
                "state": "completed",
                "detail": ("Programme stop accepted; drive settings stable."
                           if name == "Stop" else name + " start request accepted; running status unavailable."),
                "manual_blocked": name != "Stop",
            }
            result.update(self.capabilities())
            return result
        except Exception:
            self.failed = True
            raise

    def apply_gradient(self):
        if not self.gradient_connected:
            raise ValueError("Gradient service is unavailable")
        if self.failed or (self.baseline is None and not (self.programmes and self.keep_settings)):
            raise ValueError("Lighting trial is unavailable")
        try:
            self.prepare_manual()
            self.can_write()
            self.changed = True
            self.current = None
            for xy, values in sorted(GRADIENT.items()):
                self.can_write()
                self.call("sources", *(list(values) + list(xy)))
            expected = dict((xy, setter_words(values)) for xy, values in GRADIENT.items())
            actual = self.read()
            if actual != expected:
                raise ValueError("Gradient fixture drive readback differs from the command")
            self.current = actual
            result = {
                "state": "completed", "scene": "Gradient", "power": "on", "fixtures": 10,
                "detail": "Gradient drive settings confirmed on 10 lights",
                "fixture_words": [[list(xy), list(values)] for xy, values in sorted(actual.items())],
            }
            result.update(self.capabilities())
            return result
        except Exception:
            self.failed = True
            raise

    def prepare_manual(self):
        if self.programmes and self.keep_settings:
            previous, active = self.current, self.programme is not None or self.baseline is None
            self.stop_programmes()
            if not active and self.current != previous:
                raise ValueError("Another controller changed the lights; trial ownership lost")
        elif self.read() != self.current:
            raise ValueError("Another controller changed the lights; trial ownership lost")

    def move_blinds(self, name):
        if name not in ("lift", "open", "close"):
            raise ValueError("Unknown blind action")
        if not self.keep_settings or not self.blinds_connected or self.blinds_failed:
            raise ValueError("Blind controller is unavailable")
        try:
            actions = {"lift": [("lift_all", 100)], "open": [("tilt_all", 50)],
                       "close": [("tilt_all", 100), ("lift_all", 0)]}[name]
            for index, (action, value) in enumerate(actions):
                if index:
                    self.sleep(2)
                self.can_write()
                response = self.call(action, value)
                if getattr(response, "lift" if action == "lift_all" else "tilt", None) != value:
                    raise ValueError("Blind service acknowledgement did not match")
            result = {"state": "completed", "blind": name,
                      "detail": "Blind command accepted; physical position is not measured."}
            result.update(self.capabilities())
            return result
        except Exception:
            self.blinds_failed = True
            raise

    def apply(self, action, arguments):
        if self.failed or (self.baseline is None and not (self.programmes and self.keep_settings)):
            raise ValueError("Lighting trial is unavailable")
        if action == "channels":
            values = arguments["values"]
            if len(values) != 8 or any(
                isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 100
                for v in values
            ):
                raise ValueError("Channels must be eight integers in 0..100")
            name, args = "sources_all", values
        elif action == "cct":
            cct, intensity = arguments["cct"], arguments["intensity"]
            if (
                any(
                    isinstance(v, bool) or not isinstance(v, int)
                    for v in (cct, intensity)
                )
                or not 1600 <= cct <= 10000
                or not 0 <= intensity <= 1900
            ):
                raise ValueError("CCT 1600..10000 K and intensity 0..1900 required")
            name, args = "cct_all", [cct, intensity]
        else:
            raise ValueError("Unknown lighting action")
        try:
            self.prepare_manual()
            self.can_write()
            self.changed = True
            # Until a matching readback arrives, the result is uncertain.
            self.current = None
            reply = self.call(name, *args)
            calculated = ast.literal_eval(reply.cmdstr)
            if len(calculated) != 8 or any(not 0 <= v <= 1 for v in calculated):
                raise ValueError("Malformed service response")
            expected = tuple(int(float(v) * 65535) for v in calculated)
            actual = self.read()
            if any(value != expected for value in actual.values()):
                raise ValueError("Fixture drive readback differs from the command")
            self.current = actual
            result = {
                "state": "completed",
                "fixtures": 10,
                "detail": "Drive settings confirmed on 10 lights",
                "words": list(expected),
            }
            result.update(self.capabilities())
            return result
        except Exception:
            self.failed = True
            raise

    def release(self):
        if self.failed or self.blinds_failed:
            raise ValueError(
                "Outcome unknown; no automatic restore or retry. Inspect the retained receipt"
            )
        if self.keep_settings:
            self.baseline = self.current = None
            self.changed = False
            return {
                "state": "released",
                "restored": False,
                "preserved": True,
                "detail": "Lighting ownership released; current settings unchanged",
            }
        if self.baseline is None or not self.changed:
            self.baseline = self.current = None
            return {
                "state": "released",
                "restored": True,
                "detail": "No light settings changed",
            }
        if self.failed or self.current is None:
            raise ValueError(
                "Outcome unknown; no automatic restore or retry. Inspect the retained receipt"
            )
        try:
            if self.read() != self.current:
                raise ValueError(
                    "External light change detected; refuse to overwrite it"
                )
            self.current = None
            self.call("sources_all", *PRESETS[self.baseline_name])
            if self.read() != self.baseline:
                raise ValueError("Starting drive settings were not restored exactly")
            self.baseline = self.current = None
            self.changed = False
            return {
                "state": "released",
                "restored": True,
                "detail": "Starting light settings restored",
            }
        except Exception:
            self.failed = True
            raise


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", help="New private JSONL recovery journal")
    parser.add_argument(
        "--parent-pid", type=int, help="Direct panel parent; no foreign process control"
    )
    parser.add_argument(
        "--expected-master", required=True, help="Approved deployment ROS_MASTER_URI"
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Read advertised services only; no ROS node or fixture queries",
    )
    parser.add_argument(
        "--keep-settings",
        action="store_true",
        help="Release ownership without restoring lights (persistent room control)",
    )
    parser.add_argument("--status-url", default=os.environ.get("SCR_STATUS_URL"),
                        help="Approved existing Status HTTP service for Sun/Circ")
    args = parser.parse_args()
    if (
        not args.status_only
        and os.environ.get("ROS_MASTER_URI") != args.expected_master
    ):
        parser.error("ROS_MASTER_URI does not match the approved master")
    try:
        from urlparse import urlparse
    except ImportError:
        from urllib.parse import urlparse
    master = urlparse(args.expected_master)
    if (
        master.scheme != "http"
        or not master.hostname
        or master.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        parser.error("A configured remote room master is required")
    if args.status_only:
        socket.setdefaulttimeout(3)
        try:
            from xmlrpclib import ServerProxy
        except ImportError:
            from xmlrpc.client import ServerProxy
        result = ServerProxy(args.expected_master).getSystemState("scr_panel_status")
        if result[0] != 1:
            raise ValueError("Room master did not return its service graph")
        names = {name for name, nodes in result[2][2]}
        required = [
            ("Lighting", {"/get_lights", "/get_sources", "/cct_all"}),
            ("Blinds", {"/get_blinds", "/lift_all", "/tilt_all"}),
            ("Environment", {"/get_temp", "/get_rh"}),
            ("TOF", {"/get_distances", "/get_distances_all"}),
        ]
        print(
            json.dumps(
                {
                    "version": 1,
                    "services": [
                        (name, services <= names) for name, services in required
                    ],
                }
            )
        )
        return 0
    if not args.receipt or not args.parent_pid:
        parser.error("Connected control requires --receipt and --parent-pid")
    lock = open("/tmp/scr-panel-light-owner.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = os.fdopen(
        os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    )
    # Persist both the receipt name and its newly created run directory before
    # any hardware command can be accepted. File fsync alone misses these entries.
    receipt_dir = os.path.dirname(os.path.abspath(args.receipt))
    for directory in (receipt_dir, os.path.dirname(receipt_dir)):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    socket.setdefaulttimeout(10)
    import rospy
    from scr_control.srv import (
        GetLights,
        GetSources,
        OctaLight_sourcesAll,
        OctaLight_CCTAll,
        OctaLight_sources,
        BlindLiftAll,
        BlindTiltAll,
    )

    rospy.init_node("scr_panel_lights", anonymous=True, disable_signals=True)
    types = dict(
        get_lights=GetLights,
        get_sources=GetSources,
        sources_all=OctaLight_sourcesAll,
        cct_all=OctaLight_CCTAll,
        sources=OctaLight_sources,
        lift_all=BlindLiftAll,
        tilt_all=BlindTiltAll,
    )

    def expired(signum, frame):
        raise RuntimeError("Lighting service deadline expired; outcome may be unknown")

    signal.signal(signal.SIGALRM, expired)
    deadline = [clock() + 30]

    def call(name, *values):
        remaining = deadline[0] - clock()
        if remaining <= 0:
            raise RuntimeError("Whole lighting operation exceeded 30 seconds")
        signal.alarm(min(12, max(1, int(math.ceil(remaining)))))
        try:
            return rospy.ServiceProxy(name, types[name])(*values)
        finally:
            signal.alarm(0)

    inbox = {"buffer": "", "last_seen": clock(), "eof": False, "requests": []}

    def consume():
        while select.select([sys.stdin], [], [], 0)[0] and not inbox["eof"]:
            chunk = os.read(sys.stdin.fileno(), 4096).decode("utf-8")
            if not chunk:
                inbox["eof"] = True
                break
            inbox["buffer"] += chunk
            if len(inbox["buffer"]) > 8192:
                raise ValueError("Oversized adapter input")
            while "\n" in inbox["buffer"]:
                line, inbox["buffer"] = inbox["buffer"].split("\n", 1)
                if len(line) > 4096:
                    raise ValueError("Oversized adapter request")
                item = json.loads(line)
                if item.get("version") != 1:
                    raise ValueError("Unsupported adapter protocol version")
                sent = float(item["sent_monotonic_s"])
                if not 0 <= clock() - sent <= 10:
                    if item["action"] == "heartbeat":
                        continue
                    raise ValueError("Stale adapter request")
                inbox["last_seen"] = max(sent, inbox["last_seen"])
                if item["action"] != "heartbeat":
                    inbox["requests"].append(item)
                    if len(inbox["requests"]) > 1:
                        raise ValueError("Only one pending light request is permitted")

    def can_write():
        consume()
        if (
            stopping[0]
            or inbox["eof"]
            or os.getppid() != args.parent_pid
            or clock() - inbox["last_seen"] > 10
        ):
            raise ValueError("Panel lease ended before dispatch; no command sent")

    try:
        try:
            from xmlrpclib import ServerProxy
        except ImportError:
            from xmlrpc.client import ServerProxy
        socket.setdefaulttimeout(3)
        graph = ServerProxy(args.expected_master).getSystemState("scr_panel_capabilities")
        services = {name for name, nodes in graph[2][2]} if graph[0] == 1 else set()
    except Exception:
        services = set()
    finally:
        socket.setdefaulttimeout(10)
    programmes = StatusProgrammes(args.status_url, can_write, lambda: deadline[0]) if args.status_url else None
    lights = Lights(call, can_write, keep_settings=args.keep_settings,
                    programmes=programmes,
                    blinds_connected={"/lift_all", "/tilt_all"} <= services,
                    gradient_connected="/sources" in services)

    def record(event, **values):
        values.update(event=event, epoch_s=time.time(), pid=os.getpid())
        if lights.baseline is not None:
            values["baseline"] = [
                [list(xy), list(state)] for xy, state in sorted(lights.baseline.items())
            ]
        journal.write(json.dumps(values, sort_keys=True) + "\n")
        journal.flush()
        os.fsync(journal.fileno())

    def respond(request_id, result):
        result.update(lights.capabilities())
        record("result", request_id=request_id, result=result)
        print(json.dumps(dict(result, version=1, request_id=request_id)))
        sys.stdout.flush()

    stopping = [False]
    signal.signal(signal.SIGTERM, lambda signum, frame: stopping.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda signum, frame: stopping.__setitem__(0, True))
    initialized = {"version": 1, "state": "initialized"}
    initialized.update(lights.capabilities())
    print(json.dumps(initialized))
    sys.stdout.flush()
    try:
        while not stopping[0]:
            if not inbox["requests"]:
                select.select([sys.stdin], [], [], 1)
            consume()
            if (
                inbox["eof"]
                or clock() - inbox["last_seen"] > 10
                or os.getppid() != args.parent_pid
            ):
                break
            if not inbox["requests"]:
                continue
            item = inbox["requests"].pop(0)
            deadline[0] = clock() + 30
            action, request_id = item["action"], item.get("request_id")
            if action == "heartbeat":
                continue
            record("request", request=item)
            try:
                if action == "acquire":
                    result = lights.acquire()
                elif action == "release":
                    result = lights.release()
                elif action == "gradient":
                    result = lights.apply_gradient()
                elif action == "programme":
                    result = lights.run_programme(item.get("arguments", {}).get("name"))
                elif action in ("blind", "blinds"):
                    result = lights.move_blinds(item.get("arguments", {}).get("name"))
                else:
                    result = lights.apply(action, item.get("arguments", {}))
                respond(request_id, result)
                if action == "release":
                    break
            except Exception as error:
                respond(
                    request_id,
                    {
                        "state": "failed",
                        "detail": str(error),
                        "outcome_unknown": lights.failed or lights.blinds_failed,
                    },
                )
                if action == "acquire" and not lights.failed:
                    continue  # Status Stop remains usable when read-only acquisition fails.
                break
    finally:
        deadline[0] = clock() + 30
        try:
            result = lights.release()
            record("closed", result=result)
        except Exception as error:
            record("restore_failed", detail=str(error))
        journal.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
